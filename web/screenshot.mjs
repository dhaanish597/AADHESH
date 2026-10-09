import { chromium } from "playwright";

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:4242";
const OUT = new URL("../screenshots", import.meta.url);

await (async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext();

  const pages = [
    { name: "site-phone", url: `${BASE}/site`, width: 390, height: 844 },
    { name: "parchi-phone", url: `${BASE}/parchi/PCH-2026-1011-0007`, width: 390, height: 844 },
    { name: "site-desktop", url: `${BASE}/site`, width: 1440, height: 900 },
    { name: "parchi-desktop", url: `${BASE}/parchi/PCH-2026-1011-0007`, width: 1440, height: 900 },
  ];

  for (const p of pages) {
    const page = await ctx.newPage({ viewport: { width: p.width, height: p.height } });
    await page.goto(p.url, { waitUntil: "networkidle" });
    // give the QR SVG a tick so it paints
    if (p.name.startsWith("parchi")) {
      await page.waitForTimeout(250);
    }
    const path = OUT.pathname + "/" + p.name + ".png";
    await page.screenshot({ path, fullPage: false, omitBackground: false });
    console.log(`screenshot ${path}`);
    await page.close();
  }

  await browser.close();
  console.log("done");
})();
