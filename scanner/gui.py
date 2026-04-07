"""
Network Port Scanner - GUI Module
Tkinter-based graphical interface with live results, ETA, scan history,
banner grabbing toggle, preset port ranges, and safe threading.

GUI upgrades:
  - Alternating row stripes + green highlight for open ports
  - Live "X open" counter badge next to Start button
  - Sortable treeview columns (port, service, banner)
  - Right-click context menu to copy row to clipboard
  - Persistent status bar at the bottom of the window
  - Animated scan button dots while scanning
  - Window title reflects scan state
  - Scanner tab label shows result count after scan
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time

from scanner.core import PortScanner, EventType
from scanner.utils import Validator, Exporter


# ── Tooltip helper ──────────────────────────────────────────────────────────

class _Tooltip:
    """Lightweight hover tooltip — no external deps."""

    DELAY_MS  = 600
    PAD       = 6

    def __init__(self, widget: tk.Widget, text: str):
        self._widget  = widget
        self._text    = text
        self._job     = None
        self._win     = None
        widget.bind("<Enter>",    self._schedule, add="+")
        widget.bind("<Leave>",    self._cancel,   add="+")
        widget.bind("<Button>",   self._cancel,   add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._job = self._widget.after(self.DELAY_MS, self._show)

    def _cancel(self, _event=None):
        if self._job:
            self._widget.after_cancel(self._job)
            self._job = None
        if self._win:
            self._win.destroy()
            self._win = None

    def _show(self):
        if self._win:
            return
        x = self._widget.winfo_rootx() + self._widget.winfo_width() // 2
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._win = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(tw, text=self._text, justify="left",
                       background="#ffffe0", relief="solid", borderwidth=1,
                       font=("TkDefaultFont", 8), padx=self.PAD, pady=self.PAD // 2,
                       wraplength=260)
        lbl.pack()


# ── Preset port ranges ───────────────────────────────────────────────────────

PRESETS = {
    "Well-Known (1-1024)":     (1, 1024),
    "Registered (1025-49151)": (1025, 49151),
    "Common Services":         None,   # sentinel -- uses COMMON_PORTS list
    "All Ports (1-65535)":     (1, 65535),
}

COMMON_PORTS = [
    21, 22, 23, 25, 53, 80, 88, 110, 143, 389,
    443, 445, 465, 587, 636, 993, 995, 1433, 1521,
    3306, 3389, 5432, 5900, 6379, 8080, 8443, 8888,
    9200, 27017,
]

# Treeview row tags
TAG_ODD     = "odd"
TAG_EVEN    = "even"
TAG_OPEN    = "open_port"
TAG_SUMMARY = "summary"

# Animated scan button frames
_SCAN_FRAMES = ["Scanning .", "Scanning ..", "Scanning ..."]


# ── Main GUI class ────────────────────────────────────────────────────────────

class PortScannerGUI:
    """Tkinter GUI for the Network Port Scanner."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Network Port Scanner")
        self.root.geometry("940x720")
        self.root.minsize(800, 580)

        self.scanner: PortScanner | None = None
        self.scanning       = False
        self._stop_requested = False
        self.last_results: list | None = None
        self._scan_start_time: float = 0.0
        self._elapsed_after_id  = None
        self._animate_after_id  = None
        self._animate_frame     = 0
        self._open_count        = 0
        self._dark_mode         = False
        self._sort_state: dict[str, bool] = {}
        self._history: list[tuple[str, list]] = []

        self._setup_ui()
        # Don't call _apply_theme() at startup - light mode is the default.
        # Only apply theme when user explicitly toggles it.
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        # Top bar
        topbar = ttk.Frame(self.root)
        topbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 0))
        topbar.columnconfigure(0, weight=1)
        self._theme_btn = ttk.Button(topbar, text="Dark Mode",
                                     command=self._toggle_theme, width=14)
        self._theme_btn.grid(row=0, column=1, sticky="e")

        # Notebook — apply explicit tab styling so tabs are clearly visible
        # on all platforms regardless of system theme.
        _nb_style = ttk.Style()
        _nb_style.theme_use("clam")   # clam gives us reliable tab control
        _nb_style.configure("TNotebook",
            background="#e8e8e8", tabmargins=[2, 4, 0, 0])
        _nb_style.configure("TNotebook.Tab",
            background="#c8c8c8", foreground="#222222",
            padding=[12, 4], font=("TkDefaultFont", 9))
        _nb_style.map("TNotebook.Tab",
            background=[("selected", "#ffffff"), ("active", "#dedede")],
            foreground=[("selected", "#000000")],
            expand=[("selected", [1, 1, 1, 0])])

        self._notebook = ttk.Notebook(self.root)
        self._notebook.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        scanner_tab = ttk.Frame(self._notebook)
        self._notebook.add(scanner_tab, text="  Scanner  ")
        self._build_scanner_tab(scanner_tab)

        history_tab = ttk.Frame(self._notebook)
        self._notebook.add(history_tab, text="  History  ")
        self._build_history_tab(history_tab)

        # Persistent status bar
        self._statusbar_var = tk.StringVar(
            value="Ready -- enter a target and press Start Scan.")
        self._statusbar = ttk.Label(
            self.root, textvariable=self._statusbar_var,
            relief="sunken", anchor="w", padding=(6, 2))
        self._statusbar.grid(row=2, column=0, sticky="ew")

    # ── Scanner tab ───────────────────────────────────────────────────────────

    def _build_scanner_tab(self, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)

        # Settings
        settings = ttk.LabelFrame(parent, text="Scan Settings", padding=10)
        settings.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)

        ttk.Label(settings, text="Target (IP / Hostname):").grid(
            row=0, column=0, sticky="w", padx=(0, 6))
        self.target_var = tk.StringVar(value="127.0.0.1")
        target_entry = ttk.Entry(settings, textvariable=self.target_var, width=32)
        target_entry.grid(row=0, column=1, columnspan=3, sticky="ew", pady=2)
        target_entry.bind("<Return>", lambda e: self.start_scan())

        ttk.Label(settings, text="Start Port:").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=4)
        self.start_port_var = tk.StringVar(value="1")
        start_entry = ttk.Entry(settings, textvariable=self.start_port_var, width=10)
        start_entry.grid(row=1, column=1, sticky="w")
        start_entry.bind("<Return>", lambda e: self.start_scan())

        ttk.Label(settings, text="End Port:").grid(
            row=1, column=2, sticky="w", padx=(12, 6))
        self.end_port_var = tk.StringVar(value="1024")
        end_entry = ttk.Entry(settings, textvariable=self.end_port_var, width=10)
        end_entry.grid(row=1, column=3, sticky="w")
        end_entry.bind("<Return>", lambda e: self.start_scan())

        ttk.Label(settings, text="Preset:").grid(
            row=2, column=0, sticky="w", padx=(0, 6), pady=4)
        self.preset_var = tk.StringVar(value="-- choose --")
        preset_cb = ttk.Combobox(settings, textvariable=self.preset_var,
                                  values=list(PRESETS.keys()),
                                  state="readonly", width=28)
        preset_cb.grid(row=2, column=1, columnspan=2, sticky="w")
        preset_cb.bind("<<ComboboxSelected>>", self._apply_preset)

        ttk.Label(settings, text="Timeout (s):").grid(
            row=3, column=0, sticky="w", padx=(0, 6), pady=4)
        self.timeout_var = tk.StringVar(value="1.0")
        timeout_entry = ttk.Entry(settings, textvariable=self.timeout_var, width=10)
        timeout_entry.grid(row=3, column=1, sticky="w")

        ttk.Label(settings, text="Threads:").grid(
            row=3, column=2, sticky="w", padx=(12, 6))
        self.threads_var = tk.StringVar(value="100")
        threads_entry = ttk.Entry(settings, textvariable=self.threads_var, width=10)
        threads_entry.grid(row=3, column=3, sticky="w")

        self.banner_var = tk.BooleanVar(value=False)
        banner_cb = ttk.Checkbutton(settings, text="Grab service banners (slower)",
                                variable=self.banner_var)
        banner_cb.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))

        # Inline validation error label (hidden until needed)
        self._inline_err_var = tk.StringVar(value="")
        self._inline_err_lbl = ttk.Label(settings, textvariable=self._inline_err_var,
                                          foreground="#cc2200",
                                          font=("TkDefaultFont", 8))
        self._inline_err_lbl.grid(row=5, column=0, columnspan=4,
                                   sticky="w", pady=(4, 0))

        # Tooltips — attached directly to the widget references we already have
        _Tooltip(target_entry,
                 "IP address (e.g. 192.168.1.1) or hostname (e.g. scanme.nmap.org). "
                 "Press Enter to start scan.")
        _Tooltip(start_entry,  "First port to scan (1-65535)")
        _Tooltip(end_entry,    "Last port to scan (1-65535). Must be >= Start Port.")
        _Tooltip(preset_cb,    "Quick-fill the port range. "
                               "Common Services scans 29 well-known ports only.")
        _Tooltip(timeout_entry,"Seconds to wait for each connection. "
                               "Lower = faster but may miss slow hosts. (0.1-60)")
        _Tooltip(threads_entry,"Parallel scan threads. Higher = faster. "
                               "100-200 is safe for most systems. Max 1000.")
        _Tooltip(banner_cb,    "Try to read the service greeting banner on open ports. "
                               "Adds ~2s per open port - leave off for fast scans.")

        # Buttons + live open-count badge
        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        self.scan_btn = ttk.Button(btn_frame, text="Start Scan",
                                   command=self.start_scan)
        self.scan_btn.pack(side="left", padx=(0, 6))

        self.stop_btn = ttk.Button(btn_frame, text="Stop",
                                   command=self.stop_scan, state="disabled")
        self.stop_btn.pack(side="left", padx=(0, 6))

        ttk.Button(btn_frame, text="Clear",
                   command=self.clear_results).pack(side="left", padx=(0, 6))

        self.again_btn = ttk.Button(btn_frame, text="Scan Again",
                                    command=self._scan_again, state="disabled")
        self.again_btn.pack(side="left", padx=(0, 6))
        _Tooltip(self.again_btn,
                 "Re-run the exact same scan with the same settings.")

        self._open_count_var = tk.StringVar(value="")
        self._open_badge = ttk.Label(btn_frame,
                                      textvariable=self._open_count_var,
                                      foreground="#2a9d2a",
                                      font=("TkDefaultFont", 9, "bold"))
        self._open_badge.pack(side="left", padx=(12, 0))

        # Progress
        prog_frame = ttk.LabelFrame(parent, text="Progress", padding=8)
        prog_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        prog_frame.columnconfigure(0, weight=1)

        self.progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(prog_frame, variable=self.progress_var,
                        maximum=100).grid(row=0, column=0, sticky="ew", padx=4)

        status_row = ttk.Frame(prog_frame)
        status_row.grid(row=1, column=0, sticky="ew", padx=4, pady=(4, 0))
        status_row.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_row, textvariable=self.status_var).grid(
            row=0, column=0, sticky="w")

        self.elapsed_var = tk.StringVar(value="")
        ttk.Label(status_row, textvariable=self.elapsed_var,
                  foreground="#777").grid(row=0, column=1, sticky="e")

        # Results treeview
        results_frame = ttk.LabelFrame(parent, text="Results", padding=8)
        results_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)

        cols = ("port", "service", "status", "banner")
        self.tree = ttk.Treeview(results_frame, columns=cols,
                                  show="headings", selectmode="extended")
        for col, text, width, stretch in [
            ("port",    "Port",    70,  False),
            ("service", "Service", 160, False),
            ("status",  "Status",  70,  False),
            ("banner",  "Banner",  400, True),
        ]:
            self.tree.heading(col, text=text, anchor="w",
                              command=lambda c=col: self._sort_tree(self.tree, c))
            self.tree.column(col, width=width, stretch=stretch)

        self.tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(results_frame, orient="vertical",
                             command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(results_frame, orient="horizontal",
                             command=self.tree.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Right-click context menu
        self._ctx_menu = tk.Menu(self.root, tearoff=0)
        self._ctx_menu.add_command(label="Copy row",
                                    command=self._copy_selected_row)
        self._ctx_menu.add_command(label="Copy port number",
                                    command=self._copy_port_number)
        self.tree.bind("<Button-3>",       self._show_context_menu)
        self.tree.bind("<Button-2>",       self._show_context_menu)
        self.tree.bind("<Double-Button-1>", self._show_row_detail)

        # Log label (row=2 — below the horizontal scrollbar)
        self.log_var = tk.StringVar(value="")
        ttk.Label(results_frame, textvariable=self.log_var,
                  foreground="#888", wraplength=800, justify="left").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # Export buttons
        export_frame = ttk.Frame(parent)
        export_frame.grid(row=4, column=0, sticky="ew", padx=8, pady=(4, 8))

        _export_tips = {
            "Export TXT":  "Plain text report with summary header.",
            "Export JSON": "Machine-readable JSON with full metadata.",
            "Export CSV":  "Spreadsheet-compatible CSV for Excel/Sheets.",
        }
        self.export_btns: list[ttk.Button] = []
        for label, ext, fn in [
            ("Export TXT",  ".txt",  self.export_txt),
            ("Export JSON", ".json", self.export_json),
            ("Export CSV",  ".csv",  self.export_csv),
        ]:
            btn = ttk.Button(export_frame, text=label,
                              command=fn, state="disabled")
            btn.pack(side="left", padx=(0, 6))
            _Tooltip(btn, _export_tips[label])
            self.export_btns.append(btn)

        self._configure_tree_tags(self.tree)

    # ── History tab ───────────────────────────────────────────────────────────

    def _build_history_tab(self, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(3, weight=1)

        ttk.Label(parent, text="Previous scans in this session:",
                  padding=(8, 8, 8, 4)).grid(row=0, column=0, sticky="w")

        hist_frame = ttk.Frame(parent)
        hist_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 4))
        hist_frame.columnconfigure(0, weight=1)
        hist_frame.rowconfigure(0, weight=1)

        self.history_list = tk.Listbox(hist_frame, activestyle="dotbox",
                                        selectmode="single", height=6)
        self.history_list.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(hist_frame, orient="vertical",
                             command=self.history_list.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.history_list.configure(yscrollcommand=vsb.set)
        self.history_list.bind("<<ListboxSelect>>", self._load_history_entry)

        # History export buttons
        hist_export_frame = ttk.Frame(parent)
        hist_export_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))

        self.hist_export_btns: list[ttk.Button] = []
        for label, ext, fn in [
            ("Export TXT",  ".txt",  self._hist_export_txt),
            ("Export JSON", ".json", self._hist_export_json),
            ("Export CSV",  ".csv",  self._hist_export_csv),
        ]:
            btn = ttk.Button(hist_export_frame, text=label,
                              command=fn, state="disabled")
            btn.pack(side="left", padx=(0, 6))
            self.hist_export_btns.append(btn)

        # Detail treeview
        detail_frame = ttk.LabelFrame(parent, text="Details", padding=8)
        detail_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 8))
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)

        cols = ("port", "service", "status", "banner")
        self.hist_tree = ttk.Treeview(detail_frame, columns=cols,
                                       show="headings", height=8)
        for col, w, stretch in [
            ("port",    70,  False),
            ("service", 160, False),
            ("status",  70,  False),
            ("banner",  400, True),
        ]:
            self.hist_tree.heading(
                col, text=col.capitalize(), anchor="w",
                command=lambda c=col: self._sort_tree(self.hist_tree, c))
            self.hist_tree.column(col, width=w, stretch=stretch)

        self.hist_tree.grid(row=0, column=0, sticky="nsew")
        vsb2 = ttk.Scrollbar(detail_frame, orient="vertical",
                              command=self.hist_tree.yview)
        vsb2.grid(row=0, column=1, sticky="ns")
        self.hist_tree.configure(yscrollcommand=vsb2.set)

        self._hist_ctx_menu = tk.Menu(self.root, tearoff=0)
        self._hist_ctx_menu.add_command(
            label="Copy row",
            command=lambda: self._copy_row_from(self.hist_tree))
        self.hist_tree.bind(
            "<Button-3>",
            lambda e: self._show_ctx_for(e, self.hist_tree, self._hist_ctx_menu))
        self.hist_tree.bind(
            "<Button-2>",
            lambda e: self._show_ctx_for(e, self.hist_tree, self._hist_ctx_menu))

        self._configure_tree_tags(self.hist_tree)

    # ─────────────────────────────────────────────────────────────────────────
    # Theme
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        style = ttk.Style(self.root)
        if self._dark_mode:
            bg, fg     = "#1e1e1e", "#dcdcdc"
            entry_bg   = "#2d2d2d"
            select_bg  = "#3a5a3a"
            stripe_odd    = "#252525"
            stripe_even   = "#2d2d2d"
            open_colour   = "#1a3a1a"
            summary_colour= "#1a1a2e"
            sb_bg, sb_fg  = "#141414", "#aaaaaa"
            badge_fg      = "#4ec94e"

            self.root.configure(bg=bg)
            style.theme_use("clam")
            style.configure(".", background=bg, foreground=fg,
                            fieldbackground=entry_bg, bordercolor="#444")
            for w in ("TFrame", "TLabelframe"):
                style.configure(w, background=bg)
            style.configure("TLabelframe.Label", background=bg, foreground=fg)
            style.configure("TLabel",       background=bg, foreground=fg)
            style.configure("TButton",      background="#3a3a3a", foreground=fg)
            style.configure("TEntry",       fieldbackground=entry_bg, foreground=fg)
            style.configure("TCombobox",    fieldbackground=entry_bg, foreground=fg)
            style.configure("TCheckbutton", background=bg, foreground=fg)
            style.configure("TNotebook",    background=bg, tabmargins=[2, 4, 0, 0])
            style.configure("TNotebook.Tab",
                background="#3a3a3a", foreground="#dcdcdc", padding=[12, 4])
            style.map("TNotebook.Tab",
                background=[("selected", "#1e1e1e"), ("active", "#4a4a4a")],
                foreground=[("selected", "#ffffff")],
                expand=[("selected", [1, 1, 1, 0])])
            style.configure("Treeview",
                background=entry_bg, foreground=fg,
                fieldbackground=entry_bg, rowheight=22)
            style.configure("Treeview.Heading",
                background="#2d2d2d", foreground=fg)
            style.map("Treeview", background=[("selected", select_bg)])
            self._theme_btn.configure(text="Light Mode")
            self._open_badge.configure(foreground=badge_fg)
            self._statusbar.configure(background=sb_bg, foreground=sb_fg)
        else:
            stripe_odd    = "#f5f5f5"
            stripe_even   = "#ffffff"
            open_colour   = "#d4edda"
            summary_colour= "#e8eaf6"
            badge_fg      = "#2a9d2a"

            # Use a fresh style instance on the default theme to get real
            # system colors - never pass empty strings, they render as black
            # on Windows.
            style.theme_use("default")
            _s = ttk.Style()
            sys_bg  = _s.lookup("TFrame",  "background") or "SystemButtonFace"
            sys_fg  = _s.lookup("TLabel",  "foreground") or "SystemWindowText"
            sys_ebg = _s.lookup("TEntry",  "fieldbackground") or "SystemWindow"
            sys_tbg = _s.lookup("Treeview","background") or "SystemWindow"
            sys_tfg = _s.lookup("Treeview","foreground") or "SystemWindowText"

            self.root.configure(bg=sys_bg)
            style.configure(".",           background=sys_bg,  foreground=sys_fg)
            style.configure("TFrame",      background=sys_bg)
            style.configure("TLabelframe", background=sys_bg)
            style.configure("TLabelframe.Label", background=sys_bg, foreground=sys_fg)
            style.configure("TLabel",      background=sys_bg,  foreground=sys_fg)
            style.configure("TButton",     background=sys_bg,  foreground=sys_fg)
            style.configure("TEntry",      fieldbackground=sys_ebg, foreground=sys_fg)
            style.configure("TCombobox",   fieldbackground=sys_ebg, foreground=sys_fg)
            style.configure("TCheckbutton",background=sys_bg,  foreground=sys_fg)
            style.configure("TNotebook",   background="#e8e8e8", tabmargins=[2, 4, 0, 0])
            style.configure("TNotebook.Tab",
                background="#c8c8c8", foreground="#222222", padding=[12, 4])
            style.map("TNotebook.Tab",
                background=[("selected", "#ffffff"), ("active", "#dedede")],
                foreground=[("selected", "#000000")],
                expand=[("selected", [1, 1, 1, 0])])
            style.configure("Treeview",
                background=sys_tbg, foreground=sys_tfg,
                fieldbackground=sys_tbg, rowheight=22)
            style.configure("Treeview.Heading", background=sys_bg, foreground=sys_fg)
            style.map("Treeview", background=[("selected", "SystemHighlight")])
            self._theme_btn.configure(text="Dark Mode")
            self._open_badge.configure(foreground=badge_fg)
            self._statusbar.configure(background=sys_bg, foreground=sys_fg)

        for tree in (self.tree, self.hist_tree):
            tree.tag_configure(TAG_ODD,     background=stripe_odd)
            tree.tag_configure(TAG_EVEN,    background=stripe_even)
            tree.tag_configure(TAG_OPEN,    background=open_colour,
                               font=("TkDefaultFont", 9, "bold"))
            tree.tag_configure(TAG_SUMMARY, background=summary_colour,
                               foreground="#888888")

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        self._apply_theme()

    def _configure_tree_tags(self, tree: ttk.Treeview):
        """Seed tags with light-mode defaults; _apply_theme() overrides them."""
        tree.tag_configure(TAG_ODD,     background="#f5f5f5")
        tree.tag_configure(TAG_EVEN,    background="#ffffff")
        tree.tag_configure(TAG_OPEN,    background="#d4edda",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure(TAG_SUMMARY, background="#e8eaf6",
                           foreground="#888888")

    # ─────────────────────────────────────────────────────────────────────────
    # Sortable columns
    # ─────────────────────────────────────────────────────────────────────────

    def _sort_tree(self, tree: ttk.Treeview, col: str):
        """Sort treeview by column, toggling direction. Summary rows stay put."""
        rows = []
        for iid in tree.get_children():
            tags = tree.item(iid, "tags")
            if TAG_SUMMARY in tags:
                continue
            val = tree.set(iid, col)
            try:
                # Use a (0, int) tuple so numeric keys always sort before
                # string keys and the two types never compare directly,
                # which raises TypeError in Python 3.
                sort_key = (0, int(val))
            except (ValueError, TypeError):
                sort_key = (1, val.lower() if isinstance(val, str) else str(val))
            rows.append((sort_key, iid))

        ascending = not self._sort_state.get(f"{id(tree)}_{col}", False)
        self._sort_state[f"{id(tree)}_{col}"] = ascending
        rows.sort(key=lambda x: x[0], reverse=not ascending)

        summary_count = sum(
            1 for iid in tree.get_children()
            if TAG_SUMMARY in tree.item(iid, "tags"))

        for idx, (_, iid) in enumerate(rows):
            tree.move(iid, "", summary_count + idx)
            # Preserve TAG_OPEN; re-stripe the rest
            current_tags = tree.item(iid, "tags")
            if TAG_OPEN in current_tags:
                tree.item(iid, tags=(TAG_OPEN,))
            else:
                tree.item(iid, tags=(TAG_ODD if idx % 2 == 0 else TAG_EVEN,))

        # Update heading arrow indicators
        arrow = " ^" if ascending else " v"
        for c in tree["columns"]:
            heading_text = tree.heading(c, "text")
            clean = heading_text.replace(" ^", "").replace(" v", "")
            tree.heading(c, text=clean + (arrow if c == col else ""))

    # ─────────────────────────────────────────────────────────────────────────
    # Context menu / clipboard
    # ─────────────────────────────────────────────────────────────────────────

    def _show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        try:
            self._ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._ctx_menu.grab_release()

    def _show_ctx_for(self, event, tree: ttk.Treeview, menu: tk.Menu):
        iid = tree.identify_row(event.y)
        if not iid:
            return
        tree.selection_set(iid)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _show_row_detail(self, event=None):
        """Open a popup showing full details of the double-clicked result row."""
        sel = self.tree.selection()
        if not sel:
            return
        values = self.tree.item(sel[0], "values")
        if not values or len(values) < 4:
            return
        port, service, status, banner = values[0], values[1], values[2], values[3]
        # Don't open a detail popup for summary/divider rows
        if str(port).startswith("---") or str(service).startswith("-- Scan"):
            return

        popup = tk.Toplevel(self.root)
        popup.title(f"Port {port} Details")
        popup.geometry("480x280")
        popup.resizable(True, True)
        popup.transient(self.root)
        popup.grab_set()

        frame = ttk.Frame(popup, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        fields = [
            ("Port",    str(port)),
            ("Service", str(service)),
            ("Status",  str(status)),
            ("Banner",  str(banner) if banner else "(none)"),
        ]
        for row_idx, (label, value) in enumerate(fields):
            ttk.Label(frame, text=label + ":", font=("TkDefaultFont", 9, "bold"),
                      anchor="w").grid(row=row_idx, column=0, sticky="nw",
                                       padx=(0, 12), pady=4)
            # Use a Text widget for banner so it wraps and is selectable
            if label == "Banner":
                txt = tk.Text(frame, height=5, width=40, wrap="word",
                              font=("TkFixedFont", 9), relief="groove",
                              background="#f8f8f8")
                txt.insert("1.0", value)
                txt.config(state="disabled")
                txt.grid(row=row_idx, column=1, sticky="ew", pady=4)
            else:
                ttk.Label(frame, text=value, anchor="w",
                          wraplength=320).grid(row=row_idx, column=1,
                                               sticky="w", pady=4)

        btn_row = ttk.Frame(popup, padding=(16, 0, 16, 12))
        btn_row.pack(fill="x")

        def _copy_all():
            popup.clipboard_clear()
            popup.clipboard_append(
                f"Port: {port}\nService: {service}\n"
                f"Status: {status}\nBanner: {banner}")
            self._set_status(f"Copied details for port {port}")

        ttk.Button(btn_row, text="Copy All", command=_copy_all).pack(side="left")
        ttk.Button(btn_row, text="Close", command=popup.destroy).pack(side="right")

        # Centre popup over main window
        popup.update_idletasks()
        px = self.root.winfo_x() + (self.root.winfo_width()  - popup.winfo_width())  // 2
        py = self.root.winfo_y() + (self.root.winfo_height() - popup.winfo_height()) // 2
        popup.geometry(f"+{px}+{py}")

    def _copy_row_from(self, tree: ttk.Treeview):
        sel = tree.selection()
        if not sel:
            return
        values = tree.item(sel[0], "values")
        text = "\t".join(str(v) for v in values)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._set_status(f"Copied: {text[:80]}")

    def _copy_selected_row(self):
        self._copy_row_from(self.tree)

    def _copy_port_number(self):
        sel = self.tree.selection()
        if not sel:
            return
        port = self.tree.item(sel[0], "values")[0]
        self.root.clipboard_clear()
        self.root.clipboard_append(str(port))
        self._set_status(f"Copied port: {port}")

    # ─────────────────────────────────────────────────────────────────────────
    # Status bar
    # ─────────────────────────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self._statusbar_var.set(msg)

    def _show_inline_error(self, msg: str):
        """Show validation error inline below settings (no popup)."""
        self._inline_err_var.set("  ⚠  " + msg)

    def _clear_inline_error(self):
        self._inline_err_var.set("")

    def _on_resolve_failed(self, err: str):
        """Called on the GUI thread when background DNS validation fails."""
        self.scanning = False
        self.scan_btn.config(text="Start Scan", state="normal")
        self.stop_btn.config(state="disabled")
        self.elapsed_var.set("")
        for attr in ("_elapsed_after_id", "_animate_after_id"):
            aid = getattr(self, attr, None)
            if aid:
                self.root.after_cancel(aid)
                setattr(self, attr, None)
        self.root.title("Network Port Scanner")
        self._show_inline_error(err)
        self._set_status(f"Error: {err}")

    # ─────────────────────────────────────────────────────────────────────────
    # Preset handler
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_preset(self, _event=None):
        choice = self.preset_var.get()
        if choice == "Common Services":
            self.start_port_var.set("common")
            self.end_port_var.set("common")
            self._set_status(
                f"Preset: Common Services ({len(COMMON_PORTS)} ports)")
        elif choice in PRESETS and PRESETS[choice]:
            s, e = PRESETS[choice]
            self.start_port_var.set(str(s))
            self.end_port_var.set(str(e))
            self._set_status(f"Preset: {choice}  ({e - s + 1:,} ports)")

    # ─────────────────────────────────────────────────────────────────────────
    # Scan lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def _safe_after(self, fn) -> None:
        """Schedule fn on the GUI thread, silently ignoring a destroyed root.

        After _on_close() calls root.destroy() the background thread may still
        be alive and try to marshal work back via root.after().  Tkinter raises
        TclError in that case; catching it here keeps the daemon thread clean.
        """
        try:
            self.root.after(0, fn)
        except Exception:
            pass

    def start_scan(self):
        if self.scanning:
            return

        self._stop_requested = False
        self._clear_inline_error()

        target = self.target_var.get().strip()

        use_common_ports = (self.start_port_var.get() == "common")

        if use_common_ports:
            start_port = COMMON_PORTS[0]
            end_port   = COMMON_PORTS[-1]
            port_list  = COMMON_PORTS
        else:
            try:
                start_port = int(self.start_port_var.get())
                end_port   = int(self.end_port_var.get())
            except ValueError:
                self._show_inline_error("Start port and end port must be integers.")
                return
            port_list = None

        try:
            timeout = float(self.timeout_var.get())
            threads = int(self.threads_var.get())
        except ValueError:
            self._show_inline_error(
                "Timeout must be a decimal number; threads must be an integer.")
            return

        if not use_common_ports:
            ok, err = Validator.validate_ports(start_port, end_port)
            if not ok:
                self._show_inline_error(err)
                return

        for ok, err in [Validator.validate_timeout(timeout),
                        Validator.validate_threads(threads)]:
            if not ok:
                self._show_inline_error(err)
                return

        # Reset UI
        self._clear_inline_error()
        self.tree.delete(*self.tree.get_children())
        self.log_var.set("")
        self.progress_var.set(0)
        self.elapsed_var.set("")
        self._open_count = 0
        self._open_count_var.set("")
        self._animate_frame = 0

        total = (len(port_list) if port_list
                 else end_port - start_port + 1)

        self.scanning = True
        self.scan_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.again_btn.config(state="disabled")
        for b in self.export_btns:
            b.config(state="disabled")

        # Show a resolving state immediately so the UI feels responsive while
        # DNS runs in the background thread below.
        self.status_var.set("Resolving...")
        self._set_status(f"Resolving {target}...")
        self.root.title(f"Network Port Scanner -- Resolving {target}...")
        self._scan_start_time = time.monotonic()

        self._tick_elapsed()
        self._tick_animate()

        grab_banners = self.banner_var.get()   # capture on GUI thread — not safe to call from background thread

        def _validate_then_scan():
            # Run DNS validation off the GUI thread to avoid freezing the UI
            # for up to 3 seconds on a slow DNS server.
            ok, err, resolved_ip = Validator.validate_target(target)
            if not ok:
                # Marshal back to the GUI thread for all UI updates.
                self._safe_after(lambda: self._on_resolve_failed(err))
                return

            # If the user clicked Stop during DNS resolution, honour it now
            # before the scanner is ever constructed.
            if self._stop_requested:
                self._safe_after(lambda: self._finish_scan([]))
                return

            self.scanner = PortScanner(
                target, start_port, end_port,
                timeout=timeout, threads=threads,
                grab_banners=grab_banners,
                port_list=port_list,
                resolved_ip=resolved_ip,   # reuse — avoids a second DNS lookup
            )
            self._safe_after(lambda: self._set_status(
                f"Scanning {target}  --  {total:,} port(s) queued..."))
            self._safe_after(lambda: self.status_var.set("Starting..."))
            self._safe_after(lambda: self.root.title(
                f"Network Port Scanner -- Scanning {target}..."))
            self.scanner.scan()

        threading.Thread(target=_validate_then_scan, daemon=True).start()
        self.root.after(100, self._poll_result_queue)

    # ── Tickers ───────────────────────────────────────────────────────────────

    def _tick_elapsed(self):
        if not self.scanning:
            return
        elapsed = time.monotonic() - self._scan_start_time
        self.elapsed_var.set(f"Elapsed: {elapsed:.0f}s")
        self._elapsed_after_id = self.root.after(1000, self._tick_elapsed)

    def _tick_animate(self):
        if not self.scanning:
            return
        frame = _SCAN_FRAMES[self._animate_frame % len(_SCAN_FRAMES)]
        self.scan_btn.config(text=frame)
        self._animate_frame += 1
        self._animate_after_id = self.root.after(500, self._tick_animate)

    # ── Result queue poller ───────────────────────────────────────────────────

    def _poll_result_queue(self):
        if self.scanner is None:
            # DNS resolution is still in progress on the background thread;
            # keep rescheduling so we pick up events as soon as the scanner exists.
            if self.scanning:
                self.root.after(100, self._poll_result_queue)
            return

        try:
            for _ in range(100):
                event = self.scanner.result_queue.get_nowait()
                kind  = event[0]

                if kind == EventType.OPEN_PORT:
                    p = event[1]
                    self._open_count += 1
                    self.tree.insert(
                        "", "end",
                        values=(p['port'], p['service'],
                                p['status'], p.get('banner', '')),
                        tags=(TAG_OPEN,))
                    self.tree.yview_moveto(1)
                    self._open_count_var.set(f"  {self._open_count} open")
                    self._set_status(
                        f"Open port found: {p['port']} ({p['service']})")

                elif kind == EventType.PROGRESS:
                    scanned, total = event[1], event[2]
                    pct = (scanned / total * 100) if total else 0
                    self.progress_var.set(pct)
                    if scanned > 0:
                        elapsed   = time.monotonic() - self._scan_start_time
                        rate      = scanned / elapsed if elapsed > 0 else 1
                        remaining = (total - scanned) / rate
                        eta = f"  ETA: {remaining:.0f}s" if pct < 99 else ""
                        open_str = (f"  —  {self._open_count} open"
                                    if self._open_count else "")
                        self.status_var.set(
                            f"Scanning... {scanned}/{total} "
                            f"({pct:.1f}%){eta}{open_str}")

                elif kind == EventType.STATUS:
                    self.log_var.set(event[1])
                    self._set_status(event[1])

                elif kind == EventType.ERROR:
                    msg = f"Error: {event[1]}"
                    self.log_var.set(msg)
                    self._set_status(msg)
                    self._finish_scan([])
                    return

                elif kind == EventType.SCAN_COMPLETE:
                    scan_time = event[2] if len(event) > 2 else None
                    self._finish_scan(event[1], scan_time)
                    return

        except Exception:
            pass

        if self.scanning:
            self.root.after(100, self._poll_result_queue)

    # ── Scan finish ───────────────────────────────────────────────────────────

    def _finish_scan(self, results: list, core_scan_time: float = None):
        for attr in ("_elapsed_after_id", "_animate_after_id"):
            aid = getattr(self, attr, None)
            if aid:
                self.root.after_cancel(aid)
                setattr(self, attr, None)

        scan_time = (core_scan_time if core_scan_time is not None
                     else time.monotonic() - self._scan_start_time)

        self.last_results = results
        self.progress_var.set(100)
        self.elapsed_var.set(f"Elapsed: {scan_time:.1f}s")

        n       = len(results)
        stopped = self._stop_requested or bool(self.scanner and self.scanner.should_stop)
        msg     = (f"Stopped -- {n} open port(s) found before stopping."
                   if stopped else
                   f"Done in {scan_time:.1f}s -- {n} open port(s) found.")

        self.status_var.set(msg)
        self._set_status(msg)

        # Window title + tab label
        target = self.scanner.target if self.scanner else "?"
        self.root.title(
            f"Network Port Scanner -- {n} open  [{target}]")
        self._notebook.tab(
            0, text=f"  Scanner ({n} open)  " if n else "  Scanner  ")

        # Summary header rows
        s_port = self.scanner.start_port if self.scanner else "?"
        e_port = self.scanner.end_port   if self.scanner else "?"
        for i, row in enumerate([
            ("------", "-- Scan Summary " + "-" * 34, "", ""),
            ("Target",  target, "", ""),
            ("Range",   f"{s_port} - {e_port}", "", ""),
            ("Time",    f"{scan_time:.2f}s", "", ""),
            ("Found",   f"{n} open port(s)", "", ""),
            ("------", "-" * 50, "", ""),
        ]):
            self.tree.insert("", i, values=row, tags=(TAG_SUMMARY,))

        if not results:
            self.tree.insert("", "end",
                             values=("", "No open ports found.", "", ""),
                             tags=(TAG_EVEN,))

        self.scanning = False
        self.scan_btn.config(text="Start Scan", state="normal")
        self.stop_btn.config(state="disabled")
        # "Scan Again" is only meaningful when we have a completed scanner to
        # replay; if the user stopped during DNS resolution self.scanner is
        # still None and the button would silently do nothing.
        self.again_btn.config(state="normal" if self.scanner else "disabled")
        for b in self.export_btns:
            b.config(state="normal")

        if self.scanner:
            label = (f"{self.scanner.target}  "
                     f"{self.scanner.start_port}-{self.scanner.end_port}  "
                     f"({n} open)  {time.strftime('%H:%M:%S')}")
            self._history.append((label, results))
            self.history_list.insert("end", label)

    def _scan_again(self):
        """Re-run the last scan with the same target and settings."""
        if not self.scanner or self.scanning:
            return
        # Re-populate the input fields from the last scanner instance
        self.target_var.set(self.scanner.target)
        if self.scanner.port_list:
            self.start_port_var.set("common")
            self.end_port_var.set("common")
        else:
            self.start_port_var.set(str(self.scanner.start_port))
            self.end_port_var.set(str(self.scanner.end_port))
        self.timeout_var.set(str(self.scanner.timeout))
        self.threads_var.set(str(self.scanner.thread_count))
        self.start_scan()

    def stop_scan(self):
        self._stop_requested = True
        if self.scanner:
            self.scanner.stop()
        self.status_var.set("Stopping...")
        self._set_status(
            "Stop requested -- waiting for workers to finish...")
        self.stop_btn.config(state="disabled")

    def clear_results(self):
        self.tree.delete(*self.tree.get_children())
        self.progress_var.set(0)
        self.elapsed_var.set("")
        self.status_var.set("Ready")
        self.log_var.set("")
        self._open_count = 0
        self._open_count_var.set("")
        self.last_results = None
        self._notebook.tab(0, text="  Scanner  ")
        self.root.title("Network Port Scanner")
        self._set_status("Results cleared.")
        self.again_btn.config(state="disabled")
        for b in self.export_btns:
            b.config(state="disabled")

    # ── Window close ──────────────────────────────────────────────────────────

    def _on_close(self):
        # Signal the background DNS/scan thread to abort before destroying
        # the root so it never calls self.root.after() on a dead widget.
        self._stop_requested = True
        if self.scanner:
            self.scanner.stop()
        self.root.destroy()

    # ── History helpers ───────────────────────────────────────────────────────

    def _load_history_entry(self, _event=None):
        sel = self.history_list.curselection()
        if not sel:
            return
        _, results = self._history[sel[0]]
        self.hist_tree.delete(*self.hist_tree.get_children())
        for idx, p in enumerate(results):
            tag = TAG_OPEN if p.get("status") == "open" \
                  else (TAG_ODD if idx % 2 == 0 else TAG_EVEN)
            self.hist_tree.insert(
                "", "end",
                values=(p['port'], p['service'],
                        p['status'], p.get('banner', '')),
                tags=(tag,))
        for b in self.hist_export_btns:
            b.config(state="normal")
        self._set_status(f"History: {len(results)} open port(s) shown.")

    def _get_selected_history(self):
        sel = self.history_list.curselection()
        if not sel:
            return None
        return self._history[sel[0]]

    def _do_hist_export(self, ext: str, filetypes: list, exporter_fn):
        entry = self._get_selected_history()
        if not entry:
            messagebox.showwarning("Warning", "Select a history entry first.")
            return
        label, results = entry
        parts = label.split()
        target = parts[0] if parts else "unknown"
        port_range = parts[1] if len(parts) > 1 else "1-65535"
        try:
            s, e = (int(x) for x in port_range.split("-"))
        except Exception:
            s, e = 1, 65535
        filepath = filedialog.asksaveasfilename(
            defaultextension=ext, filetypes=filetypes)
        if not filepath:
            return
        ok, err = exporter_fn(target, s, e, results, filepath)
        if ok:
            messagebox.showinfo("Export Successful", f"Saved to:\n{filepath}")
            self._set_status(f"Exported to {filepath}")
        else:
            messagebox.showerror("Export Failed",
                                  f"Could not write file:\n{err}")

    def _hist_export_txt(self):
        self._do_hist_export(".txt",
            [("Text files", "*.txt"), ("All files", "*.*")], Exporter.to_text)

    def _hist_export_json(self):
        self._do_hist_export(".json",
            [("JSON files", "*.json"), ("All files", "*.*")], Exporter.to_json)

    def _hist_export_csv(self):
        self._do_hist_export(".csv",
            [("CSV files", "*.csv"), ("All files", "*.*")], Exporter.to_csv)

    # ── Main scan export helpers ──────────────────────────────────────────────

    def _do_export(self, ext: str, filetypes: list, exporter_fn):
        if self.last_results is None or self.scanner is None:
            messagebox.showwarning("Warning",
                                    "No scan results to export. Run a scan first.")
            return
        filepath = filedialog.asksaveasfilename(
            defaultextension=ext, filetypes=filetypes)
        if not filepath:
            return
        ok, err = exporter_fn(
            self.scanner.target, self.scanner.start_port,
            self.scanner.end_port, self.last_results, filepath)
        if ok:
            messagebox.showinfo("Export Successful", f"Saved to:\n{filepath}")
            self._set_status(f"Exported to {filepath}")
        else:
            messagebox.showerror("Export Failed",
                                  f"Could not write file:\n{err}")

    def export_txt(self):
        self._do_export(".txt",
            [("Text files", "*.txt"), ("All files", "*.*")], Exporter.to_text)

    def export_json(self):
        self._do_export(".json",
            [("JSON files", "*.json"), ("All files", "*.*")], Exporter.to_json)

    def export_csv(self):
        self._do_export(".csv",
            [("CSV files", "*.csv"), ("All files", "*.*")], Exporter.to_csv)