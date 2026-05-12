"""
Shared utilities for Claude Usage Widget.
Colors, utilization parsing, time formatting, and local token tracking.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOCAL_TRACKING_FILE = Path.home() / ".claude" / "usage-tracking.json"

# ── Colors ──────────────────────────────────────────────────────────────────

COLOR_GREEN = "#22c55e"
COLOR_YELLOW = "#eab308"
COLOR_RED = "#ef4444"
COLOR_GRAY = "#6b7280"

DEFAULT_THRESHOLDS = {"warn": 60, "critical": 85}


def get_color_for_pct(pct: float, thresholds: dict | None = None) -> str:
    """Return color based on percentage (0-100 scale)."""
    warn = (thresholds or DEFAULT_THRESHOLDS).get("warn", 60)
    critical = (thresholds or DEFAULT_THRESHOLDS).get("critical", 85)
    if pct < warn:
        return COLOR_GREEN
    elif pct < critical:
        return COLOR_YELLOW
    else:
        return COLOR_RED


def hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))


def parse_utilization(raw: float) -> tuple[int, float]:
    """Return (percentage_int, decimal_0_to_1) from API utilization value."""
    if raw >= 1:  # Already a percentage (API returns 0-100 scale; 1.0 means 1%)
        return int(raw), raw / 100
    return int(raw * 100), raw


def compute_burn_rate(seven: dict) -> float | None:
    """Return the 7d burn rate multiplier, or None if the window is too new."""
    resets_at_str = seven.get("resets_at")
    if not resets_at_str:
        return None
    pct7, _ = parse_utilization(seven.get("utilization", 0))
    try:
        resets_at = datetime.fromisoformat(resets_at_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        window_secs = 7 * 24 * 3600
        elapsed_secs = window_secs - (resets_at - now).total_seconds()
        if elapsed_secs < 0.05 * window_secs:  # ignore first ~8h
            return None
        return (pct7 / 100) / (elapsed_secs / window_secs)
    except Exception:
        return None


def format_reset_clock(iso_str: str | None) -> str:
    """Format reset time as a clock time, e.g. '9:00P'. Used when auto-poll is off."""
    if not iso_str:
        return "unknown"
    try:
        reset_dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone()
        return reset_dt.strftime("%-I:%M") + ("A" if reset_dt.hour < 12 else "P")
    except Exception:
        return "unknown"


def format_reset_clock_7d(iso_str: str | None) -> str:
    """Format reset time as day + clock, e.g. 'Th 7:00P'. Used for 7d window when auto-poll is off."""
    if not iso_str:
        return "unknown"
    try:
        reset_dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone()
        day = reset_dt.strftime("%a")[:2]  # "Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"
        time_str = reset_dt.strftime("%-I:%M") + ("A" if reset_dt.hour < 12 else "P")
        return f"{day} {time_str}"
    except Exception:
        return "unknown"


def fmt_tokens(n: int) -> str:
    """Abbreviate a token count: 87K, 1.2M."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def load_local_usage(profile: str, five_hour_start: datetime | None = None) -> dict | None:
    """Aggregate token usage from the local tracking file for a profile."""
    if not LOCAL_TRACKING_FILE.exists():
        return None
    try:
        data = json.loads(LOCAL_TRACKING_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    now = datetime.now(timezone.utc)
    five_hour_start = five_hour_start or (now - timedelta(hours=5))
    today_start     = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start      = now - timedelta(days=7)
    month_start     = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    buckets = {
        "five_hour": [0, 0, 0],   # [input, output, cache]
        "today":     [0, 0, 0],
        "week":      [0, 0, 0],
        "month":     [0, 0, 0],
        "all":       [0, 0, 0],
    }

    for s in data.get("sessions", []):
        if s.get("profile") != profile:
            continue
        inp   = s.get("input_tokens", 0)
        out   = s.get("output_tokens", 0)
        cache = s.get("cache_read_input_tokens", 0) + s.get("cache_creation_input_tokens", 0)

        buckets["all"][0] += inp
        buckets["all"][1] += out
        buckets["all"][2] += cache

        ts_str = s.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts >= month_start:
                buckets["month"][0] += inp
                buckets["month"][1] += out
                buckets["month"][2] += cache
            if ts >= week_start:
                buckets["week"][0] += inp
                buckets["week"][1] += out
                buckets["week"][2] += cache
            if ts >= today_start:
                buckets["today"][0] += inp
                buckets["today"][1] += out
                buckets["today"][2] += cache
            if ts >= five_hour_start:
                buckets["five_hour"][0] += inp
                buckets["five_hour"][1] += out
                buckets["five_hour"][2] += cache
        except Exception:
            pass

    def _make(vals: list) -> dict:
        inp, out, cache = vals
        return {"input": inp, "output": out, "cache": cache, "total": inp + out + cache}

    return {
        "five_hour": _make(buckets["five_hour"]),
        "today":     _make(buckets["today"]),
        "week":      _make(buckets["week"]),
        "month":     _make(buckets["month"]),
        "all":       _make(buckets["all"]),
    }


def load_transcript_tokens(projects_dir: str, five_hour_start: datetime | None = None) -> dict | None:
    """Scan CC transcript JSONL files and aggregate token usage by time window."""
    base = Path(projects_dir).expanduser()
    if not base.exists():
        return None

    now = datetime.now(timezone.utc)
    five_hour_start = five_hour_start or (now - timedelta(hours=5))
    today_start     = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start      = now - timedelta(days=7)
    month_start     = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    buckets = {
        "five_hour": [0, 0, 0],
        "today":     [0, 0, 0],
        "week":      [0, 0, 0],
        "month":     [0, 0, 0],
        "all":       [0, 0, 0],
    }

    for jsonl_file in base.rglob("*.jsonl"):
        try:
            with open(jsonl_file, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        if msg.get("type") != "assistant":
                            continue
                        usage = msg.get("message", {}).get("usage")
                        if not usage:
                            continue
                        inp   = usage.get("input_tokens", 0)
                        out   = usage.get("output_tokens", 0)
                        cache = usage.get("cache_read_input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)

                        buckets["all"][0] += inp
                        buckets["all"][1] += out
                        buckets["all"][2] += cache

                        ts_str = msg.get("timestamp", "")
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if ts >= month_start:
                                buckets["month"][0] += inp
                                buckets["month"][1] += out
                                buckets["month"][2] += cache
                            if ts >= week_start:
                                buckets["week"][0] += inp
                                buckets["week"][1] += out
                                buckets["week"][2] += cache
                            if ts >= today_start:
                                buckets["today"][0] += inp
                                buckets["today"][1] += out
                                buckets["today"][2] += cache
                            if ts >= five_hour_start:
                                buckets["five_hour"][0] += inp
                                buckets["five_hour"][1] += out
                                buckets["five_hour"][2] += cache
                        except Exception:
                            pass
                    except (json.JSONDecodeError, KeyError):
                        pass
        except OSError:
            pass

    def _make(vals: list) -> dict:
        inp, out, cache = vals
        return {"input": inp, "output": out, "cache": cache, "total": inp + out + cache}

    return {
        "five_hour": _make(buckets["five_hour"]),
        "today":     _make(buckets["today"]),
        "week":      _make(buckets["week"]),
        "month":     _make(buckets["month"]),
        "all":       _make(buckets["all"]),
    }


def format_reset_time(iso_str: str | None) -> str:
    if not iso_str:
        return "unknown"
    try:
        reset_dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        total_sec = int((reset_dt - datetime.now(timezone.utc)).total_seconds())
        if total_sec <= 0:
            return "any moment"
        days, remainder = divmod(total_sec, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    except Exception:
        return iso_str
