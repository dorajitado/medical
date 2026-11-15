// Known positive synthetic nodules test candidate-to-candidate navigation;
// actual inference and empty/positive public results are tested separately.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';

test('two nodules synchronize CT, 3D, details and clear across models/series', async ({ page }) => {
  test.setTimeout(90000);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto('/');
  await page.getByRole('button', { name: '영상 열기', exact: true }).click();
  await page.getByRole('button',{name:'AI 분석 · 3D',exact:true}).click();
  await page.getByRole('combobox', { name: '분석 모델', exact: true }).click();
  await page.getByRole('option', { name: '폐결절 후보', exact: true }).click();
  await expect(page.getByText('이번 실행의 AI 후보: 2개', { exact: true })).toBeVisible();
  await expect(page.getByText('합성 검증용 마스크 — 실제 AI 모델 출력이 아닙니다.', { exact: true })).toBeVisible();
  await expect(page.getByText('추론 실측값 없음 · 합성 검증 자료', { exact: true })).toBeVisible();
  const studies = await (await page.request.get('/api/studies')).json();
  const series = await (await page.request.get(`/api/studies/${studies.items[0].id}/series`)).json();
  const sid = series.items[0].id;
  const runs = await (await page.request.get(`/api/series/${sid}/analyses`)).json();
  const run = runs.items.find((r: { model_id: string }) => r.model_id === 'lung_nodules');
  const result = await (await page.request.get(`/api/analyses/${run.id}/result`)).json();
  const mesh = page.locator('canvas[aria-label="본인 CT 분할 기반 3D"]');
  await expect(mesh).toBeVisible();
  for (const candidate of result.findings) {
    await page.getByRole('button', { name: new RegExp(`^${candidate.title} · `) }).click();
    await expect(page.getByTestId('selected-candidate-title')).toHaveText(candidate.title);
    await expect(page.getByTestId('ct-selected-candidate')).toContainText(candidate.id);
    await expect(page.getByTestId('3d-selected-candidate')).toContainText(candidate.id);
    await expect(page.getByText(`분할 슬라이스 ${candidate.representative_index_xyz[2] + 1} / 32`, { exact: true })).toBeVisible();
    await expect(page.getByTestId('selected-candidate-lps')).toHaveText(`대표 위치 LPS(mm): ${candidate.representative_lps_mm.map((v: number) => v.toFixed(2)).join(', ')}`);
  }
  fs.mkdirSync('data/findings-browser-results', { recursive: true });
  await page.screenshot({ path: 'data/findings-browser-results/synthetic-linked-review.png', fullPage: true });
  // Boundary invalidation is also checked during a deliberately delayed mask
  // request. A late previous-model response must not resurrect its selection.
  await page.route('**/api/analyses/*/slices/*', async route => { await new Promise(resolve => setTimeout(resolve, 250)); await route.continue().catch(() => {}); });
  await page.getByLabel('분할 슬라이스', { exact: true }).fill('5');
  await page.getByRole('combobox', { name: '분석 모델', exact: true }).click();
  await page.getByRole('option', { name: '흉수·심낭삼출', exact: true }).click();
  await expect(page.getByTestId('selected-candidate-title')).toHaveCount(0);
  await expect(page.getByTestId('ct-selected-candidate')).toHaveCount(0);
  await expect(page.getByTestId('3d-selected-candidate')).toHaveCount(0);
  await expect(page.getByText('이번 실행의 AI 후보: 2개', { exact: true })).toBeVisible();
  await page.getByRole('combobox', { name: '열람할 시리즈', exact: true }).click();
  await page.getByRole('option', { name: '시리즈를 선택해 주세요', exact: true }).click();
  await expect(mesh).toHaveCount(0);
  await expect(page.locator('canvas[aria-label="원본 CT와 AI 분할 마스크"]')).toHaveCount(0);
  // Supported widths remain usable with actual 3D and multiple candidates.
  await page.unroute('**/api/analyses/*/slices/*');
  await page.getByRole('combobox', { name: '열람할 시리즈', exact: true }).click();
  await page.getByRole('option', { name: /SYNTHETIC CANDIDATE PHANTOM/ }).click();
  await page.getByRole('button', { name: '영상 열기', exact: true }).click();
  await page.getByRole('button',{name:'AI 분석 · 3D',exact:true}).click();
  await expect(mesh).toBeVisible();
  for (const [width, height] of [[1280, 720], [390, 844]]) {
    await page.setViewportSize({ width, height });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
    const overflow = await page.evaluate(() => Array.from(document.querySelectorAll('main,aside')).some(el => el.scrollWidth > el.clientWidth + 2));
    expect(overflow).toBeFalsy();
  }
});

test('3D request failure is shown and retry restores actual surfaces', async ({ page }) => {
  // The production error/retry path is exercised against a single transient
  // API failure. The subsequent response is the real fixture surface endpoint.
  let fail = true;
  await page.route('**/api/analyses/*/surfaces', async route => {
    if (fail) { fail = false; await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'QA transient surface failure' }) }); }
    else await route.continue();
  });
  await page.goto('/');
  await page.getByRole('button', { name: '영상 열기', exact: true }).click();
  await page.getByRole('button',{name:'AI 분석 · 3D',exact:true}).click();
  await expect(page.getByText('QA transient surface failure', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '재시도', exact: true }).click();
  await expect(page.locator('canvas[aria-label="본인 CT 분할 기반 3D"]')).toBeVisible();
  await expect(page.getByText('QA transient surface failure', { exact: true })).toHaveCount(0);
});
