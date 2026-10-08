# Environmental Hacks 2026 — Verified Intelligence Report & Winning Plan

**Version 2.0** — rebuilt after adversarial review. See the changelog below for what moved and why.
**Prepared for:** Team Garden (code B3RJZS) — 3–4 builders, online track, full-stack capable
**Event:** Environmental Hacks, Event 02 of 6, Bharat Builds Tour (WeMakeDevs × AWS)
**Window:** Thu 8 Oct – Sun 11 Oct 2026
**Document date:** 8 October 2026 — Day 1. If you read nothing else, read Part 0 and Part 6.

---

## Changelog from v1

| What changed | Why |
|---|---|
| **The operator flipped.** The site supervisor now has a self-interested reason to use this: crew retention during a shutdown that is happening to him anyway | v1's fatal flaw — the tool manufactured liability for the person installing it. Nobody adopts that |
| **The money moved.** Worker compensation comes from the statutory labour cess fund, not from the employer's pocket | Removes the incentive conflict entirely. Telling a worker what they're owed costs the contractor nothing |
| **The headline number is rupees, not receipts** | "₹X documented for 34 workers" is Beacon's "nobody got woken up." "Receipts written" is a log line |
| **Corpus cut from 24–30 obligations to 10–14, one entity type, one source order** | The corpus was a research problem on the critical path, and amendment reconciliation could have made the citations confidently wrong |
| **SMS replaced by QR handoff** | Dodges the Indian SNS SMS problem with something *more* plausible, not less — and it demos beautifully |
| **`make verify` must be shown failing** | A hash check over files you never touch always passes and proves nothing |
| **Cedar now has a real job** — three principals with genuinely different visibility, using the organizers' own opt-in-assist pattern | v1's Cedar was a three-line conditional wearing a costume |
| **Explicit ranked cut ladder** | The worker side was structurally last to be built and therefore first to be cut. It is now protected above everything |
| **New Part 12: the failure analysis, with mitigations** | Shipping a project with a written account of how it could fail is itself a credibility signal |

Parts 1–5 are unchanged and still correct.

---

## PART 0 — The one-page decision

Build in **Track 01: Air**. Not an air quality monitor — an engine for the law that air quality already triggers, and for the people that law displaces.

Delhi-NCR's Graded Response Action Plan (GRAP) is real, published, staged, binding law. At Stage III and IV, construction stops across the capital. It happens every winter. **The work stopping is not the open question.** The open question is whether the daily-wage workers who lose those days ever see the compensation they are statutorily entitled to — paid not by the contractor but from the labour cess fund, which is famously under-disbursed — and whether the contractor still has a crew when the ban lifts.

**Aadesh** reads live station AQI and the officially invoked GRAP stage, resolves them against one site's profile, issues cited halt obligations, and produces a claim-ready **parchi** for every worker, acknowledged by that worker, provable afterwards.

The one-sentence pitch:

> The shutdown is coming anyway. Aadesh makes sure your 34 men get the money the law already owes them — so they're still here on the day the ban lifts.

That sentence is why this version works and v1 did not. It gives the person holding the phone a reason to hold it.

---

## PART 1 — Verified event facts, and seven corrections to your existing research

Everything below was read directly off the live WeMakeDevs site and the organizers' own blog posts on 7–8 October 2026. Where your two PDFs disagree with the source, the source wins.

### 1.1 Confirmed structure

| Item | Verified detail |
|---|---|
| Dates | Online Thu 8 – Sun 11 Oct 2026, anywhere in India |
| In-person | Optional build day, DTU Delhi, Sat 10 Oct, 8 AM – 8 PM. Separate Luma application. Explicitly stated to add **nothing** to your score |
| Teams | 1–4. University students in India, 18+. One submission per team, one team per person |
| Tracks | Air · Heat and Water · Waste and Energy. Each judged **only against its own track** |
| Track prize | ₹2,00,000 cash **+ $2,000** AWS credits, one winner **per track** (three winners total) |
| Runners-up | 4 teams across all tracks, $1,000 AWS credits each. Automatic entry, nothing extra to do |
| Blogs | Top 5 blogs → AirPods, for **5 individuals**. Must be published on AWS Builder Center and linked in the submission |
| Amazon | Up to 10 fast-track interviews across all tracks. Ceiling, not a promise. Decided **separately** from prizes, by different people. Pre-final year (2028) and final year (2027) only |
| Eligibility gate | AWS Builder Center profile with university enrollment verified via SheerID. Pending verification does not block submission or judging, but does block the interview and the rewards |
| AWS requirement | Project must use **at least one AWS open-source tool OR be deployed on AWS**. Both paths scored identically |
| Submission | Public repo + YouTube video **under 3:00** (public or unlisted) + short writeup. No live demo, no call |
| Registered | 5,956 at time of capture; expect materially higher by Thursday |

### 1.2 The official judging criteria — and a warning

Five criteria, in the order the site lists them: **Idea and Impact**, **Built on AWS**, **Design and usability**, **The execution**, **The demo video**.

**There are no published weights.** The 30 / 25 / 20 / 15 / 10 split in your strategy PDF is invented. Do not optimise against numbers that do not exist — in particular, do not under-invest in Design and usability on the assumption it is worth only 15%. The site's own phrasing for it is the sharpest test in the whole rubric: *"Would someone who isn't on your team know what to do with it?"*

The site also explicitly flattens the Build It / Ship It distinction: *"We judge what you built, not what you spent."*

### 1.3 Seven corrections to your uploaded research

1. **Submission deadline.** Your PDF says the deadline is **8:00 AM IST on 11 Oct**. That is when the form *opens*. The organizers' Delhi blog states: *"Online submissions stay open until Sunday 11 October, 8:00 PM IST."* The schedule page still says exact hours are being finalised. **Treat the window as 8 AM – 8 PM Sunday, and confirm on the schedule page and Discord on Thursday.** Planning around 8 AM would have cost you the most valuable twelve hours of the weekend.

2. **FloodRoute was not a winner.** Your PDF lists it as a "high-ranking finalist" with winning factors. It is not on the winners page. It appears on the *All projects* page as one of 1,180 submissions, with no award. Treat it instead as a warning: a flood-routing project has already been built in this exact ecosystem.

3. **Beacon Night Shift did not use Cedar.** Your PDF puts Cedar in its stack. The winner's own Builder Center write-up lists Bedrock, Step Functions, Transcribe, Polly, DynamoDB, Lambda and CloudWatch. Its guardrail was a hand-built command allowlist plus literal spoken consent, not a policy engine.

4. **Prize shape has changed since First Commit.** First Commit was 1st / 2nd / 3rd (₹2L / ₹1.5L / ₹1L) plus Best UI. Environmental Hacks is **three equal, parallel ₹2L track winners**. This is a structural change: track selection is now a genuine strategic lever, because you are not competing against the whole field, only against your track.

5. **"Build It" and "Ship It" are no longer tracks.** The FAQ literally asks "What happened to Build It and Ship It?" They are now two *ways to build*, both eligible, both equally scored.

6. **Typo worth fixing in your own notes:** the track prize is **$2,000** in AWS credits, not "$2,00,000."

7. **The mentors are cloud engineers, not climate people.** The 20 named AWS mentors are cloud support engineers, cloud/database engineers, technical account managers, professional services consultants, one senior AI/ML consultant, and marketing and education leads. Nobody on that list is an atmospheric scientist. **Implication:** a plausible-looking but fake architecture will be caught instantly; a correct, well-reasoned use of services will be genuinely appreciated; and nobody will be impressed by climate jargon.

---

## PART 2 — What the organizers have explicitly told you they want

The announcement blog by Aayush Sharma (COO, WeMakeDevs) is the single most important document for this hackathon, and most teams will skim it. It is close to a marking scheme written in plain English.

**The thesis, in their words:** *"Most environmental problems are already being measured... What usually goes missing is the last step, the one where a number turns into something a person can act on this week."*

**The anti-pattern, named and pre-emptively penalised:** *"Environment hackathons produce a lot of dashboards. Someone finds a rainfall or air quality feed, plots it on a map, colours the concerning parts red, and ships it... a map mostly tells people something they can already sense."*

**The test they will apply:** *"The projects that stand out go one step past that and answer what somebody should do differently because of it."* And then, pointedly: *"Our first judging criterion is written in exactly that shape... The second half is where most projects lose points."*

**The instruction nobody follows:** *"Write down one sentence describing the person you are building for, not the technology you plan to use."*

**The credibility rule:** *"Check what the data actually means before you build on it, because a station that reports hourly and a satellite pass that happens twice a day are very different things to promise a user. Say plainly in your demo where your numbers come from and how fresh they are. That honesty reads as competence, not as a weakness."*

### 2.1 The trap hidden in that same blog

The blog offers six example ideas "if you are stuck on Thursday morning." Roughly six thousand registrants have read it. **These six are now the most dangerous ideas at the hackathon:**

- Air: a morning message to a school deciding whether PE and assembly move indoors
- Air: an exposure planner telling a delivery rider the two cleanest hours on their route
- Heat & Water: a tanker predictor for one housing society
- Heat & Water: a monsoon commute helper that knows which route floods first
- Waste & Energy: a bin-photo segregation checker with a building score
- Waste & Energy: a rooftop solar payback estimator by pincode

Every team that arrives without an idea will pick from that list. Expect each of those to be submitted dozens of times. The blog is a gift and a minefield in the same breath: use its *principles*, avoid its *examples*.

### 2.2 Agents are table stakes, not a differentiator

Kunal's First Commit recap, published 7 October: *"The theme was open, and a lot of what came back was agents."* And on the Bangalore build day: *"AWS mentors ran a hands-on workshop on building AI agents with the Strands Agents SDK, and you could see it in the submissions. Agents were everywhere, including at the top of the board."*

The DTU build day runs **the same Strands Agents workshop again**, 11:00–12:30 on Saturday, for a room of roughly a thousand builders.

**Conclusion: "we built a Strands agent on Bedrock" is the median submission of this hackathon.** It earns you the Built on AWS tick and zero distinctiveness. What differentiates is not that you used an agent — it is **what you refused to let the agent decide**, and what your system does deterministically instead.

### 2.3 The organizers published the exact engineering pattern they admire

Their tutorial *How to Build a Real-Data AI Project on the AWS Open Source Stack* walks through a reference project (SchemeProof) and names five reusable techniques. This is effectively a rubric for Built on AWS and Execution:

1. **Rules as data, not as a prompt.** Conditions live in a file as `{field, operator, value, label, page, quote}`. Testable, editable in seconds, traceable to a source line.
2. **Documents you can prove.** Download the source from its official domain, verify it is the document type you expected, SHA-256 the bytes, store in S3, index the extracted pages in OpenSearch, then ship **one command** that re-proves every quote still exists in the bytes you cited.
3. **Authorization as policy.** The moment a second kind of user exists, put the rules in Cedar. `forbid` beats `permit`, and `@id` labels let you turn a denial into a human sentence.
4. **A constrained, checked model.** Decide what the model may not do, write that contract into code, validate its output against the contract, keep a deterministic answer ready for when it fails.
5. **The whole stack locally** via LocalStack and SAM, so the same code runs against AWS unchanged.

And the line that should shape your Sunday: *"Verification is a command rather than a claim... a reproducible check speaks to four of those five at once."* Plus: *"Under a four-day clock: this is the highest-return twenty minutes in the whole build. Most projects claim real data and cannot show it."*

---

## PART 3 — Previous winners, verified, and the pattern they share

### 3.1 First Commit, by the numbers

13,667 registered · 4,270 teams formed · **1,180 projects submitted** (8.6% of registrants actually shipped) · 1,400+ in the room in Bangalore · 10 fast-track interviews awarded.

### 3.2 The actual results

| Place | Project | Team | Prize | What it was |
|---|---|---|---|---|
| 1st + Ship It | **Suraksha** | StarBugs (3) | ₹2,00,000 + $3,000 | Agentic companion for an aging parent |
| 2nd + Build It | **Beacon Night Shift** | CoffeAndCode (**solo**) | ₹1,50,000 + $2,000 | On-call agent that fixes the 3 AM page |
| 3rd + Best UI | **CampusEvac** | 3 Builds (3) | ₹1,00,000 + $1,000 | Fire drill as a two-player browser game |
| Runner-up | Magpie | Voxton (4) | $1,000 | AI-native finance workspace |
| Runner-up | FreshTrace | Powerpuff Girls (4) | $1,000 | — |
| Runner-up | Expressive captions | Need Sleep (3) | $1,000 | — |
| Runner-up | Factcade | Mohammed Ali Khan (**solo**) | $1,000 | AI ops copilot for factories |

Two of seven awarded projects were solo. Team size is not the constraint; clarity is.

### 3.3 The pattern — in the judges' own words

This is the most valuable thing in this report. Kunal described each winner, and the descriptions reveal what he was actually rewarding.

**On Suraksha:** *"It is the only one of the three winners built for somebody who is not the user. The person operating the software and the person it looks after are different people, and almost every design decision gets harder once that is true, because the one who needs the help is the one least likely to be holding the phone."*

**On Beacon:** *"proposes one fix from an allowlist and dry-runs it, then waits for you to approve it out loud. Say yes to it handling that fault by itself next time, and the second time it fires nobody gets woken up."*

**On CampusEvac:** *"Neither can finish alone, which is how it ends up training the warden role that drills rarely cover."*

Strip the subject matter away and all three are the same shape:

> **Two humans with asymmetric knowledge or power, a piece of software that mediates a commitment between them, explicit consent at the boundary, and a demo moment where you can watch the outcome change.**

None of them is a dashboard. None is a single-user CRUD app. Each has a **named mechanism** you can repeat in one sentence a week later — the Sleep Contract; the operator who is not the beneficiary; the two players who cannot finish alone. That nameability is what survives a judging panel reading 300 submissions.

Also note Beacon's author on process, because it is cheap and it works: he wrote down every problem with a timestamp as he hit it (notes became both the demo script and the winning blog), and before submitting he **set the whole project up from scratch the way a judge would** — it broke in two places that never broke on his own machine.

---

## PART 4 — The competitive landscape you are entering

### 4.1 Volume model

First Commit converted 13,667 registrants into 1,180 submissions. Environmental Hacks had 5,956 registered mid-week before opening and will likely land somewhere in the 8,000–12,000 range. Applying a similar conversion, expect roughly **600–1,000 submissions, split three ways.**

Track split will not be even. My estimate:

- **Air — the largest track.** It is October, the build day is in Delhi, stubble burning is live, and AQI is the single most legible environmental number in India. But it is crowded with *one archetype*, which is the opportunity.
- **Heat and Water — mid-sized and badly timed.** Heatwaves are eight months away and the monsoon has gone. Two of its three obvious sub-topics were handed out in the blog.
- **Waste and Energy — probably the smallest**, because it has no glamorous real-time feed. Genuinely the best raw odds. Kept as the fallback in Appendix B.

### 4.2 The strategic read, stated as a bet you are consciously placing

Raw odds favour the quiet track. But a track prize does not go to the team with the best odds — it goes to the single most memorable project in that track. In Air, roughly two-thirds of submissions will be variations of the same AQI map, which means a judge arrives at your submission already numb and primed to reward anything categorically different.

**Own this consciously:** I am recommending the most crowded track on the theory that differentiating inside a saturated field beats being generic in an empty one. If Air draws 400 submissions and Waste draws 120, that is roughly a 3× harder field. The theory holds only if you are *categorically* different, not merely a better version of the same thing. Aadesh is categorically different — it never shows an AQI number as an output — but if you find yourselves drifting toward a prettier AQI tracker by Saturday, the bet has failed and you should know it.

The second argument for Air is harder to argue with: **it is the only track whose problem will be physically happening, outside the window, during judging.** Delhi's air degrades sharply across 8–11 October. A heatwave project in October has to ask the judge to imagine May.

### 4.3 Archetypes you must not build

| Archetype | Why it loses |
|---|---|
| AQI map / forecast / "red zones" dashboard | The named anti-pattern. Hundreds of these |
| Generic climate LLM chatbot | No domain value, no cloud depth, hallucination-prone |
| Waste image classifier (YOLO/ResNet on bin photos) | Suggested in the blog; adds no architectural depth |
| Rooftop solar / carbon footprint calculator | Suggested in the blog; static inputs, no urgency |
| Flood route navigation | Suggested in the blog *and* already built here (FloodRoute) |
| School AQI morning advisory | Suggested in the blog; expect dozens |
| Tanker predictor for a housing society | Suggested in the blog; expect dozens |
| Municipal officer command centre | Unverifiable persona, requires fabricated budget/asset data |
| **"GRAP stage tracker with alerts"** | **Your nearest competitor. Several teams will build this. They show the stage; you show what it costs and who gets paid** |

---

## PART 5 — Where your ThermalOps plan breaks

Your research is genuinely good — the track-scoring matrix, the anti-pattern diagnosis, the Cedar and Strands reasoning are all sound instincts, and much of that reasoning carries straight into the new plan. But the specific proposal has four problems I do not think survive a judging panel.

**1. Off-season.** Extreme heat and wet-bulb mortality are May–June phenomena. On 10 October, a demo about a heatwave is a demo about a hypothetical. Every number on screen has to be simulated or historical, and you will be narrating a situation the judge cannot feel. Meanwhile the judges in Delhi will be breathing an AQI in the 200s–300s.

**2. The persona is unverifiable, and it is the one persona judges distrust most.** "Municipal Ward Disaster Management Officer" is a role no student on your team has met, in an institution none of you can access. The organizers asked for one sentence about the person you are building for. "A ward officer at a Delhi municipal corporation" invites the question "which one, and what did they tell you?" — and you have no answer. Worse, the entire premise is that this officer *wants* automated dispatch authority, which is an assumption about institutional behaviour you cannot support.

**3. It needs data that does not exist publicly, so you must fabricate the core.** The plan's heart is a linear programme optimising water tanker allocation, misting van routing and cooling shelter activation against a ward daily emergency budget. **None of that data is public.** Tanker fleet capacity, depot locations, misting unit inventory, per-ward emergency budgets — all invented. You would be running a real optimiser over synthetic constraints and presenting the output as operational. That directly violates the organizers' data-honesty rule.

**4. The stack is the median submission.** Strands Agents + Bedrock + Step Functions + Cedar + a ward map is, after two Strands workshops for thousands of builders, the default architecture of this hackathon. Your PDF's self-assessed 96/100 assumes that stack is a differentiator. It is now the baseline.

**What survives and comes forward:** the prescriptive-over-passive thesis, Cedar as a real guardrail, the human-in-the-loop approval gate, the Beacon-style scoped temporal contract, and the clean-machine deployment test. Those are all correct. They just need to sit on a problem where the data is real and the person is reachable.

---

## PART 6 — The idea: Aadesh

> **Aadesh** (आदेश) — *order, directive*. It is what CAQM issues, and it is what the system issues.
> Three nouns carry the whole product, and you should use all three on camera:
> **Aadesh** is the system. A **Standing Order** is the rule a supervisor pre-commits to. A **Parchi** (पर्ची) is the slip each worker ends up holding — the thing a daily-wage worker's entire economic life already runs on.

### 6.1 The pitch, in one sentence

> The shutdown is coming anyway. Aadesh makes sure your 34 men get the money the law already owes them — so they're still here on the day the ban lifts.

### 6.2 The problem, precisely

GRAP — the Graded Response Action Plan, issued by the Commission for Air Quality Management for Delhi-NCR — is not an advisory. It is a staged, legally binding schedule of restrictions tied to AQI bands. At the upper stages, dust-generating construction and demolition stops across the capital. This is enforced, it bites, and it happens every winter.

Three things are broken, and **only the third is the real prize**:

**(a) The law arrives as a PDF, late.** CAQM publishes orders on a JavaScript-rendered portal as dense multi-page documents. They reach a small site as a WhatsApp forward or a newspaper headline, stripped of detail. A supervisor cannot answer "which of my activities became illegal this morning, and under which clause?"

**(b) The stage is city-wide; the duties are entity-specific.** Nothing translates "Stage III invoked" into the nine things *this* site must stop.

**(c) The halt displaces people who are legally owed money and almost never receive it.** When construction stops under GRAP, daily-wage workers lose the day. Compensation for exactly this exists — paid from the **statutory labour cess fund** administered by the state construction workers' welfare board, not from the contractor's pocket. The fund is chronically under-disbursed. The bottlenecks are that the worker must be registered, must know a payment was announced, and must be able to evidence that they were displaced on a day the stage was active. **That evidence does not exist anywhere.**

### 6.3 Why the operator actually wants this — the fix to v1's fatal flaw

v1 of this plan pointed the tool at a site supervisor and asked him to install something whose only function was to generate liabilities for him. That was wrong, and it would have been the first question a judge asked.

Two facts fix it completely.

**The money is not his.** Compensation comes from the cess fund, not from his payroll. Telling his workers what they are owed costs him nothing.

**He has a real, self-interested problem the shutdown creates: his crew scatters.** When a site shuts for a week, daily-wage labourers go to another site or go home to the village, and restarting is slow and expensive. A supervisor who can tell his men on the morning of the halt — *here is your parchi, here is what you are owed, here is how to claim it* — has a materially better chance of having a crew on the day the ban lifts.

So the value proposition to the person holding the phone is **crew retention**, and the value to the person it protects is **money they are owed**. Those are not in tension. That is the Suraksha shape — operator and beneficiary are different people — but with the incentives finally pointing the same way.

### 6.4 Who it is for — one sentence each

- **Operator:** the supervisor or labour contractor at a construction site in Delhi-NCR, who is about to lose a week of work and does not want to lose his crew with it.
- **Beneficiary:** the daily-wage construction worker who loses the day and has an entitlement nobody has ever documented for them.
- **Third principal (and the reason Cedar earns its place):** a **facilitator** — a union rep, NGO caseworker or welfare-board helpdesk volunteer — who assists workers with claims and must be able to help **without** being handed the worker's full personal record.

### 6.5 What it does — the mechanism

1. **Reads the air honestly.** Live station-level readings from the nearest CPCB monitoring station (ingested via OpenAQ's documented API, with CPCB cited as the authority), stamped with station ID, reading time and a staleness flag.

2. **Separates the number from the law — in one line, not two widgets.** A GRAP stage is *invoked by a CAQM order*, not computed by arithmetic. CAQM can invoke pre-emptively on forecast, or hold off. Aadesh shows a single status line:

   > **Stage III — invoked by CAQM order of 6 Oct (hash `a3f91c…`).** Nearest station Rohini reads 412 at 09:00, which also implies Stage III.

   When the two diverge, that line turns amber and says so explicitly. Every competing team will compute a stage from a number and call it the law. This is a 12-second differentiator, delivered as one sentence.

3. **Resolves obligations as data.** The site profile crosses the active stage against a small, heavily cited rules corpus. Each obligation returns `met` / `not_met` / `unknown` with clause id, page and verbatim quote. A missing fact is never inferred as false. Pure Python — no model anywhere near this decision.

4. **Issues a Standing Order.** The supervisor signs one, once: *"if Stage III is invoked for my station, issue the dust-work halt and open a parchi for every worker on my roster."* Scoped to one trigger, one site, one action, expiring at the end of the season. This is Beacon's Sleep Contract in civic clothing — pre-committed consent, narrow and time-boxed, rather than an agent with standing authority.

5. **Hands the parchi over by QR, which is how India actually works.** When the halt fires, the supervisor's screen shows a QR per worker. Each worker scans with their own phone, sees their parchi in Hindi, and taps to acknowledge. No SMS gateway, no app install, no assumption about who owns a smartphone — one phone that has the list, and a scan. It is more plausible than SMS and it films beautifully.

6. **Requires the other side to close the loop.** **Cedar forbids the supervisor from acknowledging on a worker's behalf.** The halt record is incomplete until the people it displaced have confirmed it. Neither party can finish alone — CampusEvac's property, here because a claim genuinely needs the claimant's confirmation.

7. **Writes the parchi.** An immutable record: stage, hash of the invoking order, station reading with timestamp, obligation ids, worker identity and acknowledgement time, the entitlement clause with its quote, and a readiness checklist of what the worker still needs (registration number, bank details) to claim. Exportable as a one-page document.

8. **Lets a facilitator help, without oversharing.** A worker can opt in to assistance. The facilitator then gets `AssistClaim` — a redacted view — and never `ViewParchi`. Opting in to help never becomes opting in to full disclosure, and that distinction is enforced by policy rather than remembered by whoever writes the next endpoint. This is the organizers' own published Cedar pattern, used because it is genuinely needed.

9. **The model explains, and only explains.** Strands Agents on Bedrock gets two tools: render an already-computed obligation or entitlement into plain Hindi or English, and answer a question by citing already-computed results. Output is contract-checked — must cite a clause id that exists, must not assert an obligation the engine did not compute, must not use "approved", "guaranteed" or "legal advice". Fail the contract and a deterministic sentence is used. **The model can be entirely unavailable and Aadesh still works.**

10. **Verification is a command that can fail.** `make verify` re-hashes every stored order and re-checks that every cited quote still appears in the indexed page it claims. Then `make verify --tamper` flips a single byte in a scratch copy and shows the check catch it. A hash check that has never failed proves only that you did not delete your files.

### 6.6 The number on screen

Two counters, one for each audience, both climbing during the demo:

> **₹1,02,000 in entitlement documented · 34 of 34 workers acknowledged · crew retained: 34/34**

That is the "nobody got woken up" moment. "Receipts written" is a log line; rupees and retained men are an outcome.

### 6.7 Answering "but this doesn't actually clean any air"

A judge may reasonably say the project improves compliance with a rule rather than reducing emissions. Have one sentence ready, and say it in the video:

> GRAP's hardest problem is not knowing when to halt — it is that halting is socially expensive, so it gets delayed, diluted and lifted early. The displacement is what makes enforcement politically costly. Pay for the displacement and document it, and the halt becomes cheaper to enforce and harder to quietly skip.

That is true, it is non-obvious, and it reframes the project from "compliance admin" to "making the intervention survivable for the people who bear its cost."

### 6.8 Novelty check

AQI apps exist (SAFAR, CPCB's Sameer, AQI.in). News outlets publish stage explainers. CAQM publishes orders. Welfare boards publish schemes. What does not exist: **a per-site obligation resolver with clause-level citations that converts a GRAP halt into an acknowledged, provable, claim-ready record for each displaced worker.** The gap is exactly "a number turning into something a person can act on this week," which is the sentence the organizers opened their announcement with.

### 6.9 Scope — one entity type, and a hard kill list

**Build:** construction site only. 10–14 obligations plus 3–4 entitlement clauses, all cited from a single current consolidated order where possible.

**Do not build:** a map as the primary screen; an AQI forecasting model; any computer vision; a second entity type (stretch goal only, below the worker view); multi-city; actual claim filing or payments; integration with any real government system; hardware; a native mobile app; social features; more than three principal types.

### 6.10 What you are explicitly *not* claiming — put this in the UI, README and video

Mirror the organizers' own SchemeProof discipline:

> Aadesh is not a government application and not legal advice. We do not file claims and we have no access to any welfare board system. We produce a cited document and a readiness checklist; the claim is filed by the worker or their facilitator through official channels. Every obligation is a cited starting point that must be verified against the official CAQM order.

Phrase outputs as "this clause applies to your profile", never "you are permitted" or "you will be paid".

**And one hard instruction:** do not encode GRAP thresholds, action lists or entitlement amounts from memory, from this document, or from a news article. GRAP has been revised repeatedly, with orders amending earlier orders. On Day 1, locate the current CAQM order, download it from the official domain, hash it, and encode only from the text you are holding. If you cannot establish which order is current for a given measure, **drop that obligation** — a confidently wrong citation is worse than no citation, because you have loudly advertised provenance.

---

## PART 7 — Architecture

### 7.1 Flow

```
EventBridge (every 15 min)
  └─> Lambda: ingest
        ├─ OpenAQ / CPCB nearest-station AQI  ──> DynamoDB (reading + station + ts + staleness)
        └─ S3: hashed CAQM order objects ──> OpenSearch (indexed pages, searchable quotes)

Lambda: resolve
  └─ site profile × invoked stage × rules-as-data corpus
        └─> obligation set [{status, clause_id, page, quote}]   ← pure Python, no model

Step Functions: standing order
  stage trip ─> resolve ─> Cedar authorize ─> open parchi per worker ─> PENDING_ACK
             ─> QR scanned, worker acknowledges ─> parchi sealed (DynamoDB) ─> CloudWatch audit

Bedrock + Strands Agents  ← explanation only, output contract-checked, deterministic fallback
Cognito ─> Next.js on Amplify Hosting (public URL)  |  Cedar ─> every read and write
```

### 7.2 Service-by-service justification

| Service | Its job here | Why this one |
|---|---|---|
| **Amazon S3** | Exact downloaded bytes of every CAQM order, keyed by SHA-256 | Object storage is the right home for evidence that must not change; the hash makes a citation checkable |
| **OpenSearch** (AWS open source) | Full-text index of extracted order pages | A citation is only verifiable if the real document text is searchable. Run in Docker locally for the verify command |
| **Amazon DynamoDB** | Readings, site profile, roster, standing orders, parchis, acknowledgements | Single-key reads, no joins, no migrations while the clock runs |
| **AWS Lambda** | Ingest, rule evaluation, parchi generation, QR issuance | Short bursts triggered by an event — exactly Lambda's shape |
| **Amazon EventBridge** | 15-minute polling and threshold-trip events | Makes the system event-driven rather than request-driven, which is what a standing order needs |
| **AWS Step Functions** | Standing-order state machine including the `PENDING_ACK` wait state | The acknowledgement gate needs durable state across hours |
| **Amazon SNS** | Notifying the supervisor and any registered facilitator | Fan-out without running a queue consumer. **Worker delivery is QR, not SMS** — say so |
| **Amazon Cognito** | Supervisor / worker / facilitator identity | Three principals need real identity before Cedar means anything |
| **Cedar** (AWS open source) | Who may issue a halt, who may acknowledge, what a facilitator may see | Policy outside application code; `forbid` beats `permit`; `@id` turns a denial into a sentence |
| **Strands Agents SDK** (AWS open source) | Calls Bedrock for plain-language Hindi/English explanation | Model-agnostic, and the natural place to enforce an output contract |
| **Amazon Bedrock** | Hosts the model behind the explanation layer | Claude Haiku for latency; nothing decisional |
| **Amazon CloudWatch** | Execution logs and audit trail of every issued order | A compliance tool with no audit trail is not a compliance tool |
| **Amplify Hosting** | The public URL a judge can open | Free tier, trivial deploy from the repo |

### 7.3 Cedar policies — now doing real work

Three principals with genuinely different visibility is what justifies a policy engine. The two `forbid` rules are the demo.

```cedar
permit (principal, action == Action::"IssueHalt", resource)
when { principal.role == "supervisor" && resource.site == principal.assignedSite };

permit (principal, action == Action::"AckParchi", resource)
when { resource.worker == principal };

permit (principal, action == Action::"AssistClaim", resource)
when { principal.role == "facilitator" && resource.sharedForAssistance == true };

@id("no-proxy-acknowledgement")
forbid (principal, action == Action::"AckParchi", resource)
when { resource.worker != principal };

@id("assist-is-not-disclosure")
forbid (principal, action == Action::"ViewParchi", resource)
when { principal.role == "facilitator" };
```

```python
DENIALS = {
  "no-proxy-acknowledgement":
    "Cedar denied this: a supervisor cannot acknowledge a halt on a worker's behalf.",
  "assist-is-not-disclosure":
    "Cedar denied this: a facilitator can assist a shared claim, but cannot read the worker's record.",
}
```

The second one is the interesting case and worth fifteen seconds on camera. A facilitator who is explicitly asked for help still cannot read the parchi — they reach it through `AssistClaim`, which returns a redacted view. **Opting in to help never becomes opting in to disclosure.** That is a real design decision a judge can interrogate, and it is the exact pattern the organizers published.

### 7.4 Rules-as-data shape

```json
{
  "obligation_id": "grap3-cnd-dust-01",
  "entity_types": ["construction_site"],
  "triggers_at_stage": 3,
  "label": "Dust-generating construction and demolition work must stop",
  "field": "has_dust_generating_activity",
  "operator": "eq",
  "value": true,
  "source_doc": "caqm-order-<sha256-prefix>",
  "page": 4,
  "quote": "<verbatim text from the order you downloaded and hashed>",
  "consequence": {
    "worker_entitlement_ref": "cess-fund-displacement-01",
    "issues_parchi": true
  }
}
```

Entitlement clauses use the same shape with their own source document. **Ten to fourteen obligations, every quote verbatim.** If you catch yourself paraphrasing to save time, stop — the paraphrase breaks `make verify`, and `make verify` is the centrepiece of your architecture segment.

---

## PART 8 — Four-day plan for four people, online

Roles, assigned now and not renegotiated:

- **A — Corpus & credibility.** Source the CAQM order, hash, index, encode 10–14 obligations plus entitlements with verbatim citations, build `make verify` **and** `make verify --tamper`, write the tests.
- **B — AWS backend.** Ingest, resolve, Step Functions, parchi issuance, QR, DynamoDB, S3, Cognito, deploy.
- **C — Frontend.** Supervisor screens, the worker parchi view, QR scan flow, Hindi, legibility.
- **D — Guardrails, demo & writing.** Cedar policies and denial copy, Strands/Bedrock constrained layer, demo video, Builder Center blog, the one real conversation (Appendix D).

### Day 1 — Thursday 8 Oct

Everyone: AWS Builder Center profile + SheerID verification **submitted today** — it can take two days and it gates interview eligibility. Claim free tier and the $25 event credits. **Enable Bedrock model access in `us-east-1` in the first hour** — the most common Day 1 killer. Repo, Apache-2.0, README skeleton.

Then: A locates and hashes the current CAQM order and encodes the **first six** obligations with real quotes. B gets the ingest Lambda returning a real reading from a real station end to end. C builds the obligations screen against hardcoded JSON. D drafts the Cedar schema and five policies, and makes the phone call in Appendix D.

**Hard gate by midnight:** scope frozen in the README — one entity type, the kill list copied in verbatim, the cut ladder below copied in verbatim, and one sentence naming the person you are building for.

### Day 2 — Friday 9 Oct

A finishes the corpus at 10–14 obligations plus entitlements and ships both verify commands. B builds the resolver, the Step Functions standing-order machine with the `PENDING_ACK` wait state, parchi issuance and QR generation. C wires the supervisor screen to live data and builds the standing-order screen. D gets Cedar enforcing on every read and write, with denial sentences surfacing in the UI.

**End of day:** a stage trip opens real parchis from real air data.

### Day 3 — Saturday 10 Oct

You are online, so you get the full twelve hours the DTU teams spend travelling and queueing. Spend them on what normally gets cut.

A writes tests and the data-provenance section of the README. B deploys to AWS with a **public URL** and builds replay mode (recorded real readings, labelled as replay on screen, so an API outage cannot kill the recording). C finishes the worker parchi view, the QR scan flow and Hindi. D builds the Strands/Bedrock explanation layer with contract validation and fallback.

**Evening, all four — the step that won Beacon:** clone the repo onto a clean machine or fresh container and set it up following only your own README. Fix what breaks. It will break. Then record a throwaway run-through and watch it back — you are replacing the DTU showcase rehearsal you are not attending.

### Day 4 — Sunday 11 Oct

**Code freeze 11:00.** No exceptions.

11:00–14:00 record. Budget six to ten takes. Cut to **under 2:55**. 14:00–16:00 README, writeup, architecture diagram, AI-tool disclosure, publish the Builder Center blog. **Submit by 17:00** — three hours before the 20:00 close. Verify the YouTube link opens in a signed-out incognito window first.

### 8.1 The cut ladder — decided now, not at 2 AM on Sunday

Cut from the bottom up. **Nothing above the line goes, ever.**

1. Live station ingest with honest timestamps
2. The obligation engine with verbatim citations
3. The worker parchi, with QR handoff and acknowledgement
4. `make verify` and `make verify --tamper`
5. Cedar with the two forbid rules surfacing in the UI
6. The Standing Order pre-commitment
7. Deployed public URL
8. ——— *everything above this line survives; everything below is expendable* ———
9. Hindi rendering (fall back to English-only before you ship bad Hindi)
10. Facilitator role and the redacted assist view
11. Bedrock/Strands explanation layer (the deterministic text is already correct)
12. Cognito (fall back to a signed role switcher)
13. Parchi PDF export
14. Second entity type (school)

Items 11 and 12 are the ones teams are most reluctant to cut and should be most willing to. The model adds polish, not correctness. Auth adds realism, not function. If either threatens items 1–7, drop it and say in the video that role switching is simulated — the organizers reward that kind of honesty and penalise the opposite.

---

## PART 9 — The three-minute demo, timestamped

The video is the only thing the judges see. No live demo, no call. A feature that exists only in the writeup does not count.

| Time | Content |
|---|---|
| **0:00–0:20** | One person. A site in Delhi, 34 men on daily wages. Stage III is invoked, work stops for six days, the crew scatters to other sites and villages, and not one of them claims the compensation the law already owes them — because nobody told them, and nobody can prove they were displaced. No logo, no team intro, no title card. |
| **0:20–0:35** | The gap, honestly. Put the actual CAQM order on screen and scroll it. "This is the user interface today." Then the key line: *the money exists, it comes from the cess fund, not from the contractor — it just never arrives.* |
| **0:35–1:45** | Live system. Real station reading, station ID, timestamp. The **single status line** showing the invoked stage with its order hash alongside the implied stage. Stage trips. Nine obligations resolve for this site, each with clause, page and quote. The Standing Order fires. **QR grid appears; a second phone scans one; the worker's parchi loads in Hindi; they tap acknowledge.** Supervisor tries to acknowledge for a second worker — **Cedar denies it on screen in a human sentence.** Facilitator opens a shared claim and gets the redacted view, not the record. Counters climb: **₹ documented · 34/34 acknowledged**. |
| **1:45–2:20** | Architecture in one pass, then proof. Run `make verify` — *"Verified N source objects and M citations against indexed source bytes."* Then run `make verify --tamper` and **show it fail**. Say the freshness out loud: station data hourly; the stage comes from an order, not from our arithmetic. |
| **2:20–2:40** | What changed, and the reframe. The retention number. Then the one sentence from 6.7 about why paying for displacement makes enforcement survivable. |
| **2:40–2:55** | Close on the mechanism: *"The shutdown was always going to happen. Aadesh is what makes sure 34 men get paid for it — and come back."* Disclaimer on screen: not a government application, not legal advice. |

Three rules: no slides for the first 100 seconds, narrate what the *user* is doing rather than what the code is doing, and never apologise for anything on screen.

---

## PART 10 — The blog, which is nearly free money

Five AirPods, for **five individuals**, for blogs on AWS Builder Center linked in your submission. At First Commit, writing was by the organizers' own account *"the part most teams skip."* One hour on Sunday evening for a one-in-ten-ish shot is the best expected value available to you all weekend.

Write **one** blog with a real engineering thesis. Your strongest angle:

> **"We built a compliance tool and refused to let the model decide anything."** — rules as data with clause-level citations, SHA-256 provenance so a citation is checkable, a verify command we deliberately made able to fail, Cedar forbidding both proxy acknowledgement and facilitator disclosure, an output contract on the Bedrock layer with a deterministic fallback, and the distinction between a number implying a stage and an order invoking one.

Include the Cedar policy, the obligation JSON, the contract-check function, and both verify outputs. Name what broke. Prashant Thakur's winning write-up works because he admits he found a bug that could have let the agent approve a fix nobody authorised. That admission is the most credible paragraph in it.

---

## PART 11 — Risk register

| Risk | Mitigation |
|---|---|
| **Bedrock model access not enabled** | Hour one, `us-east-1`. Most common Day 1 killer |
| **CPCB portal is scrape-hostile** | Ingest via OpenAQ's documented API, cite CPCB as the authority, cache every reading in DynamoDB |
| **CAQM site is a JavaScript SPA** (confirmed — no server-rendered content) | Locate the order PDFs and hash the files. Do not build a scraper against an Angular app |
| **Amendment reconciliation: which order is current?** | Prefer a single consolidated order. Where currency is unclear, **drop the obligation**. 10 certain beats 25 uncertain |
| **Corpus work stalls / quotes get paraphrased** | One owner, 6 obligations by end of Day 1, verify runs from Day 2 so paraphrase fails loudly and immediately |
| **Entitlement amounts vary or are announced per-event** | Do not hardcode a rupee figure you cannot cite. Show the clause and the mechanism; show amount as "as announced for this event" with its source, or show the count of displaced days if no figure is citable |
| **Worker delivery** | QR handoff, not SMS. No sender-ID registration, no app install, no assumption about phone ownership. State this explicitly rather than implying SMS works |
| **Managed OpenSearch exceeds free tier** | Run OpenSearch in Docker locally for indexing and verify. Using an AWS open-source tool is independently sufficient for eligibility; the hybrid is explicitly allowed |
| **API outage mid-recording** | Replay mode with recorded real readings, labelled as replay on screen |
| **Model hallucinates an obligation** | It cannot — the model never produces obligations. Contract check requires an existing clause id; fail closed to deterministic text |
| **"This doesn't clean air"** | The one-sentence answer in 6.7, said in the video at 2:20 |
| **"Why would a contractor install this?"** | The crew-retention answer in 6.3, said in the video at 0:20 |
| **A simpler, prettier GRAP tracker beats you** | You never show an AQI number as an output. Lead with money and men, not with the stage |
| **Someone proposes a new feature on Saturday** | The Day 1 kill list and cut ladder in the README. Point at them |
| **Deadline ambiguity** | Confirm the exact close on the schedule page and Discord Thursday. Submit at 17:00 regardless |

---

## PART 12 — How this still fails, and what we did about it

Keep this section. A short version of it belongs in your README, because shipping a project with a written account of its own weaknesses reads as confidence, not doubt.

**Fixed in v2, but watch for regression:**

*The operator had no reason to want it.* Solved by crew retention and by the money coming from the cess fund rather than the contractor. **Regression risk:** if your video opens on obligations and clauses rather than on a scattering crew, you have silently reverted to v1. The first twenty seconds decide this.

*The corpus was a research problem on the critical path.* Solved by cutting to 10–14 obligations from one order, with "drop it if currency is unclear" as a standing rule. **Regression risk:** ambition on Friday afternoon.

*The verify command could never fail.* Solved by `--tamper`.

*Cedar was a three-line conditional in costume.* Solved by the third principal and the assist-is-not-disclosure rule.

*The worker side was structurally last and therefore first to be cut.* Solved by the ranked cut ladder, which puts it third from the top.

**Not fixed, accepted, and worth knowing:**

*The impact is one step removed from emissions.* You improve compliance with a rule designed to clean air; you do not clean air directly. The 6.7 argument is good and true, but a project that measurably reduces an exposure has a cleaner answer to criterion one. This is the single biggest remaining soft spot.

*It is NCR-only, because GRAP is.* Own it: "GRAP is NCR-only; the engine is a rules corpus, so another city is another corpus." If none of you is in Delhi, you can still talk to a supervisor locally — shutdown-driven crew loss is universal in Indian construction even where GRAP is not.

*The invoked-versus-implied distinction may not land.* It is one line in the UI and twelve seconds on camera. If it confuses your throwaway-recording audience on Saturday night, cut it to a footnote rather than defending it.

*You are in the most crowded track by choice.* Stated in 4.2. If by Saturday the project has drifted toward a nicer AQI tracker, the bet has failed and you should know it that evening, not on Sunday.

---

## PART 13 — Honest self-audit

**Idea and Impact — strong, with one soft spot.** Real problem, in season, a named beneficiary who is not the operator, aligned incentives on both sides, and a change you can put a rupee figure against. The soft spot is indirectness (Part 12). **Cheapest point available to you:** one real conversation with a site supervisor or worker, quoted in the README and the video. Appendix D has the script. It converts a plausible persona into a verified one in under thirty minutes.

**Built on AWS — strong.** Thirteen services, each load-bearing. Three AWS open-source projects used for their actual purpose. Resist a fourteenth; a judge who builds cloud for a living can tell decoration from structure.

**Design and usability — your lever.** You said you can ship the whole front end, and CampusEvac won ₹1L on interface quality alone. Spend the surplus on legibility, the QR flow and the Hindi — not on animation.

**Execution — strong, conditional on the clean-machine test.** The criterion most teams lose by accident.

**Demo video — strong if you respect the script.** The most common failure is ninety seconds of architecture. Architecture gets thirty-five seconds, after the proof that the thing works.

---

## Appendix A — Data sources, with honest freshness

Declare all of this in the README and say the important parts aloud in the video.

| Source | What you get | Real update frequency | Note |
|---|---|---|---|
| **OpenAQ** | Documented REST API over air quality measurements | Point sensors, 5-minute to hourly | Your technical ingestion path |
| **CPCB National AQI** | Official national monitoring network readings | Station-level, hourly | The authority you cite |
| **CAQM GRAP orders** | The legal text: stages, thresholds, action lists | By order, irregular | Hash the bytes. Site is a JS SPA — fetch the PDFs |
| **State labour / BoCW welfare board** | Construction worker registration and displacement relief | By notification | The clauses that make the parchi matter. Cite, do not assume an amount |
| **DPCC / Delhi govt notifications** | State-level implementation detail | By order | Secondary corpus if time allows |
| **IMD** | Wind and forecast bulletins | District nowcasts, few times daily | Optional, for next-day pre-warning only |
| **Registry of Open Data on AWS** | Sentinel, Landsat, NOAA GOES, NASA POWER in S3 | Satellite passes 1–2/day | Not needed. Do not bolt on satellite data for decoration |

Never describe a twice-daily satellite pass or an hourly station reading as "real-time."

## Appendix B — Fallback, if you conclude Air is unmanageable

**LeakLedger** — Track 02, structurally identical engine, far quieter track. Indian water utilities publish **citizen charters** with service-level timelines: a reported leak must be attended within so many hours. Those charters are rules-as-data with citable clauses, exactly like GRAP. A citizen reports a leak with a location and a rough flow estimate; the engine computes litres lost per hour of SLA breach, escalates automatically up the charter's own published ladder as each tier expires, and produces a provable receipt of how much water was wasted while the utility was out of compliance with its own promise. Same architecture, same three-principal Cedar shape, different corpus. The number that climbs is litres.

Weaker than Aadesh on persona sharpness and seasonality, stronger on field thinness. Decide by Thursday noon, not later.

## Appendix C — Day 1 checklist

- [ ] All four: AWS Builder Center profile created, SheerID verification **submitted today**
- [ ] All four: tour registration and check-in for Environmental Hacks confirmed
- [ ] Bedrock model access enabled in `us-east-1` (hour one)
- [ ] AWS account on free tier, $200 credits + $25 event credits claimed
- [ ] Exact submission close time confirmed on the schedule page and Discord
- [ ] Public repo, Apache-2.0 licence, README skeleton committed
- [ ] Current CAQM order located, downloaded from the official domain, SHA-256 hashed, in S3
- [ ] First 6 obligations encoded with verbatim quotes and page numbers
- [ ] `make verify` running, even against 6 obligations
- [ ] **The conversation in Appendix D, done, with a quote written down**
- [ ] README scope freeze: one entity type, kill list, cut ladder, one-sentence persona
- [ ] Roles assigned and written down
- [ ] Problem log started, with timestamps — it becomes the demo script and the blog

## Appendix D — The one real conversation

Thirty minutes, Day 1, by one person. There is construction within walking distance of wherever you are. Find the supervisor or a worker on a break. Be straightforward: you are a student building something for a competition and you want to know if the problem is real.

Five questions, in this order:

1. When work stops because of pollution rules, what actually happens on the site that morning — how do you find out?
2. What happens to the men? Do they come back when it restarts, or do you lose them?
3. Has anyone here ever received money from the government for a day the site was shut?
4. Is anyone on this site registered with the labour welfare board? Do they know their number?
5. If you could hand each man something on that morning, what would actually be useful to him?

Write down one verbatim sentence. Put it in the README and, if it is good, on screen in the video. If the answers contradict this plan — for example, if crews do *not* scatter, or if compensation is routinely paid — **that is extremely valuable and you should tell me, because the pitch would need to change.** A plan that survives contact is worth more than a plan that was never tested.

---

### Sources

All event facts verified 7–8 October 2026 against: the Environmental Hacks overview, rules, schedule and mentors pages on wemakedevs.org/aws/env; the First Commit winners and all-projects pages; *Announcing Environmental Hacks* (Aayush Sharma, 29 Sep 2026); *First Commit Hackathon Recap and What's Next* (Kunal Kushwaha, 7 Oct 2026); *Bharat Builds Tour: What is Happening in Delhi on 10 October* (Aayush Sharma, 6 Oct 2026); *How to Build a Real-Data AI Project on the AWS Open Source Stack* (Aayush Sharma, 18 Sep 2026); and *My First Commit hackathon experience: building Beacon Night Shift* (Prashant Thakur, AWS Builder Center, 1 Oct 2026).

GRAP stage thresholds, action lists and any compensation amounts are deliberately **not** reproduced in this document. Encode them only from the current official order you download and hash yourself.
