// Real public-example predictions exercise empty nodules, positive effusion,
// source CT/3D/detail identity, actual WebGL controls and surface picking.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

test('real new-model states and linked 3D/CT candidate review', async ({ page }) => {
  test.setTimeout(120000);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const external: string[] = [];
  page.on('request', r => { const u = new URL(r.url()); if (u.protocol.startsWith('http') && !['127.0.0.1', 'localhost'].includes(u.hostname)) external.push(r.url()); });
  const evidence = JSON.parse(fs.readFileSync(path.resolve('data/qa-week4/last-run.json'), 'utf8'));
  await page.goto('/#viewer');
  await page.getByRole('button', { name: '영상 열기', exact: true }).click();
  await page.getByRole('button',{name:'AI 분석 · 3D',exact:true}).click();
  const mesh = page.locator('canvas[aria-label="본인 CT 분할 기반 3D"]');
  await expect(mesh).toBeVisible({ timeout: 30000 });
  await page.getByRole('combobox', { name: '분석 모델', exact: true }).click();
  await page.getByRole('option', { name: '폐결절 후보', exact: true }).click();
  await expect(page.getByText('이번 실행의 AI 후보: 0개', { exact: true })).toBeVisible();
  await expect(page.getByText(/후보 없음 · 이 모델에서 영역이 생성되지 않았습니다/)).toBeVisible();
  await expect(mesh).toHaveCount(0);
  await page.getByRole('combobox', { name: '분석 모델', exact: true }).click();
  await page.getByRole('option', { name: '흉수·심낭삼출', exact: true }).click();
  const run = evidence.week4_models.pleural_pericard_effusion.run_id;
  const result = await (await page.request.get(`/api/analyses/${run}/result`)).json();
  const candidate = result.findings[0];
  expect(candidate).toBeTruthy();
  await page.getByRole('button', { name: new RegExp(`^${candidate.title} · `) }).click();
  await expect(page.getByTestId('selected-candidate-title')).toHaveText(candidate.title);
  await expect(page.getByTestId('ct-selected-candidate')).toContainText(candidate.id);
  await expect(page.getByTestId('3d-selected-candidate')).toContainText(candidate.id);
  await expect(page.getByText(`분할 슬라이스 ${candidate.representative_index_xyz[2] + 1} / 30`, { exact: true })).toBeVisible();
  await expect(mesh).toBeVisible();
  const hash = () => mesh.evaluate((el: HTMLCanvasElement) => {
    const buffer = document.createElement('canvas'); buffer.width = el.width; buffer.height = el.height;
    const context = buffer.getContext('2d')!; context.drawImage(el, 0, 0);
    let value = 2166136261;
    for (const byte of context.getImageData(0, 0, buffer.width, buffer.height).data) value = Math.imul(value ^ byte, 16777619);
    return value >>> 0;
  });
  const pixels = () => mesh.evaluate((el: HTMLCanvasElement) => {
    const buffer = document.createElement('canvas'); buffer.width = el.width; buffer.height = el.height;
    const context = buffer.getContext('2d')!; context.drawImage(el, 0, 0);
    return Array.from(context.getImageData(0, 0, buffer.width, buffer.height).data);
  });
  // Let ResizeObserver/camera aspect settle before recording the initial view.
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const original = await hash();
  const initialPixels = await pixels();
  await mesh.scrollIntoViewIfNeeded();
  const box = await mesh.boundingBox();
  if (!box) throw new Error('3D viewport missing');
  await page.mouse.move(box.x + box.width * .5, box.y + box.height * .5);
  await page.mouse.down(); await page.mouse.move(box.x + box.width * .7, box.y + box.height * .6, { steps: 8 }); await page.mouse.up();
  await expect.poll(hash).not.toBe(original);
  const rotated = await hash();
  await mesh.hover(); await page.mouse.wheel(0, -150);
  await expect.poll(hash).not.toBe(rotated);
  await page.getByRole('button', { name: '3D 시점 초기화', exact: true }).click();
  // Antialiasing may differ by subpixel rounding after orbit/zoom. Require the
  // reset image's mean absolute channel error to remain below 1/255 intensity.
  const restoredPixels = await pixels();
  const error = restoredPixels.reduce((sum, value, i) => sum + Math.abs(value - initialPixels[i]), 0) / initialPixels.length;
  expect(error).toBeLessThan(1);
  await page.getByRole('checkbox', { name: '3D 윤곽선', exact: true }).check();
  await expect.poll(hash).not.toBe(original);
  await page.getByRole('checkbox', { name: '3D 윤곽선', exact: true }).uncheck();
  await page.getByLabel('3D 불투명도', { exact: true }).fill('0.2');
  await expect.poll(hash).not.toBe(original);
  await page.getByLabel('3D 불투명도', { exact: true }).fill('0.65');
  await page.getByRole('checkbox', { name: `3D 구조 표시: ${candidate.title}`, exact: true }).uncheck();
  await expect.poll(hash).not.toBe(original);
  await page.getByRole('checkbox', { name: `3D 구조 표시: ${candidate.title}`, exact: true }).check();
  await page.getByRole('button', { name: '후보 선택 해제', exact: true }).click();
  await expect(page.getByTestId('3d-selected-candidate')).toHaveCount(0);
  // Find a rendered surface pixel, then use the UI pointer raycast. This avoids
  // assuming that a concave region's bounding-box centre lies on its surface.
  const point = await mesh.evaluate((el: HTMLCanvasElement) => {
    const buffer = document.createElement('canvas'); buffer.width = el.width; buffer.height = el.height;
    const context = buffer.getContext('2d')!; context.drawImage(el, 0, 0);
    const data = context.getImageData(0, 0, buffer.width, buffer.height).data;
    for (let y = 5; y < buffer.height - 5; y += 3) for (let x = 5; x < buffer.width - 5; x += 3) {
      const i = (y * buffer.width + x) * 4;
      if (Math.abs(data[i] - 16) + Math.abs(data[i + 1] - 25) + Math.abs(data[i + 2] - 35) > 80) return { x: x / buffer.width, y: y / buffer.height };
    }
    return null;
  });
  expect(point).not.toBeNull();
  await mesh.click({ position: { x: point!.x * box.width, y: point!.y * box.height } });
  await expect(page.getByTestId('selected-candidate-title')).toHaveText(candidate.title);
  await expect(page.getByTestId('ct-selected-candidate')).toContainText(candidate.id);
  await expect(page.getByTestId('3d-selected-candidate')).toContainText(candidate.id);
  fs.mkdirSync('data/analysis-browser-results', { recursive: true });
  await mesh.screenshot({ path: 'data/analysis-browser-results/public-effusion-3d.png' });
  await page.screenshot({ path: 'data/analysis-browser-results/public-candidate-workspace.png', fullPage: true });
  // Model changes clear the whole selection; the old effusion is not a nodule.
  await page.getByRole('combobox', { name: '분석 모델', exact: true }).click();
  await page.getByRole('option', { name: '폐결절 후보', exact: true }).click();
  await expect(page.getByTestId('selected-candidate-title')).toHaveCount(0);
  await expect(page.getByTestId('ct-selected-candidate')).toHaveCount(0);
  await expect(mesh).toHaveCount(0);
  expect(external).toEqual([]);
});
