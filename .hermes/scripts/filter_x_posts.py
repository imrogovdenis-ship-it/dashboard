#!/usr/bin/env python3
"""Filter X timeline JSON, translate to Russian, write top 10 to news.json.

Learns from news_prefs.json:
  - keywords: explicit interest terms (strong boost)
  - term_scores: tokens learned from +/- votes
  - source_scores: @handles learned from +/- votes
  - category_scores: ai/biz/market/tech weights
  - hidden_urls: hard suppress
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

from googletrans import Translator

REPO = Path("/root/work/dashboard-repo")
PREFS_PATH = REPO / "news_prefs.json"
OUT_PATH = REPO / "news.json"

translator = Translator()

STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is", "are",
    "this", "that", "it", "as", "at", "by", "from", "be", "was", "were", "will", "has",
    "have", "had", "not", "but", "you", "we", "they", "their", "our", "your", "its",
    "http", "https", "www", "com", "rt", "via", "just", "about", "more", "than", "into",
    "over", "after", "before", "что", "как", "это", "для", "при", "или", "если", "уже",
}


def load_prefs() -> dict:
    if not PREFS_PATH.exists():
        return {
            "keywords": [],
            "term_scores": {},
            "source_scores": {},
            "category_scores": {},
            "hidden_urls": [],
            "votes": [],
        }
    try:
        data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        data.setdefault("keywords", [])
        data.setdefault("term_scores", {})
        data.setdefault("source_scores", {})
        data.setdefault("category_scores", {})
        data.setdefault("hidden_urls", [])
        data.setdefault("votes", [])
        return data
    except Exception as e:
        print(f"  [prefs] load error: {e}", file=sys.stderr)
        return {
            "keywords": [],
            "term_scores": {},
            "source_scores": {},
            "category_scores": {},
            "hidden_urls": [],
            "votes": [],
        }


def translate_text(text, max_len=250):
    if not text or len(text.strip()) < 5:
        return text
    try:
        result = translator.translate(text[:1000], dest="ru")
        translated = result.text
        if len(translated) > max_len:
            translated = translated[: max_len - 3] + "..."
        return translated
    except Exception as e:
        print(f"  [translate error: {e}], keeping original", file=sys.stderr)
        return text[:max_len] + ("..." if len(text) > max_len else "")


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9][a-zA-Zа-яА-ЯёЁ0-9+.#-]{2,}", text.lower())
    out = []
    for w in words:
        w = w.replace("ё", "е")
        if w in STOP:
            continue
        if w.isdigit():
            continue
        out.append(w)
    return out


def main():
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    prefs = load_prefs()
    keywords = [str(k).strip().lower().replace("ё", "е") for k in prefs.get("keywords") or [] if str(k).strip()]
    term_scores = {str(k).lower().replace("ё", "е"): float(v) for k, v in (prefs.get("term_scores") or {}).items()}
    source_scores = {str(k): float(v) for k, v in (prefs.get("source_scores") or {}).items()}
    category_scores = {str(k): float(v) for k, v in (prefs.get("category_scores") or {}).items()}
    hidden = set(prefs.get("hidden_urls") or [])

    posts = data.get("data", [])
    includes = data.get("includes", {})
    users = {u["id"]: u["username"] for u in includes.get("users", [])}

    def score_post(post):
        t = post.get("text", "").lower().replace("ё", "е")
        metrics = post.get("public_metrics", {})
        likes = metrics.get("like_count", 0)
        retweets = metrics.get("retweet_count", 0)
        replies = metrics.get("reply_count", 0)
        impressions = metrics.get("impression_count", 0)
        engagement = likes + retweets * 2 + replies * 0.5 + impressions * 0.01

        score = 0.0
        category = "tech"

        # 1 — Гермес / автономные агенты
        hermes_kw = [
            "hermes", "hermes agent", "autonomous agent", "ai agent",
            "agentic", "agent framework", "multi-agent", "agent orchestration",
        ]
        for kw in hermes_kw:
            if kw in t:
                score += 100
                score += engagement * 0.15
                category = "ai"

        # 2 — Крипта на стыке ИИ
        crypto_ai = [
            "crypto ai", "ai crypto", "crypto + ai", "ai + crypto",
            "decentralized ai", "blockchain ai", "token ai",
            "ai token", "crypto", "bitcoin", "ethereum", "solana",
            "defi", "web3 ai", "nft", "blockchain",
        ]
        for kw in crypto_ai:
            if kw in t:
                score += 90
                score += engagement * 0.15
                if category == "tech":
                    category = "market"

        # 3 — Фундаментальные ИИ новости
        ai_kw = [
            "llm", "gpt", "claude", "openai", "anthropic", "deepseek",
            "mixture of experts", "reasoning model", "frontier model",
            "agi", "ai breakthrough", "foundation model", "ai model",
            "training run", "inference", "open source ai", "transformer",
        ]
        for kw in ai_kw:
            if kw in t:
                score += 70
                score += engagement * 0.1
                if category in ("tech",):
                    category = "ai"

        # 4 — Сделки / M&A
        deal_kw = [
            "acquisition", "merger", "m&a", "acquired", "buyout",
            "investment", "funding round", "series", "valuation",
            "ipo", "spac", "billion", "deal", "partnership",
            "joint venture", "strategic investment",
        ]
        for kw in deal_kw:
            if kw in t:
                score += 60
                score += engagement * 0.1
                if category in ("tech", "market"):
                    category = "biz"

        # 5 — AI Class / Portal / VR
        other_kw = [
            ("aiclass", 45, ["ai class", "ai education", "learn ai", "ai course"]),
            (
                "portal",
                40,
                [
                    "portal tech", "portal vr", "vr", "virtual reality",
                    "ar", "augmented reality", "robotics", "ai glasses",
                    "smart glasses", "vision pro", "quest",
                ],
            ),
            (
                "tech",
                10,
                ["apple", "google", "microsoft", "meta", "nvidia", "tesla", "open source", "github", "launch"],
            ),
        ]
        for cat, w, kwords in other_kw:
            for kw in kwords:
                if kw in t:
                    score += w
                    score += engagement * 0.05
                    if category == "tech":
                        category = cat if cat != "aiclass" else "ai"

        # Learned: explicit keywords (strong)
        for kw in keywords:
            if kw and kw in t:
                score += 120
                score += engagement * 0.2

        # Learned: term scores from +/- votes
        for tok in set(tokens(t)):
            w = term_scores.get(tok, 0.0)
            if w:
                score += w * 8.0

        # Learned: source scores
        author = users.get(post.get("author_id", ""), "unknown")
        src = "@" + author
        sw = source_scores.get(src, source_scores.get(author, 0.0))
        if sw:
            score += sw * 12.0

        # Learned: category preference
        cw = category_scores.get(category, 0.0)
        if cw:
            score += cw * 6.0

        # Penalties
        if post.get("in_reply_to_user_id"):
            score *= 0.3
        if t.startswith("rt @"):
            score *= 0.5

        # Hard suppress hidden urls
        pid = str(post.get("id", ""))
        url = f"https://x.com/{author}/status/{pid}"
        if url in hidden or pid in hidden:
            score = -1e9

        return score, category

    scored = [(score_post(p), p) for p in posts]
    scored.sort(key=lambda x: -x[0][0])
    # drop hard-suppressed
    scored = [x for x in scored if x[0][0] > -1e8]
    top10 = scored[:10]

    items = []
    now = datetime.datetime.now(datetime.timezone.utc)
    for (s, cat), p in top10:
        author = users.get(p.get("author_id", ""), "unknown")
        text = p.get("text", "")
        text_clean = re.sub(r"^RT\s+@\w+:\s*", "", text)

        print(f"  Translating post from @{author} (score={s:.1f})...", file=sys.stderr)
        # Keep a short label + longer body (dashboard merges into one block).
        title_en = text_clean[:80]
        dot = title_en.find(".")
        if dot > 20:
            title_en = title_en[: dot + 1]
        elif len(text_clean) > 80:
            title_en += "..."
        title_ru = translate_text(title_en, 80)

        # ~3 sentences worth of original text for the unified card body
        summary_en = text_clean[:480] + ("..." if len(text_clean) > 480 else "")
        summary_ru = translate_text(summary_en, 480)

        items.append(
            {
                "id": str(p.get("id", "")),
                "category": cat,
                "title": title_ru.strip(),
                "summary": summary_ru.strip(),
                "source": "@" + author,
                "url": f"https://x.com/{author}/status/{p['id']}",
                "date": p.get("created_at", now.isoformat()),
                "score": round(float(s), 2),
            }
        )

    if not items:
        items.append(
            {
                "category": "ai",
                "title": "Лента временно пуста",
                "summary": "Нет новых постов в ленте. Следующий сбор через 12ч.",
                "source": "Hermes AI",
                "date": now.isoformat(),
            }
        )

    result = {
        "updated": now.isoformat(),
        "prefs_keywords": keywords[:20],
        "items": items,
    }

    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    top_s = f"{top10[0][0][0]:.1f}" if top10 else "n/a"
    print(f"✓ Written {len(items)} items to news.json (top score: {top_s}; keywords={len(keywords)})")


if __name__ == "__main__":
    main()
