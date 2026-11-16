// Integration tests against actual persisted TotalSegmentator output from the
// public sample. No fake masks, patient data, or production database are used.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

test('real anatomy overlay, windowing, source planes, version isolation and cancellation', async ({ page }) => {
  test.setTimeout(120000);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const external: string[] = [];
  page.on('request', r => { const u = new URL(r.url()); if (u.protocol.startsWith('http') && !['127.0.0.1', 'localhost'].includes(u.hostname)) external.push(r.url()); });
  await page.goto('/#viewer');
  await page.getByRole('button', { name: '영상 열기', exact: true }).click();
  await page.getByRole('button',{name:'AI 분석 · 3D',exact:true}).click();
  const canvas = page.getByLabel('원본 CT와 AI 분할 마스크', { exact: true });
  await expect(canvas).toBeVisible({ timeout: 30000 });
  // Pixel hashes prove that masks and settings actually alter the image, not
  // merely a checkbox or label. All mutations below are local viewer settings.
  const hash = () => canvas.evaluate((el: HTMLCanvasElement) => {
    // Compact pixel checksum keeps failure output free of large base64 images.
    const bytes = el.getContext('2d')!.getImageData(0, 0, el.width, el.height).data;
    let value = 2166136261;
    for (const byte of bytes) value = Math.imul(value ^ byte, 16777619);
    return value >>> 0;
  });
  await page.getByLabel('분할 슬라이스', { exact: true }).fill('10');
  await expect(page.getByText('분할 슬라이스 11 / 30', { exact: true })).toBeVisible();
  await expect(canvas).toBeVisible();
  const withMask = await hash();
  await page.getByRole('checkbox', { name: 'AI 마스크 표시', exact: true }).uncheck();
  await expect.poll(hash).not.toBe(withMask);
  const without = await hash();
  await page.getByRole('checkbox', { name: 'AI 마스크 표시', exact: true }).check();
  await expect.poll(hash).toBe(withMask);
  await page.getByLabel('마스크 불투명도', { exact: true }).fill('0');
  await expect.poll(hash).toBe(without);
  await page.getByLabel('마스크 불투명도', { exact: true }).fill('0.4');
  const evidence = JSON.parse(fs.readFileSync(path.resolve('data/qa-week3/last-run.json'), 'utf8'));
  const plane = await (await page.request.get(`/api/analyses/${evidence.run_id}/slices/10`)).json();
  const result = await (await page.request.get(`/api/analyses/${evidence.run_id}/result`)).json();
  const label = plane.labels.find((value: number) => value > 0);
  const title = result.structures.find((structure: { label: number }) => structure.label === label).title;
  await page.getByRole('checkbox', { name: new RegExp(`^${title} · `) }).uncheck();
  await expect.poll(hash).not.toBe(withMask);
  await page.getByRole('checkbox', { name: new RegExp(`^${title} · `) }).check();
  await expect.poll(hash).toBe(withMask);
  // Avoid OHIF's own window controls by locating the button in the analysis card.
  const card = page.getByRole('heading', { name: 'AI 해부학 분할', exact: true }).locator('..').locator('..');
  await card.getByRole('button', { name: '종격동창', exact: true }).click();
  await expect.poll(hash).not.toBe(withMask);
  await expect(page.getByText(/절편 원점 LPS/)).toBeVisible();
  fs.mkdirSync(path.resolve('data/analysis-browser-results'), { recursive: true });
  await canvas.screenshot({ path: 'data/analysis-browser-results/public-anatomy-overlay.png' });
  await page.screenshot({ path: 'data/analysis-browser-results/public-workspace.png', fullPage: true });

  // Confirm that source-series selection is mandatory and cancellation keeps
  // the previous completed version. This is a real queued/running API request.
  const previous = (await (await page.request.get(`/api/series/${evidence.series_id}/analyses`)).json()).items;
  const completed = previous.find((r: { status: string; model_id: string }) => r.status === 'completed' && r.model_id === 'total');
  const start = page.getByRole('button', { name: '새 버전으로 해부학 분할', exact: true });
  await expect(start).toBeDisabled();
  await page.getByRole('checkbox', { name: '선택 시리즈와 해부학 분할의 한계를 확인했습니다', exact: true }).check();
  await expect(start).toBeEnabled();
  await start.click();
  await expect(page.getByRole('button', { name: '분석 취소', exact: true })).toBeVisible();
  // Wait for conversion to finish so this exercises termination of the owned
  // inference process rather than only cancelling a queued database row.
  await expect.poll(async () => {
    const items = (await (await page.request.get(`/api/series/${evidence.series_id}/analyses`)).json()).items;
    return items[0].stage;
  }).toBe('inference');
  await page.getByRole('button', { name: '분석 취소', exact: true }).click();
  await expect(page.getByText('취소 · 완료된 분할 결과가 없습니다.', { exact: true })).toBeVisible();
  await expect(canvas).toHaveCount(0);
  const history = (await (await page.request.get(`/api/series/${evidence.series_id}/analyses`)).json()).items;
  expect(history.some((r: { id: string; status: string }) => r.id === completed.id && r.status === 'completed')).toBeTruthy();
  expect(history.some((r: { status: string }) => r.status === 'cancelled')).toBeTruthy();
  // Selecting an earlier completed version restores its result, not the cancelled run.
  const version = page.getByRole('combobox', { name: '해부학 분석 실행 버전' });
  await version.click();
  await page.getByRole('option', { name: new RegExp(completed.id.slice(0, 8)) }).click();
  await expect(canvas).toBeVisible();

  // Changing the series dropdown invalidates the open viewer immediately;
  // selecting another series must never leave the previous mask visible.
  await page.getByRole('combobox', { name: '열람할 시리즈', exact: true }).click();
  await page.getByRole('option', { name: '시리즈를 선택해 주세요', exact: true }).click();
  await expect(canvas).toHaveCount(0);
  await page.getByRole('combobox', { name: '열람할 시리즈', exact: true }).click();
  await page.getByRole('option', { name: /Public model smoke test/ }).click();
  await page.getByRole('button', { name: '영상 열기', exact: true }).click();
  await page.getByRole('button',{name:'AI 분석 · 3D',exact:true}).click();
  await expect(canvas).toBeVisible();
  // Clear the study; all analysis controls and old masks must disappear.
  await page.getByRole('combobox', { name: '연결할 검사', exact: true }).click();
  await page.getByRole('option', { name: '검사를 선택해 주세요', exact: true }).click();
  await expect(canvas).toHaveCount(0);
  await expect(page.getByText('‘영상 열기’로 분석할 시리즈를 먼저 선택하세요.', { exact: true })).toBeVisible();
  expect(external).toEqual([]);
});
