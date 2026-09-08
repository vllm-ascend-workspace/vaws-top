#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
npm ci --no-audit --no-fund
npm run build
exec uv build "$@"
