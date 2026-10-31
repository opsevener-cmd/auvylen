import {test, expect} from "@playwright/test";

test("pretrained analysis is bilingual and never invents an unavailable prediction", async ({page}) => {
  await page.route("**/api/v1/research/pretrained/status", route => route.fulfill({json:{enabled:true, authorized:true,
    synthetic_available:false, providers:[{slug:"comboloss",display_name:"ComboLoss",available:false,reason:"missing_weights"}]}}));
  await page.goto("/research/pretrained");
  await expect(page.getByRole("heading",{name:"Pretrained Model Analysis",exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Analyze photograph",exact:true})).toBeDisabled();
  await expect(page.locator(".score-hero")).toHaveCount(0);
  await page.getByRole("button",{name:"中文",exact:true}).click();
  await expect(page.getByRole("heading",{name:"预训练模型分析",exact:true})).toBeVisible();
  await expect(page.getByRole("status")).toContainText("不可用");
  await page.reload();
  await expect(page.getByRole("heading",{name:"预训练模型分析",exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
