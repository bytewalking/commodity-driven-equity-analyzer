#!/usr/bin/env bash
# build.sh — Build the Docker image for Commodity-driven Equity Analyzer
# Usage:
#   ./build.sh              # build only
#   ./build.sh --save       # build + export as .tar for NAS transfer
#   ./build.sh --save --push registry.example.com/myuser   # build + push to registry

set -euo pipefail

IMAGE_NAME="commodity-equity-analyzer"
IMAGE_TAG="latest"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"
EXPORT_FILE="${IMAGE_NAME}.tar"

# ---- parse arguments ----
SAVE=false
PUSH_REGISTRY=""

for arg in "$@"; do
  case "$arg" in
    --save)   SAVE=true ;;
    --push)   shift; PUSH_REGISTRY="$1" ;;
  esac
done

# ---- helpers ----
log()  { echo "[$(date '+%H:%M:%S')] $*"; }
die()  { echo "ERROR: $*" >&2; exit 1; }

command -v docker &>/dev/null || die "Docker is not installed or not in PATH."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

[ -f Dockerfile ] || die "Dockerfile not found in $(pwd)"

# ---- build ----
log "Building image: ${FULL_IMAGE}"
docker build \
  --pull \
  --tag "${FULL_IMAGE}" \
  --label "build.date=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --label "build.version=$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" \
  .

log "Build complete."
docker images "${IMAGE_NAME}"

# ---- export to tar ----
if [ "$SAVE" = true ]; then
  log "Exporting image to ${EXPORT_FILE} ..."
  docker save "${FULL_IMAGE}" | gzip > "${EXPORT_FILE}.gz"
  SIZE=$(du -sh "${EXPORT_FILE}.gz" | cut -f1)
  log "Saved: ${EXPORT_FILE}.gz  (${SIZE})"
  echo ""
  echo "  Transfer to NAS:"
  echo "    scp ${EXPORT_FILE}.gz user@<nas-ip>:/path/to/destination/"
  echo ""
  echo "  Load on NAS:"
  echo "    docker load < ${EXPORT_FILE}.gz"
  echo "    docker compose up -d"
fi

# ---- push to registry ----
if [ -n "$PUSH_REGISTRY" ]; then
  REMOTE_TAG="${PUSH_REGISTRY}/${FULL_IMAGE}"
  log "Tagging as ${REMOTE_TAG} ..."
  docker tag "${FULL_IMAGE}" "${REMOTE_TAG}"
  log "Pushing to registry ..."
  docker push "${REMOTE_TAG}"
  log "Push complete: ${REMOTE_TAG}"
fi

log "Done."
