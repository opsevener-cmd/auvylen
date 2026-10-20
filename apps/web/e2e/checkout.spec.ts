import {expect, test} from "@playwright/test";

test("mobile mock checkout persists one synthetic result", async ({page, request}) => {
  await page.goto("/");
  await page.getByRole("link", {name: /View development demo/}).click();
  await expect(page.getByRole("heading", {name: "Auvylen Analysis"})).toBeVisible();
  await expect(page.getByText("¥1.00", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Create order"}).click();
  await expect(page).toHaveURL(/\/checkout\/av_[a-f0-9]+$/);
  const orderId = page.url().split("/").at(-1);
  await expect(page.getByText("Mock Payment", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Simulate successful payment"}).click();
  await expect(page).toHaveURL(/\/result\/[a-f0-9-]+$/);
  await expect(page.getByText("Development / Synthetic Result", {exact: true})).toBeVisible();
  await expect(page.getByText("Analysis status: COMPLETED", {exact: true})).toBeVisible();
  await expect(page.getByText("Raw score", {exact: true})).toBeVisible();
  await expect(page.getByText("0.1.0", {exact: true})).toBeVisible();
  const api = `http://127.0.0.1:${process.env.E2E_API_PORT ?? "8000"}/api/v1`;
  const order = await (await request.get(`${api}/orders/${orderId}`)).json();
  expect(order.status).toBe("COMPLETED");
  expect(order.amount).toBe(100);
  expect(order.paid_at).toBeTruthy();
  const result = await (await request.get(`${api}/analyses/${order.analysis_id}/result`)).json();
  expect(result.metadata.synthetic).toBe(true);
  expect(result.engine_version).toBe("0.1.0");
});
