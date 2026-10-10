# Aadesh AWS Deployment

Deploy Aadesh to AWS using AWS SAM (Serverless Application Model).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AWS Infrastructure                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Frontend (Amplify Hosting)                                                   │
│  ┌─────────────────┐                                                          │
│  │  Next.js App     │ ← Cognito Auth                                         │
│  │  amp.app.domain  │                                                         │
│  └────────┬────────┘                                                          │
│           │                                                                   │
│           ▼                                                                   │
│  API Gateway (REST API)                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  /api/* → Lambda Proxy (Cognito Authorizer)                            │ │
│  │  /resolve  → Lambda                                                       │ │
│  │  /standing-order → Lambda                                                 │ │
│  │  /parchi/acknowledge → Lambda                                            │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│           │                                                                   │
│           ▼                                                                   │
│  Lambda Functions (Python 3.13, ARM64)                                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ api_handler  │ │ ingest_*     │ │ resolve_*    │ │ standing_*   │       │
│  │ (main API)   │ │ (EventBridge)│ │              │ │              │       │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ parchi_ack   │ │ task_waiter  │ │ create_*     │ │ seal_*       │       │
│  │              │ │ (SFN waiter) │ │              │ │              │       │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                                               │
│  Step Functions Workflow                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  StageTrip → Resolve → Authorize → CreateParchis → PendingAck          │ │
│  │                                      ↓                                   │ │
│  │                         WaitForTaskToken (parchi-ack-waiter)            │ │
│  │                                      ↓                                   │ │
│  │                         SealParchis → Audit                             │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  Data Layer                                                                   │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐            │
│  │ DynamoDB         │ │ S3              │ │ OpenSearch       │            │
│  │ - parchis        │ │ - corpus/       │ │ - corpus pages   │            │
│  │ - readings       │ │   (hashed PDFs) │ │   (indexed text) │            │
│  │ - standing_orders│ │                 │ │                  │            │
│  │ - sites          │ │                 │ │                  │            │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘            │
│                                                                               │
│  Identity & Auth                                                              │
│  ┌──────────────────┐                                                        │
│  │ Cognito User Pool │ ← User sign-up/sign-in, JWT tokens                  │
│  │ Cognito Domain    │ ← Hosted UI (optional)                              │
│  └──────────────────┘                                                        │
│                                                                               │
│  AI / Explanation (optional)                                                  │
│  ┌──────────────────┐                                                        │
│  │ Bedrock + Strands │ ← Explanation only, outside enforcement path        │
│  │ (when configured) │   Deterministic fallback always available           │
│  └──────────────────┘                                                        │
│                                                                               │
│  Monitoring                                                                   │
│  ┌──────────────────┐ ┌──────────────────┐                                 │
│  │ CloudWatch Logs  │ │ CloudWatch       │                                 │
│  │ - Lambda logs    │ │ - Alarms         │                                 │
│  │ - SFN execution  │ │ - Dashboard      │                                 │
│  └──────────────────┘ └──────────────────┘                                 │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Service Responsibilities

Every AWS service in this deployment has a specific, justified purpose. No service is added merely to increase the count.

| Service | Purpose | Why |
|---------|---------|-----|
| **Lambda** | Backend compute | Serverless Python handlers over aadesh_core |
| **DynamoDB** | Parchi/state persistence | Append-only parchi records, readings cache, standing orders |
| **S3** | Corpus document storage | Hashed CAQM order bytes — source of truth for citations |
| **API Gateway** | Frontend API entry point | Single HTTP entry with Cognito auth |
| **Cognito** | User authentication | JWT tokens for frontend, role-based access |
| **Step Functions** | Standing Order workflow | Durable workflow with waitForTaskToken for worker ack |
| **EventBridge** | Scheduled AQI ingestion | Every-15-min reading fetch |
| **CloudWatch** | Logging & monitoring | Lambda logs, alarms, dashboard |
| **Bedrock** | AI explanations (opt-in) | Strands agent for plain-language explanations only |
| **OpenSearch** | Corpus indexing (opt-in) | Searchable citations for verification |
| **Amplify** | Frontend hosting | Next.js deployment, CI/CD |

## Prerequisites

- [AWS CLI](https://aws.amazon.com/cli/) configured with credentials
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) installed
- Python 3.13+
- Node.js 18+ (for frontend)
- [uv](https://docs.astral.sh/uv/) (for Python dependencies)

## Deployment Steps

### 1. Configure AWS Credentials

```bash
aws configure
# Or use SSO:
aws sso login
```

### 2. Set Environment Variables

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
export AWS_REGION=ap-south-1
export AADESH_ENV=dev
export AADESH_CORPUS_BACKEND=s3
# etc.
```

### 3. Deploy Backend with SAM

```bash
cd infra/aws

# Build dependencies
sam build --use-container

# Deploy (first time creates Cognito, DynamoDB, etc.)
sam deploy \
  --guided \
  --stack-name aadesh-dev \
  --region ap-south-1 \
  --parameter-overrides \
    Environment=dev \
    CorpusBackend=s3 \
    ExplainBackend=deterministic \
    OpenSearchDomainEndpoint="" \
    CognitoUserPoolId="" \
    CognitoDomainPrefix=""

# For subsequent deploys:
sam deploy
```

The stack this repo actually runs is deployed without any of those flags on the command line:
`infra/aws/samconfig.toml` records its stack name, region and the twelve parameter values it
carries. That file is **gitignored** (`.gitignore:29`), so a fresh clone has to recreate it from
the stack's own parameters (`describe-stacks`) rather than from memory. Several of them (`Environment=prod`, `ExplainBackend=bedrock`, the Bedrock model, the site
label) differ from the template defaults, so a bare `sam deploy` that fell back to those defaults
would change the system while appearing to change nothing. `sam build` first: it is what packages
the rebuilt layer (`../build/lambda-layer`, assembled by `build-lambda.sh` because `cedarpy` is a
native wheel that must be resolved for Linux).

### 3.1 Check the two CORS facts a browser enforces, which curl cannot

An API Gateway deployment is what makes a CORS change real, and API Gateway answers some requests
— no token, an expired one, a malformed one, a throttled one — **before any Lambda runs**. Those
refusals therefore never pass through the handler, so they carry none of the headers the handler
sets, and a browser hides them from the console: every screen reports `Failed to fetch` and the
console concludes the API is down. The console's origin is declared for exactly those responses in
`infra/aws/template.yaml` (see the `GatewayResponses` block there, and §9.3 of
`docs/superpowers/specs/2026-10-09-aadesh-aws-deployment-design.md`).

Both facts are asserted against the deployed stage by flow 1 of `infra/aws/verify_deployment.py`:
`OPTIONS` must answer with the console's origin *and nothing else*, and a tokenless `GET` must be a
`401` that still carries it. Run it after any change to the API:

```bash
uv run --with boto3 python infra/aws/verify_deployment.py \
  --api-url <ApiUrl output> \
  --user-pool-id <UserPoolId output> \
  --client-id <UserPoolClientId output>
```

The last word is the browser's, not the script's: sign in on the deployed console and load
`/supervisor`. `Failed to fetch` there is the same bug, however clean the script looks.

Then sign out and load `/site`. It must read "This screen needs a signed-in session. Use Sign in in
the header." and **not** "Is the API running? Start it with `make api`" — that 401 came from a
running API, and answering a readable refusal with a local-server hint tells a visitor to fix the
wrong thing. The console draws that distinction at the point the error is caught (`isUnreachable`
in `web/lib/api.ts`), so the hint survives only for the case it was written for: `make web` with no
`make api` behind it.

### 3.2 The account's concurrency ceiling, and the 500 it hides

This account allows **10 concurrent Lambda executions**, and its unreserved floor is also 10 — so
**no function can reserve concurrency at all**. Reserving three for the console was rejected
outright:

```
Specified ReservedConcurrentExecutions for function decreases account's
UnreservedConcurrentExecution below its minimum value of [10].
```

The standing-order machine fans out to one branch per worker, so it used to be able to occupy all
ten slots. When the console's function lost that race, its invocation was throttled, and API
Gateway answered with a 500 carrying **no CORS header** — `Failed to fetch` on screen, against an
API that was up the whole time. That is the same symptom as an undeclared CORS header, produced
from the shape of the account rather than from the API definition.

The stack therefore does two things instead: `PendingAck` fans out to **5**, and every Lambda task
retries **`Lambda.TooManyRequestsException`** (which Step Functions reports separately from the
service exceptions — without it, a throttled branch was caught and recorded as a worker who *did
not answer*). `API_CONFIGURATION_ERROR`, `INTEGRATION_FAILURE` and `INTEGRATION_TIMEOUT` are also
declared in `GatewayResponses` with the console's origin, because those types pre-empt
`DEFAULT_5XX` — and the 500 above is `API_CONFIGURATION_ERROR`'s default response, body and all.

**Checking it** needs the acknowledgement burst, not a single request:

```bash
# CloudWatch: both must stay flat while a standing order runs
aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Throttles \
  --dimensions Name=FunctionName,Value=aadesh-prod-api --start-time <ISO> --end-time <ISO> \
  --period 60 --statistics Sum --region ap-south-1
```

`verify_deployment.py` flow 8 acknowledges all 34 Parchis and fails on any reply that is not a 200
or a designed 400, so it is the check that catches this; a burst that produces 34/34 declarations of
acknowledgement with zero throttles is the pass condition.

### 4. Deploy Frontend to Amplify

```bash
cd web

# Build the Next.js app
npm install
npm run build

# Deploy to Amplify (first time creates the app)
amplify init
amplify add hosting
amplify configure hosting --manual \
  --app-domain aadesh-apps \
  --bucket aadesh-web-bucket \
  --branch-name main

amplify publish
```

Or use the AWS Console:
1. Go to AWS Amplify
2. Click "New App" → "Host web app"
3. Connect your Git repository
4. Amplify auto-detects Next.js and builds

### 5. Configure Cognito (if not auto-created)

If using the hosted UI:

```bash
# Get the Cognito domain
aws cognito-idp describe-user-pool-domain \
  --domain aadesh-dev-auth \
  --region ap-south-1
```

Configure the callback URL in the Cognito app client:
- Allowed Callback URLs: `https://<amplify-domain>.amplifyapp.com/signin-callback`
- Allowed Sign-out URLs: `https://<amplify-domain>.amplifyapp.com/signout-callback`

### 6. Upload Corpus to S3

```bash
aws s3 sync corpus/ s3://aadesh-dev-corpus-<account>-<region>/corpus/ \
  --delete \
  --region ap-south-1
```

### 7. Configure Bedrock (if using AI explanations)

```bash
# Enable Bedrock model access in us-east-1
aws bedrock list-foundation-models --region us-east-1

# Enable desired models via console:
# https://console.aws.amazon.com/bedrock/home#/modelaccess
```

### 8. Set Up QR Signing Secret

Store the QR signing secret in AWS Secrets Manager:

```bash
aws secretsmanager create-secret \
  --name aadesh/qr-signing-secret \
  --secret-string "$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  --region ap-south-1
```

Update the Lambda environment variable `AADESH_QR_SIGNING_SECRET` to reference the secret.

## Stack Outputs

After deployment, SAM outputs these values:

| Output | Description |
|--------|-------------|
| `ApiUrl` | API Gateway endpoint (use in frontend) |
| `UserPoolId` | Cognito User Pool ID |
| `UserPoolClientId` | Cognito App Client ID |
| `UserPoolDomain` | Cognito hosted UI domain |
| `ParchisTableArn` | DynamoDB table for Parchis |
| `CorpusBucketName` | S3 bucket for corpus documents |

## Frontend Configuration

Set these environment variables in your Amplify app (Amplify Console → App settings → Environment variables):

```
NEXT_PUBLIC_API_BASE_URL=<ApiUrl from SAM output>
AWS_REGION=ap-south-1
COGNITO_USER_POOL_ID=<UserPoolId>
COGNITO_CLIENT_ID=<UserPoolClientId>
COGNITO_DOMAIN=<UserPoolDomain>
```

## Local Development

See [Local Development](./LOCAL_DEV.md) for running the full stack locally.

## Testing

### Unit Tests (offline, no AWS)

```bash
make test
```

### Integration Tests (LocalStack)

```bash
make test-integration
```

Requires Docker running LocalStack.

### Verification

```bash
make verify
make verify-tamper
```

## Cleanup

To remove all AWS resources:

```bash
cd infra/aws
sam delete --stack-name aadesh-dev --region ap-south-1
```

To also remove the Amplify app:

```bash
amplify delete
```

## Cost Estimate (Monthly, dev environment)

| Service | Estimated Cost |
|---------|---------------|
| Lambda | ~$0.00 (free tier covers development) |
| DynamoDB | ~$0.00 (on-demand, low traffic) |
| S3 | ~$0.00 (corpus is small) |
| API Gateway | ~$0.00 (free tier) |
| Cognito | ~$0.00 (MAU under 50k) |
| Step Functions | ~$0.00 (low throughput) |
| EventBridge | ~$0.00 (schedules free) |
| CloudWatch | ~$0.00 (basic monitoring) |
| Bedrock | Pay-per-token (opt-in only) |
| OpenSearch | ~$15/month (t3.small, opt-in only) |
| **Total** | **~$0-15/month** (depending on opt-ins) |

## Production Considerations

Before deploying to production:

1. **Enable Point-in-Time Recovery** on DynamoDB tables (already enabled in prod condition)
2. **Configure CloudWatch Alarms** for errors and latency
3. **Set up VPC** if requiring private network access
4. **Enable AWS WAF** on API Gateway for DDoS protection
5. **Configure backup** for S3 corpus bucket (cross-region replication)
6. **Enable CloudTrail** for audit logging
7. **Rotate secrets** regularly (QR signing key, API keys)
8. **Configure HTTPS** enforcement on API Gateway
9. **Set up budget alerts** to monitor costs
10. **Review IAM policies** for least-privilege compliance

## Troubleshooting

### Lambda permissions error

```bash
# Check Lambda execution role
aws iam get-role-policy \
  --role-name aadesh-dev-lambda-execution \
  --policy-name AWSLambdaBasicExecutionRole
```

### Cognito callback URL mismatch

Ensure the callback URL in Cognito app client matches your Amplify domain exactly.

### API Gateway 403 errors

Check that the Cognito authorizer is properly configured and the JWT token is valid.

### Step Functions execution fails

Check CloudWatch Logs for the specific Lambda that failed:

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/aadesh-dev-<function-name> \
  --filter-pattern "ERROR" \
  --region ap-south-1
```

## Security

- **Never commit secrets** — use AWS Secrets Manager or SSM Parameter Store
- **Least-privilege IAM** — each Lambda has only the permissions it needs
- **Cedar authorization** — all access controlled by Cedar policies, not just Cognito auth
- **Encryption at rest** — DynamoDB and S3 use AES-256
- **Encryption in transit** — all AWS service communication uses TLS
- **No public S3 access** — bucket policy denies unencrypted transport

## Cedar Policies in AWS

The Cedar authorization policies are bundled with the Lambda deployment package.
They are stored at:

```
/var/task/infra/cedar/policies.cedar
/var/task/infra/cedar/denials.json
/var/task/infra/cedar/schema.cedarschema.json
```

These are the SAME policies used locally and in tests. The authorization
boundary is identical in all environments.
