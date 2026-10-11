# Aadesh AWS Deployment Summary

This summary mirrors `infra/aws/template.yaml` (reviewed 10 October 2026). It describes the
resources declared by the template; it does not claim that every optional path is exercised by
the frontend demo.

## Template inventory

The SAM template declares **33 resources**:

| Kind | Count | Logical resources |
|---|---:|---|
| Lambda layer | 1 | `AadeshCodeLayer` |
| Lambda functions | 9 | `ApiHandler`, `IngestHandler`, `StageTripHandler`, `ResolveHandler`, `AuthorizeHandler`, `CreateParchisHandler`, `ParchiAckWaiter`, `SealParchisHandler`, `AuditHandler` |
| DynamoDB tables | 7 | `ParchisTable`, `OperationalTable`, `StandingOrdersTable`, `TriggerRunsTable`, `ReadingsTable`, `SitesTable`, `ConsentsTable` |
| S3 bucket and policy | 2 | `CorpusBucket`, `CorpusBucketPolicy` |
| Cognito resources | 3 | `UserPool`, `UserPoolDomain`, `UserPoolClient` |
| Amplify resources | 2 | `AmplifyApp`, `AmplifyBranch` |
| API Gateway | 1 | `AadeshApi` |
| Step Functions | 1 | `StandingOrderStateMachine` |
| EventBridge rule | 1 | `StageInvocationRule` |
| IAM role | 1 | `EventBridgeToStepFunctionsRole` |
| CloudWatch log groups | 2 | `WorkflowLogGroup`, `ApiLogGroup` |
| CloudWatch alarms | 2 | `ApiErrorsAlarm`, `WorkflowFailuresAlarm` |
| CloudWatch dashboard | 1 | `Dashboard` |

There is **no OpenSearch domain** in the template. The corpus verifier reads local hashed source
bytes and does not depend on a deployed search service. The Amplify branch is `main` with
`EnableAutoBuild: false`; `infra/aws/deploy-web.sh` publishes the static export manually.

## Deployment

Deploy the backend with SAM from `infra/aws/` using the documented parameters. For the frontend,
run `STACK=<stack-name> make deploy-web` from the repository root. The script reads `ApiUrl` and
`AmplifyAppId` from CloudFormation, builds the static export, uploads it through an Amplify
deployment job, waits for completion, then prints the branch URL.

The template defaults `ExplainBackend` to `deterministic`. The deterministic explanation path is
immediate and does not wait on a Bedrock cold start; model access is optional and remains outside
the rules and authorization path.

## CORS and public routes

The template's API CORS origin is `https://main.${AmplifyApp.AppId}.amplifyapp.com`, which matches
the production `main` branch used by the manual publisher. Worker view and acknowledgement,
aggregate impact, latest reading and health routes are explicitly public; other API routes use
the Cognito authorizer by default.

## Consent storage

`ConsentsTable` is the durable home of worker consent for facilitator assistance. Its hash key
is `scope_key = consent#<worker>#<facilitator>#<parchi>`, so one scope has at most one consent
record -- there is no second live record that a revocation could leave behind. A
`context_id-index` GSI answers "the record this handle names", which is how a worker revokes by
the context id they were given. Every write is a conditional put keyed on a `version`
attribute, so a grant formed before a revocation loses the race instead of restoring the
consent; the API function's `ConsentState` statement grants only `GetItem`, `PutItem` and
`Query` on the table and its index.

The table has a `ttl` attribute pointing at the consent's expiry, but that is housekeeping
only: DynamoDB deletes lapsed items asynchronously, so expiry is decided by comparing
`expires_at` against the current time on every authorization check.

## Verification

The repository verification commands are local and require no AWS resources:

```text
make verify          # all manifest source hashes and cited quotations
make verify-tamper   # detects a byte change in an isolated scratch copy
```

The tamper command intentionally prints the verifier's failure against the modified scratch
copy; the Make target succeeds only when that expected failure is detected.
