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
- **Usage overview + multi-period charts** — a hero card shows the selected period total, plus model-stacked charts for `today` / `7d` / `30d` / `90d` / `all`.
- **Cleaner overview rows** — the Usage Overview lists the Top 5 models and folds the rest into `Other`, with best-effort provider/source labels on model rows.
- **Clear token accounting** — Claude can be shown as `billable` or `raw`, and Codex/Gemini keep their reported-token semantics.
- **Setup helper CLI** — `tokenused doctor`, `sync-plugins`, `install-config`, and `smoke` make installation and debugging repeatable.
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

Plugins land in `$(brew --prefix)/opt/tokenused/share/tokenused/`, and the helper CLI becomes available as `tokenused`.

Shortest path after Homebrew:

```bash
# 1. Check prerequisites and paths
tokenused doctor

# 2. Patch + build UsageBoard (one time)
git clone https://github.com/marsmay/UsageBoard.git ../UsageBoard
cd ../UsageBoard
git apply "$(brew --prefix)/opt/tokenused/share/tokenused/patches/usageboard-build-and-refresh.patch"
bash scripts/build.sh
cd -

# 3. Copy/update TokenUsed plugins into UsageBoard
tokenused sync-plugins

# 4. Merge TokenUsed entries into UsageBoard config without removing other plugins
tokenused install-config

# 5. Run installed-plugin smoke checks
tokenused smoke
```

`brew info tokenused` also prints the activation guide.

### 🛠️ Option B: Manual

```bash
# 1. Clone
git clone https://github.com/uniStark/token-used.git
cd token-used

# 2. Patch + build UsageBoard (one time)
git clone https://github.com/marsmay/UsageBoard.git ../UsageBoard
cd ../UsageBoard
git apply ../token-used/patches/usageboard-build-and-refresh.patch
bash scripts/build.sh
cd ../TokenUsed

# 3. Check prerequisites and paths
python3 bin/tokenused doctor

# 4. Copy/update TokenUsed plugins into UsageBoard
python3 bin/tokenused sync-plugins

# 5. Merge TokenUsed entries into UsageBoard config without removing other plugins
python3 bin/tokenused install-config

# 6. Run installed-plugin smoke checks
python3 bin/tokenused smoke

# 7. Open UsageBoard, click the menu-bar icon — you should see the overview + per-CLI panels
```

If anything goes wrong, see [Troubleshooting](#troubleshooting) below.

### Manual fallback without the helper CLI

If you cannot use `bin/tokenused`, the old manual install path still works:

```bash
mkdir -p "$HOME/Library/Application Support/UsageBoard/plugins"
cp plugins/*.py "$HOME/Library/Application Support/UsageBoard/plugins/"
chmod +x "$HOME/Library/Application Support/UsageBoard/plugins/"*.py
sed "s|__HOME__|$HOME|g" examples/config.example.json > "$HOME/Library/Application Support/UsageBoard/config.json"
```

Prefer `tokenused install-config` when possible because it merges/upserts the TokenUsed plugin entries instead of replacing your whole UsageBoard config.

---

## 🩹 What the Patch Changes

`patches/usageboard-build-and-refresh.patch` makes several small changes to upstream UsageBoard:

| File | Change | Why |
|---|---|---|
| `Package.swift` | `swift-tools-version: 6.3` → `6.2` | Lets Swift 6.2 toolchains build it |
| `Sources/UsageBoardApp/DashboardView.swift` | Adds `store.refreshAll()`, `visiblePlugins`, an in-panel segmented period picker, and layout tweaks for long titles / badges | Refresh on every panel open; auto-hide CLIs with no data; switch periods without re-running plugins; avoid clipped model names and large numbers |
| `Sources/UsageBoardApp/UsageBoardStore.swift` | Preserves `iconURL`, `dimensions`, `defaultDimension`, and `dimensionOrder` in cached plugin state | Keeps dynamic icons and multi-period data after restart |
| `Sources/UsageBoardCore/Models.swift` | Adds `dimensions`, `defaultDimension`, `dimensionOrder`, `iconURL`, and `UsageItem.trailingText` support across plugin output, snapshots, and cached state | Lets plugins emit all periods at once; allows dynamic icon overrides; shows token counts in the right column |
| `Sources/UsageBoardCore/PluginExecutor.swift` | Changes the default timeout from `15s` to `180s` and prefers plugin-emitted `iconURL` | Prevents cold scans of large directories from timing out; lets Usage Overview show the dominant provider icon |

If you'd rather use UsageBoard unmodified, the plugins still work — you just lose auto-hide, right-column token counts, in-panel period switching, and dynamic icons.

---

## 🧰 CLI Reference

Use `tokenused <command>` after Homebrew install, or `python3 bin/tokenused <command>` from a manual clone.

| Command | What it does |
|---|---|
| `doctor` | Checks Python, UsageBoard paths, plugin/config locations, session-data visibility, and common patch/install problems. Start here when the panel is empty or stale. |
| `sync-plugins` | Copies or updates TokenUsed plugin scripts in `~/Library/Application Support/UsageBoard/plugins/` and makes them executable. |
| `install-config` | Merges/upserts TokenUsed plugin entries into UsageBoard `config.json`; it should not remove unrelated UsageBoard plugins or user settings. |
| `smoke` | Runs lightweight installed-plugin checks so you can catch JSON/schema/runtime errors before opening UsageBoard. |

The CLI helps with TokenUsed installation only. The UsageBoard patch remains the key enhancement path: without it, plugins can still run, but multi-period switching, right-column token counts, auto-hide, layout fixes, and dynamic icons are degraded or unavailable.

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

> **Overview rows**: the Daily Overview shows the Top 5 models for the selected period and folds the rest into `Other`. Model names are kept as specific as the source data allows, and rows include best-effort source/provider hints where available.

To customise: open UsageBoard → menu-bar icon → gear → **Plugins** → click the plugin → adjust parameters. No restart needed.

### Progress-bar colour semantics

The four plugins use **different** colour rules on purpose:
- **Daily overview** — red/orange/blue based on each model's share of today's total (≥50% red, ≥25% orange, otherwise blue)
- **Per-CLI** — red/orange/blue based on today's tokens vs the peak day in the period (≥100% red = today broke the peak, ≥80% orange, otherwise blue)

---

## 📁 Project Layout

```
TokenUsed/
├── bin/
│   └── tokenused                         # Install/debug helper CLI
├── plugins/                            # UsageBoard Python plugins
│   ├── daily-overview-plugin.py        # ⭐ Today overview (3 CLIs aggregated, per-model rows + 7-day bar chart)
│   ├── claude-code-usage-plugin.py     # Claude Code single-CLI panel
│   ├── gemini-cli-usage-plugin.py      # Gemini CLI single-CLI panel
│   ├── codex-local-usage-plugin.py     # Codex CLI single-CLI panel
│   ├── _shared.py                      # Compatibility facade imported by plugin entrypoints
│   └── _shared_*.py                    # Private shared modules (core/cache/parsers/builders)
├── patches/
│   └── usageboard-build-and-refresh.patch  # UsageBoard UI / schema / executor enhancements
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

**Start with `tokenused doctor`**: it checks the common failure points in one place:
```bash
tokenused doctor
# or, from a manual clone:
python3 bin/tokenused doctor
```
Use its output to confirm whether the issue is missing UsageBoard paths, missing session data, unsynced plugins, an unmerged config, or an unpatched UsageBoard build.

**Panel shows "JSON 解析失败 / failed to parse"**: run the plugin manually to see the raw error:
```bash
python3 "$HOME/Library/Application Support/UsageBoard/plugins/daily-overview-plugin.py" \
  --usageboard-param USAGEBOARD_LANGUAGE=en
```

You can also run `tokenused smoke` to exercise the installed plugins through the helper CLI.

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

CI (`.github/workflows/ci.yml`) runs `git apply --check` and a patched `swift build` on every push, so malformed or uncompilable patches fail before they can ship.

---

## 📄 License

MIT — see [LICENSE](./LICENSE). Plugin scripts are free to modify and redistribute.

## 🙏 Acknowledgements

- [UsageBoard](https://github.com/marsmay/UsageBoard) — the menu-bar host this project plugs into.
- [lobe-icons](https://github.com/lobehub/lobe-icons) — plugin icon set referenced in `examples/config.example.json`.
