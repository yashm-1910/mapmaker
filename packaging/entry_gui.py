"""PyInstaller entry script for the frozen Mapmaker.exe.

A one-line wrapper rather than freezing mapmaker/gui.py directly: PyInstaller treats
the entry script as a top-level module, so freezing gui.py itself would import it
outside the `mapmaker` package it belongs to and break its own `from mapmaker import ...`
lines. Importing through the package keeps the frozen app running exactly the same
code path as `mapmaker-gui` does when pip-installed.
"""
import multiprocessing

from mapmaker.gui import main

if __name__ == "__main__":
    # Harmless here (nothing spawns processes today), but this must be the first thing
    # a frozen Windows app calls if anything ever does -- without it, a child process
    # re-runs the whole executable instead of the worker function.
    multiprocessing.freeze_support()
    main()
