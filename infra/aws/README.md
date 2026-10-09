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
