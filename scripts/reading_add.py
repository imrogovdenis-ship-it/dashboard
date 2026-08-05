#!/usr/bin/env python3
"""Add item to dashboard reading.json and optionally push to git.

Usage:
  python3 reading_add.py --url https://example.com --title "Title" --source telegram
  python3 reading_add.py --url https://example.com --tags ai,hermes --note "why"
  echo '{"url":"https://...","title":"..."}' | python3 reading_add.py --stdin

Env:
  READING_JSON  path to reading.json (default: /root/work/dashboard-repo/reading.json)
  READING_PUSH=1  git commit+push after write
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_JSON = Path(os.environ.get("READING_JSON", "/root/work/dashboard-repo/reading.json"))
REPO = DEFAULT_JSON.parent


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slug_id(url: str) -> str:
    host = urlparse(url).netloc.replace("www.", "")[:24] or "item"
    host = re.sub(r"[^a-zA-Z0-9.-]", "", host)
    return f"{host}-{uuid.uuid4().hex[:8]}"


def load(path: Path) -> dict:
    if not path.exists():
        return {"updated": now_iso(), "version": 1, "items": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    data["updated"] = now_iso()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o644)


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("empty url")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def add_item(
    path: Path,
    *,
    url: str,
    title: str = "",
    source: str = "manual",
    note: str = "",
    tags: list[str] | None = None,
    status: str = "inbox",
) -> dict:
    url = normalize_url(url)
    data = load(path)
    items = data.setdefault("items", [])
    # dedupe by url
    for it in items:
        if it.get("url") == url and it.get("status") != "done":
            it["title"] = title or it.get("title") or url
            if note:
                it["note"] = note
            if tags:
                it["tags"] = sorted(set((it.get("tags") or []) + tags))
            it["touched_at"] = now_iso()
            save(path, data)
            return it

    item = {
        "id": slug_id(url),
        "title": title.strip() or url,
        "url": url,
        "source": source,
        "status": status,
        "tags": tags or [],
        "note": note or "",
        "added_at": now_iso(),
    }
    items.insert(0, item)
    save(path, data)
    return item


def git_push(path: Path) -> str:
    repo = path.parent
    subprocess.run(["git", "add", path.name], cwd=repo, check=True)
    st = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo)
    if st.returncode == 0:
        return "no changes"
    msg = f"reading: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    subprocess.run(["git", "commit", "-m", msg], cwd=repo, check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=repo, check=True)
    return "pushed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--title", default="")
    ap.add_argument("--source", default="manual")
    ap.add_argument("--note", default="")
    ap.add_argument("--tags", default="", help="comma-separated")
    ap.add_argument("--status", default="inbox")
    ap.add_argument("--json-path", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--push", action="store_true", default=os.environ.get("READING_PUSH") == "1")
    args = ap.parse_args()

    if args.stdin:
        payload = json.load(sys.stdin)
        url = payload.get("url")
        title = payload.get("title", "")
        source = payload.get("source", args.source)
        note = payload.get("note", "")
        tags = payload.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        status = payload.get("status", "inbox")
    else:
        if not args.url:
            ap.error("--url or --stdin required")
        url, title, source, note, status = args.url, args.title, args.source, args.note, args.status
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    item = add_item(
        args.json_path,
        url=url,
        title=title,
        source=source,
        note=note,
        tags=tags,
        status=status,
    )
    print(json.dumps({"ok": True, "item": item}, ensure_ascii=False))
    if args.push:
        print(json.dumps({"git": git_push(args.json_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
