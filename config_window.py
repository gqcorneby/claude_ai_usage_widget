"""
Configuration window for Claude Usage Widget.
Lets the user add, edit, or remove accounts (label + credentials directory).
On save, writes config.json and triggers a callback so the app reloads live.
"""

import gi
gi.require_version('Gtk', '3.0')

import json
import os
from pathlib import Path

from gi.repository import Gtk, Gdk

CONFIG_DIR = Path.home() / ".config" / "claude-usage-widget"
CONFIG_FILE = CONFIG_DIR / "config.json"


class ConfigWindow(Gtk.Window):
    """Dialog for editing the list of accounts."""

    def __init__(self, current_accounts: list[dict], on_save):
        super().__init__(title="Configure Accounts")
        self.set_default_size(460, -1)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_keep_above(True)
        self._on_save_cb = on_save
        self._rows: list[tuple[Gtk.Entry, Gtk.Entry]] = []  # (label_entry, dir_entry)

        self._apply_css()

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_top(16)
        outer.set_margin_bottom(16)
        outer.set_margin_start(20)
        outer.set_margin_end(20)

        title = Gtk.Label(label="Accounts")
        title.get_style_context().add_class("cfg-title")
        title.set_halign(Gtk.Align.START)
        outer.pack_start(title, False, False, 0)

        # Column headers
        hdr_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for text, expand in [("Label", False), ("Credentials Directory", True)]:
            h = Gtk.Label(label=text)
            h.get_style_context().add_class("cfg-col-header")
            h.set_halign(Gtk.Align.START)
            hdr_row.pack_start(h, expand, expand, 0)
        outer.pack_start(hdr_row, False, False, 0)

        # Rows container
        self._rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.pack_start(self._rows_box, False, False, 0)

        for acct in current_accounts:
            self._add_row(acct.get("label", ""), acct.get("credentials_dir", ""))

        add_btn = Gtk.Button(label="+ Add Account")
        add_btn.get_style_context().add_class("cfg-add-btn")
        add_btn.set_halign(Gtk.Align.START)
        add_btn.connect("clicked", lambda _: self._add_row("", "~/.claude"))
        outer.pack_start(add_btn, False, False, 4)

        sep = Gtk.Separator()
        sep.get_style_context().add_class("cfg-sep")
        outer.pack_start(sep, False, False, 4)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.destroy())
        save_btn = Gtk.Button(label="Save & Refresh")
        save_btn.get_style_context().add_class("cfg-save-btn")
        save_btn.connect("clicked", self._on_save)
        footer.pack_end(save_btn, False, False, 0)
        footer.pack_end(cancel_btn, False, False, 0)
        outer.pack_start(footer, False, False, 0)

        self.add(outer)
        self.show_all()

    def _apply_css(self):
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            window { background-color: #1a1a2e; }
            .cfg-title { color: #e0e0ff; font-size: 16px; font-weight: bold; }
            .cfg-col-header { color: #6b7280; font-size: 11px; font-weight: bold; }
            entry {
                background-color: #2a2a4a; color: #e0e0ff;
                border: 1px solid #3a3a5a; border-radius: 4px; padding: 4px 8px;
            }
            entry:focus { border-color: #7070aa; }
            .cfg-remove-btn { color: #ef4444; background: transparent; border: none; padding: 2px 6px; }
            .cfg-remove-btn:hover { color: #ff6666; }
            .cfg-add-btn {
                color: #8888aa; background: transparent;
                border: 1px solid #3a3a5a; border-radius: 4px; padding: 4px 12px;
            }
            .cfg-add-btn:hover { color: #e0e0ff; border-color: #7070aa; }
            .cfg-save-btn {
                background-color: #3a3a6a; color: #e0e0ff;
                border: none; border-radius: 4px; padding: 4px 16px;
            }
            .cfg-save-btn:hover { background-color: #5050aa; }
            button { color: #8888aa; background: transparent; border: 1px solid #3a3a5a; border-radius: 4px; padding: 4px 12px; }
            button:hover { color: #e0e0ff; }
            .cfg-sep { background-color: #2a2a4a; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _add_row(self, label: str, cred_dir: str):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        label_entry = Gtk.Entry()
        label_entry.set_text(label)
        label_entry.set_width_chars(10)
        label_entry.set_max_width_chars(12)
        label_entry.set_placeholder_text("Name")

        dir_entry = Gtk.Entry()
        dir_entry.set_text(cred_dir)
        dir_entry.set_placeholder_text("~/.claude")

        remove_btn = Gtk.Button(label="✕")
        remove_btn.get_style_context().add_class("cfg-remove-btn")
        remove_btn.set_relief(Gtk.ReliefStyle.NONE)

        row.pack_start(label_entry, False, False, 0)
        row.pack_start(dir_entry, True, True, 0)
        row.pack_start(remove_btn, False, False, 0)

        entry_pair = (label_entry, dir_entry)
        self._rows.append(entry_pair)
        self._rows_box.pack_start(row, False, False, 0)
        row.show_all()

        def on_remove(_btn, r=row, ep=entry_pair):
            self._rows_box.remove(r)
            self._rows.remove(ep)

        remove_btn.connect("clicked", on_remove)

    def _on_save(self, _btn):
        accounts = [
            {"label": le.get_text().strip(), "credentials_dir": de.get_text().strip()}
            for le, de in self._rows
            if le.get_text().strip() and de.get_text().strip()
        ]

        if not accounts:
            dlg = Gtk.MessageDialog(
                transient_for=self, flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="At least one account is required.",
            )
            dlg.run()
            dlg.destroy()
            return

        try:
            existing = json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
        except (json.JSONDecodeError, OSError):
            existing = {}

        existing["accounts"] = accounts
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(existing, indent=2))
        os.chmod(CONFIG_FILE, 0o600)

        self.destroy()
        self._on_save_cb(accounts)
