import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const SCREENSHOTS = path.resolve(process.cwd(), "../.playwright-mcp/dynamic-site-scene");

test.beforeAll(async () => mkdir(SCREENSHOTS, { recursive: true }));

async function expectRenderedScene(page: import("@playwright/test").Page) {
  await expect(page.locator(".scene-explorer")).toBeVisible();
  await expect(page.locator(".scene-provenance")).toContainText(/synthetic|सांकेतिक/i);
  await expect(page.locator(".scene-explorer-viewport")).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  await expect(page.locator(".scene-render-error")).toHaveCount(0);
  await expect(page.locator("canvas.scene-explorer-canvas")).toBeVisible();
}

test("Worker desktop scene reconfigures, filters, and supports accessible selection", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/worker");
  await expectRenderedScene(page);
  const canvasBounds = await page.locator("canvas.scene-explorer-canvas").boundingBox();
  expect(canvasBounds).not.toBeNull();
  await page.mouse.click(canvasBounds!.x + canvasBounds!.width * 0.52, canvasBounds!.y + canvasBounds!.height * 0.52);
  await expect(page.locator(".scene-selection strong")).not.toHaveText(/Nothing selected|कोई चयन नहीं/);
  await page.locator(".scene-object-list summary").click();
  await page.getByRole("button", { name: /Floor 1 column · grid 1, 1/ }).click();
  await expect(page.locator(".scene-selection strong")).toContainText(/Floor 1 column/);
  await page.locator(".scene-explorer-toolbar select").nth(1).selectOption("2");
  await page.locator(".scene-explorer-toolbar select").nth(0).selectOption("demo-midrise-shell");
  await expect(page.locator(".scene-explorer-toolbar select").nth(1).locator("option")).toHaveCount(7);
  await page.locator(".scene-explorer-layers input[type=checkbox]").last().uncheck();
  await expect(page.locator(".scene-explorer-toolbar select").nth(0)).toHaveValue("demo-midrise-shell");
  await page.locator(".scene-explorer-layers input[type=checkbox]").last().check();
  await page.locator(".scene-object-list summary").click();
  await expect(page.locator(".scene-explorer-viewport")).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  await page.screenshot({ path: path.join(SCREENSHOTS, "worker-desktop.png"), fullPage: true, animations: "disabled" });
  expect(pageErrors).toEqual([]);
});

test("Facilitator has the same interactive scene while unauthorized case data stays redacted", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/facilitator");
  await expectRenderedScene(page);
  await expect(page.getByText("Worker consent is required")).toBeVisible();
  await expect(page.locator(".assist-main")).toContainText("Illustrative site context only");
  await page.locator(".scene-object-list summary").click();
  await page.getByRole("button", { name: /Material staging area/ }).click();
  await expect(page.locator(".scene-selection strong")).toHaveText("Material staging area");
  await page.locator(".scene-explorer-toolbar select").nth(0).selectOption("demo-midrise-shell");
  await page.locator(".scene-object-list summary").click();
  await expect(page.locator(".scene-explorer-viewport")).toHaveAttribute("data-state", "ready", { timeout: 30_000 });
  await page.screenshot({ path: path.join(SCREENSHOTS, "facilitator-desktop.png"), fullPage: true, animations: "disabled" });
  expect(pageErrors).toEqual([]);
});

test("Worker and Facilitator scenes remain usable at mobile width", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.setViewportSize({ width: 390, height: 844 });
  for (const role of ["worker", "facilitator"] as const) {
    await page.goto(`/${role}`);
    await expectRenderedScene(page);
    const sizes = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, page: document.documentElement.scrollWidth }));
    expect(sizes.page).toBeLessThanOrEqual(sizes.viewport + 1);
    await page.screenshot({ path: path.join(SCREENSHOTS, `${role}-mobile.png`), fullPage: true, animations: "disabled" });
  }
  expect(pageErrors).toEqual([]);
});

test("missing registered model asset falls back to the accessible scene object list", async ({ page }) => {
  await page.route("**/models/kenney/floor.glb", (route) => route.fulfill({ status: 404, body: "missing model" }));
  await page.goto("/worker");
  await expect(page.locator(".scene-render-error")).toBeVisible({ timeout: 30_000 });
  await page.locator(".scene-object-list summary").click();
  await page.getByRole("button", { name: /Frame work area/ }).click();
  await expect(page.locator(".scene-selection strong")).toHaveText("Frame work area");
});
