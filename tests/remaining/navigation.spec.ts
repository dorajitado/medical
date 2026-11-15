// UI-N1~3: actual menu visibility, preserved drafts/candidates and mobile drawer.
import {test,expect} from '@playwright/test';
test('left menus isolate screens and preserve study, draft and candidate',async({page})=>{
  await page.goto('/#viewer');await expect(page.getByRole('button',{name:'영상 열기',exact:true})).toBeEnabled();
  await expect(page.getByRole('button',{name:'현재 작업 공간 백업',exact:true})).not.toBeVisible();await expect(page.getByRole('button',{name:'원문에서 소견 구조화',exact:true})).not.toBeVisible();
  await page.getByRole('button',{name:'영상 열기',exact:true}).click();await page.getByRole('button',{name:'AI 분석 · 3D',exact:true}).click();
  await page.getByRole('combobox',{name:'분석 모델',exact:true}).click();await page.getByRole('option',{name:'폐결절 후보',exact:true}).click();
  await page.getByRole('button',{name:/^폐결절 후보 1 ·/}).click();const selected=await page.getByTestId('selected-candidate-title').innerText();
  const study=await page.getByRole('combobox',{name:'작업할 검사',exact:true}).inputValue().catch(()=>page.getByRole('combobox',{name:'작업할 검사',exact:true}).innerText());
  await page.getByRole('button',{name:'판독소견 · 구조화',exact:true}).click();await page.getByRole('textbox',{name:'직접 입력한 내용',exact:true}).fill('메뉴 전환 중 보존할 초안');
  await page.getByRole('button',{name:'백업 · 데이터 관리',exact:true}).click();await expect(page.getByRole('button',{name:'현재 작업 공간 백업',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'영상 열기',exact:true})).not.toBeVisible();
  await page.getByRole('button',{name:'판독소견 · 구조화',exact:true}).click();await expect(page.getByRole('textbox',{name:'직접 입력한 내용',exact:true})).toHaveValue('메뉴 전환 중 보존할 초안');
  await page.getByRole('button',{name:'AI 분석 · 3D',exact:true}).click();await expect(page.getByTestId('selected-candidate-title')).toHaveText(selected);expect(await page.getByRole('combobox',{name:'작업할 검사',exact:true}).innerText()).toBe(study);
  await expect(page.getByRole('button',{name:'AI 분석 · 3D',exact:true})).toHaveAttribute('aria-current','page');
});
test('desktop stays viewport-sized and mobile opens a left drawer',async({page})=>{
  for(const width of [1280,1920,390]){
    await page.setViewportSize({width,height:900});await page.goto('/#viewer');await expect(page.getByRole('heading',{name:'CT 영상 열람',exact:true,level:1})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight+1)).toBeTruthy();
    if(width===390){await page.getByRole('button',{name:'작업 메뉴 열기'}).click();await expect(page.getByRole('button',{name:'문서 · OCR',exact:true})).toBeVisible();}
    await page.getByRole('button',{name:'문서 · OCR',exact:true}).focus();await page.keyboard.press('Enter');
    await expect(page.getByRole('heading',{name:'문서 · OCR',exact:true,level:1})).toBeVisible();await expect(page.getByRole('button',{name:'문서 선택 (32 MiB 이하)'})).toBeVisible();
    if(width!==390)await expect.poll(()=>page.getByRole('button',{name:'문서 · OCR',exact:true}).evaluate(el=>getComputedStyle(el).backgroundColor)).toBe('rgb(27, 63, 99)');
    if(width===390){await expect(page.getByRole('button',{name:'판독소견 · 구조화',exact:true})).not.toBeVisible();await expect(page.locator('.MuiDrawer-root')).toHaveCount(0);}
    await page.screenshot({path:`data/remaining-browser-results/menu-${width}.png`,fullPage:true});
  }
});
