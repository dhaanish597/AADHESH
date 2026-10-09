# Aadesh IAM Policies — Least Privilege

Each Lambda function has only the permissions it needs to perform its specific task.
No function has broad `*` permissions except where technically required (e.g.,
Lambda runtime network interface creation).

## Policy Summary

| Function | DynamoDB | S3 | Bedrock | Step Functions | CloudWatch | Other |
|----------|----------|-----|---------|----------------|------------|-------|
| api_handler | CRUD parchis, READ readings/sites/orders | READ corpus | (opt-in) InvokeModel | — | Logs: create/stream/events | — |
| ingest_handler | WRITE readings | — | — | — | Logs: create/stream/events | EC2: create/delete network interfaces |
| resolve_handler | READ sites, READ orders | READ corpus | — | — | Logs: create/stream/events | — |
| standing_order_handler | CRUD parchis, CRUD orders, READ sites | READ corpus | — | StartExecution, DescribeExecution | Logs: create/stream/events | — |
| parchi_ack_handler | CRUD parchis | — | — | — | Logs: create/stream/events | — |
| task_waiter | CRUD parchis | — | — | SendTaskSuccess | Logs: create/stream/events | — |
| parchi_creation_handler | CRUD parchis, READ sites | READ corpus | — | — | Logs: create/stream/events | — |
| parchi_seal_handler | CRUD parchis | — | — | — | Logs: create/stream/events | — |
| audit_handler | CRUD parchis, WRITE orders | — | — | — | Logs: create/stream/events | — |
| stage_trip_handler | READ sites | READ corpus | — | — | Logs: create/stream/events | — |

## DynamoDB Permissions

### parchis Table
- **api_handler**: GetItem, PutItem, UpdateItem, DeleteItem, Query (all indexes)
- **standing_order_handler**: GetItem, PutItem, UpdateItem, DeleteItem, Query
- **parchi_ack_handler**: GetItem, PutItem, UpdateItem, DeleteItem, Query
- **task_waiter**: GetItem, PutItem, UpdateItem, Query
- **parchi_creation_handler**: GetItem, PutItem, UpdateItem, Query
- **parchi_seal_handler**: GetItem, PutItem, UpdateItem, Query
- **audit_handler**: GetItem, PutItem, UpdateItem, DeleteItem, Query

### readings Table
- **api_handler**: GetItem, Query (for dashboard)
- **ingest_handler**: PutItem, UpdateItem, Query
- **resolve_handler**: GetItem, Query

### standing-orders Table
- **api_handler**: GetItem, Query
- **standing_order_handler**: GetItem, PutItem, UpdateItem, DeleteItem, Query
- **audit_handler**: PutItem, UpdateItem

### sites Table
- **api_handler**: GetItem, Query
- **resolve_handler**: GetItem, PutItem (create if missing)
- **standing_order_handler**: GetItem, PutItem
- **parchi_creation_handler**: GetItem, PutItem
- **stage_trip_handler**: GetItem

## S3 Permissions

### corpus Bucket
- **api_handler**: GetObject, ListBucket (on corpus prefix)
- **resolve_handler**: GetObject, ListBucket
- **standing_order_handler**: GetObject, ListBucket
- **parchi_creation_handler**: GetObject, ListBucket
- **stage_trip_handler**: GetObject, ListBucket

**No PutObject** — corpus is append-only, ingested via CLI/CI, not at runtime.

## Bedrock Permissions (opt-in only)

When `AADESH_EXPLAIN_BACKEND=strands_bedrock`:

- **api_handler**: `bedrock:InvokeModel` on specific models only:
  - `arn:aws:bedrock:{region}:{account}:foundation-model/amazon.nova-lite-v1:*`
  - `arn:aws:bedrock:{region}:{account}:foundation-model/amazon.nova-micro-v1:*`
  - `arn:aws:bedrock:{region}:{account}:foundation-model/anthropic.claude-haiku-4-5-20251101-v1:*`
  - `arn:aws:bedrock:{region}:{account}:foundation-model/anthropic.claude-sonnet-4-5-20250827-v1:*`

**No broad `bedrock:*`** — only InvokeModel on pre-approved models.

## Step Functions Permissions

### For Lambda invoking Step Functions
- **standing_order_handler**: `states:StartExecution`, `states:DescribeExecution` on specific state machine ARN only

### For Step Functions invoking Lambda
- State machine has `lambda:InvokeFunction` on each task Lambda via resource-based policy

### For task_waiter sending task success
- **task_waiter**: `states:SendTaskSuccess` on * (required — task token is opaque)

## CloudWatch Permissions

All functions:
- `logs:CreateLogGroup` on `/aws/lambda/{function-name}:*`
- `logs:CreateLogStream` on `/aws/lambda/{function-name}:*`
- `logs:PutLogEvents` on `/aws/lambda/{function-name}:*`

**No `logs:*`** — only on specific log groups.

## EC2 Permissions (ingest_handler only)

Ingest handler needs to create network interfaces for VPC (if configured):
- `ec2:CreateNetworkInterface`
- `ec2:DescribeNetworkInterfaces`
- `ec2:DeleteNetworkInterface`

**Only if Lambda is configured for VPC**. Without VPC, these are not needed.

## Secrets Manager (optional)

If QR signing secret is stored in Secrets Manager:
- **parchi_ack_handler**: `secretsmanager:GetSecretValue` on specific secret ARN

## X-Ray

All functions:
- `xray:PutTraceSegments`
- `xray:PutTelemetryRecords`

For distributed tracing.

## IAM Role Trust Policy

All Lambda roles trust `lambda.amazonaws.com` and `states.amazonaws.com` (for workflow roles).

## Cross-Account Access

No cross-account access required. All resources in same account.

## Resource-Based Policies

### API Gateway
- Lambda permission: `lambda:InvokeFunction` granted to `apigateway.amazonaws.com` on each handler ARN

### Step Functions
- Lambda permission: `lambda:InvokeFunction` granted to `states.amazonaws.com` on each task Lambda ARN

## Security Notes

1. **No `*` resources** except where technically required (EC2 network interfaces)
2. **No `*` actions** except where technically required
3. **Least privilege**: each function has only what it needs
4. **No admin access**: no `*:*` anywhere
5. **Resource-level restrictions**: DynamoDB table ARNs, S3 bucket ARNs, Bedrock model ARNs
6. **Condition keys**: Use `aws:SourceAccount`, `aws:SourceArn` where applicable
7. **Encryption**: All data at rest encrypted (DynamoDB, S3)
8. **Secure transport**: S3 bucket policy denies unencrypted transport

## Verification

To verify IAM policies are correct:

```bash
# List all policies for a role
aws iam list-role-policies --role-name aadesh-dev-lambda-execution

# Get specific policy
aws iam get-role-policy --role-name aadesh-dev-lambda-execution --policy-name DynamoDBAccess

# Simulate principal permissions
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::ACCOUNT:role/aadesh-dev-lambda-execution \
  --action-names dynamodb:GetItem \
  --resource-arns arn:aws:dynamodb:REGION:ACCOUNT:table/aadesh-dev-parchis
```

## Updating Policies

To add or modify permissions:

1. Edit `infra/aws/template.yaml`
2. Update the `Policies` section for the relevant function
3. Rebuild and redeploy:
   ```bash
   sam build --use-container
   sam deploy
   ```

**Do not** attach policies directly to roles in the console — always go through SAM template
to maintain infrastructure-as-code.
