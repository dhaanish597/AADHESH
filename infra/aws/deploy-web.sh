#!/usr/bin/env sh
set -eu

fail() { printf 'deploy-web: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"; }

need git
need aws
need npm
need jq
need zip
need curl

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || fail "run this inside the Aadesh git repository"
STACK="${STACK:-}"
[ -n "$STACK" ] || fail "set STACK to the deployed CloudFormation stack name (for example: STACK=aadesh-prod make deploy-web)"

OUTPUTS="$(aws cloudformation describe-stacks --stack-name "$STACK" --query 'Stacks[0].Outputs' --output json)" || fail "could not read outputs for CloudFormation stack '$STACK'"
API_URL="$(printf '%s' "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="ApiUrl") | .OutputValue' | head -n 1)"
APP_ID="$(printf '%s' "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="AmplifyAppId") | .OutputValue' | head -n 1)"
[ -n "$API_URL" ] && [ "$API_URL" != null ] || fail "stack '$STACK' does not expose ApiUrl"
[ -n "$APP_ID" ] && [ "$APP_ID" != null ] || fail "stack '$STACK' does not expose AmplifyAppId"

WEB="$ROOT/web"
OUT="$WEB/out"
[ -f "$WEB/package-lock.json" ] || fail "missing web/package-lock.json"
(cd "$WEB" && npm ci) || fail "npm ci failed in web/"
(cd "$WEB" && AADHESH_STATIC_EXPORT=1 NEXT_PUBLIC_AADESH_DEMO=0 NEXT_PUBLIC_API_BASE_URL="$API_URL" NEXT_PUBLIC_LIVE_URL="https://main.$APP_ID.amplifyapp.com" npm run build) || fail "static frontend build failed"
[ -d "$OUT" ] || fail "Next.js build completed without creating web/out"
sh "$ROOT/infra/aws/normalize-static-export.sh" || fail "could not prepare static route payloads"

TMP="$(mktemp -d)" || fail "could not create temporary deployment directory"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
ARCHIVE="$TMP/aadesh-web.zip"
(cd "$OUT" && zip -qr "$ARCHIVE" .) || fail "could not archive web/out"

DEPLOYMENT="$(aws amplify create-deployment --app-id "$APP_ID" --branch-name main --output json)" || fail "Amplify could not create a deployment"
UPLOAD_URL="$(printf '%s' "$DEPLOYMENT" | jq -r '.zipUploadUrl')"
JOB_ID="$(printf '%s' "$DEPLOYMENT" | jq -r '.jobId')"
[ -n "$UPLOAD_URL" ] && [ "$UPLOAD_URL" != null ] || fail "Amplify returned no upload URL"
[ -n "$JOB_ID" ] && [ "$JOB_ID" != null ] || fail "Amplify returned no job id"
curl --fail --silent --show-error -X PUT -H 'Content-Type: application/zip' --upload-file "$ARCHIVE" "$UPLOAD_URL" || fail "upload to Amplify failed"
aws amplify start-deployment --app-id "$APP_ID" --branch-name main --job-id "$JOB_ID" >/dev/null || fail "Amplify could not start the deployment"

printf 'Amplify job %s' "$JOB_ID"
while :; do
  JOB="$(aws amplify get-job --app-id "$APP_ID" --branch-name main --job-id "$JOB_ID" --output json)" || fail "could not read Amplify deployment status"
  STATUS="$(printf '%s' "$JOB" | jq -r '.job.summary.status')"
  case "$STATUS" in
    SUCCEED) printf '\nLive URL: https://main.%s.amplifyapp.com\n' "$APP_ID"; break ;;
    FAILED|CANCELLED) printf '\n' >&2; printf '%s\n' "$JOB" | jq -r '.job.summary.statusReason // "Amplify deployment failed"' >&2; exit 1 ;;
    *) printf '.'; sleep 10 ;;
  esac
done
