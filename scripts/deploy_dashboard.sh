#!/usr/bin/env bash
set -euo pipefail

# Deploy Quantuzo dashboard to HuggingFace Spaces (static SDK).
#
# Requires HF_TOKEN environment variable (or set in .env).
# Usage: ./scripts/deploy_dashboard.sh

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DASHBOARD_DIR="$REPO_ROOT/dashboard"
SPACE_REPO="burakaydinofficial/Quantuzo"
CLONE_DIR="$(mktemp -d)"

# Load .env if present
if [[ -f "$REPO_ROOT/.env" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
fi

if [[ -z "${HF_TOKEN:-}" ]]; then
  echo "Error: HF_TOKEN is not set. Export it or add to .env" >&2
  exit 1
fi

# Build
echo "Building dashboard..."
(cd "$DASHBOARD_DIR" && npm run build)

# Clone Space repo
echo "Cloning Space repo..."
git clone "https://user:${HF_TOKEN}@huggingface.co/spaces/${SPACE_REPO}" "$CLONE_DIR"

# Preserve .git, replace everything else
find "$CLONE_DIR" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +

# Copy build output
cp -r "$DASHBOARD_DIR/dist/"* "$CLONE_DIR/"

# Write Space metadata
cat > "$CLONE_DIR/README.md" << 'EOF'
---
title: Quantuzo Dashboard
emoji: 📊
sdk: static
app_file: index.html
pinned: false
---
EOF

# Push
cd "$CLONE_DIR"
git add -A
if git diff --cached --quiet; then
  echo "No changes to deploy."
else
  git commit -m "Deploy dashboard"
  git push
  echo "Deployed to https://huggingface.co/spaces/${SPACE_REPO}"
fi

# Cleanup
rm -rf "$CLONE_DIR"
