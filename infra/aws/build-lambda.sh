#!/usr/bin/env bash
# Assemble the Lambda deployment artefact.
#
# Why this script exists at all, rather than `sam build --use-container`: `cedarpy` is the real
# Cedar engine, distributed as a NATIVE wheel. A build on the developer's Windows machine would
# fetch a Windows wheel and the deployed function would import-fail at first request. So the
# artefact is assembled here with explicitly-targeted Linux wheels, and the policy engine that
# runs in production is the same pinned 4.12.1 the tests run against.
#
# Everything the functions need at runtime lives in ONE layer:
#
#   build/lambda-layer/python/aadesh_core        the deterministic core
#   build/lambda-layer/python/aadesh_adapters    the AWS adapters
#   build/lambda-layer/python/aadesh_app         the shared application
#   build/lambda-layer/python/aadesh_cli         `aadesh_cli.verify` (the verification screen)
#   build/lambda-layer/python/aadesh_aws         the Lambda handlers + the bundled Cedar policy
#   build/lambda-layer/python/{cedarpy,jsonschema,...}   third-party, Linux wheels
#
# and the Cedar policy set is copied in from `infra/cedar/` so the deployed authorizer is the
# same artefact that was reviewed, not a file fetched from a bucket at runtime.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="$ROOT/build"
LAYER="$OUT/lambda-layer"
PY_TARGET="$LAYER/python"

# Lambda runs x86_64 here. x86_64 is chosen over arm64 only because the manylinux wheel tag for
# it is the one every dependency publishes without exception, and a build that cannot resolve a
# native wheel is a build nobody can reproduce.
PLATFORM="${AADESH_LAMBDA_PLATFORM:-x86_64-manylinux_2_17}"
PY_VERSION="${AADESH_LAMBDA_PY_VERSION:-3.13}"

# uv is used rather than pip because uv's `--python-platform` resolves the FULL dependency
# tree for the target platform -- including the transitive native wheel (`rpds-py`) that
# jsonschema needs and that a naive `pip download --platform` can silently miss.
UV="${UV:-uv}"

echo "==> cleaning $OUT"
rm -rf "$LAYER" "$OUT/placeholder"
mkdir -p "$PY_TARGET" "$OUT/placeholder"

echo "==> copying first-party packages"
for pkg in aadesh_core aadesh_adapters aadesh_app aadesh_cli aadesh_aws; do
  cp -r "$ROOT/services/$pkg" "$PY_TARGET/$pkg"
done

echo "==> bundling the Cedar policy set (the deployed authorization boundary)"
rm -rf "$PY_TARGET/aadesh_aws/cedar"
mkdir -p "$PY_TARGET/aadesh_aws/cedar"
cp "$ROOT/infra/cedar/policies.cedar" \
   "$ROOT/infra/cedar/denials.json" \
   "$ROOT/infra/cedar/schema.cedarschema.json" \
   "$PY_TARGET/aadesh_aws/cedar/"

echo "==> stripping caches and host-only scripts"
find "$PY_TARGET" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find "$PY_TARGET" -type f -name '*.pyc' -delete 2>/dev/null || true
# Console scripts resolved for the build host are useless (and confusing) inside Lambda.
rm -rf "$PY_TARGET/bin"

echo "==> resolving Linux wheels for $PLATFORM / python $PY_VERSION"
"$UV" pip install \
  --quiet \
  --target "$PY_TARGET" \
  --python-platform "$PLATFORM" \
  --python-version "$PY_VERSION" \
  --only-binary :all: \
  "cedarpy==4.12.1" "jsonschema>=4.23"

# A Lambda function's own package cannot be an empty zip, and every handler here is imported
# from the layer. So each function points at this one-line placeholder package.
cat > "$OUT/placeholder/aadesh_bootstrap.py" <<'PY'
"""Placeholder package. The handler code lives in the AadeshCodeLayer, so the function's own
deployment package only has to be non-empty."""

__all__: list[str] = []
PY

echo "==> layer size"
du -sh "$LAYER" 2>/dev/null || true
echo "==> done: $LAYER"
