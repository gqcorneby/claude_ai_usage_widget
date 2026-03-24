"""
Detail popup window for Claude Usage Widget.
Shows per-account usage breakdown with progress bars and reset timers.
"""

import gi
gi.require_version('Gtk', '3.0')

from gi.repository import Gtk, Gdk

from shared import get_color_for_pct, parse_utilization, format_reset_time


class UsageDetailWindow(Gtk.Window):
    """Popup window showing detailed usage info for all accounts."""

    def __init__(self, accounts_data: list[dict], last_updated: str,
                 thresholds: dict, version: str, on_refresh):
        super().__init__(title="Claude AI Usage")
        self.set_default_size(400, -1)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.MOUSE)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_keep_above(True)
        self.set_decorated(True)
        self.connect("focus-out-event", lambda *_: self.destroy())

        self._apply_css()

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(16)
        vbox.set_margin_bottom(16)
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)

        # Header
        title = Gtk.Label(label="Claude Usage")
        title.get_style_context().add_class("title-label")
        title.set_halign(Gtk.Align.START)
        vbox.pack_start(title, False, False, 0)

        # Render each account
        for acct in accounts_data:
            self._add_account_section(vbox, acct, thresholds)

        # Footer
        sep = Gtk.Separator()
        sep.get_style_context().add_class("separator")
        vbox.pack_start(sep, False, False, 4)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        updated = Gtk.Label(label=f"Updated: {last_updated}")
        updated.get_style_context().add_class("metric-sub")
        footer.pack_start(updated, False, False, 0)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.set_relief(Gtk.ReliefStyle.NONE)
        btn_css = Gtk.CssProvider()
        btn_css.load_from_data(b"""
            button { color: #8888aa; background: transparent; border: none; padding: 2px 8px; }
            button:hover { color: #e0e0ff; }
        """)
        refresh_btn.get_style_context().add_provider(btn_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        refresh_btn.connect("clicked", lambda _: (self.destroy(), on_refresh()))
        footer.pack_end(refresh_btn, False, False, 0)
        vbox.pack_start(footer, False, False, 0)

        ver = Gtk.Label(label=f"v{version}")
        ver.get_style_context().add_class("reset-label")
        ver.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(ver, False, False, 0)

        self.add(vbox)
        self.show_all()

    def _apply_css(self):
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            window { background-color: #1a1a2e; }
            .title-label { color: #e0e0ff; font-size: 16px; font-weight: bold; }
            .account-label { color: #c0c0ff; font-size: 14px; font-weight: bold; }
            .section-label { color: #a0a0c0; font-size: 11px; font-weight: bold; letter-spacing: 2px; }
            .metric-sub { color: #8888aa; font-size: 11px; }
            .reset-label { color: #6b7280; font-size: 11px; }
            .status-ok { color: #22c55e; font-size: 11px; }
            .status-err { color: #ef4444; font-size: 11px; }
            .separator { background-color: #2a2a4a; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _add_account_section(self, vbox: Gtk.Box, acct: dict, thresholds: dict):
        """Add one account's usage section to the popup."""
        label = acct["label"]
        usage = acct.get("usage_data")
        error = acct.get("error")

        sep = Gtk.Separator()
        sep.get_style_context().add_class("separator")
        vbox.pack_start(sep, False, False, 4)

        # Account header row
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        name = Gtk.Label(label=f"Account: {label}")
        name.get_style_context().add_class("account-label")
        header.pack_start(name, False, False, 0)

        if error:
            st = Gtk.Label(label=f"  {error}")
            st.get_style_context().add_class("status-err")
            header.pack_end(st, False, False, 0)
        elif usage:
            st = Gtk.Label(label="  Connected")
            st.get_style_context().add_class("status-ok")
            header.pack_end(st, False, False, 0)
        vbox.pack_start(header, False, False, 0)

        # Subscription info
        sub_info = acct.get("subscription_info")
        if sub_info and sub_info.get("subscription_type"):
            sub_lbl = Gtk.Label(label=f"Plan: {sub_info['subscription_type']}")
            sub_lbl.get_style_context().add_class("metric-sub")
            sub_lbl.set_halign(Gtk.Align.START)
            vbox.pack_start(sub_lbl, False, False, 0)

        if not usage:
            if not error:
                err_lbl = Gtk.Label(label="No data available")
                err_lbl.get_style_context().add_class("status-err")
                err_lbl.set_halign(Gtk.Align.START)
                vbox.pack_start(err_lbl, False, False, 2)
            return

        for key, window_label in [("five_hour", "5-HOUR"), ("seven_day", "7-DAY")]:
            bucket = usage.get(key)
            if not bucket:
                continue

            section = Gtk.Label(label=window_label)
            section.get_style_context().add_class("section-label")
            section.set_halign(Gtk.Align.START)
            vbox.pack_start(section, False, False, 2)

            pct, decimal = parse_utilization(bucket.get("utilization", 0))
            color = get_color_for_pct(pct, thresholds)

            val = Gtk.Label()
            val.set_markup(f'<span foreground="{color}" font_weight="bold" font="24">{pct}%</span>')
            val.set_halign(Gtk.Align.START)
            vbox.pack_start(val, False, False, 0)

            # Progress bar
            bar = Gtk.LevelBar()
            bar.set_min_value(0)
            bar.set_max_value(1.0)
            bar.set_value(min(decimal, 1.0))
            bar.set_size_request(-1, 8)
            bar.remove_offset_value("low")
            bar.remove_offset_value("high")
            bar.remove_offset_value("full")
            bar_css = Gtk.CssProvider()
            bar_css.load_from_data(f"""
                levelbar trough {{ background-color: #2a2a4a; border-radius: 4px; min-height: 8px; }}
                levelbar trough block.filled {{ background-color: {color}; border-radius: 4px; min-height: 8px; }}
            """.encode())
            bar.get_style_context().add_provider(bar_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            vbox.pack_start(bar, False, False, 0)

            reset_str = format_reset_time(bucket.get("resets_at"))
            reset_lbl = Gtk.Label(label=f"Resets in {reset_str}")
            reset_lbl.get_style_context().add_class("reset-label")
            reset_lbl.set_halign(Gtk.Align.START)
            vbox.pack_start(reset_lbl, False, False, 0)
