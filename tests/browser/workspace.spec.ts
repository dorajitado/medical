// Existing intake/report regressions follow the dedicated navigation menus.
import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
test.describe.serial('isolated local workspace',()=>{
  test.beforeAll(()=>{execFileSync(path.resolve('.venv/Scripts/python.exe'),['-m','backend.create_qa_fixture']);});
  test('folder selection, study metadata, typed report and version persistence',async({page})=>{
    await page.goto('/#home');await expect(page.getByText('로컬 저장소 연결됨')).toBeVisible();await expect(page.getByText('아직 등록된 검사가 없습니다.')).toBeVisible();
    await page.getByLabel('DICOM 폴더 선택',{exact:true}).setInputFiles(path.resolve('data/qa-fixtures/ct'));
    await expect(page.getByText('등록 처리 완료')).toBeVisible();await page.getByRole('button',{name:'검사 선택: SYNTHETIC QA ONLY',exact:true}).click();
    const models=(await(await page.request.get('/api/models')).json()).items;const ready=models.filter((m:{status:string})=>m.status==='ready').length;
    await expect(page.getByText('실행 준비됨',{exact:true})).toHaveCount(ready);await expect(page.getByText('미설치',{exact:true})).toHaveCount(models.length-ready);
    await page.getByRole('button',{name:'CT 영상 열람',exact:true}).click();await expect(page.getByRole('button',{name:'영상 열기',exact:true})).toBeEnabled();
    await expect(page.getByText(/CTPA 여부 미확정/)).toBeVisible();await expect(page.getByRole('combobox',{name:'열람할 시리즈'})).toContainText('시리즈 설명 미기재 · 2장');
    await page.getByRole('button',{name:'판독소견 · 구조화',exact:true}).click();
    await page.getByRole('combobox',{name:'입력 출처'}).click();await page.getByRole('option',{name:'병원 판독소견서 직접 옮겨 적기'}).click();
    await page.getByRole('textbox',{name:'직접 입력한 내용'}).fill('합성 검증용 원문. 결절 없음. <script>alert(1)</script>');await page.getByRole('button',{name:'선택 검사에 새 버전 저장'}).click();
    await expect(page.getByText('최근 입력 · 병원 판독 전사 (사용자 입력)')).toBeVisible();await page.getByRole('button',{name:'이 내용을 새 버전으로 수정'}).click();
    await expect(page.getByRole('textbox',{name:'직접 입력한 내용'})).toHaveValue('합성 검증용 원문. 결절 없음. <script>alert(1)</script>');
    await page.getByRole('textbox',{name:'직접 입력한 내용'}).fill('합성 검증용 수정본. 의심 소견.');await page.getByRole('button',{name:'선택 검사에 새 버전 저장'}).click();
    await page.reload();await expect(page.getByLabel('선택 작업 보조 패널').getByText('합성 검증용 수정본. 의심 소견.',{exact:true})).toBeVisible();await expect(page.getByLabel('선택 작업 보조 패널').getByText('합성 검증용 원문. 결절 없음. <script>alert(1)</script>',{exact:true})).toBeVisible();
    await page.getByRole('button',{name:'AI 분석 · 3D',exact:true}).click();await page.getByRole('switch',{name:'입체 구조 영역'}).click();await expect(page.getByRole('switch',{name:'입체 구조 영역'})).not.toBeChecked();
    await page.reload();await expect(page.getByRole('switch',{name:'입체 구조 영역'})).not.toBeChecked();
  });
  test('layout has no horizontal overflow at supported sizes',async({page})=>{
    for(const [width,height] of [[1280,720],[1920,1080],[390,844]]){
      await page.setViewportSize({width,height});await page.goto('/#home');await expect(page.getByText('로컬 저장소 연결됨')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await expect(page.getByRole('button',{name:'CT 폴더 선택'})).toBeEnabled();
      await page.screenshot({path:`data/browser-results/workspace-${width}.png`,fullPage:true});
    }
  });
  test('failed connection does not masquerade as empty successful data',async({page})=>{
    await page.route('**/api/health',r=>r.abort());await page.goto('/#home');await expect(page.getByText('서버 연결 필요')).toBeVisible();await expect(page.getByText('조회할 수 없음').first()).toBeVisible();await expect(page.getByRole('button',{name:'CT 폴더 선택'})).toBeDisabled();
    await page.unroute('**/api/health');await page.getByRole('button',{name:'재시도',exact:true}).first().click();await expect(page.getByText('로컬 저장소 연결됨')).toBeVisible();
  });
});
