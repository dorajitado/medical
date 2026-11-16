// UI-07: the manual is a local reader that neither mutates the workspace nor
// replaces the current CT workflow. Known synthetic fixtures stay in this QA.
import { test, expect } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

test('app help opens the guide independently and print uses the reader action', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '종합 검토', exact: true, level: 1 })).toBeVisible();
  const appUrl = page.url();
  const study = await page.getByRole('combobox', { name: '작업할 검사' }).textContent();
  const [manual] = await Promise.all([
    page.waitForEvent('popup'),
    page.getByRole('link', { name: '사용자 매뉴얼 (새 창)' }).click(),
  ]);
  await expect(manual.getByRole('heading', { name: '흉부 CT 검토실 사용자 매뉴얼', level: 1 })).toBeVisible();
  await expect(manual.locator('#quickstart')).toContainText('병원 소견서는 없어도 됩니다.');
  await expect(manual.locator('main section:visible')).toHaveCount(1);
  await expect(manual.getByRole('button', { name: '이전 페이지', exact: true })).toBeDisabled();
  await manual.getByRole('button', { name: '다음 페이지', exact: true }).click();
  await expect(manual.locator('#page-indicator')).toHaveText('2 / 12 페이지');
  await expect(manual.locator('#quickstart')).toBeHidden();
  await manual.getByRole('button', { name: '이전 페이지', exact: true }).click();
  await expect(manual.locator('#page-indicator')).toHaveText('1 / 12 페이지');
  await manual.getByRole('link', { name: '4. 종합 분석 실행', exact: true }).click();
  await expect(manual).toHaveURL(/user-manual\.html#analysis$/);
  await expect(manual.locator('#analysis')).toContainText('실행 완료 항목 수 ÷ 선택한 항목 수');
  await expect(manual.getByRole('link', { name: '4. 종합 분석 실행', exact: true })).toHaveAttribute('aria-current', 'page');
  await manual.getByRole('button', { name: '다음 페이지', exact: true }).click();
  await expect(manual.locator('#page-indicator')).toHaveText('5 / 12 페이지');
  await manual.goBack();
  await expect(manual.locator('#page-indicator')).toHaveText('4 / 12 페이지');
  await manual.goForward();
  await expect(manual.locator('#page-indicator')).toHaveText('5 / 12 페이지');
  await manual.reload();
  await expect(manual.locator('#results')).toBeVisible();
  await manual.getByRole('button', { name: '이전 페이지', exact: true }).click();
  await expect(manual.locator('#analysis h2')).toBeFocused();
  expect(page.url()).toBe(appUrl);
  await expect(page.getByRole('combobox', { name: '작업할 검사' })).toHaveText(study || '');
  // Observe explicit printing without invoking the OS print dialog in CI.
  await manual.evaluate(() => {
    (window as any).__manualPrinted = false;
    window.print = () => { (window as any).__manualPrinted = true; };
  });
  await manual.getByRole('button', { name: '현재 페이지 인쇄 / PDF', exact: true }).click();
  expect(await manual.evaluate(() => (window as any).__manualPrinted)).toBe(true);
  await manual.emulateMedia({ media: 'print' });
  await expect(manual.getByRole('navigation', { name: '매뉴얼 목차' })).toBeHidden();
  await expect(manual.getByRole('button', { name: '현재 페이지 인쇄 / PDF' })).toBeHidden();
  await expect(manual.getByRole('heading', { name: '흉부 CT 검토실 사용자 매뉴얼' })).toBeVisible();
  await expect(manual.locator('#analysis h2')).toHaveCSS('break-after', 'avoid');
  await expect(manual.locator('main section:visible')).toHaveCount(1);
  await expect(manual.locator('#analysis')).toBeVisible();
  await expect(manual.locator('#quickstart')).toBeHidden();
});

test('standalone guide works offline, all contents resolve and layouts fit', async ({ page, context }) => {
  const requests: string[] = [];
  page.on('request', request => { if (request.url().startsWith('http')) requests.push(request.url()); });
  await context.setOffline(true);
  await page.goto(pathToFileURL(path.resolve('public/user-manual.html')).href);
  const anchors = await page.locator('nav a').evaluateAll(links => links.map(link => (link as HTMLAnchorElement).hash));
  expect(anchors).toHaveLength(12);
  for (const anchor of anchors) await expect(page.locator(anchor)).toHaveCount(1);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: '본문 바로가기' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#quickstart$/);
  // All chapters are individually reachable, and only one participates in
  // layout at any time. First/last controls cannot navigate beyond the guide.
  for (const [index, anchor] of anchors.entries()) {
    await page.locator(`nav a[href="${anchor}"]`).click();
    await expect(page.locator('main section:visible')).toHaveCount(1);
    await expect(page.locator('#page-indicator')).toHaveText(`${index+1} / 12 페이지`);
  }
  await expect(page.getByRole('button', { name: '다음 페이지', exact: true })).toBeDisabled();
  const fileUrl=pathToFileURL(path.resolve('public/user-manual.html')).href;
  await page.goto(fileUrl+'#not-a-chapter');
  await expect(page).toHaveURL(/#quickstart$/);
  await expect(page.getByRole('button', { name: '이전 페이지', exact: true })).toBeDisabled();
  await page.goto(fileUrl+'#data');await page.reload();
  await expect(page.locator('#page-indicator')).toHaveText('11 / 12 페이지');
  for (const [width,height] of [[1280,720],[1920,1080],[390,844]]) {
    await page.setViewportSize({ width, height });
    await page.goto(fileUrl+'#analysis');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth && document.documentElement.scrollHeight <= innerHeight+1)).toBe(true);
    if(width===390){
      const contents=page.getByRole('navigation', {name:'매뉴얼 목차'});
      await expect(contents).toBeHidden();
      await page.getByRole('button',{name:'목차',exact:true}).click();
      await expect(contents).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(contents).toBeHidden();
      await expect(page.getByRole('button',{name:'목차',exact:true})).toBeFocused();
      await page.getByRole('button',{name:'목차',exact:true}).click();
    }
    await page.getByRole('link',{name:'10. 자주 막히는 부분',exact:true}).click();
    if(width===390) await expect(page.getByRole('navigation', {name:'매뉴얼 목차'})).toBeHidden();
    await page.locator('#chapter-content').evaluate(node => {node.scrollTop=node.scrollHeight;});
    await page.getByRole('button',{name:'다음 페이지',exact:true}).click();
    await expect(page.locator('#page-indicator')).toHaveText('11 / 12 페이지');
    expect(await page.locator('#chapter-content').evaluate(node=>node.scrollTop)).toBe(0);
    await expect(page.locator('#data h2')).toBeFocused();
    await page.goto(fileUrl+'#quickstart');
    await expect(page.getByRole('heading', { name: '흉부 CT 검토실 사용자 매뉴얼' })).toBeVisible();
    await expect(page.getByRole('button',{name:'다음 페이지',exact:true})).toBeInViewport();
    await page.screenshot({ path: `data/ct-review-browser-results/user-manual-pages-${width}.png` });
  }
  expect(requests).toEqual([]);
});
