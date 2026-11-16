// CTG-02~06: a report-free primary workflow, explicit optional context and exact
// evidence navigation. Positive fixture outputs are not diagnostic performance.
import {test,expect} from '@playwright/test';
import fs from 'node:fs';
const headers={'X-Workspace-Request':'1'};
test.describe.serial('CT-first integrated review',()=>{
  test('no-report default, one batch, plain results, exact CT/3D, user review and exports',async({page})=>{
    const external:string[]=[];const starts:string[]=[];
    page.on('request',r=>{if(r.url().startsWith('http')&&!r.url().startsWith('http://127.0.0.1:8005'))external.push(r.url());if(r.method()==='POST')starts.push(r.url());});
    await page.goto('/');await expect(page.getByRole('heading',{name:'종합 검토',level:1,exact:true})).toBeVisible();
    await expect(page.getByRole('switch',{name:'병원 소견과도 대조하기 (선택)'})).not.toBeChecked();
    await expect(page.getByTestId('ct-review-headline')).toContainText('제안 6건');
    const study=(await(await page.request.get('/api/studies')).json()).items[0];
    expect((await(await page.request.get(`/api/studies/${study.id}/reports`)).json()).items).toEqual([]);
    await page.getByRole('button',{name:'이번 CT 분석 시작',exact:true}).click();
    await page.getByRole('checkbox',{name:'선택한 CT 시리즈와 분석 범위를 확인했습니다',exact:true}).check();
    await page.getByRole('button',{name:'종합 분석 실행',exact:true}).click();
    await expect(page.getByText(/종합 분석 진행 · \d\/4개 항목 실행 완료/)).toBeVisible();
    // Task completion drives the accessible numeric bar; it must move before
    // completion without a clock-based estimate inside a running model.
    const progress=page.getByRole('progressbar',{name:'종합 분석 완료율'});
    await expect(progress).toBeVisible();
    await expect.poll(async()=>Number(await progress.getAttribute('aria-valuenow'))).toBeGreaterThan(0);
    expect(Number(await progress.getAttribute('aria-valuenow'))).toBeLessThan(100);
    await page.screenshot({path:'data/ct-review-browser-results/ct-progress-running.png'});
    await expect(page.getByText('선택 범위 분석 완료',{exact:true})).toBeVisible({timeout:30000});
    await expect(progress).toHaveAttribute('aria-valuenow','100');
    await expect(progress).toHaveAttribute('aria-valuetext','100% · 4개 중 4개 분석 완료');
    expect(starts.filter(s=>s.endsWith('/ct-batches'))).toHaveLength(1);expect(starts.filter(s=>s.endsWith('/analyses'))).toHaveLength(0);
    const series=(await(await page.request.get(`/api/studies/${study.id}/series`)).json()).items[0];
    const batch=(await(await page.request.get(`/api/series/${series.id}/ct-batches`)).json()).items[0];
    expect(batch.models).toHaveLength(4);expect(batch.completed_count).toBe(4);
    const view=await(await page.request.get(`/api/series/${series.id}/ct-review?batch_id=${batch.id}`)).json();
    expect(view.report_sources).toEqual([]);expect(view.proposal_count).toBe(6);
    const first=view.candidates[0];
    await page.getByRole('button',{name:'CT에서 위치 확인',exact:true}).first().click();
    await expect(page.getByRole('button',{name:'AI 분석 · 3D',exact:true})).toHaveAttribute('aria-current','page');
    await expect(page.getByTestId('ct-selected-candidate')).toContainText(first.finding_id);
    await expect(page.getByTestId('3d-selected-candidate')).toContainText(first.finding_id);
    await expect(page.getByTestId('selected-candidate-lps')).toHaveText(`대표 위치 LPS(mm): ${first.representative_lps_mm.map((n:number)=>n.toFixed(2)).join(', ')}`);
    await page.getByRole('button',{name:'종합 검토',exact:true}).click();
    const card=page.locator(`[data-proposal-ref="${first.ref}"]`);await card.getByRole('button',{name:'측정·출처와 검토 기록',exact:true}).click();
    await card.getByRole('combobox',{name:'CT 후보 사용자 검토 상태'}).click();await page.getByRole('option',{name:'사용자 확인 표시',exact:true}).click();
    await card.getByRole('textbox',{name:'CT 후보 검토 메모'}).fill('합성 CT 원본 위치 확인 기록');await card.getByRole('button',{name:'후보 검토 기록 저장'}).click();
    await expect(card.getByText('사용자 확인 표시',{exact:true}).first()).toBeVisible();
    await page.getByRole('button',{name:'CT 종합 검토 저장',exact:true}).click();
    await expect(page.getByRole('link',{name:'CT 검토 JSON 저장'})).toBeVisible();
    const snapshot=await(await page.request.get((await page.getByRole('link',{name:'CT 검토 JSON 저장'}).getAttribute('href'))!)).json();
    expect(snapshot.schema_version).toBe('chest-review-2');expect(snapshot.report_sources).toEqual([]);expect(snapshot.integrated_review.proposal_count).toBe(6);expect(snapshot.user_reviews[0].note).toBe('합성 CT 원본 위치 확인 기록');
    const pdf=await page.request.get((await page.getByRole('link',{name:'CT 검토 PDF 저장'}).getAttribute('href'))!);expect(pdf.headers()['content-type']).toContain('application/pdf');
    fs.mkdirSync('data/ct-review-browser-results',{recursive:true});fs.writeFileSync('data/ct-review-browser-results/ct-only-review.pdf',await pdf.body());
    // Inspect populated results at both desktop widths, not only empty/error UI.
    for(const width of [1920,1280]){
      await page.setViewportSize({width,height:1080});await page.getByTestId('ct-review-headline').scrollIntoViewIfNeeded();
      await page.screenshot({path:`data/ct-review-browser-results/ct-positive-${width}.png`});
    }
    expect(external).toEqual([]);
  });
  test('report context is optional even when enabled without data, and excluded again after opt-out',async({page})=>{
    await page.goto('/');await expect(page.getByTestId('ct-review-headline')).toBeVisible();
    const toggle=page.getByRole('switch',{name:'병원 소견과도 대조하기 (선택)'});
    await toggle.check();await expect(page.getByTestId('ct-report-context')).toContainText('등록된 소견서가 없습니다');
    await page.getByRole('button',{name:'CT 종합 검토 저장',exact:true}).click();await expect(page.getByRole('link',{name:'CT 검토 JSON 저장'})).toBeVisible();
    const study=(await(await page.request.get('/api/studies')).json()).items[0];
    await page.request.post(`/api/studies/${study.id}/reports`,{headers,data:{source:'hospital_transcription',text:'SYNTHETIC OPTIONAL REPORT PRIVATE MARKER'}});
    await toggle.uncheck();await toggle.check();await expect(page.getByTestId('ct-report-context')).toContainText('입력 소견은 있지만');
    await toggle.uncheck();await page.getByRole('button',{name:'CT 종합 검토 저장',exact:true}).click();
    await expect(page.getByText('소견서 없이도 사용할 수 있는 CT 종합 검토 기록을 저장했습니다.',{exact:true})).toBeVisible();
    const out=await(await page.request.get((await page.getByRole('link',{name:'CT 검토 JSON 저장'}).getAttribute('href'))!)).json();
    expect(JSON.stringify(out)).not.toContain('SYNTHETIC OPTIONAL REPORT PRIVATE MARKER');expect(out.integrated_review.report_context.enabled).toBe(false);
  });
  test('a failed model stays failed and queued cancellation never becomes a normal result',async({page})=>{
    await page.goto('/');await expect(page.getByTestId('ct-review-headline')).toBeVisible();
    const failure=await page.request.post('/api/qa/fail-next/lung_nodules',{headers,data:{}});expect(failure.status()).toBe(200);
    await page.getByRole('button',{name:'이번 CT 분석 시작',exact:true}).click();
    await page.getByRole('checkbox',{name:'선택한 CT 시리즈와 분석 범위를 확인했습니다',exact:true}).check();await page.getByRole('button',{name:'종합 분석 실행',exact:true}).click();
    await expect(page.getByText('일부 범위만 분석됨',{exact:true})).toBeVisible({timeout:30000});
    await expect(page.getByRole('progressbar',{name:'종합 분석 완료율'})).toHaveAttribute('aria-valuenow','75');
    await expect(page.getByText('실패 1개 · 취소 0개 — 완료 비율에 포함하지 않았습니다.',{exact:true})).toBeVisible();
    await page.getByRole('button',{name:'분석한 범위와 아직 확인하지 않은 항목',exact:true}).click();await expect(page.getByText('결절 의심 부위 찾기 · 분석 실패',{exact:true})).toBeVisible();
    await page.getByRole('button',{name:'이번 CT 분석 시작',exact:true}).click();await page.getByRole('checkbox',{name:'선택한 CT 시리즈와 분석 범위를 확인했습니다',exact:true}).check();await page.getByRole('button',{name:'종합 분석 실행',exact:true}).click();
    await page.getByRole('button',{name:'진행 중인 종합 분석 취소',exact:true}).click();
    await expect(page.getByText(/^(분석 상태 확인 필요|일부 범위만 분석됨)$/)).toBeVisible({timeout:15000});
    await expect(page.getByTestId('ct-review-headline')).not.toContainText('표시된 후보가 없습니다');
    // Cancellation can race a genuine completed task. Compare the UI with the
    // persisted count rather than assuming all four tasks were cancelled.
    const study=(await(await page.request.get('/api/studies')).json()).items[0];
    const series=(await(await page.request.get(`/api/studies/${study.id}/series`)).json()).items[0];
    const batch=(await(await page.request.get(`/api/series/${series.id}/ct-batches`)).json()).items[0];
    const percent=Math.round(batch.completed_count/batch.selected_count*1000)/10;
    await expect(page.getByRole('progressbar',{name:'종합 분석 완료율'})).toHaveAttribute('aria-valuenow',String(percent));
    expect(percent).toBeLessThan(100);
  });
  test('responsive CT-first screen and transient review failure retry',async({page})=>{
    for(const width of [1280,1920,390]){
      await page.setViewportSize({width,height:900});await page.goto('/');await expect(page.getByTestId('ct-review-headline')).toBeVisible();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight+1)).toBeTruthy();
      await expect(page.getByRole('switch',{name:'병원 소견과도 대조하기 (선택)'})).not.toBeChecked();
      await page.screenshot({path:`data/ct-review-browser-results/ct-first-${width}.png`});
    }
    await page.route('**/api/series/*/ct-review?*',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'합성 CT 검토 통신 실패'})}));await page.reload();
    await expect(page.getByText('합성 CT 검토 통신 실패',{exact:true})).toBeVisible();await expect(page.getByTestId('ct-review-headline')).toHaveCount(0);
    await page.unroute('**/api/series/*/ct-review?*');await page.getByRole('button',{name:'재시도',exact:true}).click();await expect(page.getByTestId('ct-review-headline')).toBeVisible();
  });
});
