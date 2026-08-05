#!/usr/bin/env python3
"""Merge news preference updates into news_prefs.json and optionally git-push.

Usage:
  echo '{"op":"vote","url":"...","v":1,"title":"...","source":"@x","category":"ai"}' | python3 news_prefs_update.py --stdin --push
  echo '{"op":"keyword_add","keyword":"jetson"}' | python3 news_prefs_update.py --stdin --push
  echo '{"op":"keyword_del","keyword":"jetson"}' | python3 news_prefs_update.py --stdin --push
  echo '{"op":"replace","prefs":{...}}' | python3 news_prefs_update.py --stdin --push
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PREFS = REPO / "news_prefs.json"

STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is", "are",
    "this", "that", "it", "as", "at", "by", "from", "be", "was", "were", "will", "has",
    "have", "had", "not", "but", "you", "we", "they", "http", "https", "www", "com", "rt",
    "что", "как", "это", "для", "при", "или",
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load() -> dict:
    if PREFS.exists():
        try:
            d = json.loads(PREFS.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {
        "updated": now_iso(),
        "keywords": [],
        "term_scores": {},
        "source_scores": {},
        "category_scores": {},
        "votes": [],
        "hidden_urls": [],
    }


def save(d: dict) -> None:
    d["updated"] = now_iso()
    PREFS.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9][a-zA-Zа-яА-ЯёЁ0-9+.#-]{2,}", (text or "").lower())
    out = []
    for w in words:
        w = w.replace("ё", "е")
        if w in STOP or w.isdigit():
            continue
        out.append(w)
    return out[:24]


def clamp(x: float, lo: float = -50.0, hi: float = 50.0) -> float:
    return max(lo, min(hi, x))


def apply_vote(prefs: dict, payload: dict) -> dict:
    v = int(payload.get("v") or 0)
    if v not in (-1, 1):
        raise ValueError("v must be +1 or -1")
    url = str(payload.get("url") or "").strip()
    title = str(payload.get("title") or "")
    summary = str(payload.get("summary") or "")
    source = str(payload.get("source") or "").strip()
    category = str(payload.get("category") or "").strip() or "tech"

    prefs.setdefault("term_scores", {})
    prefs.setdefault("source_scores", {})
    prefs.setdefault("category_scores", {})
    prefs.setdefault("votes", [])
    prefs.setdefault("hidden_urls", [])

    delta = 3.0 * v
    if source:
        prefs["source_scores"][source] = clamp(float(prefs["source_scores"].get(source, 0)) + delta)
    if category:
        prefs["category_scores"][category] = clamp(
            float(prefs["category_scores"].get(category, 0)) + (1.5 * v)
        )

    for tok in tokens(f"{title} {summary}"):
        prefs["term_scores"][tok] = clamp(float(prefs["term_scores"].get(tok, 0)) + (1.0 * v))

    # prune near-zero terms
    prefs["term_scores"] = {
        k: round(float(val), 2)
        for k, val in prefs["term_scores"].items()
        if abs(float(val)) >= 0.5
    }
    # keep top 200 by abs weight
    if len(prefs["term_scores"]) > 200:
        top = sorted(prefs["term_scores"].items(), key=lambda kv: -abs(float(kv[1])))[:200]
        prefs["term_scores"] = {k: v for k, v in top}

    if v < 0 and url:
        if url not in prefs["hidden_urls"]:
            prefs["hidden_urls"].append(url)
        prefs["hidden_urls"] = prefs["hidden_urls"][-200:]
    if v > 0 and url and url in prefs["hidden_urls"]:
        prefs["hidden_urls"] = [u for u in prefs["hidden_urls"] if u != url]

    prefs["votes"].append(
        {
            "url": url,
            "v": v,
            "title": title[:120],
            "source": source,
            "category": category,
            "at": now_iso(),
        }
    )
    prefs["votes"] = prefs["votes"][-300:]
    return prefs


def apply_keyword(prefs: dict, kw: str, add: bool = True) -> dict:
    kw = kw.strip().replace("ё", "е")
    if not kw:
        raise ValueError("empty keyword")
    if len(kw) > 64:
        kw = kw[:64]
    kws = [str(x) for x in prefs.get("keywords") or []]
    low = {x.lower() for x in kws}
    if add:
        if kw.lower() not in low:
            kws.append(kw)
    else:
        kws = [x for x in kws if x.lower() != kw.lower()]
    prefs["keywords"] = kws[:80]
    return prefs


def _git(args: list[str]) -> subprocess.CompletedProcess:
    # Avoid broken global ~/.gitconfig mounts inside containers.
    base = [
        "git",
        "-c",
        "user.email=hermes@ai-class.tech",
        "-c",
        "user.name=Hermes Agent",
        "-c",
        "safe.directory=*",
    ]
    return subprocess.run(base + args, cwd=REPO, check=True, capture_output=True, text=True)


def git_push() -> str:
    _git(["add", "news_prefs.json"])
    st = subprocess.run(
        ["git", "-c", "safe.directory=*", "diff", "--cached", "--quiet"],
        cwd=REPO,
    )
    if st.returncode == 0:
        return "no_change"
    msg = f"news prefs: {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M UTC}"
    _git(["commit", "-m", msg])
    _git(["push", "origin", "main"])
    return "pushed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--file")
    args = ap.parse_args()

    if args.stdin:
        payload = json.load(sys.stdin)
    elif args.file:
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    else:
        print("need --stdin or --file", file=sys.stderr)
        return 2

    prefs = load()
    op = str(payload.get("op") or "").strip()

    if op == "vote":
        prefs = apply_vote(prefs, payload)
    elif op == "keyword_add":
        prefs = apply_keyword(prefs, str(payload.get("keyword") or ""), add=True)
    elif op == "keyword_del":
        prefs = apply_keyword(prefs, str(payload.get("keyword") or ""), add=False)
    elif op == "replace":
        incoming = payload.get("prefs") or {}
        if not isinstance(incoming, dict):
            raise ValueError("prefs must be object")
        # merge wisely
        for key in ("keywords", "term_scores", "source_scores", "category_scores", "hidden_urls", "votes"):
            if key in incoming:
                prefs[key] = incoming[key]
    elif op == "sync":
        # full client snapshot
        incoming = payload.get("prefs") or payload
        if isinstance(incoming.get("keywords"), list):
            prefs["keywords"] = [str(x)[:64] for x in incoming["keywords"]][:80]
        if isinstance(incoming.get("term_scores"), dict):
            prefs["term_scores"] = {
                str(k)[:48]: clamp(float(v)) for k, v in list(incoming["term_scores"].items())[:200]
            }
        if isinstance(incoming.get("source_scores"), dict):
            prefs["source_scores"] = {
                str(k)[:48]: clamp(float(v)) for k, v in list(incoming["source_scores"].items())[:100]
            }
        if isinstance(incoming.get("category_scores"), dict):
            prefs["category_scores"] = {
                str(k)[:24]: clamp(float(v)) for k, v in list(incoming["category_scores"].items())[:20]
            }
        if isinstance(incoming.get("hidden_urls"), list):
            prefs["hidden_urls"] = [str(u)[:300] for u in incoming["hidden_urls"]][-200:]
        if isinstance(incoming.get("votes"), list):
            prefs["votes"] = incoming["votes"][-300:]
    else:
        raise ValueError(f"unknown op: {op}")

    save(prefs)
    result = {"ok": True, "op": op, "keywords": prefs.get("keywords", []), "updated": prefs.get("updated")}
    if args.push:
        try:
            result["git"] = git_push()
        except Exception as e:
            result["git"] = f"error:{e}"
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        raise SystemExit(1)
