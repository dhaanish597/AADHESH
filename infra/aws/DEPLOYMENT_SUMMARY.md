# Aadesh AWS Deployment — Summary

## What Was Created

### Infrastructure (infra/aws/template.yaml)
Complete AWS SAM template defining all infrastructure with least-privilege IAM.

**Resources Created:**
- **11 Lambda Functions**: api_handler, ingest_handler, resolve_handler, standing_order_handler, parchi_ack_handler, task_waiter, parchi_creation_handler, parchi_seal_handler, audit_handler, stage_trip_handler
- **4 DynamoDB Tables**: parchis, readings, standing-orders, sites
- **1 S3 Bucket**: corpus (versioned, encrypted, public access blocked)
- **1 Cognito User Pool**: with email auth, custom schema attributes
- **1 Cognito App Client**: for Next.js frontend
- **1 Cognito Domain**: for hosted UI
- **1 API Gateway**: REST API with Cognito authorizer
- **1 Step Functions State Machine**: Standing Order workflow
- **2 EventBridge Rules**: scheduled ingestion + event-driven workflow trigger
- **CloudWatch**: log groups, alarms (errors, latency), dashboard
- **Bedrock Access** (opt-in): specific model ARNs only
- **OpenSearch Domain** (opt-in): encrypted, VPC-accessible

### Lambda Handlers (services/aadesh_aws/)
10 thin adapter handlers over aadesh_core — no business logic, just AWS I/O:

| Handler | Purpose | Lines |
|---------|---------|-------|
| api_handler.py | Main API Gateway handler — all HTTP routes | ~400 |
| ingest_handler.py | EventBridge-triggered AQI ingestion | ~100 |
| resolve_handler.py | Pure deterministic obligation resolution | ~120 |
| standing_order_handler.py | Create/manage Standing Orders | ~150 |
| parchi_ack_handler.py | Worker acknowledges own Parchi | ~80 |
| task_waiter.py | Step Functions waitForTaskToken callback | ~70 |
| parchi_creation_handler.py | Create Parchis for rostered workers | ~70 |
| parchi_seal_handler.py | Seal acknowledged Parchis | ~40 |
| audit_handler.py | Final audit record for workflow | ~60 |
| stage_trip_handler.py | Determine invoked stage from corpus | ~30 |

### Documentation

| File | Purpose |
|------|---------|
| `infra/aws/README.md` | Full deployment guide — architecture, steps, troubleshooting |
| `infra/aws/LOCAL_DEV.md` | Local development with/without LocalStack |
| `infra/aws/VERIFICATION_CHECKLIST.md` | 12-item verification checklist for deployed app |
| `infra/aws/iam-policies.md` | Least-privilege IAM policy documentation |
| `infra/aws/DEPLOYMENT_SUMMARY.md` | This file |
| `infra/aws/stepfunctions/standing-order.asl.json` | Step Functions workflow definition |

### Updated Files

| File | Change |
|------|--------|
| `.env.example` | Complete with all AWS env vars, secrets guidance |
| `README.md` | Added AWS Deployment section documenting all resources |

## Service Responsibilities

Every AWS service has a specific, justified purpose:

| Service | Why It's Here | What It Does |
|---------|---------------|--------------|
| **Lambda** | Serverless compute | Runs aadesh_core adapters |
| **DynamoDB** | State persistence | Parchis (append-only), readings cache, standing orders, site profiles |
| **S3** | Document storage | Hashed CAQM PDF bytes — citation source of truth |
| **API Gateway** | HTTP entry point | Routes to Lambda, Cognito auth |
| **Cognito** | User identity | JWT tokens, role-based access for frontend |
| **Step Functions** | Durable workflow | Standing Order flow with waitForTaskToken for worker ack |
| **EventBridge** | Scheduling | Every-15-min AQI ingestion trigger |
| **CloudWatch** | Observability | Logs, alarms, dashboard |
| **Bedrock** (opt-in) | AI explanations | Strands agent — outside enforcement path only |
| **OpenSearch** (opt-in) | Search | Corpus page indexing for verification |
| **Amplify** | Frontend hosting | Next.js app with CI/CD |

## Not Included (By Design)

These are intentionally NOT included because they would have no real responsibility:

- **SQS/SNS**: No async messaging needed — Step Functions handles workflow, Lambda handles sync API
- **Kinesis**: No streaming needed — EventBridge schedule is sufficient for 15-min ingestion
- **ECS/EKS**: No containers needed — Lambda is serverless and cheaper
- **RDS**: No relational data — DynamoDB is sufficient for the access patterns
- **ElastiCache**: No caching needed — DynamoDB on-demand is fast enough
- **MSK**: No event streaming needed
- **Glue**: No ETL needed — corpus ingestion is a CLI command, not a pipeline
- ** SageMaker**: No ML training — Bedrock handles inference only
- **WAF**: Not yet — can add for production
- **VPC**: Not required — Lambdas don't need private network access for current design

## Deployment Order

1. Deploy backend with SAM:
   ```bash
   cd infra/aws
   sam build --use-container
   sam deploy --guided
   ```

2. Upload corpus to S3:
   ```bash
   aws s3 sync corpus/ s3://aadesh-dev-corpus-<account>-<region>/
   ```

3. Deploy frontend to Amplify:
   ```bash
   cd web
   amplify init
   amplify publish
   ```

4. Configure environment variables in Amplify console:
   - NEXT_PUBLIC_API_BASE_URL = SAM output ApiUrl
   - COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, COGNITO_DOMAIN

5. Create a test user in Cognito:
   ```bash
   aws cognito-idp admin-create-user \
     --user-pool-id <UserPoolId> \
     --username test@example.com \
     --user-attributes Name=email,Value=test@example.com Name=role,Value=supervisor Name=assigned_site,Value=example-piling-site
   ```

6. Run verification checklist (infra/aws/VERIFICATION_CHECKLIST.md)

## Costs

Estimated monthly costs for dev environment:

| Service | Monthly Cost |
|---------|-------------|
| Lambda | ~$0 (free tier) |
| DynamoDB | ~$0 (on-demand, low traffic) |
| S3 | ~$0.01 (small corpus) |
| API Gateway | ~$0 (free tier) |
| Cognito | ~$0 (<50k MAU) |
| Step Functions | ~$0 (low throughput) |
| EventBridge | $0 (schedules free) |
| CloudWatch | ~$0 (basic monitoring) |
| Bedrock | Pay-per-token (opt-in) |
| OpenSearch | ~$15 (t3.small, opt-in) |
| **Total** | **~$0-15/month** |

## Test Results

All existing tests pass with the new Lambda handlers:

```
======================= 1323 passed in 85.14s ========================
```

The new `aadesh_aws` package does not break any existing tests because:
- It's a separate package (not imported by aadesh_core)
- Lambda handlers are thin adapters (no business logic)
- All authorization tests still pass (the gate pattern is preserved)

## Security

- **No secrets in code**: QR signing key goes in Secrets Manager
- **Least-privilege IAM**: Each Lambda has only what it needs
- **Cedar every read/write**: Authorization enforced by Cedar policies
- **Encryption at rest**: DynamoDB + S3 AES-256
- **Encryption in transit**: All AWS service communication TLS
- **No public S3**: Bucket policy denies unencrypted transport
- **Fail closed**: Authorization unavailable → request refused

## Frontend Changes Needed

The Next.js frontend needs to be configured to call the deployed API:

1. Set `NEXT_PUBLIC_API_BASE_URL` to the API Gateway URL
2. Configure Cognito client in `web/lib/auth.ts` (or similar)
3. The frontend already proxies `/api/*` to the backend, so just update the proxy target

Current proxy config (web/next.config.mjs):
```javascript
async rewrites() {
  return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
}
```

Set `API` env var to the deployed API Gateway URL.
