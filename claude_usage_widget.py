#!/usr/bin/env python3
"""
Claude AI Usage Widget — Linux System Tray (Multi-Account)
Shows claude.ai subscription usage (5h / 7d) in the taskbar for multiple accounts.
Click to see detailed breakdown + reset timers.

Reads credentials from configurable Claude Code directories.
Config: ~/.config/claude-usage-widget/config.json

Author: Statotech Systems (original), extended for multi-account
Version: 2.0.0
License: MIT
"""

__version__ = "2.0.0"
__author__ = "Statotech Systems"

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
gi.require_version('Notify', '0.7')

from gi.repository import Gtk, AppIndicator3, GLib, Notify
import cairo
import json
import os
import sys
import urllib.request
import urllib.error
import ssl
import threading
import time
from datetime import datetime
from pathlib import Path

from shared import (
    COLOR_GRAY, DEFAULT_THRESHOLDS, get_color_for_pct, hex_to_rgb,
    parse_utilization, format_reset_time,
)
from usage_popup import UsageDetailWindow
from config_window import ConfigWindow

# ── Config ──────────────────────────────────────────────────────────────────

APP_ID = "claude-usage-widget"
APP_NAME = "Claude Usage"
USAGE_API_URL = "https://api.anthropic.com/api/oauth/usage"

CONFIG_DIR = Path.home() / ".config" / APP_ID
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_ACCOUNTS = [
    {"label": "Claude", "credentials_dir": "~/.claude"},
]
DEFAULT_POLL_INTERVAL = 300  # 5 minutes


# ── Icon generation ─────────────────────────────────────────────────────────

def write_icon(pct: float, error: bool = False) -> str:
    """Generate PNG icon with Cairo and return path."""
    color = COLOR_GRAY if error else get_color_for_pct(pct)
    r, g, b = hex_to_rgb(color)

    size = 32
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)

    ctx.set_operator(cairo.OPERATOR_CLEAR)
    ctx.paint()
    ctx.set_operator(cairo.OPERATOR_OVER)

    ctx.set_source_rgba(r, g, b, 0.25)
    ctx.arc(size/2, size/2, 13, 0, 2 * 3.14159)
    ctx.fill()

    ctx.set_source_rgb(r, g, b)
    ctx.set_line_width(2)
    ctx.arc(size/2, size/2, 13, 0, 2 * 3.14159)
    ctx.stroke()

    ctx.set_source_rgb(r, g, b)
    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(22)
    text = "C"
    x_bearing, y_bearing, width, height, *_ = ctx.text_extents(text)
    ctx.move_to(size/2 - width/2 - x_bearing, size/2 - height/2 - y_bearing)
    ctx.show_text(text)

    icon_dir = Path("/tmp") / APP_ID
    icon_dir.mkdir(exist_ok=True)
    icon_path = icon_dir / "icon.png"
    surface.write_to_png(str(icon_path))
    return str(icon_path)


# ── Config loading ──────────────────────────────────────────────────────────

def load_config() -> dict:
    """Load widget config, creating defaults if missing."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"[claude-usage] Bad config, using defaults: {e}", file=sys.stderr)

    config = {
        "accounts": DEFAULT_ACCOUNTS,
        "poll_interval_seconds": DEFAULT_POLL_INTERVAL,
        "thresholds": DEFAULT_THRESHOLDS,
    }
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    os.chmod(CONFIG_FILE, 0o600)
    return config


# ── Per-account token loading ───────────────────────────────────────────────

def load_token(credentials_dir: str) -> str | None:
    """Load OAuth access token from a Claude Code credentials directory."""
    cred_path = Path(credentials_dir).expanduser() / ".credentials.json"
    if not cred_path.exists():
        return None
    try:
        data = json.loads(cred_path.read_text())
        return data.get("claudeAiOauth", {}).get("accessToken")
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def load_subscription_info(credentials_dir: str) -> dict | None:
    """Load subscription info from a Claude Code credentials directory."""
    cred_path = Path(credentials_dir).expanduser() / ".credentials.json"
    if not cred_path.exists():
        return None
    try:
        data = json.loads(cred_path.read_text())
        oauth = data.get("claudeAiOauth", {})
        if oauth:
            return {
                "subscription_type": oauth.get("subscriptionType", "").title(),
                "rate_limit_tier": oauth.get("rateLimitTier", ""),
            }
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return None


# ── API call ────────────────────────────────────────────────────────────────

class RateLimitError(Exception):
    pass


def fetch_usage(token: str) -> dict | None:
    """Fetch usage data from the Claude API."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": f"claude-usage-widget/{__version__}",
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
    }
    req = urllib.request.Request(USAGE_API_URL, headers=headers, method="GET")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimitError()
        print(f"[claude-usage] HTTP {e.code}: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[claude-usage] Error: {e}", file=sys.stderr)
        return None


# ── Main App ────────────────────────────────────────────────────────────────

class ClaudeUsageApp:
    def __init__(self):
        self.config = load_config()
        self.accounts = self.config.get("accounts", DEFAULT_ACCOUNTS)
        self.poll_interval = self.config.get("poll_interval_seconds", DEFAULT_POLL_INTERVAL)
        self.thresholds = self.config.get("thresholds", DEFAULT_THRESHOLDS)

        # Per-account state
        self.account_states: dict[str, dict] = {}
        for acct in self.accounts:
            self.account_states[acct["label"]] = {
                "credentials_dir": acct["credentials_dir"],
                "token": None, "usage_data": None,
                "subscription_info": None, "error": None,
                "last_notification_threshold": 0,
            }

        self.last_updated = "never"
        self.running = True
        self.startup_notification_sent = False

        Notify.init(APP_NAME)

        # Create indicator
        icon_path = write_icon(0, error=True)
        self.indicator = AppIndicator3.Indicator.new(
            APP_ID, icon_path, AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title(APP_NAME)
        self.indicator.set_label("--", "")

        self._build_menu()

        # Start background polling
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def _build_menu(self):
        self.menu = Gtk.Menu()
        self.menu_items = {}

        for acct in self.accounts:
            lbl = acct["label"]
            item = Gtk.MenuItem(label=f"{lbl}: --%")
            item.set_sensitive(False)
            self.menu.append(item)
            self.menu_items[lbl] = item

        self.menu.append(Gtk.SeparatorMenuItem())

        item_details = Gtk.MenuItem(label="Show Details...")
        item_details.connect("activate", self.on_show_details)
        self.menu.append(item_details)

        item_refresh = Gtk.MenuItem(label="Refresh Now")
        item_refresh.connect("activate", lambda _: self.force_refresh())
        self.menu.append(item_refresh)

        item_configure = Gtk.MenuItem(label="Configure...")
        item_configure.connect("activate", self.on_configure)
        self.menu.append(item_configure)

        self.menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", self.on_quit)
        self.menu.append(item_quit)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)

    def _poll_loop(self):
        """Background thread: fetch usage for all accounts periodically."""
        while self.running:
            results = {}
            for label, state in self.account_states.items():
                results[label] = self._fetch_account(label, state)
            GLib.idle_add(self._update_ui, results)
            time.sleep(self.poll_interval)

    def _fetch_account(self, label: str, state: dict) -> dict:
        """Fetch usage for a single account. Returns update dict."""
        cred_dir = state["credentials_dir"]
        try:
            token = load_token(cred_dir)
            if not token:
                return {"error": "No token", "usage_data": None, "token": None}
            data = fetch_usage(token)
            sub_info = load_subscription_info(cred_dir)
            if data is None:
                return {"error": "API error", "usage_data": None, "token": token,
                        "subscription_info": sub_info}
            return {"error": None, "usage_data": data, "token": token,
                    "subscription_info": sub_info}
        except RateLimitError:
            print(f"[claude-usage] {label}: rate limited", file=sys.stderr)
            return {"error": "Rate limited", "usage_data": None, "token": state.get("token")}
        except Exception as e:
            print(f"[claude-usage] {label}: {e}", file=sys.stderr)
            return {"error": str(e), "usage_data": None, "token": state.get("token")}

    def force_refresh(self):
        def _do():
            results = {}
            for label, state in self.account_states.items():
                results[label] = self._fetch_account(label, state)
            GLib.idle_add(self._update_ui, results)
        threading.Thread(target=_do, daemon=True).start()

    def _update_ui(self, results: dict):
        """Update indicator label + icon from fetched data (GTK thread)."""
        self.last_updated = datetime.now().strftime("%H:%M:%S")

        for label, result in results.items():
            self.account_states[label].update(result)

        # Build tray label: "G:67% N:12%"
        label_parts = []
        max_pct = 0
        any_ok = False

        for acct in self.accounts:
            lbl = acct["label"]
            state = self.account_states[lbl]
            usage = state.get("usage_data")

            if usage:
                any_ok = True
                five = usage.get("five_hour", {}) or {}
                seven = usage.get("seven_day", {}) or {}
                pct5, _ = parse_utilization(five.get("utilization", 0))
                pct7, _ = parse_utilization(seven.get("utilization", 0))
                label_parts.append(f"{lbl}:{pct5}%")
                max_pct = max(max_pct, pct5, pct7)

                r5 = format_reset_time(five.get("resets_at"))
                self.menu_items[lbl].set_label(f"{lbl}: 5h {pct5}% | 7d {pct7}% (resets {r5})")
            else:
                label_parts.append(f"{lbl}:!")
                self.menu_items[lbl].set_label(f"{lbl}: {state.get('error', 'error')}")

        tray_text = " ".join(label_parts)
        self.indicator.set_label(tray_text, "")

        icon_path = write_icon(max_pct) if any_ok else write_icon(0, error=True)
        self.indicator.set_icon_full(icon_path, tray_text)

        # Startup notification
        if not self.startup_notification_sent and any_ok:
            self.startup_notification_sent = True
            n = Notify.Notification.new("Claude Usage Widget Started", tray_text, "dialog-information")
            n.show()

        # Per-account threshold notifications
        for acct in self.accounts:
            lbl = acct["label"]
            state = self.account_states[lbl]
            usage = state.get("usage_data")
            if not usage:
                continue
            five = usage.get("five_hour", {}) or {}
            seven = usage.get("seven_day", {}) or {}
            pct5, _ = parse_utilization(five.get("utilization", 0))
            pct7, _ = parse_utilization(seven.get("utilization", 0))
            self._check_threshold(lbl, max(pct5, pct7), state)

        return False  # GLib.idle_add one-shot

    def _check_threshold(self, label: str, pct: int, state: dict):
        """Send notification when an account crosses a threshold."""
        if not self.startup_notification_sent:
            return

        prev = state.get("last_notification_threshold", 0)
        warn = self.thresholds.get("warn", 60)
        crit = self.thresholds.get("critical", 85)

        current = 0
        if pct >= 100:
            current = 100
        elif pct >= crit:
            current = crit
        elif pct >= warn:
            current = warn

        if current <= prev:
            return

        urgency = Notify.Urgency.CRITICAL if current >= crit else Notify.Urgency.NORMAL
        icon = "dialog-warning" if current >= crit else "dialog-information"
        n = Notify.Notification.new(f"{label}: Usage at {pct}%", f"Account {label} reached {pct}%", icon)
        n.set_urgency(urgency)
        n.show()
        state["last_notification_threshold"] = current

    def on_configure(self, _widget):
        ConfigWindow(self.accounts, self._reload_accounts)

    def _reload_accounts(self, new_accounts: list[dict]):
        """Rebuild account state from updated config and refresh."""
        self.accounts = new_accounts
        self.account_states = {
            acct["label"]: {
                "credentials_dir": acct["credentials_dir"],
                "token": None, "usage_data": None,
                "subscription_info": None, "error": None,
                "last_notification_threshold": 0,
            }
            for acct in new_accounts
        }
        self._build_menu()
        self.force_refresh()

    def on_show_details(self, _widget):
        accts_data = []
        for acct in self.accounts:
            lbl = acct["label"]
            state = self.account_states[lbl]
            accts_data.append({
                "label": lbl,
                "usage_data": state.get("usage_data"),
                "error": state.get("error"),
                "subscription_info": state.get("subscription_info"),
            })
        UsageDetailWindow(accts_data, self.last_updated, self.thresholds,
                          __version__, self.force_refresh)

    def on_quit(self, _widget):
        self.running = False
        Notify.uninit()
        Gtk.main_quit()

    def run(self):
        Gtk.main()


if __name__ == "__main__":
    app = ClaudeUsageApp()
    app.run()
