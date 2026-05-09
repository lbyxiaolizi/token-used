# TokenUsed

> **Local-only token usage plugins for [UsageBoard](https://github.com/marsmay/UsageBoard)**, aggregating Claude Code / Gemini CLI / Codex CLI sessions into one macOS menu-bar dashboard.

[简体中文](./README_ZH.md) · English

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE) ![Platform](https://img.shields.io/badge/platform-macOS%2013%2B-lightgrey)

<p align="center">
  <img src="images/menubar-panel.png" alt="UsageBoard menu-bar panel" width="425"><br>
  <sub>Usage Overview (hero total + per-model rows + right-column token count) atop per-CLI panels</sub>
</p>

<details>
<summary>📊 Click to see expanded 7-day charts</summary>

<p align="center">
  <img src="images/today-overview-expanded.png" alt="Usage Overview with 7-day stacked chart" width="425">
  <img src="images/cli-panels-expanded.png" alt="Per-CLI panels with 7-day charts" width="425"><br>
  <sub>Click the chevron under any panel to expand its 7-day stacked bar chart by model</sub>
</p>

</details>

---

## ✨ Features

- **Zero remote API calls** — everything is read from local JSONL/JSON session files; no ChatGPT subscription or quota API needed.
- **Three CLIs in one panel** — Claude Code, Gemini CLI, Codex CLI usage aggregated by model.
- **Today overview + 7/30 day chart** — a hero card shows today's total across all CLIs, plus a stacked bar chart by model.
- **Auto-hide empty panels** — if you've never used a CLI (e.g. Gemini), its panel disappears automatically.
- **Right-column token count** — UsageBoard's reset-time slot is repurposed via the `trailingText` field to show the per-model token count.
- **Native macOS WidgetKit project included** — code-complete in `widget/`; gallery distribution requires a paid Apple Developer Program account (see [Native Widget](#native-widget-status)).

---

## 📋 Requirements

| Component | Version | Notes |
|---|---|---|
| macOS | 13.0 + | UsageBoard requirement |
| Python 3 | 3.8 + | System Python or Homebrew both fine |
| [UsageBoard](https://github.com/marsmay/UsageBoard) | upstream `main` | Will be patched and rebuilt locally |
| Swift toolchain | 6.2 + | Only needed if you build UsageBoard from source |
| Xcode 16 + | optional | Only needed if you also build the native widget app |

You also need **at least one** of these CLIs to have produced session data:

- Claude Code → `~/.claude/projects/**/*.jsonl`
- Gemini CLI → `~/.gemini/tmp/**/session-*.json`
- Codex CLI → `~/.codex/sessions/**/*.jsonl` and `~/.codex/archived_sessions/*.jsonl`

CLIs with zero data hide automatically — install all four plugins anyway and use what you have.

---

## 🚀 Quick Start

### 🍺 Option A: Homebrew (recommended)

```bash
brew tap unistark/tap
brew install tokenused
```

Plugins land in `$(brew --prefix)/opt/tokenused/share/tokenused/`. `brew info tokenused` prints the four-step activation guide (patch + build UsageBoard, copy plugins, optional config drop-in).

### 🛠️ Option B: Manual

```bash
# 1. Clone
git clone https://github.com/uniStark/TokenUsed.git
cd TokenUsed

# 2. Patch + build UsageBoard (one time)
git clone https://github.com/marsmay/UsageBoard.git ../UsageBoard
cd ../UsageBoard
git apply ../TokenUsed/patches/usageboard-build-and-refresh.patch
bash scripts/build.sh
cd ../TokenUsed

# 3. Install plugins
mkdir -p "$HOME/Library/Application Support/UsageBoard/plugins"
cp plugins/*.py "$HOME/Library/Application Support/UsageBoard/plugins/"
chmod +x "$HOME/Library/Application Support/UsageBoard/plugins/"*.py

# 4. (optional) Drop in the example config — substitute __HOME__ with your real $HOME
sed "s|__HOME__|$HOME|g" examples/config.example.json > "$HOME/Library/Application Support/UsageBoard/config.json"

# 5. Open UsageBoard, click the menu-bar icon — you should see four panels
```

If anything goes wrong, see [Troubleshooting](#troubleshooting) below.

---

## 🩹 What the Patch Changes

`patches/usageboard-build-and-refresh.patch` makes three small changes to upstream UsageBoard:

| File | Change | Why |
|---|---|---|
| `Package.swift` | `swift-tools-version: 6.3` → `6.2` | Lets Swift 6.2 toolchains build it |
| `Sources/UsageBoardApp/DashboardView.swift` | Adds `store.refreshAll()` to `.onAppear` + filters out empty panels (`visiblePlugins`) | Refresh on every panel open; auto-hide CLIs with no data |
| `Sources/UsageBoardCore/Models.swift` | Adds optional `trailingText: String?` field on `UsageItem` | Lets plugins put per-row token counts in the right column |

If you'd rather use UsageBoard unmodified, the plugins still work — you just lose auto-hide and the right-column token count.

---

## ⚙️ Configuration

All four plugins read parameters from the UsageBoard plugin settings UI. Defaults work out of the box. Override only when needed.

### Daily Overview (`daily-overview-plugin.py`)

| Parameter | Default | Description |
|---|---|---|
| `CLAUDE_DIR` | `~/.claude/projects` | Where Claude Code stores session JSONL |
| `GEMINI_DIR` | `~/.gemini/tmp` | Where Gemini CLI stores `session-*.json` |
| `CODEX_DIR` | `~/.codex` | Codex CLI base dir (scans `sessions/` + `archived_sessions/`) |
| `CHART_PERIOD` | `30d` | Default period: `today` / `7d` / `30d` / `90d` / `all` (12 months) — chart auto-buckets: day → week (90d) → month (all) |
| `TOKEN_MODE` | `billable` | `billable` (input+output+cache_creation, matches Claude Code `/cost`) or `raw` (also includes `cache_read_input_tokens` hits — typically ~95% of the total) |

### Per-CLI plugins (`claude-code-usage-plugin.py`, `gemini-cli-usage-plugin.py`, `codex-local-usage-plugin.py`)

| Parameter | Default | Description |
|---|---|---|
| `*_DIR` | same as above | Override scan path for that CLI |
| `STAT_PERIOD` | `30d` | Default period: `today` / `7d` / `30d` / `90d` / `all` |
| `TOKEN_MODE` (Claude only) | `billable` | Same semantics as Daily Overview. Has no effect on Codex/Gemini panels (their reported tokens have no cache-read concept) |

> **In-panel segmented picker**: every plugin emits a `dimensions` map with all five periods, so once data is in cache (~30s first run), `Today ↔ 7d ↔ 30d ↔ 90d ↔ All` switches instantly — no plugin re-spawn, no re-parse. The selection is persisted per-plugin via `@AppStorage("usageboard.period.<pluginID>")`.

> **Why two modes?** Claude's `usage` report counts every prompt-cache hit as `cache_read_input_tokens`. With heavy tool use, this can balloon the "raw" total to 100×+ what you actually billed. `billable` matches the four-component cost formula Anthropic uses (`input + output + cache_creation`); switching only re-projects the in-cache totals — no reparse.

To customise: open UsageBoard → menu-bar icon → gear → **Plugins** → click the plugin → adjust parameters. No restart needed.

### Progress-bar colour semantics

The four plugins use **different** colour rules on purpose:
- **Daily overview** — red/orange/blue based on each model's share of today's total (≥50% red, ≥25% orange, otherwise blue)
- **Per-CLI** — red/orange/blue based on today's tokens vs the peak day in the period (≥100% red = today broke the peak, ≥80% orange, otherwise blue)

---

## 📁 Project Layout

```
TokenUsed/
├── plugins/                            # UsageBoard Python plugins
│   ├── daily-overview-plugin.py        # ⭐ Today overview (3 CLIs aggregated, per-model rows + 7-day bar chart)
│   ├── claude-code-usage-plugin.py     # Claude Code single-CLI panel
│   ├── gemini-cli-usage-plugin.py      # Gemini CLI single-CLI panel
│   └── codex-local-usage-plugin.py     # Codex CLI single-CLI panel
├── patches/
│   └── usageboard-build-and-refresh.patch  # The three UsageBoard patches
├── examples/
│   └── config.example.json             # Drop-in UsageBoard config with all four plugins registered
├── widget/                             # Native macOS WidgetKit app (Xcode project — see status below)
├── images/                             # README screenshots
├── README.md                           # This file (English)
├── README_ZH.md                        # 中文版
└── LICENSE                             # MIT
```

---

## 🍎 Native Widget Status

`widget/` contains a complete WidgetKit + SwiftUI Xcode project (Small / Medium / Large sizes, Swift Charts 7-day bar chart). It builds and runs locally, but on **macOS 15+ Sequoia / Tahoe** the system daemon `chronod` refuses to register Personal-Team-signed widget extensions in the desktop widget gallery — **you need a paid [Apple Developer Program](https://developer.apple.com/programs/) ($99/yr) account** to actually use it.

If you don't pay for the Program, stick with the menu-bar UsageBoard panel — it has all the same data. The widget code is kept ready to ship the day signing becomes possible.

---

## 📊 Data Sources

| Plugin | Reads from | Field |
|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` | `message.usage.{input,output,cache_*}_tokens` + `message.model` |
| Gemini CLI | `~/.gemini/tmp/**/session-*.json` | `messages[].tokens.total` + `messages[].model` |
| Codex CLI | `~/.codex/sessions/**/*.jsonl` + `archived_sessions/*.jsonl` | `payload.info.total_token_usage.total_tokens` (model picked from preceding `turn_context`) |

The overview plugin reads all three in parallel.

---

## 🐛 Troubleshooting

**Panel shows "JSON 解析失败 / failed to parse"**: run the plugin manually to see the raw error:
```bash
python3 "$HOME/Library/Application Support/UsageBoard/plugins/daily-overview-plugin.py" \
  --usageboard-param USAGEBOARD_LANGUAGE=en
```

**Build error `swift-tools-version 6.3 is not supported`**: you forgot to apply the patch. `cd UsageBoard && git apply ../TokenUsed/patches/usageboard-build-and-refresh.patch`.

**Right column shows `--`**: you're running unpatched UsageBoard. The `trailingText` feature requires the patch.

**Gemini panel still shows with `0 tokens`**: you're running unpatched UsageBoard, or the Gemini plugin is from before the empty-items change — `cp plugins/gemini-cli-usage-plugin.py ~/Library/Application\ Support/UsageBoard/plugins/` and click the menu-bar icon to refresh.

---

## 🤝 Contributing

PRs welcome. Useful directions:

- New CLI plugins (e.g. Aider, Cursor CLI, Cline, OpenRouter) — copy any `*-usage-plugin.py` as a template, follow the `# UsageBoardPlugin: ... # /UsageBoardPlugin` metadata block.
- Better colour/threshold rules — current rules are documented in the [Configuration](#configuration) section.
- Native widget polish — once the Apple Developer Program issue is sorted, the `widget/` project is ready for distribution.
- Localisations beyond `zh-Hans` / `en`.

Please run `python3 plugins/<your-plugin>.py --usageboard-param USAGEBOARD_LANGUAGE=en` and confirm the JSON validates against existing fixtures before submitting.

Run the test suite locally — same one CI runs:

```bash
python3 -m unittest tests.test_plugins -v
```

### 🛠 Maintainers — regenerating the patch

`patches/usageboard-build-and-refresh.patch` is a real `git diff` and must stay one. If you have [RTK (Rust Token Killer)](https://github.com/uniStark/rtk) installed in Claude Code, its hook intercepts `git diff` / `git status` etc. and rewrites the output into a token-compressed form that **is not a valid unified diff**. To regenerate the patch correctly:

```bash
cd ../UsageBoard
# bypass the RTK hook so git produces a real unified diff
rtk proxy git diff > ../TokenUsed/patches/usageboard-build-and-refresh.patch
# verify on a clean tree
git stash && git apply --check ../TokenUsed/patches/usageboard-build-and-refresh.patch && git stash pop
```

CI (`.github/workflows/ci.yml`) runs `git apply --check` on every push so a malformed patch fails the build before it can ship.

---

## 📄 License

MIT — see [LICENSE](./LICENSE). Plugin scripts are free to modify and redistribute.

## 🙏 Acknowledgements

- [UsageBoard](https://github.com/marsmay/UsageBoard) — the menu-bar host this project plugs into.
- [lobe-icons](https://github.com/lobehub/lobe-icons) — plugin icon set referenced in `examples/config.example.json`.
