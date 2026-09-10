"""PyInstaller hook for contextily (the basemap tiles behind every map).

Two things PyInstaller cannot see from the source:

  * contextily reads its own version through importlib.metadata at import time,
    which needs the .dist-info directory copied into the bundle -- otherwise the
    import raises PackageNotFoundError.
  * xyzservices' provider list is a JSON data file, and contextily's default
    provider is looked up in it by name at runtime.
"""
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

datas = copy_metadata("contextily")
datas += collect_data_files("xyzservices")

# joblib spins up a Memory cache and (optionally) worker processes; both of its
# backends are selected by name at runtime.
hiddenimports = ["joblib", "geopy", "mercantile", "xyzservices"]
