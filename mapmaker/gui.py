"""A small desktop window for running mapmaker without a terminal.

This is the no-code path: pick the workbook, pick which map(s) to draw, press a
button, see the results. Everything it does is what `mapmaker --file ...` does --
same workbook, same settings sheets, same outputs -- so a user can start here and
never learn the command line, while nothing about the CLI changes.

Launch it as the `mapmaker-gui` command (a GUI entry point, so on Windows it opens
with no console window behind it), or by double-clicking `Mapmaker.bat` in a source
checkout. Built on tkinter, which ships with Python itself -- no extra dependency.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
import warnings
from pathlib import Path

# Must be set before anything imports matplotlib.pyplot (mapmaker.render does).
# Rendering runs on a worker thread so the window stays responsive, and only the
# non-interactive Agg backend is safe to drive from a thread that isn't the GUI's
# own -- an interactive backend would try to open its own event loop and can
# deadlock or crash against tkinter's.
import matplotlib

matplotlib.use("Agg")

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from mapmaker import __version__, config as config_mod

ALL_MAPS = "All maps in the workbook"

# Remembers the last workbook between sessions, so the common case (same workbook
# every time) is open-and-click. Kept in the user's home directory rather than next
# to the package, which may sit in a read-only install location.
_SETTINGS_FILE = Path.home() / ".mapmaker_gui.json"


def _load_last_workbook() -> str:
    try:
        return str(json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")).get("workbook", ""))
    except Exception:
        return ""


def _save_last_workbook(path: str) -> None:
    try:
        _SETTINGS_FILE.write_text(json.dumps({"workbook": path}), encoding="utf-8")
    except OSError:
        pass  # a non-writable home directory just means "don't remember"; not worth surfacing


def _open_in_file_manager(path: Path) -> None:
    """Reveal `path` in the OS file manager (Explorer / Finder / xdg-open)."""
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - opening a user-chosen folder in Explorer
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


class MapmakerApp:
    """The single application window."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Mapmaker {__version__}")
        self.root.minsize(700, 460)

        self.workbook_var = tk.StringVar(value=_load_last_workbook())
        self.map_var = tk.StringVar(value=ALL_MAPS)
        self.status_var = tk.StringVar(value="Choose a workbook to begin.")
        # Messages from the render thread; drained by _poll_messages on the GUI thread,
        # since tkinter widgets may only be touched from the thread that created them.
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.output_dirs: list[Path] = []
        self.running = False

        self._build_widgets()
        self._poll_messages()

    # -- layout -------------------------------------------------------------

    def _build_widgets(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Excel workbook:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.workbook_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="Browse…", command=self.browse).grid(row=0, column=2)

        ttk.Label(frame, text="Map to generate:").grid(row=1, column=0, sticky="w", pady=4)
        self.map_combo = ttk.Combobox(
            frame, textvariable=self.map_var, state="readonly",
            values=[ALL_MAPS, *config_mod.MAP_TYPE_LABELS.values()],
        )
        self.map_combo.grid(row=1, column=1, sticky="ew", padx=6)

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        self.generate_btn = ttk.Button(buttons, text="Generate maps", command=self.generate)
        self.generate_btn.pack(side="left")
        ttk.Button(buttons, text="Edit workbook in Excel", command=self.open_workbook).pack(side="left", padx=6)
        self.output_btn = ttk.Button(buttons, text="Open output folder", command=self.open_output, state="disabled")
        self.output_btn.pack(side="left")

        ttk.Label(frame, textvariable=self.status_var, foreground="#444").grid(
            row=3, column=0, columnspan=3, sticky="w"
        )

        log_frame = ttk.LabelFrame(frame, text="Details", padding=6)
        log_frame.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        frame.rowconfigure(4, weight=1)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

    # -- button actions -----------------------------------------------------

    def browse(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Select the mapmaker workbook",
            filetypes=[("Excel workbook", "*.xlsx *.xlsm"), ("All files", "*.*")],
        )
        if chosen:
            self.workbook_var.set(chosen)
            self.status_var.set("Ready.")

    def open_workbook(self) -> None:
        path = Path(self.workbook_var.get().strip())
        if not path.is_file():
            messagebox.showerror("Mapmaker", "Pick an existing workbook first.")
            return
        _open_in_file_manager(path)

    def open_output(self) -> None:
        for directory in self.output_dirs:
            if directory.is_dir():
                _open_in_file_manager(directory)

    def generate(self) -> None:
        if self.running:
            return
        path = Path(self.workbook_var.get().strip())
        if not path.is_file():
            messagebox.showerror("Mapmaker", "Pick an existing .xlsx workbook first.")
            return
        _save_last_workbook(str(path))

        label = self.map_var.get()
        map_type = None if label == ALL_MAPS else config_mod._LABEL_TO_MAP_TYPE.get(label.lower())

        self.running = True
        self.generate_btn.configure(state="disabled")
        self.output_btn.configure(state="disabled")
        self.output_dirs = []
        self._clear_log()
        self.status_var.set("Generating… this can take a minute while map tiles download.")
        threading.Thread(target=self._render, args=(path, map_type), daemon=True).start()

    # -- worker thread ------------------------------------------------------

    def _render(self, path: Path, map_type: str | None) -> None:
        """Run the render off the GUI thread, reporting back only through `self.messages`."""
        # Imported here rather than at module scope so the window appears immediately:
        # pulling in geopandas/contextily/matplotlib takes a noticeable moment, and a
        # blank frozen window during startup is exactly what this GUI exists to avoid.
        from mapmaker.cli import BUILDERS

        try:
            configs = config_mod.load_workbook_configs(path)
            if not configs:
                raise ValueError(
                    f"{path.name} has none of the expected data sheets "
                    f"({', '.join(config_mod.MAP_TYPES)}); nothing to render."
                )
            map_types = [map_type] if map_type else list(configs)
            saved: list[Path] = []
            for mt in map_types:
                cfg = configs.get(mt)
                label = config_mod.MAP_TYPE_LABELS.get(mt, mt)
                if cfg is None:
                    self.messages.put(("log", f"Skipped {label}: the workbook has no '{mt}' sheet."))
                    continue
                # Same rule as the CLI: `enabled=false` only skips a map on a
                # render-everything run, never when that map was asked for by name.
                if not map_type and not cfg.get("enabled", True):
                    self.messages.put(("log", f"Skipped {label} (turned off in the settings sheet)."))
                    continue
                self.messages.put(("log", f"Drawing {label}…"))
                # Surface matplotlib/contextily warnings (a failed basemap, a UTM zone
                # mismatch) in the log instead of a terminal the user never sees.
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    out = BUILDERS[mt](cfg)
                for w in caught:
                    # Only the warnings that mean something to the person running this --
                    # ResourceWarning/DeprecationWarning noise from the libraries underneath
                    # would just make the log look like an error report when nothing is wrong.
                    if issubclass(w.category, (UserWarning, RuntimeWarning)):
                        self.messages.put(("log", f"  Warning: {w.message}"))
                for p in out if isinstance(out, list) else [out]:
                    saved.append(Path(p))
                    self.messages.put(("log", f"  Saved: {p}"))
            self.messages.put(("done", saved))
        except Exception as exc:
            self.messages.put(("log", traceback.format_exc()))
            self.messages.put(("error", exc))

    # -- GUI-thread message pump -------------------------------------------

    def _poll_messages(self) -> None:
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "done":
                self._finish(payload)
            elif kind == "error":
                self._fail(payload)
        self.root.after(100, self._poll_messages)

    def _finish(self, saved: list[Path]) -> None:
        self.running = False
        self.generate_btn.configure(state="normal")
        if saved:
            self.output_dirs = list(dict.fromkeys(p.parent for p in saved))
            self.output_btn.configure(state="normal")
            self.status_var.set(f"Done — {len(saved)} map(s) saved.")
        else:
            self.status_var.set("Finished, but no maps were generated. See the details above.")

    def _fail(self, exc: Exception) -> None:
        self.running = False
        self.generate_btn.configure(state="normal")
        self.status_var.set("Something went wrong — see the details below.")
        messagebox.showerror("Mapmaker", f"{type(exc).__name__}: {exc}")

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")


def main() -> None:
    """Entry point for the `mapmaker-gui` command."""
    root = tk.Tk()
    MapmakerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
