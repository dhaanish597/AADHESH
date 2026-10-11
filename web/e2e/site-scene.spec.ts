import { expect, test } from "@playwright/test";

test("production frontend build does not turn on demo mode by default", async ({ page }) => {
  await page.goto("/supervisor");
  await expect(page.getByRole("button", { name: "Current corpus" })).toBeEnabled();
  await expect(page.getByText(/Seeded demonstration/i)).toHaveCount(0);
});

test("site model zones open the resolver-backed inspector", async ({ page }) => {
  await page.goto("/supervisor?demo=1");
  await expect(page.getByRole("group", { name: "Interactive construction site model" })).toBeVisible();
  await expect(page.locator(".scene-loading, .site-scene-canvas, .site-scene-fallback").first()).toBeVisible();
  await expect.poll(async () => page.locator(".scene-loading").count()).toBe(0);
  await expect(page.locator("canvas.site-scene-canvas")).toBeVisible();
  await expect(page.getByRole("group", { name: "Site zones" })).toBeVisible();
  await page.getByRole("button", { name: /Dust controls/ }).click();
  await expect(page.getByRole("heading", { name: "Site inspector" })).toBeVisible();
  await expect(page.getByText("Historical replay — the January 2026 Stage III invocation was revoked. This is not a current restriction.")).toBeVisible();
});

test("site model falls back to accessible schematic zones without WebGL", async ({ page }) => {
  await page.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, type: string, ...args: unknown[]) {
      if (type.startsWith("webgl")) return null;
      return Reflect.apply(getContext, this, [type, ...args]);
    } as typeof HTMLCanvasElement.prototype.getContext;
  });
  await page.goto("/supervisor?demo=1");
  await expect(page.getByText("3D view unavailable · schematic view")).toBeVisible();
  await page.getByRole("button", { name: /Worker point/ }).click();
  await expect(page.getByRole("heading", { name: "Site inspector" })).toBeVisible();
  await expect(page.getByText("Worker assembly point")).toBeVisible();
});
