#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_REPO="michaelhart/meshcore-mqtt-broker"
UPSTREAM_REF="main"
IMAGE_NAME="ghcr.io/ipnet-mesh/meshcore-mqtt-broker"
PLATFORM="linux/amd64,linux/arm64"
WORKDIR="$(mktemp -d)"
BUILD_ARGS=()

cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      UPSTREAM_REF="$2"
      shift 2
      ;;
    --platform)
      PLATFORM="$2"
      shift 2
      ;;
    *)
      BUILD_ARGS+=("$1")
      shift
      ;;
  esac
done

echo "==> Cloning ${UPSTREAM_REPO} @ ${UPSTREAM_REF} into ${WORKDIR}"
git clone --depth 1 --branch "${UPSTREAM_REF}" "https://github.com/${UPSTREAM_REPO}.git" "${WORKDIR}/source"

echo "==> Copying custom Dockerfile"
cp "$(dirname "$0")/Dockerfile" "${WORKDIR}/source/Dockerfile"

echo "==> Building ${IMAGE_NAME}:latest"
docker buildx build \
  --platform "${PLATFORM}" \
  -t "${IMAGE_NAME}:latest" \
  -t "${IMAGE_NAME}:sha-$(git -C "${WORKDIR}/source" rev-parse --short HEAD)" \
  "${WORKDIR}/source" \
  "${BUILD_ARGS[@]}"

echo "==> Done"
