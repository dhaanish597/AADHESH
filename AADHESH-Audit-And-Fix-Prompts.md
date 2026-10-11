# AADHESH — Repo Audit, Winner Gap Analysis & Structured Fix Prompts

**Audited:** `AADHESH-main.zip`, 10 Oct 2026 · **Deadline:** Sun 11 Oct, 20:00 IST
**Realistic working time left:** ~12 hours before an 11:00 IST Sunday code freeze.

---

## 0. The verdict in one paragraph

Your engine is winning-grade and your shop window is boarded up. The Python core, the corpus integrity gate, the Cedar policies, the 80-file test suite and the 1,073-line SAM template are, in several specific ways, **better than anything that won First Commit**. But **Tailwind is never imported and 292 of your 295 CSS classes do not exist**, so every page renders as unstyled browser-default HTML — which is not "looks like a docs website" by coincidence, it *is* an unstyled document. On top of that, nothing ever publishes the frontend to Amplify, and the console demands a Cognito login that no judge will create. Three defects, all mechanical, all fixable today. Spend every remaining hour on the window and almost none on the engine.

**One substantive finding you must act on:** `corpus/entitlements/cess_fund.json` contains **zero entitlements**. The project's central claim — "your 34 men get the money the law already owes them" — currently has no cited evidence behind it. Section 4 tells you how to fix the pitch honestly in 40 minutes rather than fake it.

---

## 1. What the previous winners actually did, and where you stand

Verified from source on 9–10 Oct: `github.com/AfreenInnovates/campus` (CampusEvac, Best UI, ₹1L), the Beacon Night Shift author's own write-up (Build It, ₹1.5L), and Kunal Kushwaha's recap of all three winners.

| Winning trait | How the winner did it | AADHESH today |
|---|---|---|
| **A named art direction, written down** | Line 3 of their `globals.css`: *"CampusEvac neo-brutalism: warm paper, plum ink, hard shadows, sunset accents."* 450 lines of tokens and component classes | ❌ `globals.css` is 93 lines of nav CSS. No `@import "tailwindcss"`, no `@theme`, no `:root` tokens |
| **Custom design tokens, zero defaults** | 11 named CSS vars mapped through `@theme inline` | ❌ 13 token names *referenced* (`accent`, `panel`, `line`…), none *defined* |
| **Named component classes** | `.brutal-panel`, `.brutal-slab`, `.hud-panel`, `.brutal-num` | ❌ ~115 referenced (`.evidence-console`, `.stage-display`, `.parchi-*`), none authored |
| **A URL a judge can just open** | Amplify Hosting, no auth wall, room codes for instant two-device demo | ❌ Cognito wall on `/supervisor`; `lib/demo-seed.ts` (292 lines) is dead code, imported nowhere |
| **The frontend is actually deployed** | `amplify.yml` at repo root, CDK wires it up | ❌ `AWS::Amplify::App` created with `EnableAutoBuild: false`, no `Repository`, no `BuildSpec`, no `amplify.yml`, no deploy step |
| **Demo cannot be killed by an API** | Ran Polly at *build* time, committed hashed MP3s + `manifest.json` | ⚠️ `ExplainBackend=deterministic` gives you this for free — use it, and say so |
| **Phone treated as first-class** | `viewportFit: cover`, safe-area insets everywhere, runtime-measured touch dock | ⚠️ Viewport meta is correct; nothing below it can work until CSS exists |
| **Reduced motion respected** | Honoured in three separate blocks | ❌ Not present |
| **UI visible without cloning** | 8 captioned screenshots committed, Mermaid diagram in README | ❌ 22 KB README, zero images, ASCII diagram only |
| **Clean-machine setup test** | Beacon's author credits this for his win: *"It broke in two places that never broke on my own machine"* | ❌ `sam-deploy.ps1` hardcodes `C:\Users\clash\Documents\AADHESH` |

### Where you are already ahead — protect these, do not refactor them

- **`make verify` *and* `make verify-tamper`.** The tamper proof exists and flips a real byte. No First Commit winner had anything this strong. This is your single best architecture-segment moment.
- **The corpus CLI refuses paraphrase at ingest.** *"Every quote is checked VERBATIM against the page it cites… A paraphrase is refused at the door."* That is a demoable integrity gate, not a claim.
- **`invoked_stage.json` models lifecycle properly** — Stage III invoked 16 Jan 2026, **revoked 22 Jan 2026**, both cited, both hashed, with an explicit note that it is replay-only and not currently in force. The "an AQI observation by itself does not activate a legal workflow" guarantee is genuinely implemented, not asserted.
- **Cedar is real.** 15 policies, three `@id`-annotated forbids, `denials.json` mapping each to a human sentence, and a test asserting every forbid has an entry. This is exactly the organizers' published pattern, done properly.
- **80 test files**, including `test_authorization_no_bypass.py`, `test_explanation_security.py`, and `test_asl_matches_core_machine.py` — which asserts the deployed Step Functions ASL matches the in-core state machine. That is a level of rigour judges rarely see.
- **1,073-line SAM template**: 6 DynamoDB tables, S3 with versioning, Cognito, API Gateway with a Cognito authorizer and 5 deliberately-public routes, 9 Lambdas, Step Functions with `waitForTaskToken`, EventBridge, CloudWatch alarms + dashboard. Deeper AWS than CampusEvac's CDK stack.
- **`make test` needs no Docker, no AWS, no network.** Stated as a design rule in the Makefile. A judge can run your tests in 30 seconds.

**Read that list again before you touch anything.** The temptation over the next twelve hours will be to improve the engine. Don't. It already scores.

---

## 2. Findings, severity-ranked, with evidence

### P0-1 · BLOCKER · Tailwind is never imported; the UI is unstyled HTML

**Evidence.** `web/app/globals.css` is 93 lines and the only CSS file in the project. It contains no `@import "tailwindcss"`, no `@theme`, and no `:root` block. It defines exactly 5 classes (`.site-root`, `.site-main`, `.site-bottom-nav`, `.site-bottom-link`, `.site-bottom-link-active`). Across `web/app/**` and `web/components/**` there are **554 `className` attributes referencing 295 distinct classes — 292 of which are undefined.** Of those, 146 are Tailwind utilities that cannot resolve because Tailwind isn't loaded, and ~115 are custom semantic classes that were never written. The 93 lines that *do* exist reference `--surface-panel`, `--paper-edge`, `--text-secondary`, `--text-ink`, `--accent` and `--text-faint`, none of which are defined anywhere either.

**The tell.** `web/tailwind.config.ts` carries this comment: *"Tailwind v4 is configured in CSS-first style inside app/globals.css (@theme inline). All colours, fonts, radii and shadows live as named tokens in globals.css and are never slate/zinc/gray defaults."* That comment describes code that was never written. An agent shipped the documentation and skipped the implementation, and nobody opened the page.

**Consequence.** Default serif-ish browser rendering, full-width text, no colour, no hierarchy. Exactly the symptom you reported.

### P0-2 · BLOCKER · No judge can get into the deployed console

`lib/api.ts` throws `"This screen needs a signed-in session. Use Sign in in the header."` on 401. `/site` redirects to `/supervisor`, which is auth-gated. Five endpoints are deliberately public — `/api/worker/view`, `/api/worker/acknowledge`, `/api/impact`, `/api/reading/latest`, `/api/health` — so a read-only demo is *architecturally already possible*. But `web/lib/demo-seed.ts` is 292 lines of **dead code imported by nothing**. You built the seed and never wired it up.

### P0-3 · BLOCKER · Nothing publishes the frontend

`AmplifyApp` and `AmplifyBranch` are declared, but: `EnableAutoBuild: false`, no `Repository` property, no `BuildSpec`, no `amplify.yml` anywhere in the repo, and `sam-deploy.ps1` has no frontend step. The `AmplifyDefaultDomain` output therefore returns a URL for an app with nothing deployed to it. The `CustomRules` 404-200 rewrite is correctly written for a static export — the plumbing is right, the publish step is simply absent.

### P0-4 · BLOCKER · The entitlement corpus is empty

`corpus/entitlements/cess_fund.json` is `{"entitlements": []}`. Meanwhile `corpus/obligations/construction_site.json` has **8 real, cited obligations** across Stages I, III and IV with verbatim quotes from the actual CAQM orders (the quotes even carry authentic OCR artifacts like `4O1-45Of`, which is a credibility asset — do not clean them).

So the obligation half is evidenced and the entitlement half — the emotional and strategic core, the reason the supervisor cooperates — has nothing behind it. Any rupee figure on screen right now is unsourced. Fix in §4.

### P1-5 · `sam-deploy.ps1` runs on exactly one laptop

```
Set-Location "C:\Users\clash\Documents\AADHESH\infra\aws"
$SamCli = "C:\Program Files\Amazon\AWSSAMCLI\bin\sam.cmd"
$Region = "ap-south-1"
```
Hardcoded user path, hardcoded SAM binary, PowerShell-only, and the stack region (`ap-south-1`) differs from `BedrockRegion` (`us-east-1`). A judge reproducing the deploy fails at line 8. This is precisely the clean-machine failure Beacon's author credits for his win.

### P1-6 · Docs contradict the template

`infra/aws/DEPLOYMENT_SUMMARY.md` claims **4** DynamoDB tables (the template has **6**: Parchis, Operational, StandingOrders, TriggerRuns, Readings, Sites), **11** Lambdas (the template has **9**), **2** EventBridge rules (I found **1**), and an **OpenSearch domain** that is not in the template at all. A judge who reads your docs and then greps your template finds the gap, and it taints the parts that *are* accurate.

### P1-7 · Repo hygiene, and one real credibility leak

- `CUsersclashAppDataLocalTempaadesh-supervisor.json` — 43 KB at repo root, a Windows temp path flattened into a filename. It is the first thing a judge sees on GitHub.
- `web/audit.json`, `web/package-check.json`, `web/screenshot.mjs` — scratch artifacts.
- `corpus/incoming_sources/` — raw downloads with GUID filenames (`01fcdebf-83e1-4cfe-….pdf`, `GRAP Order dated 220120265838a44f-….pdf`). The curated, hashed copies already live in `corpus/sources/`.
- **`docs/research/` contains the strategy PDFs and `Environmental-Hacks-Winning-Plan.md`.** That document includes a model of how judges score, an analysis of which archetypes other teams will submit, and a section titled "Why We Can Beat Other Teams." In a public repo, it reframes your project from *a problem we saw* into *a project reverse-engineered from a rubric*, which attacks criterion one directly. **Delete it from the repo before submission.** Keep it locally.
- `docs/superpowers/specs|plans` — agent planning artifacts. Less harmful (AI tool use is permitted and you should disclose it), but rename the directory to `docs/design/` so it reads as engineering rather than as a toolchain footprint.

### P2-8 · Smaller items

`@phosphor-icons/react` is a dependency, and `next.config.mjs` even tunes `optimizePackageImports` for it, but every icon in `components/ui.tsx` is a hand-rolled SVG — the package is unused. No `opengraph-image`, so your submitted URL previews as a blank card. No `prefers-reduced-motion` block. No README screenshots.

---

## 3. The plan for your remaining ~12 hours

Do these strictly in order. Each prompt is self-contained and copy-pasteable. **Stop at 11:00 IST Sunday regardless of where you are** and spend the rest on video, README and submission.

| # | Task | Box | Score impact |
|---|---|---|---|
| **P1** | Restore the stylesheet — tokens + Tailwind + 115 component classes | 4 h | Design & usability, Execution — **enormous** |
| **P2** | Demo mode: a judge-openable console with no login | 2 h | Design & usability — **blocker** |
| **P3** | Publish the frontend to Amplify, get a live URL | 1.5 h | Built on AWS, Execution — **blocker** |
| **P4** | Entitlement honesty fix — reframe the headline number | 40 m | Idea & impact — **credibility** |
| **P5** | Repo hygiene + docs truth-up + remove `docs/research` | 45 m | Execution, Idea & impact |
| **P6** | README screenshots + Mermaid + OG image | 45 m | Demo video, Design |
| **P7** | Cross-platform deploy script + clean-machine test | 1 h | Execution — do only if P1–P6 are done |

---

## PROMPT P1 — Restore the stylesheet

> Paste this first. Nothing else matters until the page has pixels.

=== COPY ===

Our Next.js console at `web/` renders as completely unstyled HTML. I have diagnosed the root cause precisely; do not re-investigate, just fix it.

**Root cause.** `web/app/globals.css` is 93 lines, is the only CSS file in the project, and contains no `@import "tailwindcss"`, no `@theme` block, and no `:root` token definitions. Across `web/app/**` and `web/components/**` there are 554 `className` attributes referencing 295 distinct classes, of which **292 are undefined**: 146 are Tailwind utilities that cannot resolve because Tailwind is never imported, and ~115 are custom semantic classes that were never authored. The existing 93 lines also reference six CSS variables that are themselves undefined (`--surface-panel`, `--paper-edge`, `--text-secondary`, `--text-ink`, `--accent`, `--text-faint`).

**Before you write code,** load design guidance with your skill tool, in this order: `frontend-design`, then `color-palette`, then `typography-guide`, then `design-system`. If a skill is unavailable, say so explicitly and fetch these instead, then summarise what you took from each: https://tailwindcss.com/docs/theme · https://tailwindcss.com/docs/colors · https://www.myndex.com/APCA/ · https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion · https://developer.mozilla.org/en-US/docs/Web/CSS/env

**Do not install any UI kit.** No shadcn, no DaisyUI, no Material. Do not introduce a single `slate-*`, `zinc-*` or `gray-*` utility. Every colour comes from our tokens.

### Task A — rebuild `web/app/globals.css`

Start the file with `@import "tailwindcss";` then a comment naming the art direction, then `:root`, then `@theme inline`, then the component layers.

**The art direction, which you must write as the opening comment and then hold to:**

> Aadesh "Field Instrument": a dark concrete operations console for the supervisor, and a warm stamped-paper parchi for the worker. Amber and red are STATE, never decoration. Hard edges, tabular numerals, no glassmorphism, no gradients-as-decoration, no neo-brutalism.

**Define exactly these 13 token families, because the codebase already references them by these names.** Do not rename them; the TSX depends on them.

`accent` · `panel` · `panelAlt` · `line` · `lineStrong` · `rule` · `danger` · `success` · `faint` · `ink` · `dim` · `link` · `concrete` (used as `concrete-700`)

Starting values — refine with the `color-palette` skill and verify every text-on-background pair with APCA before committing:

```css
:root {
  /* console surfaces — cool, never purple */
  --concrete-900:#13161a; --concrete-800:#1b1f25; --concrete-700:#252a32; --concrete-600:#343a44;
  --panel:#1b1f25; --panel-alt:#252a32;
  --line:#2c323b; --line-strong:#3f4651; --rule:#3f4651;
  /* text */
  --ink:#eef1f4; --dim:#c2c9d2; --faint:#8b949e;
  /* state — the only saturated colours in the console */
  --accent:#ffb000;  /* stage invoked / standing order armed */
  --danger:#e5332a;  /* work stopped */
  --success:#1f9d55; /* permitted / acknowledged */
  --link:#4a7cf0;    /* provenance, hashes, citations */
  /* parchi — warm paper artifact */
  --paper:#f6f1e4; --paper-edge:#e3dac4;
  --stamp-ink:#1a1a18; --stamp-red:#b3261e; --stamp-blue:#1f3a93;
  /* aliases the existing 93 lines already use */
  --surface-panel:var(--panel); --text-ink:var(--ink);
  --text-secondary:var(--dim); --text-faint:var(--faint);
}
```

Map all of them through `@theme inline` as `--color-accent`, `--color-panel`, `--color-panelAlt`, `--color-line`, `--color-lineStrong`, `--color-rule`, `--color-danger`, `--color-success`, `--color-faint`, `--color-ink`, `--color-dim`, `--color-link`, `--color-concrete-700`, plus `--font-sans: var(--font-plex-sans)`, `--font-deva: var(--font-plex-deva)`, `--font-mono: var(--font-plex-mono)`. The three fonts are already correctly loaded in `web/app/layout.tsx` — do not touch that file except where Task D requires it.

### Task B — author the missing component classes

These are referenced in the TSX and must all exist. Group them in commented sections in this order: **shell → home → system map → stage → supervisor → worker/parchi → evidence → cedar → facilitator → impact**.

```
Shell:        site-header site-brand site-nav header-cta status-dot status-separator
              footer-mark label data uppercase underline
Home:         experience-home experience-hero experience-section experience-footer
              hero-copy hero-lede hero-actions hero-divider hero-titlemark hero-status
              hero-product-label hero-bottomline brand-glyph action-primary action-secondary
              site-visual site-visual-top site-visual-foot site-svg path-flow path-key key-line key-dash
              section-heading-row section-index section-intro inline-note map-footnote
System map:   system-map system-section system-nodes system-node-name system-node-number
              system-connectors optional-connector flow-explorer flow-rail flow-section
              flow-readout flow-step-node flow-step-number flow-step-title
              node-inspector node-facts node-role inspector-title
Stage:        stage-section stage-explorer stage-display stage-main stage-value stage-measure
              stage-implied stage-controls observation-origin
Supervisor:   operations-workspace operations-header operations-title operations-scene-row
              operations-missions operations-loading operations-error
              site-scene site-scene-surface site-scene-svg site-scene-dot
              site-scene-legend site-scene-legend-item site-object-label site-object-mark
              site-inspector site-inspector-card site-inspector-header site-inspector-body
              missions-list mission-item-check boundaries-row
              workflow-progress workflow-progress-rail
              progress-node-bar progress-node-fill progress-node-count progress-node-detail
              progress-node-glyph progress-node-label progress-node-meta
Worker:       worker-journey worker-route supervisor-journey facilitator-journey
              journeys-section journey-lines journey-link journey-foot
Evidence:     evidence-console evidence-section evidence-trail evidence-counts
              evidence-expand evidence-verdict verdict-sub verification-output tamper-note
              provenance-inspector provenance-step implementation-status
Explanation:  explanation-inspector explanation-branch
Misc:         dim-on-concrete
```

Design rules for them:

- `.action-primary` is the consequential button. Give it physical press feedback — a small transform on `:active` and a shadow that responds — in the spirit of a real switch. `.action-secondary` is quiet and bordered.
- `.stage-display` / `.stage-value` / `.stage-main` are the state anchor. The invoked stage must be the single most prominent thing on the supervisor screen, legible across a room.
- `.stage-implied` and `.observation-origin` carry the AQI-implied reading and must be visually *subordinate* to the invoked stage. When the two disagree, `.stage-implied` takes `--accent`. **Never let the AQI number out-rank the invoked stage.**
- `.data`, `.progress-node-count`, `.stage-value`, `.evidence-counts` and anything numeric: `font-family: var(--font-mono)` and `font-variant-numeric: tabular-nums`. Numbers must not reflow as they tick.
- `.label` is the operational micro-label: uppercase, 600 weight, `letter-spacing:.14em`, `font-size:.6875rem`, colour `--faint`.
- `.verification-output` and `.evidence-console` are terminal-like: mono, dark, left rule in `--link`, preserved whitespace.
- `.tamper-note` must read as a deliberate warning, in `--danger`.
- `.progress-node-fill` animates width with a 220 ms `cubic-bezier(0.22,0.8,0.24,1)`.
- Parchi surfaces use `--paper` / `--paper-edge` / `--stamp-*` and must look like a physical slip: visible serial, stamped header, a perforation or deckle edge. Body text minimum 18px, status line 32px+, primary button at least 56px tall — it is read outdoors in sunlight, one-handed.
- Devanagari: give `.font-deva` and any Hindi container `line-height:1.65` minimum (Latin sits at 1.45). Test with `आपका काम आज बंद है` and confirm no matra clipping.

### Task C — accessibility and motion

Add one global `@media (prefers-reduced-motion: reduce)` block that neutralises every animation and transition. Visible focus rings in `--link` on all interactive elements, never `outline:none` without a replacement. Minimum 44×44px touch targets. Keep the existing `env(safe-area-inset-*)` usage in the bottom nav and extend it to any new edge-anchored surface.

### Task D — prove it

1. `cd web && npm install && npm run build` must pass. Then `npm run dev`.
2. Screenshot `/`, `/supervisor`, `/worker`, `/verify`, `/cedar`, `/facilitator`, `/impact` at **390×844** and **1440×900**.
3. **Squint test:** blur each screenshot. On `/supervisor` the most prominent element must be the stage/state display. On `/worker` it must be the status line and the acknowledge button. If a nav bar, a block of clause text, or the AQI number wins, the hierarchy is wrong — fix and re-shoot.
4. Re-run the undefined-class check and report the number. It must be zero:
   ```bash
   cd web && grep -ohE 'className="[^"]*"' app/*.tsx app/*/*.tsx components/*.tsx \
     | sed 's/className="//;s/"$//' | tr ' ' '\n' | sed '/^$/d' | sort -u > /tmp/used.txt
   ```
   Cross-check against the classes you defined plus real Tailwind utilities.
5. Grep your diff for `slate-`, `zinc-`, `gray-`, `bg-card`, `text-muted-foreground`. Every hit is a bug.
6. Report the three weakest things about the result and what you would fix with one more hour.

**Do not touch** `services/`, `corpus/`, `infra/`, `tests/`, or `Makefile`. If a fix seems to require backend changes, stop and ask.

=== COPY ===

---

## PROMPT P2 — Demo mode, so a judge can actually see it

=== COPY ===

A judge will open our deployed URL, not create an account. Today `/site` redirects to `/supervisor`, which is Cognito-gated, and `lib/api.ts` shows *"This screen needs a signed-in session."* That is a scoring blocker for "Design and usability," whose published test is *"Would someone who isn't on your team know what to do with it?"*

We already have everything needed. **Five API routes are deliberately unauthenticated** in `infra/aws/template.yaml`: `POST /api/worker/view`, `POST /api/worker/acknowledge`, `GET /api/impact`, `GET /api/reading/latest`, `GET /api/health`. And `web/lib/demo-seed.ts` is 292 lines of seed data that **is imported by nothing** — it is dead code.

Build a read-only demo mode:

1. Add `NEXT_PUBLIC_AADESH_DEMO=1`. When set, or when `?demo=1` is present, the console renders the supervisor, worker, cedar, facilitator and evidence screens from `lib/demo-seed.ts` instead of calling authenticated endpoints. Wire up the seed that already exists; do not write a new one.
2. Keep the public endpoints live even in demo mode — `/api/impact`, `/api/reading/latest` and `/api/health` need no session, so the demo should show *real* data where it legitimately can and seeded data only where auth would otherwise block it.
3. Add a persistent, honest banner on every demo screen: **`DEMO — seeded site, real corpus`**, with a link to sign in for the live console. Never let demo data masquerade as live. This honesty is explicitly rewarded by the organizers.
4. On `/`, replace any sign-in-first path with two unmistakable entry buttons: **"Open the supervisor console"** and **"See a worker's parchi"**, both landing in demo mode with no auth. Keep "Sign in" available in the header, de-emphasised.
5. `/site` currently `redirect()`s to `/supervisor`. Keep the redirect but preserve the query string so `/site?demo=1` works.
6. The Cedar denial must be reachable in demo mode. Seed the state where a supervisor attempts to acknowledge on a worker's behalf, and render the `no-proxy-acknowledgement` sentence from `infra/cedar/denials.json` as a **deliberate denial panel, not a toast**. This is a scripted beat in our demo video.

Acceptance: in a fresh incognito window with no cookies, I can reach the supervisor console, the worker parchi, a Cedar denial, and the verification output, without ever signing in, and every screen states plainly which data is seeded and which is live.

=== COPY ===

---

## PROMPT P3 — Publish the frontend and get a live URL

=== COPY ===

Our `infra/aws/template.yaml` creates `AWS::Amplify::App` and `AWS::Amplify::Branch`, but with `EnableAutoBuild: false`, no `Repository`, no `BuildSpec`, and there is **no `amplify.yml` anywhere in the repo** and no frontend step in `infra/aws/sam-deploy.ps1`. So `AmplifyDefaultDomain` returns a URL for an app with nothing deployed to it. The `CustomRules` 404-200 rewrite is already correct for a static export — only the publish step is missing.

Do the manual-deployment path, because it does not require connecting a Git provider and will work today:

1. Add `amplify.yml` at the repo root with a build spec that runs in `web/`: `npm ci`, then `AADHESH_STATIC_EXPORT=1 NEXT_PUBLIC_API_BASE_URL=$API_URL NEXT_PUBLIC_AADESH_DEMO=1 npm run build`, with `baseDirectory: web/out` and `node_modules` cached.
2. Add `infra/aws/deploy-web.sh` (POSIX sh, no PowerShell, no hardcoded paths) that:
   - reads `ApiUrl` and `AmplifyAppId` from `aws cloudformation describe-stacks --stack-name "$STACK"`,
   - builds the static export in `web/` with `AADHESH_STATIC_EXPORT=1` and that `ApiUrl`,
   - zips `web/out`,
   - calls `aws amplify create-deployment` / `start-deployment` for branch `main`,
   - polls until the job succeeds and prints the live URL.
   Every path relative to the repo root, discovered via `git rev-parse --show-toplevel`. Fail loudly with a readable message if a prerequisite is missing.
3. Confirm the CORS origin in the template (`AllowOrigin: 'https://main.${AmplifyApp.AppId}.amplifyapp.com'`) matches the branch you actually deploy to. If it does not, fix it and say which you changed.
4. Add a `web` target to the root `Makefile`: `make deploy-web`.
5. After deploying, verify from a clean browser: the live URL loads, `/supervisor?demo=1` renders, `/api/health` answers, and the browser console has no CORS errors. Paste the live URL and a screenshot.

Set `ExplainBackend=deterministic` for the demo deployment so no screen can depend on a Bedrock cold start. Say so in the README — the deterministic path is a feature, not a limitation.

=== COPY ===

---

## PROMPT P4 — The entitlement honesty fix

> This one is about credibility, and it is the finding I most want you to read.

**The problem.** `corpus/entitlements/cess_fund.json` is `{"entitlements": []}`. Your obligations file has 8 real cited clauses; your entitlements file has none. So the claim "₹1,02,000 documented for 34 workers" has no source behind it. Your own corpus CLI would refuse it — which is the system working correctly and telling you something.

Separately: `corpus/invoked_stage.json` records Stage III invoked 16 Jan 2026 and **revoked 22 Jan 2026**, with `lifecycle: "revoked"` and a note saying it is replay-only and not currently in force. That is admirable honesty, and it means **your demo is a replay of a real dated invocation, not a live halt.** Frame it that way and it is a strength; imply it is live and a judge who reads the repo catches you.

=== COPY ===

Two honesty fixes in the corpus and the UI. Do not invent a citation for either.

**1. Entitlements.** `corpus/entitlements/cess_fund.json` has zero entries, so nothing on screen may claim a rupee amount. Choose one path and tell me which:

- *(Preferred, ~30 min)* Add 2–3 entitlement clauses **only if** you can cite verbatim text, with page number, from a document you ingest and hash through `make corpus ARGS="ingest …"` — a BoCW Act provision or a state welfare-board notification on relief for construction workers during a work stoppage. Cite the *existence of the entitlement and the mechanism*, not an amount, unless an amount is literally in the text.
- *(Fallback, ~10 min)* Leave entitlements empty and change the headline metric to things you can already evidence: **`34 displaced days documented · 34/34 acknowledged · 8 obligations cited`**, plus a per-worker "claim readiness" checklist (registration number, bank details, parchi serial). The parchi then says *what happened and what to take to the welfare board*, not *what you will be paid*.

Either way, remove every hardcoded rupee figure from the UI and from `lib/demo-seed.ts`. Search for `₹` and report each hit.

**2. Replay framing.** The invoked stage in our corpus was revoked on 22 Jan 2026. Every screen showing it must say so in words, not just in a field. Add a persistent provenance line on the supervisor and parchi screens, in this shape:

> `Stage III · invoked by CAQM order 16 Jan 2026 · revoked 22 Jan 2026 · replaying a cited invocation · sha256 <prefix>`

Give it `--accent`, not `--danger`, and make "replaying a cited invocation" plain text a non-technical reader understands. If a live reading from `/api/reading/latest` is available, show it beside this line clearly labelled as an observation, and state explicitly that an observation does not invoke a stage — which is already a guarantee your resolver enforces. Surface that guarantee rather than hiding it.

=== COPY ===

---

## PROMPT P5 — Repo hygiene and docs truth-up

=== COPY ===

Clean the repository for judging. Make exactly these changes and show me the diff.

**Delete from the repo** (keep local copies where noted):
- `CUsersclashAppDataLocalTempaadesh-supervisor.json` — 43 KB of scratch at the repo root with a flattened Windows temp path as a filename.
- `web/audit.json`, `web/package-check.json`, `web/screenshot.mjs` — scratch artifacts.
- `corpus/incoming_sources/` — raw downloads with GUID filenames. The curated, hashed copies already live in `corpus/sources/`. Confirm `make verify` still passes after removal, then add the directory to `.gitignore`.
- **`docs/research/`** — move it out of the repo entirely. **Keep your local copy.** It contains hackathon strategy, a judge-scoring model and competitive analysis of other teams; in a public repo it undermines the "a problem we actually saw" framing that criterion one rewards.

**Rename:** `docs/superpowers/` → `docs/design/`, and keep the specs and plans. They are legitimate design records; the directory name is the only problem.

**Add to `.gitignore`:** `corpus/incoming_sources/`, `web/out/`, `*.tmp.json`, and a root-level glob catching `CUsers*`.

**Truth-up `infra/aws/DEPLOYMENT_SUMMARY.md`.** It currently contradicts the template. Regenerate every count by reading `infra/aws/template.yaml` and verify these corrections: **6** DynamoDB tables, not 4 (Parchis, Operational, StandingOrders, TriggerRuns, Readings, Sites); **9** Lambda functions, not 11; **1** EventBridge rule, not 2; and **no OpenSearch domain exists in the template** — either remove the claim or mark it explicitly as not deployed. Any resource named in the doc must appear in the template, and vice versa.

**Remove the unused dependency.** `@phosphor-icons/react` is installed and `next.config.mjs` tunes `optimizePackageImports` for it, but every icon in `components/ui.tsx` is a hand-rolled SVG. Either adopt Phosphor for the icons or drop the package and the `optimizePackageImports` entry. Pick one and tell me which.

**Fix the stale comment** in `web/tailwind.config.ts`. It claims tokens live in `globals.css` as `@theme inline` — only true once P1 has landed. Make the comment match reality.

Finally: `make test && make verify && make verify-tamper` must all still pass. Paste the output.

=== COPY ===

---

## PROMPT P6 — Make the UI visible without cloning

=== COPY ===

CampusEvac won Best UI partly because a judge could see their interface without running anything: eight captioned screenshots committed to the repo and a Mermaid architecture diagram rendered inline in the README. Our README is 22 KB of prose with zero images. Fix that.

1. With the dev server running in demo mode, capture screenshots at 1440×900 and 390×844 of: the home flow, the supervisor console showing the invoked stage and obligations, a worker parchi in Hindi, the Cedar denial panel, the verification output including the tamper failure, and the evidence trail. Save to `docs/images/` as WebP where it keeps them under ~250 KB each.
2. Add an **Interface** section near the top of `README.md` — above the architecture prose, because it is what a judge scrolling for ten seconds will actually look at — with each image captioned in one sentence describing what the screen *does*.
3. Replace the ASCII flow diagram around line 109 with a **Mermaid** `flowchart LR` that GitHub renders natively, showing: CAQM source → hash + index → verifier → resolver → Cedar → Standing Order (Step Functions) → parchi → acknowledgement → sealed record, with the AWS services named on the relevant edges. Keep the ASCII version below it in a collapsed `<details>` block if you like it.
4. Add `web/app/opengraph-image.tsx` generating a 1200×630 card using our tokens and IBM Plex: the product name, the one-line pitch, and the live URL. Right now the submitted link previews as a blank card.
5. Add a **Status** section stating plainly what works end to end, what is seeded in demo mode, and what is not built. Model it on CampusEvac's: *"The core loop — lobby, sync, drill, verification, report — is fully working end to end."* Honest scoping reads as confidence.
6. Put the live URL, the demo-mode URL and the YouTube link in the first ten lines of the README.

=== COPY ===

---

## 4. Submission-day checklist

Freeze code at **11:00 IST**. Then:

- [ ] `make test` · `make verify` · `make verify-tamper` all pass on a clean clone
- [ ] Live URL opens in a signed-out incognito window and reaches supervisor + parchi + Cedar denial + verify with no login
- [ ] Demo banner visible wherever data is seeded; replay framing visible wherever the revoked Stage III invocation is shown
- [ ] No `₹` figure anywhere without a citation behind it
- [ ] `docs/research/` gone from the repo; junk files gone; `DEPLOYMENT_SUMMARY.md` matches the template
- [ ] README: live URL, demo URL, YouTube link in the first ten lines; Interface screenshots; Mermaid diagram; Status section; AI-tool disclosure
- [ ] Demo video **under 2:55**, uploaded, opens in a signed-out browser
- [ ] Builder Center blog published and linked in the submission form
- [ ] **Submit by 17:00 IST** — three hours before close

**Video priority, given what you actually have:** lead with the person and the halt; show the obligation list with its verbatim quotes including the OCR artifacts; show the Cedar denial as a designed panel; then run `make verify` and `make verify-tamper` on camera and let the tamper check *fail*. That last beat is the strongest thirty seconds in your submission and no First Commit winner had an equivalent. Say the replay framing out loud — "CAQM invoked this on 16 January and revoked it on the 22nd; we are replaying a cited invocation" — because volunteering that is exactly the honesty the organizers said reads as competence.

**What not to do with your last hours:** do not refactor the core, do not add a tenth AWS service, do not attempt Hindi copy you cannot verify, and do not start the second entity type. The engine already scores. Finish the window.
