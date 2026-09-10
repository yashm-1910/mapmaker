"""PyInstaller entry point for the console Mapmaker-cli.exe.

Two executables are built from one bundle (see mapmaker.spec) rather than one
executable that switches on its arguments, because the two need opposite Windows
subsystems: the GUI must be a windowed binary (no console box flashing behind the
window), while this one must be a console binary so that

  * running it from cmd/PowerShell prints its output where the user is looking, and
  * the GUI can capture its stdout/stderr when it runs a render as a subprocess
    (mapmaker/gui.py::_render).

Both executables share the same `_internal` folder, so shipping the second one
costs about a megabyte, not a second copy of GDAL.
"""
from __future__ import annotations

import multiprocessing


def run() -> None:
    multiprocessing.freeze_support()  # see entry_gui.py for why

    from mapmaker.cli import main
    main()


if __name__ == "__main__":
    run()
