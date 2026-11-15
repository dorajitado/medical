// Known positive fixture checks UI/data persistence, never diagnostic accuracy.
import { test,expect } from '@playwright/test';
const headers={'X-Workspace-Request':'1'};
test.describe.serial('remaining local workflow',()=>{
  test('structure, confirm matching, review, immutable PDF/JSON and keyboard focus',async({page})=>{
    const external:string[]=[];page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:8004')&&!r.url().startsWith('data:')&&!r.url().startsWith('blob:'))external.push(r.url());});
    await page.goto('/#reports');await expect(page.getByRole('button',{name:'원문에서 소견 구조화'})).toBeEnabled();
    await page.getByRole('button',{name:'원문에서 소견 구조화'}).click();
    await page.getByRole('checkbox',{name:'항목 1 원문과 해석을 확인했습니다',exact:true}).check();
    await page.getByRole('checkbox',{name:'항목 2 원문과 해석을 확인했습니다',exact:true}).check();
    await page.getByRole('button',{name:'정정 내용을 새 버전으로 저장'}).click();await expect(page.getByText('원문을 보존하고 새 정정 버전을 저장했습니다.')).toBeVisible();
    await page.getByRole('button',{name:'소견 · AI 대조',exact:true}).click();
    // Select only segmentation/anatomy/effusion here; independent MONAI pairing
    // has its own panel and retains its own score scale.
    for(const model of ['total','lung_nodules','pleural_pericard_effusion'])await page.getByRole('checkbox',{name:new RegExp(`^${model} ·`)}).check();
    await page.getByRole('button',{name:'선택 소견과 AI 후보 대조'}).click();
    await expect(page.getByText('입력 소견 상태',{exact:true})).toBeVisible();
    const confirmations=page.getByRole('checkbox',{name:/^연결 확인:/});await expect(confirmations).toHaveCount(2);await confirmations.first().check();
    await page.getByRole('button',{name:'연결 검토 새 버전 저장'}).click();await expect(page.getByText('사용자 연결 검토를 새 버전으로 저장했습니다.')).toBeVisible();
    await page.getByRole('button',{name:'검토 · 정리본',exact:true}).click();
    await page.getByRole('textbox',{name:'검토 메모',exact:true}).fill('합성 기능 검토 메모');await page.getByRole('textbox',{name:'진료 때 확인할 질문',exact:true}).fill('원본 측정 방법 확인');
    await page.getByRole('button',{name:'검토·메모·질문 저장'}).click();
    await page.getByRole('button',{name:'현재 검토 상태로 정리본 생성'}).click();
    const jsonLink=page.getByRole('link',{name:'출처 JSON 저장'});await expect(jsonLink).toBeVisible();
    const url=await jsonLink.getAttribute('href');const snapshot=await(await page.request.get(url!)).json();expect(snapshot.user_reviews[0].note).toBe('합성 기능 검토 메모');expect(snapshot.comparison.payload.report_counts.confirmed).toBe(1);
    await page.getByRole('button',{name:'로컬 문장 배치 정리 (원문 보존)'}).click();await expect(page.getByText('로컬 모델이 원문 문구를 보존한 배치 정리 버전을 저장했습니다.')).toBeVisible({timeout:30000});
    const polished=await(await page.request.get((await jsonLink.getAttribute('href'))!)).json();expect(polished.summary_id).not.toBe(snapshot.summary_id);expect(polished.editorial.clauses.map((c:any)=>c.text).sort()).toEqual(['8 mm nodule.','No pleural effusion.'].sort());
    const pdf=await page.request.get((await page.getByRole('link',{name:'한글 PDF 저장'}).getAttribute('href'))!);expect(pdf.headers()['content-type']).toContain('application/pdf');expect((await pdf.body()).subarray(0,4).toString()).toBe('%PDF');
    await page.getByRole('button',{name:'판독소견 · 구조화',exact:true}).click();await page.getByRole('button',{name:'작업 영역 확대'}).focus();await page.keyboard.press('Enter');await expect(page.getByRole('button',{name:'보조 패널 펼치기'})).toHaveAttribute('aria-pressed','true');await page.keyboard.press('Enter');
    await page.reload();await page.getByRole('button',{name:'검토 · 정리본',exact:true}).click();await expect(page.getByText('합성 기능 검토 메모',{exact:false})).toBeVisible();expect(external).toEqual([]);
  });
  test('independent models, backup verification, prepared evaluation and error retry',async({page})=>{
    await page.goto('/#models');
    for(const [label,model] of [['분할 모델 실행','lung_nodules'],['MONAI 모델 실행','monai_nodule']]){await page.getByRole('combobox',{name:label,exact:true}).click();await page.getByRole('option',{name:new RegExp(`^${model} ·`)}).first().click();}
    await page.getByRole('button',{name:'동일 원본의 두 모델 비교'}).click();await expect(page.getByText('monai_nodule · 후보 2개',{exact:true})).toBeVisible();
    await page.getByRole('combobox',{name:'모델 연결 1 상태',exact:true}).click();await page.getByRole('option',{name:'사용자 확인',exact:true}).click();await page.getByRole('textbox',{name:'모델 연결 1 근거'}).fill('합성 두 모델 동일 중심 확인');
    await page.getByRole('button',{name:'모델 연결 검토 새 버전 저장'}).click();
    await page.getByRole('button',{name:'백업 · 데이터 관리',exact:true}).click();await page.getByRole('button',{name:'현재 작업 공간 백업'}).click();
    await page.getByRole('button',{name:'검증·복원 안내',exact:true}).first().click();await expect(page.getByText(/앱\/영상 서비스 종료 후 restore-backup.ps1/)).toBeVisible();
    await page.getByRole('button',{name:'평가 · 지원 범위',exact:true}).click();await page.getByRole('button',{name:'선택 검사 평가 사례 준비'}).click();await expect(page.getByText(/등록 버전 1건/)).toBeVisible();await expect(page.getByText(/임상 인수 not_established/)).toBeVisible();
    const study=(await(await page.request.get('/api/studies')).json()).items[0];const bad=await page.request.post(`/api/maintenance/studies/${study.id}/delete`,{headers,data:{confirmation:'wrong'}});expect(bad.status()).toBe(422);
  });
  test('document upload preserves pages and a draft, and saves a distinct transcript source',async({page})=>{
    await page.goto('/#reports');await page.getByRole('textbox',{name:'직접 입력한 내용',exact:true}).fill('아직 저장하지 않은 사용자 초안');
    await page.getByRole('button',{name:'문서 · OCR',exact:true}).click();
    await page.locator('input[accept="application/pdf,image/png,image/jpeg"]').setInputFiles('data/qa-remaining/summary-ko.pdf');
    await expect(page.getByRole('link',{name:'보존 원본 다운로드'})).toBeVisible({timeout:20000});
    await expect(page.getByRole('img',{name:'보존 문서 1쪽',exact:true})).toBeVisible();
    await page.getByRole('textbox',{name:'원문 대조·수정한 전사 텍스트'}).fill('문서 대조 후 사용자 정정 전사. 결절 의심.');
    await page.getByRole('checkbox',{name:'선택한 검사와 문서가 일치하고 전사 내용을 확인했습니다'}).check();
    await page.getByRole('button',{name:'문서 출처로 소견 저장'}).click();
    await page.getByRole('button',{name:'판독소견 · 구조화',exact:true}).click();
    await expect(page.getByText('최근 입력 · 문서 추출·사용자 전사 확인 (의학 검증 전)',{exact:true})).toBeVisible();
    await expect(page.getByRole('textbox',{name:'직접 입력한 내용',exact:true})).toHaveValue('아직 저장하지 않은 사용자 초안');
  });
  test('expanded panels fit supported resolutions without placeholder data',async({page})=>{
    for(const width of [390,1280,1920]){
      await page.setViewportSize({width,height:900});await page.goto('/#evaluation');await expect(page.getByText('로컬 저장소 연결됨')).toBeVisible();
      await expect(page.getByText('AI-10-C · 림프절·침윤·기종·기흉 등 추가 소견 · not_supported',{exact:true})).toBeVisible();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
      await page.screenshot({path:`data/remaining-browser-results/workflow-${width}.png`,fullPage:true});
    }
  });
});
