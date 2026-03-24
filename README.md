# ⚡ Claude AI Usage Widget — Linux Taskbar (Multi-Account Fork)

> **Fork of [StaticB1/claude_ai_usage_widget](https://github.com/StaticB1/claude_ai_usage_widget)**
> The only change from the original is **multi-account support** — monitor multiple Claude accounts simultaneously from a single tray icon.

A lightweight system tray widget that shows your Claude AI subscription usage (5h and 7d rate limit windows) directly in your Linux taskbar.

![Claude Usage Widget Screenshot](screenshot.png)

## What's Different from the Original

- **Multiple accounts** — tray label shows `Work:67% Personal:12%` for all accounts at a glance
- **Per-account popup** — clicking opens a breakdown for each account with 5h + 7d bars and reset timers
- **Config-driven accounts** — `~/.config/claude-usage-widget/config.json` lists each account's label and Claude Code config dir
- **Graceful failures** — if one account's token fails it shows `Work:!` but the others keep working
- **Interactive install** — `install.sh` now asks how many accounts you want and where their credentials are
- **pyenv support** — installer detects pyenv and creates an isolated venv so the widget survives Python version switches
- **5-minute poll** — bumped from 2 min to 5 min

Everything else (API, icon, notifications, autostart) is unchanged from the original.

---

## Quick Start

```bash
git clone https://github.com/gqcorneby/claude_ai_usage_widget.git
cd claude_ai_usage_widget
./install.sh
claude-widget-start
```

The installer will ask how many accounts to monitor and where each one's Claude Code config directory is.

## Requirements

- Linux with GTK3 (GNOME, KDE, XFCE, etc.)
- Python 3.10+
- `gir1.2-appindicator3-0.1`, `gir1.2-notify-0.7` (installer handles these)

## Install

```bash
./install.sh
```

The installer will:
1. Detect pyenv or fall back to system Python
2. Install system GI libraries via apt
3. Create an isolated venv (survives pyenv version changes)
4. Ask you to configure your accounts interactively
5. Set up autostart on login

```
▸ Setting up accounts…
  How many accounts do you want to monitor? [1]: 2

  — Account 1 of 2 —
  Label [Account1]: Work
  Claude config dir [~/.claude]: ~/.claude/work
  ✓ Found credentials

  — Account 2 of 2 —
  Label [Account2]: Personal
  Claude config dir [~/.claude]: ~/.claude
  ✓ Found credentials
```

## Usage

```bash
claude-widget-start   # Start
claude-widget-stop    # Stop
```

The tray label updates every 5 minutes. Click it for the full breakdown popup.

## Configuration

`~/.config/claude-usage-widget/config.json` — written by the installer, edit any time:

```json
{
  "accounts": [
    { "label": "Work",     "credentials_dir": "~/.claude/work" },
    { "label": "Personal", "credentials_dir": "~/.claude" }
  ],
  "poll_interval_seconds": 300,
  "thresholds": { "warn": 60, "critical": 85 }
}
```

Each `credentials_dir` must contain a `.credentials.json` file from Claude Code (`claude login`).

## How It Works

Uses the same internal API endpoint as Claude Code's `/usage`:

```
GET https://api.anthropic.com/api/oauth/usage
Authorization: Bearer <oauth-token>
anthropic-beta: oauth-2025-04-20
```

Credentials are read directly from Claude Code's credential files — no separate login required.

## Uninstall

```bash
./uninstall.sh
```

Removes all installed files, scripts, desktop entries, and temp files. Prompts before removing your account config.

## Troubleshooting

| Problem | Fix |
|---|---|
| Account shows `!` | Check `/tmp/claude-widget.log`. Usually an expired token — re-run `claude login` |
| No tray icon on GNOME 43+ | Install `gnome-shell-extension-appindicator` and enable it |
| `AppIndicator3` import fails | `sudo apt install gir1.2-appindicator3-0.1` |
| Widget broke after pyenv switch | Re-run `./install.sh` — creates a new venv from current pyenv version |
| `command not found` after install | Run `hash -r` or open a new terminal |

```bash
cat /tmp/claude-widget.log   # Check logs
```

## License

MIT — see original repo for full history and credits.

## Credits

Original widget by **[Statotech Systems](https://github.com/StaticB1)**.
Multi-account fork by [gqcorneby](https://github.com/gqcorneby).
