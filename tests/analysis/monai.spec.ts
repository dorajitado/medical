// Actual independent detector output on the retained public example only.
import {test,expect} from '@playwright/test';
test('MONAI boxes retain independent scores and never invent segmentation volume',async({page})=>{
  await page.setViewportSize({width:1920,height:1080});await page.goto('/#viewer');await page.getByRole('button',{name:'영상 열기',exact:true}).click();await page.getByRole('button',{name:'AI 분석 · 3D',exact:true}).click();
  await page.getByRole('combobox',{name:'분석 모델',exact:true}).click();await page.getByRole('option',{name:'MONAI 결절 탐지',exact:true}).click();
  await expect(page.locator('canvas[aria-label="원본 CT와 AI 탐지상자"]')).toBeVisible({timeout:30000});
  const study=(await(await page.request.get('/api/studies')).json()).items[0];const series=(await(await page.request.get(`/api/studies/${study.id}/series`)).json()).items[0];
  const runs=(await(await page.request.get(`/api/series/${series.id}/analyses`)).json()).items;const run=runs.find((r:any)=>r.model_id==='monai_nodule'&&r.status==='completed');
  const result=await(await page.request.get(`/api/analyses/${run.id}/result`)).json();expect(result.findings.length).toBeGreaterThan(0);
  const finding=result.findings[0];expect(finding.volume_mm3).toBeNull();expect(finding.diameter_mm).toBeNull();
  await page.getByRole('button',{name:new RegExp(`^${finding.title} ·`)}).click();await expect(page.getByText('부피: 탐지상자만 제공 · 분할 부피 없음',{exact:true})).toBeVisible();await expect(page.getByText(/MONAI 탐지 점수: .*악성 확률이 아님/)).toBeVisible();
  await expect(page.getByTestId('3d-selected-candidate')).toContainText(finding.id);await expect(page.getByTestId('ct-selected-candidate')).toContainText(finding.id);
  const mesh=await(await page.request.get(`/api/analyses/${run.id}/surfaces`)).json();expect(mesh.objects.every((m:any)=>m.representation==='detection_box_not_segmentation')).toBeTruthy();
});
