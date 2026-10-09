# Aadesh Local Development

Run the full Aadesh stack locally, including AWS service emulators.

## Quick Start

```bash
# 1. Setup Python environment
make setup

# 2. Setup environment
cp .env.example .env

# 3. Run the local API
make api

# 4. Run the frontend (in another terminal)
make web
```

Then open `http://localhost:3000`.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Local Development Stack                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Frontend (Next.js)                                                           │
│  http://localhost:3000                                                        │
│  └─▶ API calls proxied to backend                                            │
│                                                                               │
│  Backend (Python HTTP server)                                                 │
│  http://localhost:8787                                                        │
│  └─▶ Same aadesh_core that runs in Lambda                                  │
│                                                                               │
│  Optional: LocalStack (emulates AWS services)                                │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                         │
│  │ DynamoDB     │ │ S3           │ │ OpenSearch   │                         │
│  │ (localhost)  │ │ (localhost)  │ │ (localhost)  │                         │
│  └──────────────┘ └──────────────┘ └──────────────┘                         │
│                                                                               │
│  Optional: Cognito Emulator                                                  │
│  Use fake JWT tokens for local testing                                       │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Local Development Modes

### Mode 1: Pure Local (No Docker)

Use in-memory stores and local filesystem corpus. No AWS services needed.

```bash
# Set environment
export AADESH_ENV=local
export AADESH_STORE_BACKEND=memory
export AADESH_CORPUS_BACKEND=local
export AADESH_AUTHZ_BACKEND=cedar

# Run API
make api

# Run web (separate terminal)
make web
```

This is what `make dev` does.

### Mode 2: LocalStack (AWS Emulation)

Run the same code that deploys to AWS, against LocalStack.

```bash
# Start LocalStack (requires Docker)
docker run -d --name localstack \
  -p 4566:4566 \
  -e SERVICES=dynamodb,s3,es,lambda,events,sts \
  -e DEFAULT_REGION=ap-south-1 \
  localstack/localstack:latest

# Configure environment for LocalStack
export AWS_ENDPOINT_URL=http://localhost:4566
export AADESH_STORE_BACKEND=dynamodb
export AADESH_CORPUS_BACKEND=s3
export AADESH_AUTHZ_BACKEND=cedar

# Create DynamoDB tables (one-time)
aws --endpoint-url=http://localhost:4566 dynamodb create-table \
  --table-name aadesh-parchis \
  --attribute-definitions AttributeName=parchi_id,AttributeType=S \
  --key-schema AttributeName=parchi_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

# Deploy Lambda functions to LocalStack (optional)
samlocal deploy --guided
```

### Mode 3: Hybrid (Local API, Simulated Cognito)

Run the real API locally but simulate Cognito authentication.

```bash
export AADESH_ENV=local
export AADESH_STORE_BACKEND=memory

# Run API with Cognito simulation
make api

# Frontend gets fake JWT tokens from a mock endpoint
# Or bypass auth entirely for local dev:
export NEXT_PUBLIC_API_BASE_URL=http://localhost:8787
```

## Running Tests

### Unit Tests (Offline)

```bash
make test
```

Runs pytest with markers `not integration` and `not requires_index`.
No Docker, no AWS, no network beyond PyPI.

### Integration Tests (LocalStack)

```bash
make test-integration
```

Requires Docker running LocalStack.

### Full Test Suite

```bash
make test-all
```

Runs all tests including integration and index-dependent tests.

### Verification

```bash
make verify          # Re-prove every citation against hashed source bytes
make verify-tamper   # Flip one byte, prove detection works
```

## Frontend Development

### Run Frontend Only

```bash
cd web
npm install
npm run dev
```

The frontend proxies API calls to `http://localhost:8787` by default.

### Environment Variables

Create `web/.env.local`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8787
```

### Inspect Webpack/Next Config

```bash
cd web
npm run build    # Build for production
npm start        # Run production build locally
```

## API Endpoints (Local)

When running `make api`, these endpoints are available:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check, Cedar validation status |
| `/api/supervisor` | GET | Supervisor screen — obligations, stage, site |
| `/api/roster` | GET | Worker roster summary |
| `/api/roster/qr` | POST | Worker QR codes (creates Parchis) |
| `/api/facilitator` | GET | Facilitator redacted view demo |
| `/api/verify` | GET | Corpus verification report |
| `/api/impact` | GET | Public impact aggregation |
| `/api/standing-order` | POST | Create Standing Order (replay demo) |
| `/api/worker/view` | POST | Worker Parchi view by QR payload |
| `/api/worker/acknowledge` | POST | Worker acknowledges own Parchi |
| `/api/cedar/supervisor-acknowledge` | POST | Demo Cedar denial (supervisor can't ack) |

## Cognito in Local Development

For local development, you have several options:

### Option A: Skip Auth (Development Only)

The local API doesn't enforce Cognito auth when `AADESH_ENV=local`.
Frontend can call the API directly.

### Option B: Mock JWT Tokens

Generate a fake JWT for local testing:

```bash
# Install jwt-cli
npm install -g jsonwebtoken

# Create a fake token
jwt signing-secret \
  --payload '{"sub":"worker-001","role":"worker","assigned_site":"example-piling-site"}' \
  --secret change-me

# Use in requests:
curl -H "Authorization: Bearer <token>" http://localhost:8787/api/...
```

### Option C: Cognito Local Emulator

Use [localcognito](https://github.com/fimiama/localcognito) or similar to
run a Cognito-like service locally.

### Option D: AWS Cognito (Real) for Integration Testing

Deploy Cognito to a dev AWS account and point local frontend at it:

```bash
export COGNITO_USER_POOL_ID=<real-pool-id>
export COGNITO_CLIENT_ID=<real-client-id>
export NEXT_PUBLIC_API_BASE_URL=https://<api-id>.execute-api.ap-south-1.amazonaws.com/dev/
```

## Debugging

### API Logs

The local API server logs to stdout. Add debug logging:

```bash
make api DEBUG=1
```

### Lambda Local Debugging

Use `samlocal` (SAM CLI local):

```bash
samlocal local invoke ApiHandler --event events/api-event.json
```

### DynamoDB Local Query

With LocalStack:

```bash
aws --endpoint-url=http://localhost:4566 dynamodb scan \
  --table-name aadesh-parchis
```

## Port Configuration

| Service | Default Port | Configurable |
|---------|--------------|--------------|
| Next.js frontend | 3000 | `PORT` env var |
| Python API server | 8787 | `make api PORT=8787` |
| LocalStack | 4566 | Docker port mapping |
| OpenSearch (local) | 9200 | `AADESH_OPENSEARCH_URL` |

## Common Issues

### Port already in use

```bash
# Find what's using port 8787
lsof -i :8787    # macOS
netstat -tlnp | grep 8787   # Linux

# Or use a different port
make api -- --port 8788
```

### CORS errors in browser

The API server sets `Access-Control-Allow-Origin: *` by default for local dev.
In production, this is restricted to Amplify domains.

### Corpus not found

Ensure `corpus/` directory exists in the project root:

```bash
ls -la corpus/
# Should contain:
#   manifest.json
#   sources/
#   obligations/
```

### Dependencies missing

```bash
make setup   # Recreates venv and installs dependencies
```

## Environment Variables Quick Reference

| Variable | Local Default | AWS Prod |
|----------|---------------|----------|
| `AADESH_ENV` | `local` | `prod` |
| `AADESH_STORE_BACKEND` | `memory` | `dynamodb` |
| `AADESH_CORPUS_BACKEND` | `local` | `s3` |
| `AADESH_AUTHZ_BACKEND` | `cedar` | `cedar` |
| `AADESH_EXPLAIN_BACKEND` | `deterministic` | `deterministic` (or `strands_bedrock`) |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8787` | `https://<api-id>.execute-api...` |
| `AADESH_QR_SIGNING_SECRET` | `change-me-not-a-real-secret` | (Secrets Manager) |

## VS Code Setup

For Python debugging, add to `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: API Server",
      "type": "python",
      "request": "launch",
      "module": "aadesh_web.server",
      "args": ["--port", "8787"],
      "env": {
        "AADESH_ENV": "local",
        "AADESH_STORE_BACKEND": "memory"
      }
    }
  ]
}
```

## Tips

1. **Keep `make verify` green** — citation verification is the centrepiece
2. **Use in-memory stores for quick iteration** — switch to DynamoDB for integration tests
3. **The same aadesh_core runs everywhere** — local, test, Lambda, all identical
4. **Demo data is honest** — always marked as replay/synthetic, never presented as live
