# Reading system · Personal OS + Obsidian

## Layers

| Layer | Role |
|-------|------|
| **Phone** | Capture in ≤3 taps (Share → Telegram bot / Shortcut → webhook) |
| **Personal OS** | Surface: inbox triage on dashboard |
| **Obsidian** | Source of truth for notes & long-term reading |
| **reading.json** | Machine index the OS reads (git-synced) |

## Obsidian vault layout

```
Reading/
  inbox.md              # human queue (optional mirror)
  notes/                # one note per deep-read item
  reading.json          # optional local copy of machine index
```

### inbox.md format (append-only)

```markdown
- [ ] 2026-08-04 https://example.com Title here #tag
```

### notes/YYYY-MM-DD-slug.md

```markdown
---
url: https://...
status: inbox|reading|done|later
tags: []
added: 2026-08-04
---

# Title

## Why saved

## Notes
```

## Phone · 3 clicks

### A) Telegram (recommended)
1. Share link → choose secretary/reading bot  
2. Send  
3. Done — item appears in Personal OS after push

Bot/Hermes writes `reading.json` via `scripts/reading_add.py`.

### B) iOS Shortcut / Android HTTP shortcut
POST JSON to capture webhook:
```json
{"url":"https://...","title":"optional","note":"","tags":["ai"]}
```

### C) Obsidian mobile
Share → Obsidian → append to `Reading/inbox.md`  
(then sync vault; optional Hermes job converts inbox.md → reading.json)

## Capture script (server)

```bash
python3 scripts/reading_add.py --url "https://..." --title "..." --source telegram
# updates reading.json + git commit/push
```

## Personal OS

Panel **Чтение** loads `reading.json?t=...`  
Statuses: inbox → reading → done / later  
Local pin doesn't replace server list (server is SoT for cross-device).
