"""PyInstaller entry point for the windowed Mapmaker.exe.

Kept as a thin file of its own (rather than pointing PyInstaller straight at
mapmaker/gui.py) so the frozen build has a stable, importable-free starting
script: PyInstaller runs this as `__main__`, and everything it needs from the
package is a normal import from there.

The matching console executable is built from entry_cli.py -- see
mapmaker.spec, which produces both from one shared bundle.
"""
from __future__ import annotations

import multiprocessing


def run() -> None:
    # Not used by mapmaker itself, but joblib (pulled in by contextily) can start
    # worker processes. Under a frozen build each worker re-launches this .exe, so
    # without freeze_support() the workers would re-run the GUI instead of the work.
    multiprocessing.freeze_support()

    from mapmaker.gui import main
    main()


if __name__ == "__main__":
    run()
