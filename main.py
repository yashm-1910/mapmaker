"""Dev-convenience wrapper for running from a source checkout without installing:

    python main.py --file data/mapmaker.xlsx

Once the package is installed (`pip install .`), the same thing is available
anywhere as the `mapmaker` console script -- see mapmaker/cli.py and
pyproject.toml's `[project.scripts]`.
"""
from mapmaker.cli import main

if __name__ == "__main__":
    main()
