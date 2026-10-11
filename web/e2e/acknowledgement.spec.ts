import { expect, request, test } from "@playwright/test";

/**
 * The end-to-end browser proof for the local demonstration.
 *
 * The replay notice, the acknowledgement flow, the Cedar denial screen and the consent
 * grant/revoke controls are all driven in a real Chrome against the real Next.js app; the same
 * operations are also asserted over the real local API the app proxies to. Every token,
 * authorization decision and consent record here is produced by the actual backend -- no
 * fixtures, no mocks, and no identities beyond the demo roster the application itself ships.
 */
const API_URL = process.env.AADESH_API_URL ?? "http://127.0.0.1:8787";

type RosterWorker = {
  worker_id: string;
  parchi_id: string | null;
  state: string | null;
  payload: string | null;
};

test("historical replay, real acknowledgement, Cedar denials and consent-controlled assistance", async ({
  page,
}) => {
  const api = await request.newContext({ baseURL: API_URL });

  // 1. Mint a real, opaque token for a synthetic demo worker through the real backend.
  const orderResponse = await api.post("/api/standing-order", { data: { scenario: "replay" } });
  expect(orderResponse.ok()).toBeTruthy();

  const rosterResponse = await api.post("/api/roster/qr", { data: { scenario: "replay" } });
  expect(rosterResponse.ok()).toBeTruthy();
  const roster = (await rosterResponse.json()) as { workers: RosterWorker[] };
  const worker = roster.workers.find((w) => w.state === "pending_ack" && w.payload);
  expect(worker, "a pending worker with a real token should exist").toBeTruthy();
  const payload = worker!.payload as string;
  expect(payload.startsWith("aadesh://ack/")).toBeTruthy();
  // The token carries no worker identity in the payload itself.
  expect(payload).not.toContain(worker!.worker_id);
  expect(payload).not.toContain(worker!.parchi_id as string);

  // 2. The worker opens their own Parchi and acknowledges it in the browser.
  await page.goto(`/worker#payload=${encodeURIComponent(payload)}`);
  await page.getByRole("button", { name: "English" }).click();
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByText(worker!.parchi_id as string).first()).toBeVisible();
  await expect(page.getByText(/Synthetic demonstration record · not a live measurement/)).toBeVisible();
  await page.getByRole("button", { name: "How does it relate to this activity?" }).click();
  await expect(page.getByText(/does not include an activity-specific explanation/)).toBeVisible();
  await page.getByRole("button", { name: /I have reviewed my Parchi/i }).click();
  await expect(page.getByRole("status").filter({ hasText: /Confirmation recorded by the server/i })).toBeVisible();

  // 4. The server confirms the state change (server-confirmed state, not an optimistic UI).
  const viewResponse = await api.post("/api/worker/view", { data: { payload } });
  const view = (await viewResponse.json()) as { state: string };
  expect(view.state).toBe("acknowledged");

  // 5. Supervisor proxy acknowledgement is refused by the real Cedar policy, exercised through
  //    the /cedar screen — which asks the backend for the decision rather than showing a canned
  //    denial.
  await page.goto("/cedar");
  await page.getByRole("button", { name: /Acknowledge worker/i }).click();
  await expect(page.getByText(/^Denied$/)).toBeVisible();
  await expect(page.getByText(/no-proxy-acknowledgement/).first()).toBeVisible();

  //    The same call over the API returns the same refusal with the same policy id.
  const proxyResponse = await api.post("/api/cedar/supervisor-acknowledge", {
    data: { worker_id: worker!.worker_id },
  });
  const proxy = (await proxyResponse.json()) as { denied?: boolean; allowed?: boolean; policy_id: string };
  expect(proxy.denied === true || proxy.allowed === false).toBeTruthy();
  expect(proxy.policy_id).toBe("no-proxy-acknowledgement");

  // 6. Facilitator access to the full Parchi is refused.
  const facilitatorResponse = await api.get("/api/facilitator");
  const facilitator = (await facilitatorResponse.json()) as {
    read_attempt: { allowed: boolean; policy_id: string | null };
  };
  expect(facilitator.read_attempt.allowed).toBe(false);
  expect(facilitator.read_attempt.policy_id).toBe("assist-is-not-disclosure");

  // 7. Assistance without a live worker-granted consent is denied.
  const deniedResponse = await api.post("/api/assist", {
    data: { worker_id: worker!.worker_id, parchi_id: worker!.parchi_id },
  });
  const denied = (await deniedResponse.json()) as { allowed: boolean; policy_id: string };
  expect(denied.allowed).toBe(false);
  expect(denied.policy_id).toBe("assist-requires-live-consent");

  // 8. The facilitator route denies access before consent and does not disclose case identifiers.
  await page.evaluate(() => window.sessionStorage.removeItem("aadesh_demo"));
  await page.goto("/facilitator");
  await expect(page.getByRole("heading", { name: "Worker consent is required" })).toBeVisible();
  await expect(page.getByText(worker!.worker_id, { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /grant consent/i })).toHaveCount(0);

  // The worker returns to their own token-backed Parchi and controls the consent request.
  await page.goto(`/worker#payload=${encodeURIComponent(payload)}`);
  await page.getByRole("button", { name: "सहायता की अनुमति दें" }).click();
  await expect(page.getByRole("status").filter({ hasText: "सर्वर ने सहायता-अनुमति दर्ज की" })).toBeVisible();
  const storedConsent = await page.evaluate(() => sessionStorage.getItem("aadesh.worker.consent-reference"));
  expect(storedConsent).toBeTruthy();
  expect(storedConsent).not.toContain(worker!.worker_id);
  expect(storedConsent).not.toContain(worker!.parchi_id as string);

  // 9. The consent the UI just created now authorizes the real assistance call, REDACTED.
  const allowedResponse = await api.post("/api/assist", {
    data: { worker_id: worker!.worker_id, parchi_id: worker!.parchi_id },
  });
  const allowed = (await allowedResponse.json()) as { allowed: boolean; view: Record<string, unknown> };
  expect(allowed.allowed).toBe(true);
  const serialised = JSON.stringify(allowed).toLowerCase();
  for (const banned of ["aadhaar", "bank", "phone", "ifsc", "obligation_ids", "source_quote", "readiness_checklist"]) {
    expect(serialised, `facilitator view must not leak ${banned}`).not.toContain(banned);
  }

  // 10. The permitted facilitator UI shows only the redacted response and guided stages.
  await page.goto("/facilitator");
  const caseSummary = page.getByRole("button", { name: /Case summary/ });
  await caseSummary.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Permitted case summary" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Source guidance/ })).toBeVisible();
  await page.getByRole("button", { name: /Source guidance/ }).click();
  await expect(page.getByRole("heading", { name: "Source citations are unavailable" })).toBeVisible();

  // The worker revokes consent from their own Parchi; the facilitator refresh clears protected data.
  await page.goto(`/worker#payload=${encodeURIComponent(payload)}`);
  await page.getByRole("button", { name: "अनुमति वापस लें" }).click();
  await expect(page.getByRole("status").filter({ hasText: "सर्वर ने अनुमति वापस लेने की पुष्टि की" })).toBeVisible();
  await page.goto("/facilitator");
  await expect(page.getByRole("heading", { name: "Worker consent is required" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Permitted case summary" })).toHaveCount(0);

  const afterResponse = await api.post("/api/assist", {
    data: { worker_id: worker!.worker_id, parchi_id: worker!.parchi_id },
  });
  const after = (await afterResponse.json()) as { allowed: boolean };
  expect(after.allowed).toBe(false);

  await api.dispose();
});

test("worker mobile journey has keyboard-accessible language and interactive 3D controls", async ({ page }) => {
  const api = await request.newContext({ baseURL: API_URL });
  await api.post("/api/standing-order", { data: { scenario: "replay" } });
  const rosterResponse = await api.post("/api/roster/qr", { data: { scenario: "replay" } });
  const roster = (await rosterResponse.json()) as { workers: RosterWorker[] };
  const worker = roster.workers.find((item) => item.payload);
  expect(worker?.payload).toBeTruthy();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/worker#payload=${encodeURIComponent(worker!.payload!)}`);
  await expect(page.locator(".scene-explorer")).toBeVisible();
  await expect(page.locator(".scene-explorer-viewport")).toHaveAttribute("data-state", "ready");
  await page.getByRole("button", { name: "English" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Your Parchi, your next steps" })).toBeVisible();
  await expect(page.getByRole("button", { name: "हिन्दी" })).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("button", { name: "हिन्दी" }).click();
  await expect(page.getByRole("heading", { name: "आपकी पर्ची, आपके अगले कदम" })).toBeVisible();
  await page.locator(".scene-explorer-controls button").first().focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".scene-explorer-controls button").first()).toBeFocused();
  await page.locator(".scene-object-list summary").focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".scene-object-list")).toHaveAttribute("open", "");
  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(horizontalOverflow).toBe(false);
  await api.dispose();
});

test("worker keeps the full journey and generated 3D scene visible without a linked Parchi", async ({ page }) => {
  const workerViewRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/worker/view")) workerViewRequests.push(request.url());
  });
  await page.goto("/worker?demo=1");
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("heading", { name: "Your Parchi, your next steps" })).toBeVisible();
  await expect(page.locator(".scene-explorer")).toBeVisible();
  await expect(page.locator(".scene-provenance")).toContainText(/SYNTHETIC DEMO GEOMETRY/);
  await expect(page.getByRole("navigation", { name: "Parchi journey" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No Parchi link" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Illustrative construction site" })).toBeVisible();
  await expect(page.getByText(/personal QR provided at your site/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Worker consent is required" })).toHaveCount(0);
  expect(workerViewRequests).toHaveLength(0);
  await expect(page.getByRole("button", { name: "Open Parchi" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "I have reviewed my Parchi" })).toHaveCount(0);
  await page.getByRole("button", { name: "How does it relate to this activity?" }).click();
  await expect(page.getByRole("heading", { name: "How does it relate to this activity?" })).toBeVisible();

  await page.getByLabel("Personal QR link / token").fill("not-a-real-personal-token");
  await page.getByRole("button", { name: "Open Parchi" }).click();
  await expect(page.locator(".worker-alert")).toBeVisible();
  await expect(page.locator(".scene-explorer")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Parchi journey" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Parchi" })).toBeVisible();
  await expect(page.getByText("This demonstration Parchi is unavailable")).toHaveCount(0);
});

test("facilitator workspace, pathway and generated site scene remain visible when consent is denied", async ({ page }) => {
  await page.goto("/facilitator");
  await expect(page.getByRole("heading", { name: "Help move one step forward." })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Assistance request queue" })).toBeVisible();
  await expect(page.getByRole("group", { name: "Assistance stages" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Worker consent is required" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Illustrative site context" })).toBeVisible();
  await expect(page.locator(".scene-explorer-viewport")).toHaveAttribute("data-state", "ready");
  await page.locator(".scene-object-list summary").click();
  await page.getByRole("button", { name: /Frame work area/ }).click();
  await expect(page.locator(".scene-selection strong")).toHaveText("Frame work area");
  await expect(page.getByText(/No site survey, zone-level rule, or authorized case is implied/i)).toBeVisible();
  await expect(page.getByText("No permitted case", { exact: true })).toBeVisible();
  await expect(page.getByText("No protected case details", { exact: true })).toBeVisible();
});

test("worker scene stays accessible when WebGL is blocked", async ({ page }) => {
  const api = await request.newContext({ baseURL: API_URL });
  await api.post("/api/standing-order", { data: { scenario: "replay" } });
  const rosterResponse = await api.post("/api/roster/qr", { data: { scenario: "replay" } });
  const roster = (await rosterResponse.json()) as { workers: RosterWorker[] };
  const worker = roster.workers.find((item) => item.payload);
  expect(worker?.payload).toBeTruthy();
  await page.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, type: string, ...args: unknown[]) {
      if (type.startsWith("webgl")) return null;
      return Reflect.apply(getContext, this, [type, ...args]);
    } as typeof HTMLCanvasElement.prototype.getContext;
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/worker#payload=${encodeURIComponent(worker!.payload!)}`);
  await expect(page.locator(".scene-render-error")).toBeVisible();
  await page.locator(".scene-object-list summary").click();
  await page.getByRole("button", { name: /Frame work area/ }).click();
  await expect(page.locator(".scene-selection strong")).toHaveText("Frame work area");
  // The accessible object list remains usable while WebGL is unavailable.
  await expect(page.locator("canvas")).toHaveCount(0);
  await api.dispose();
});
