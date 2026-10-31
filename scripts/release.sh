#!/usr/bin/env bash
# Create a release tag and deploy it to EC2.
# Usage: ./scripts/release.sh <tag> [commit-sha]
#   <tag>         e.g. release-2026-06-10  (required)
#   [commit-sha]  defaults to HEAD
set -e

RELEASE_TAG="${1:-}"
COMMIT="${2:-HEAD}"

if [[ -z "$RELEASE_TAG" ]]; then
  echo "ERROR: release tag required."
  echo "Usage: ./scripts/release.sh release-YYYY-MM-DD [commit-sha]"
  echo ""
  echo "Example (tag HEAD):"
  echo "  ./scripts/release.sh release-$(date +%Y-%m-%d)"
  echo ""
  echo "Example (tag a specific commit):"
  echo "  ./scripts/release.sh release-$(date +%Y-%m-%d) abc1234"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Tagging $COMMIT as $RELEASE_TAG ==="
git tag "$RELEASE_TAG" "$COMMIT"

echo "=== Pushing tag ==="
git push origin "$RELEASE_TAG"

echo "=== Deploying ==="
"$SCRIPT_DIR/deploy.sh" "$RELEASE_TAG"
