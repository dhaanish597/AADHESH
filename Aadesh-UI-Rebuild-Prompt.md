# Aadesh — UI Rebuild Prompt & Resource Pack

**How to use this file.** Copy everything between the two `=== COPY ===` markers into your coding agent (Claude Code, Cursor, Windsurf) with your repo open. It is written to be pasted whole. Part 2 at the bottom is for you, not the agent — read it after you paste.

**Why your UI reads as a docs website.** Legal and compliance content renders, by default, as documentation: headings, paragraphs, a table of clauses. Tailwind's defaults and shadcn's defaults then push you further that way — `rounded-lg border bg-card p-6 shadow-sm` on a grey-50 background with Inter is *the* 2026 default look, and judges saw it two hundred times at First Commit. The fix is not "prettier cards." The fix is to stop building a document and build an **instrument**: something that shows one unmistakable state, issues an order, and hands over a physical-feeling artifact.

---

## What the Best UI winner actually did (verified from their repo, 9 Oct 2026)

This is evidence, not opinion. CampusEvac won Best UI and ₹1,00,000 at First Commit. I read their source.

**Repo:** `github.com/AfreenInnovates/campus` · **Tagline:** *"Two views. One safe Exit."* · **Live:** `main.d3skpx6qxc85hh.amplifyapp.com`

- **Stack:** Next.js 16 App Router, React 19, TypeScript, **Tailwind CSS v4** (CSS-first `@theme inline`, no JS config), **zustand**, react-three-fiber + drei + rapier + postprocessing, **@hugeicons/react** (not Lucide), AWS CDK, AppSync Events, DynamoDB, Polly, SES v2, Amplify Hosting.
- **A named, committed art direction.** Line 3 of their `globals.css` is a comment: *"CampusEvac neo-brutalism: warm paper, plum ink, hard shadows, sunset accents."* They decided the aesthetic before writing CSS, wrote it down, and never drifted.
- **Custom design tokens, zero default Tailwind colours.** Eleven named CSS variables (`--ink`, `--paper`, `--sun`, `--coral`, `--violet`, `--mint`, `--danger`, `--night`…) mapped through `@theme inline`. Nothing in their UI is `slate-500`.
- **Named component classes, not inline soup:** `.brutal-panel`, `.brutal-card`, `.brutal-slab`, `.brutal-button`, `.brutal-tag`, `.brutal-sticker`, `.brutal-ticker`, `.brutal-screen`, `.brutal-num`, `.hud-panel`, `.hud-key`.
- **Physical button feedback.** Hover lifts the button `translate(-1px,-1px)` and *grows* the hard shadow to `6px`; active presses it `translate(3px,3px)` and *shrinks* the shadow to `1px`. The button behaves like a real object.
- **Depth from parallax and moving shadows, never blur.** JS writes `--pointer-x`/`--pointer-y`/`--tilt-x` once per frame; CSS consumes them. The offset shadow swings *opposite* the tilt so cards read as lifting off the page.
- **`prefers-reduced-motion` honoured in three separate places.** Scroll reveals use `.reveal` + `.stagger` with `nth-child` delays in pure CSS.
- **Performance reasoning in the comments.** *"backdrop-filter over a live WebGL canvas is re-evaluated every frame, so widening it would cost real FPS"* — and on coarse pointers they drop the blur entirely.
- **Phone treated as a first-class target.** `viewportFit: cover`, `interactiveWidget: "resizes-content"`, `env(safe-area-inset-*)` on every edge-anchored surface, a runtime-measured `--touch-dock-h`, `touch-action: none` on the play surface, `overscroll-behavior: none`.
- **`font-variant-numeric: tabular-nums`** on numbers, and `-webkit-text-stroke` outline numerals as a display device.
- **Polly ran at *build* time**, not request time: `scripts/synth-voice.mts`, output committed to `public/voice/` with content-hashed filenames and a `manifest.json`. The demo never waits on an API.
- **The README is part of the submission.** Sections: The problem / What it does / Who it's for / How it works / Tech stack / **Mermaid architecture diagram** / Impact / Status / **8 captioned screenshots**.

**The transferable lesson:** they won Best UI for *craft and intent*, not for being decorative. Commit to a named aesthetic, build real tokens, make interactive things feel physical, respect the phone and reduced motion, and show your UI in the README so a judge sees it without cloning.

**Do not copy neo-brutalism.** It's taken, it's now the obvious move for anyone who studied the winners, and hard-shadow playfulness is wrong for a tool that stops work and documents wages. You need a different, equally committed direction — specified below.

---

=== COPY ===

You are my senior product designer and front-end engineer. We are 2 days into a 4-day hackathon (Environmental Hacks, WeMakeDevs × AWS). Submissions close **Sunday 11 October, 8:00 PM IST**. Judging criteria include "Design and usability," tested as: *"Would someone who isn't on your team know what to do with it?"* There is no live demo — judges see a 3-minute video, the repo, and a live URL.

Our current UI reads like a documentation website. Your job is to rebuild it as an operational instrument. Work through this brief in order and do not skip the skills step.

## 0. Use your skills first, then the web

Before writing any code, load guidance. Try your skill tool with these names, in this order:

1. `frontend-design` — distinctive, intentional visual design; avoiding templated defaults. **This is the most important one; it targets exactly our problem.**
2. `typography-guide` — typeface pairing, type scales, CSS typography systems
3. `color-palette` — palette construction with WCAG contrast checking and CSS variable export
4. `design-system` — component tokens and a living style guide
5. `ui-mockup` — high-fidelity HTML/CSS mockups, for iterating on a screen before committing it
6. `humanizer` — run all user-facing microcopy through this so nothing reads as AI-written
7. `webapp-testing` — Playwright for the screenshot self-review loop in section 8

If a skill is unavailable, say so explicitly and fall back to fetching these instead, then summarise what you took from each before coding:

- Tailwind v4 CSS-first theming: https://tailwindcss.com/docs/theme
- Tailwind v4 `@theme` + custom colours: https://tailwindcss.com/docs/colors
- next/font (self-hosted Google fonts, zero layout shift): https://nextjs.org/docs/app/api-reference/components/font
- IBM Plex Sans Devanagari specimen: https://fonts.google.com/specimen/IBM+Plex+Sans+Devanagari
- IBM Plex Sans / Mono: https://fonts.google.com/specimen/IBM+Plex+Sans
- Radix UI primitives (accessible, unstyled — style them yourself): https://www.radix-ui.com/primitives/docs/overview/introduction
- Phosphor Icons: https://phosphoricons.com — or Hugeicons: https://hugeicons.com
- Motion for React: https://motion.dev/docs/react
- APCA contrast (better than WCAG 2 for dark UI): https://www.myndex.com/APCA/
- WebAIM contrast checker: https://webaim.org/resources/contrastchecker/
- `qrcode.react`: https://www.npmjs.com/package/qrcode.react
- Safe-area insets / mobile viewport: https://developer.mozilla.org/en-US/docs/Web/CSS/env
- `prefers-reduced-motion`: https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion
- Mermaid (for the README architecture diagram): https://mermaid.js.org/syntax/flowchart.html
- next-intl, if we need real i18n routing: https://next-intl.dev

**Explicitly do NOT install shadcn/ui's default theme.** You may use Radix primitives underneath, but every token, radius, shadow and colour must be ours. If you catch yourself writing `bg-card`, `text-muted-foreground`, `rounded-lg border shadow-sm`, or any `slate-*`/`zinc-*`/`gray-*` utility, stop and use our tokens.

## 1. The product, so your design decisions have a reason

**Aadesh** (आदेश — *order, directive*). Delhi-NCR's Graded Response Action Plan (GRAP) is binding law: when air quality crosses a threshold, the Commission for Air Quality Management invokes a stage and construction work legally stops. Aadesh reads the live station reading and the officially invoked stage, resolves them against one construction site's profile, issues cited halt obligations, and produces a claim-ready **parchi** (पर्ची — a slip) for every displaced daily-wage worker, acknowledged by that worker, provable afterwards. Worker compensation comes from the statutory labour cess fund, not the contractor's pocket.

**Two users, two different bodies, two different surfaces:**

| | Supervisor | Worker |
|---|---|---|
| Who | Site supervisor / labour contractor | Daily-wage construction worker |
| Device | Laptop or tablet, on a site office desk | Their own phone, outdoors, bright sun, one hand |
| Language | English | **Hindi first** |
| Needs | One unmistakable state, then one deliberate action | One slip, one number, one button |
| Emotional register | Operational, calm, authoritative | Reassuring, dignified, concrete |

**The pitch, which the UI must make visible in five seconds:** *The shutdown is coming anyway. Aadesh makes sure your 34 men get the money the law already owes them — so they're still here on the day the ban lifts.*

**The two numbers that matter.** Not AQI. These:
- `₹1,02,000 entitlement documented`
- `34 / 34 workers acknowledged`

## 2. The art direction — commit to this and write it into globals.css

**Named direction: "Field Instrument."** Industrial safety signage meets Indian municipal paperwork. Two registers in one brand.

- The **supervisor console** is a dark operational instrument: cool concrete greys, hard edges, tabular numerals, safety amber and halt red used strictly as *state* and never as decoration. Think permit-to-work board, railway signal panel, lockout-tagout tag. Authority through restraint and precision, not through colour.
- The **worker parchi** is a warm paper artifact: cream stock, stamped ink, a serial number, a perforated edge, a QR. Think ration slip, weighbridge receipt, rubber-stamped government chit. It should feel like something you could put in your shirt pocket.

They share type, spacing and numerals, so they are obviously the same product. They differ in material, so they are obviously for different people.

**Forbidden:** neo-brutalism (taken by CampusEvac), glassmorphism, purple-to-blue gradient heroes, soft pastel "friendly SaaS," emoji as icons, dark-mode-with-neon-accents, anything that looks like a crypto dashboard.

Write the direction as a comment at the top of `globals.css`, the way CampusEvac did, and hold yourself to it.

### Tokens — start from this and refine with the `color-palette` skill

Use Tailwind v4 CSS-first theming. Verify every text/background pair with APCA or WebAIM before you commit it.

```css
/* Aadesh "Field Instrument": concrete console, stamped-paper parchi.
   Amber and red are STATE, never decoration. */
:root {
  /* console surfaces — cool, not purple */
  --concrete-900: #13161a;
  --concrete-800: #1b1f25;
  --concrete-700: #252a32;
  --concrete-600: #343a44;
  --rule:         #3f4651;

  /* console text */
  --steel-100: #eef1f4;
  --steel-300: #c2c9d2;
  --steel-500: #8b949e;

  /* state — the only saturated colours in the console */
  --halt:    #e5332a;  /* work stopped */
  --caution: #ffb000;  /* stage invoked / standing order armed */
  --clear:   #1f9d55;  /* permitted / acknowledged */
  --evidence:#4a7cf0;  /* provenance, hashes, citations */

  /* parchi — warm paper artifact */
  --paper:      #f6f1e4;
  --paper-edge: #e3dac4;
  --stamp-ink:  #1a1a18;
  --stamp-red:  #b3261e;
  --stamp-blue: #1f3a93;
}

@theme inline {
  --color-concrete-900: var(--concrete-900);
  --color-concrete-800: var(--concrete-800);
  --color-concrete-700: var(--concrete-700);
  --color-concrete-600: var(--concrete-600);
  --color-rule: var(--rule);
  --color-steel-100: var(--steel-100);
  --color-steel-300: var(--steel-300);
  --color-steel-500: var(--steel-500);
  --color-halt: var(--halt);
  --color-caution: var(--caution);
  --color-clear: var(--clear);
  --color-evidence: var(--evidence);
  --color-paper: var(--paper);
  --color-paper-edge: var(--paper-edge);
  --color-stamp-ink: var(--stamp-ink);
  --color-stamp-red: var(--stamp-red);
  --color-stamp-blue: var(--stamp-blue);

  --font-sans: var(--font-plex-sans);
  --font-deva: var(--font-plex-deva);
  --font-mono: var(--font-plex-mono);
}
```

### Typography — this choice solves our Hindi problem

Load all three via `next/font/google`:

- **IBM Plex Sans** — Latin UI. Utilitarian, engineered, not Inter.
- **IBM Plex Sans Devanagari** — Hindi. Same type family, metrically matched to Plex Sans. This is the whole reason to pick Plex: our bilingual UI will look designed rather than patched.
- **IBM Plex Mono** — serials, hashes, clause ids, timestamps, rupee amounts.

Rules:
- Every number, hash, clause id, serial and timestamp uses mono with `font-variant-numeric: tabular-nums`. Numbers must never reflow as they tick.
- Devanagari needs more vertical room than Latin — matras sit above and below. Set `line-height: 1.65` minimum on `.font-deva`, versus 1.45 for Latin. Test with a real string: `आपका काम आज बंद है` and `₹3,000 का मुआवज़ा आपका हक़ है`.
- Operational micro-labels: uppercase, `font-weight: 600`, `letter-spacing: 0.14em`, `font-size: 0.6875rem`. Use these for field names, not for content.
- The parchi is read outdoors at arm's length: body text minimum **18px**, the status line **32px+**, the acknowledge button at least **56px tall**.
- One display size per screen. If two things are both huge, neither is.

## 3. Screens to build, in priority order

Build 1–4 completely before starting 5. If time runs out, 5–7 are cuttable; 1–4 are not.

**1. `/` — the first five seconds.** A judge lands here, not logged in, and must understand the product before scrolling. Required: the one-line pitch as the largest text on the page; the live stage state with its provenance line; and two unmistakable entry buttons — **"Open the site console"** and **"See a worker's parchi"** — that drop straight into a seeded demo. **No signup wall, no email gate, no "Get started" that leads to a form.** Judges will not create an account. If auth exists, add a visible `Demo mode` affordance that bypasses it.

**2. `/site` — the supervisor console.** Top to bottom:
   - **State banner**, full-bleed, the single most prominent element: `WORK PERMITTED` on concrete, or `WORK STOPPED` on halt red. Unambiguous from across a room. This is the squint-test anchor.
   - **Provenance line**, one line, mono, small, directly under the banner: `Stage III · invoked by CAQM order 6 Oct · sha256 a3f91c… · Rohini station 412 at 09:00 IST · fresh`. When the invoked stage and the AQI-implied stage disagree, this line turns `--caution` and says so in words. Never show two competing stage widgets.
   - **The two hero numbers** (₹ documented, N/N acknowledged) in mono, large, tabular, with a short label above in micro-caps.
   - **Obligation rows.** Not a table. Each row: status glyph, the obligation in plain language, the clause id in mono, and a disclosure that expands to the verbatim quote with its page number. The *action* is the primary text; the legal quote is secondary and must never share its visual weight.
   - **Standing Order card**: armed or not, its scope, its expiry. Armed state carries `--caution`.
   - **Crew board**: 34 worker tiles in a grid, each showing acknowledgement state. This grid filling up *is* the demo climax — design it to be watched.
   - **`ISSUE HALT`**: a deliberate, consequential action. Require hold-to-confirm or typed confirmation. Never a plain button that fires on click.

**3. `/handoff` — the QR wall.** Full-screen grid of QR codes, one per worker, each labelled with name and parchi serial. Designed to be held up or projected and scanned from a metre away. High contrast, generous quiet zone, no decoration.

**4. `/parchi/[id]` — the worker's slip.** Phone-first, Hindi-first, one card, no navigation chrome. It must look like a physical object: cream stock, a visible serial, a stamped header, a perforation or deckle edge, the QR reproduced small. Content order: what happened (`आज काम बंद है`), what you are owed with the clause behind it, a single large **acknowledge** button in the thumb zone, then the readiness checklist (registration number, bank details) as checkboxes. After acknowledgement the card gets a stamp — a visible, satisfying state change. English is available via a toggle but **Hindi is the default**.

**5. `/assist/[token]` — the facilitator's redacted view.** Show the redaction. Render blocked fields as `████████` with a one-line explanation of which policy redacted them. An invisible authorization decision scores nothing; a visible one is a design feature.

**6. The Cedar denial state.** When a supervisor tries to acknowledge on a worker's behalf, do **not** fire a toast. Render a deliberate denial panel: the policy id (`no-proxy-acknowledgement`), the human sentence (*"A supervisor cannot acknowledge a halt on a worker's behalf."*), and the only legitimate next step. This is a scripted beat in our demo video — design it to be filmed.

**7. `/evidence` — the provenance ledger.** The hashed CAQM orders, each with its sha256, fetch time and page count, plus the output of `make verify` and `make verify --tamper` rendered as terminal output in mono. Design this as a ledger or register, not as a docs page.

## 4. Every state must be designed

For each screen above, build and screenshot: **default**, **empty** (no standing order armed, no parchis yet), **loading** (skeletons that match final layout — never a centred spinner), **stale** (station reading older than one hour, with the age stated), **replay mode** (a persistent, honest banner reading `REPLAY — recorded readings` whenever we are not live), **denied** (Cedar), **error** (upstream API down, with what still works), and **success** (parchi sealed). Empty and stale states are where "docs website" hides — give them as much care as the happy path.

## 5. Interaction and motion

- Motion is for state change and causality only. Nothing animates on page load except a single staggered reveal of the obligation rows.
- The crew board tiles flip to acknowledged with a short, crisp transition (≤220ms, `cubic-bezier(0.22, 0.8, 0.24, 1)`). The rupee counter counts up over ~800ms with tabular numerals so nothing shifts.
- The halt banner change is instant, not eased. Consequential state should snap.
- `ISSUE HALT` gives physical feedback on press, in the spirit of CampusEvac's buttons: a small transform and a shadow that responds.
- Honour `prefers-reduced-motion` in a single global block and verify it.
- Full keyboard reachability. Visible focus rings in `--evidence`. No focus trap anywhere.

## 6. Phone discipline, copied from the winner

`viewport` with `viewportFit: "cover"`. `env(safe-area-inset-*)` on every edge-anchored element. `overscroll-behavior: none`. `-webkit-tap-highlight-color: transparent`. Minimum 44×44px touch targets, 56px for the acknowledge button. The parchi must be fully usable one-handed at 390×844 with no horizontal scroll and no pinch-zoom required.

## 7. Copy rules

Every string ships final — no lorem, no placeholder, no `TODO`. Run all of it through the `humanizer` skill. Specifically:

- Verbs, not nouns: `Issue halt`, not `Halt management`.
- Never claim official status. Phrase as *"this clause applies to your site"*, never *"you are permitted"* or *"you will be paid"*.
- Put the disclaimer in the footer of every screen and on the parchi: *not a government application, not legal advice; we do not file claims.*
- No marketing sections. No "Features," no "How it works," no "About us," no testimonial blocks. This is a tool, not a landing page for a startup.
- Hindi must be natural Hindi, not translated English. If you are unsure of a phrasing, flag it for me rather than guessing.

## 8. Self-review loop before you tell me you're done

1. Run the dev server. Screenshot every route in section 3, in every state in section 4, at **390×844** and **1440×900**.
2. **Squint test:** blur each screenshot heavily. The single most prominent thing on `/site` must be the state banner; on `/parchi` the status line and the acknowledge button. If the AQI number, a nav bar, or a block of clause text is winning, the hierarchy is wrong — fix it and re-shoot.
3. **Five-second test:** from the `/` screenshot alone, can someone state who this is for and what it does? If not, rewrite the hero.
4. **Docs-website test:** does any screen consist mainly of a centred column of headings and paragraphs? If yes, that screen has failed the brief.
5. **Default-look test:** grep the diff for `slate-`, `zinc-`, `gray-`, `bg-card`, `text-muted-foreground`, `rounded-lg`, `shadow-sm`. Each hit is a bug.
6. Check every text/background pair against APCA or WebAIM. Report any failures rather than hiding them.
7. Re-shoot with `prefers-reduced-motion: reduce` forced on and confirm nothing breaks.

Then write a short self-critique: the three weakest things about the UI as it now stands, and what you would fix with two more hours.

## 9. Deliverables

- The rebuilt routes, with a documented `globals.css` carrying the named direction and the full token set.
- A small set of named component classes or components — our equivalent of CampusEvac's `.brutal-*` family. Name them for our domain: `.console-panel`, `.state-banner`, `.obligation-row`, `.parchi-card`, `.stamp`, `.serial`, `.provenance-line`, `.crew-tile`, `.denial-panel`.
- A `/styleguide` route rendering every token, type size, component and state on one page. This is both a working tool and something to screenshot for the blog.
- A custom `app/icon.svg` and `app/manifest.ts` so it installs and shares like a product, not a localhost page.
- Social card metadata (`opengraph-image`) so the submitted URL previews properly.
- **README screenshots:** commit the 390px and 1440px screenshots of the key states into the repo and embed them with captions, the way CampusEvac did with their eight images. Judges should see our UI without cloning anything.
- A line in the README naming the design direction and the type choice, with one sentence on why IBM Plex Sans Devanagari was chosen for the bilingual pairing.

## 10. Constraints

Next.js App Router, TypeScript, Tailwind v4 CSS-first, deployed on AWS Amplify Hosting. No UI kit's default theme. Keep the dependency list short — Radix primitives, one icon set, `qrcode.react`, and Motion only if it earns its place. Do not touch the rules engine, the Cedar policies, the ingest Lambda, or anything under our evidence/verification code. If a change you want requires touching backend logic, stop and ask me first.

Start by stating the design direction back to me in three sentences and listing the files you intend to change. Then build `/site` and `/parchi` first and show me screenshots before going further.

=== COPY ===

---

# Part 2 — for you, not the agent

**Paste order matters.** Give it the prompt, let it state the direction back and list files, sanity-check that, *then* let it build. If it starts by installing shadcn's default theme or reaches for a purple gradient, stop it immediately — those two moves undo the whole brief.

**Build `/site` and `/parchi` first, screenshot both, and judge them yourself with the squint test** before letting it touch the landing page. The landing page is the easiest place to waste three hours and the least load-bearing for the "would someone outside your team know what to do with it" criterion.

**The single highest-value visual in your whole submission** is the crew board filling up from `0/34` to `34/34` while the rupee counter climbs. That is your "nobody got woken up" moment. Tell the agent to make that one component excellent even if everything else is merely clean.

**Two things to steal from CampusEvac that cost almost nothing:**

The build-time asset trick. They ran Polly in `devDependencies` and committed the audio with content-hashed filenames so the demo never waits on an API. Your equivalent: pre-generate the Hindi explanation strings for your seeded demo scenario at build time, commit them as a fixture, and have the Bedrock path fall back to the fixture. Your video then cannot be killed by a cold start or a throttle.

The README screenshots. Eight captioned PNGs, committed. It costs ten minutes on Sunday and it means a judge who never opens your live URL still sees your interface. Most teams skip it.

**One honest caution.** You have roughly 48 hours and a submission that already needs a video, a README, a blog and a clean-machine install test. A UI rebuild of this scope is a full day for one person. Make sure whoever owns the frontend owns *only* the frontend between now and Saturday night, and that the cut ladder from the strategy document still holds — the worker parchi stays above Hindi, above the Bedrock explanation layer, above Cognito. A beautiful console with no working parchi scores worse than a plain one with a working parchi.

**If you want, I can next:** write the actual `globals.css` with every token and component class filled in and contrast-checked; draft the `/styleguide` route; or write the README skeleton with the Mermaid diagram and screenshot slots already laid out. Any of those saves the agent a pass.
