#!/usr/bin/env bash
# Fetch top posts from X timeline, filter, write to news.json, push to GitHub
set -euo pipefail

REPO_DIR="/root/work/dashboard-repo"
cd "$REPO_DIR"

# 1. Get 100 timeline posts, save to temp
TMPFILE=$(mktemp /tmp/x_timeline_XXXXX.json)
xurl timeline -n 100 > "$TMPFILE" 2>/dev/null

# 2. Filter and rank by priority topics
/tmp/whisper_env2/bin/python3 "$REPO_DIR/.hermes/scripts/filter_x_posts.py" "$TMPFILE"

# 3. Git commit and push
cd "$REPO_DIR"
git add news.json
if git diff --cached --quiet; then
  echo "No changes in news.json"
else
  git commit -m "X news: $(date -u '+%Y-%m-%d %H:%M UTC')"
  git push origin main 2>&1
  echo "Pushed to GitHub"
fi

rm -f "$TMPFILE"