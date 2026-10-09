# Aadesh AWS Deployment Verification Checklist

After deploying to AWS, verify each of these 12 items works end-to-end.

## Pre-requisites

- AWS deployment complete (SAM stack + Amplify)
- API Gateway URL obtained from SAM outputs
- Amplify app URL obtained after deployment
- Cognito user created (or demo user available)

---

## 1. Login

**Path**: `/signin` or Cognito hosted UI

**Steps**:
1. Navigate to the Amplify app URL
2. Click "Sign In" or navigate to Cognito hosted UI
3. Enter email/password for a test user
4. Complete MFA if enabled
5. Redirect to app after successful authentication

**Expected**:
- User is authenticated
- JWT token is stored in browser
- API calls include `Authorization: Bearer <token>` header
- User sees the home page with navigation

**Troubleshooting**:
- Check Cognito app client callback URL matches Amplify domain
- Verify user is confirmed (not in FORCE_CHANGE_PASSWORD state)
- Check browser console for JWT parsing errors

**Status**: [ ] Pass  [ ] Fail  [ ] N/A

---

## 2. Site Selection

**Path**: `/supervisor`

**Steps**:
1. Log in as a supervisor user (role=supervisor, assigned_site=example-piling-site)
2. Navigate to `/supervisor`
3. Observe the site header and site facts

**Expected**:
- Supervisor console loads
- Site label: "Construction Site — Delhi-NCR"
- Activity type: "Piling works"
- Project category: "Infrastructure"
- Cedar authorizes ViewSiteExecution for this site

**Troubleshooting**:
- Verify Cognito claims include `assigned_site`
- Check Cedar policy allows supervisor with assignedSite
- Check API logs for authorization errors

**Status**: [ ] Pass  [ ] Fail  [ ] N/A

---

## 3. Latest Reading

**Path**: `/supervisor` (reading section)

**Steps**:
1. On supervisor screen, locate "Air quality reading" section
2. Observe station ID, parameter, value, timestamp, freshness
3. Check provenance label

**Expected**:
- Station ID: DL-NCR-ROHINI-01
- Parameter: PM2.5
- Value: 285.0 (synth) or latest measured value
- Timestamp: within last hour
- Freshness: FRESH or STALE (based on staleness threshold)
- Provenance: SYNTHETIC (demo) or MEASURED (live)

**Troubleshooting**:
- Check EventBridge rule is triggering Ingest Lambda every 15 min
- Check DynamoDB Readings table has recent entries
- Check Ingest Lambda logs for errors

**Status**: [ ] Pass  [ ] Fail  [ ] N/A

---

## 4. Official Invocation

**Path**: `/supervisor` (stage status section)

**Steps**:
1. On supervisor screen, locate "Stage status" panel
2. Observe official stage, order reference, invocation date
3. Check lifecycle status

**Expected**:
- Official stage: Stage III (or NONE if no current invocation)
- Order doc ID: caqm-grap-2026-01
- Invocation date: 2026-01-16
- Lifecycle: revoked (historical replay) or active
- If replay: "Historical replay" pill shown
- If no invocation: "No verified current CAQM invocation" message

**Troubleshooting**:
- Check corpus in S3 has invoked_stage.json
- Verify Step Functions can read corpus from S3
- Check resolution handler logs

**Status**: [ ] Pass  [ ] Fail  [ ] N/A

---

## 5. Obligation Resolution

**Path**: `/supervisor` (obligations section)

**Steps**:
1. On supervisor screen, locate "Your obligations" panel
2. Observe list of obligations
3. Click on an obligation to expand citation details
4. Verify source quote, page, hash

**Expected**:
- List of obligations with status (MET, NOT_MET, UNKNOWN, NOT_APPLICABLE)
- Applicable obligations shown by default
- "Show all clauses" toggle available
- Each obligation shows:
  - Label
  - Required action
  - Reason
  - Source document reference
- Expanding shows verbatim quote, page, SHA-256 hash
- If not fully sourced: warning about excluded obligations

**Troubleshooting**:
- Check DynamoDB Sites table has site profile
- Verify corpus loaded from S3 correctly
- Run `make verify` locally to confirm corpus integrity

**Status**: [ ] Pass  [ ] Fail  [ ] N/A

---

## 6. Standing Order

**Path**: `/supervisor` (standing order section)

**Steps**:
1. On supervisor screen, locate "Standing Order" panel
2. Click "Run Stage III replay demo" (or "Preview only" if no invocation)
3. Observe Standing Order creation
4. Check lifecycle states

**Expected**:
- Before creation: "Not created" status
- After creation:
  - Standing Order ID shown
  - Trigger: Stage III · Exact match
  - Actions: ISSUE_HALT + OPEN_PARCHI_PER_WORKER
  - Valid from/to dates
  - Status: active (or projected_status)
- Cedar authorizes IssueHalt (supervisor scoped to site)
- "Show worker QR codes" button appears
- "Try a forbidden action" link appears (Cedar demo)

**Troubleshooting**:
- Verify Cedar policy permits IssueHalt for supervisor with assignedSite
- Check StandingOrders DynamoDB table has new record
- Check Step Functions execution started

**Status**: [ ] Pass  [ ] Fail  [ ] N/A

---

## 7. Parchi

**Path**: `/supervisor` → worker roster → QR code

**Steps**:
1. After Standing Order created, click "Show worker QR codes"
2. Observe worker roster with states
3. Search/filter workers
4. Click "Show worker QR" for a worker
5. Observe QR code
6. Click QR or copy link to open worker view

**Expected**:
- Worker roster shows 34 workers
- Each worker shows: name, state (pending/acknowledged), registered status
- QR code displays for workers with Parchis
- QR links to `/worker#payload=<token>`
- Worker view shows:
  - "This is your Parchi" header
  - Site info
  - Stage info
  - Citations (official sources)
  - Readiness checklist
  - Acknowledge button

**Troubleshooting**:
- Check Parchis table has records after Standing Order
- Verify QR token signing works
- Check Parchi view API endpoint

**Status**: [ ] Pass  [ ] Fail  [ ] N/A

---

## 8. Worker Acknowledgement

**Path**: `/worker` (after scanning QR)

**Steps**:
1. Open worker view via QR link
2. Observe Parchi details
3. Click "Acknowledge Parchi" button
4. Observe confirmation

**Expected**:
- Worker view loads with Parchi details
- Cedar checks: resource.worker == principal
- User sees "Acknowledge Parchi" button
- After click:
  - Button shows "…" during processing
  - On success: "Your Parchi has been acknowledged" message
  - Acknowledged timestamp shown
  - Content hash shown in technical details
- State changes from PENDING to ACKNOWLEDGED

**Troubleshooting**:
- Verify Cedar policy permits AcknowledgeOwnParchi for resource.worker == principal
- Check Parchi Ack Lambda logs for authorization decision
- Verify idempotency — clicking twice shows "already confirmed"

**Status**: [ ] Pass  [ ] Fail  [ ] N/A

---

## 9. Cedar Denial

**Path**: `/cedar`

**Steps**:
1. Log in as supervisor
2. Navigate to `/cedar`
3. Wait for "Preparing a pending parchi" to complete
4. Click "Acknowledge worker" button
5. Observe Cedar denial

**Expected**:
- Page shows: "Who is allowed to do this?"
- Supervisor attempts to acknowledge worker-002's Parchi
- Cedar evaluates: `resource.worker != principal`
- Denial shown:
  - Red "Denied" badge
  - Reason: "Cedar denied this: a supervisor cannot acknowledge a halt on a worker's behalf..."
  - Policy ID: no-proxy-acknowledgement
- Demonstrates that supervisor CANNOT acknowledge for worker

**Troubleshooting**:
- Check Cedar policies.cedar has forbid rule for resource.worker != principal
- Verify denials.json has entry for no-proxy-acknowledgement
- Check Cedar validation passes (no policy errors)

**Status**: [ ] Pass  [ ] Fail  [ ] N/A

---

## 10. Facilitator Redaction

**Path**: `/facilitator`

**Steps**:
1. Log in as facilitator (or use demo)
2. Navigate to `/facilitator`
3. Observe "Help with a claim, without the worker's record" page
4. Check consent lifecycle explanation
5. Observe AssistClaim decision
6. Observe ViewParchi denial

**Expected**:
- Page explains worker-controlled access
- Consent lifecycle: Request → Worker Choice → Limited Window → Revoked/Expired
- "Seeded consent scenario" note
- AssistClaim decision:
  - If consent granted: shows redacted view (context_id, parchi_id, worker_id, site_id, claim_status, consent_status, timestamps)
  - Redaction list: No worker name, No phone, No Aadhaar, No bank details, No full Parchi, No raw QR token
- ViewParchi attempt: DENIED
  - Reason: "Cedar denied this: a facilitator can assist with a claim the worker shared, but cannot read the worker's record..."
- Ungranted consent attempt: DENIED

**Troubleshooting**:
- Verify Cedar policy permits AssistClaim only with live consent
- Check facilitator cannot ViewParchi (forbid rule)
- Verify redacted view doesn't include PII

**Status**: [ ] Pass  [ ] Fail  [ ] N/A

---

## 11. Verification

**Path**: `/verify`

**Steps**:
1. Navigate to `/verify`
2. Observe verification panel
3. Click "Run verification" button
4. Observe output

**Expected**:
- Two panels: main verification + tamper check
- Main verification:
  - Command: make verify
  - Sources checked: 3
  - Citations checked: 55
  - Status: PASS (green)
  - Exit code: 0
- Tamper check:
  - Command: make verify --tamper
  - Status: FAILED (expected) (yellow)
  - Exit code: 1
  - Shows detection worked
- Technical note about `--tamper` vs `verify-tamper`

**Troubleshooting**:
- Check Lambda has access to corpus from S3
- Verify corpus files intact (hashes match manifest)
- Check Lambda logs for verification errors

**Status**: [ ] Pass  [ ] Fail  [ ] N/A

---

## 12. AI Explanation

**Path**: Supervisor or Parchi view → "Explain" button (if Bedrock configured)

**Steps**:
1. Ensure Bedrock is enabled and model access granted
2. On supervisor screen, look for explanation option
3. If configured, query explanation
4. Observe response

**Expected**:
- If Bedrock configured:
  - Explanation shows plain-language summary of resolution
  - Distinguishes official stage from implied stage
  - States "historical replay" if applicable
  - No monetary amounts invented
  - No citations invented
  - Contract-checked: if violated, falls back to deterministic
- If Bedrock NOT configured:
  - Deterministic explanation shown
  - "Explanation unavailable" or deterministic text

**Troubleshooting**:
- Verify Bedrock model access enabled in us-east-1
- Check BEDROCK_MODEL_ID set correctly
- Verify IAM allows bedrock:InvokeModel
- Check Strands adapter logs for errors

**Status**: [ ] Pass  [ ] Fail  [ ] N/A (Bedrock not configured)

---

## Summary

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Login | [ ] | |
| 2 | Site Selection | [ ] | |
| 3 | Latest Reading | [ ] | |
| 4 | Official Invocation | [ ] | |
| 5 | Obligation Resolution | [ ] | |
| 6 | Standing Order | [ ] | |
| 7 | Parchi | [ ] | |
| 8 | Worker Acknowledgement | [ ] | |
| 9 | Cedar Denial | [ ] | |
| 10 | Facilitator Redaction | [ ] | |
| 11 | Verification | [ ] | |
| 12 | AI Explanation | [ ] | Bedrock optional |

---

## Post-Verification

After all items pass:

1. **Check CloudWatch Logs**: No unexpected errors in Lambda logs
2. **Check Alarms**: No alarms in ALARM state
3. **Check Dashboard**: Metrics look healthy
4. **Test Edge Cases**:
   - Invalid QR token → error message
   - Expired consent → denial
   - Revoked stage → proper labeling
   - Missing reading → "no reading" state
5. **Security Review**:
   - Verify no PII in logs
   - Verify Cedar policies working
   - Verify JWT validation

## Rollback

If verification fails:

```bash
# Check recent deployments
sam list-deployments --stack-name aadesh-dev

# Rollback to previous version
sam rollback --stack-name aadesh-dev --region ap-south-1
```
