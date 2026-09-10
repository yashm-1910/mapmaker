"""PyInstaller hook for rasterio (pulled in by contextily to stitch basemap tiles).

PyInstaller finds imports by reading the source, and rasterio's GDAL drivers are
loaded by name at runtime (`rasterio._shim`, the `rasterio.*` extension modules)
rather than imported anywhere it can see -- so without this they are left out of
the bundle and the first basemap fetch fails with a missing-module error.

pyinstaller-hooks-contrib ships no rasterio hook, hence this one.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

# Every rasterio.* module, including the compiled ones loaded dynamically.
hiddenimports = collect_submodules("rasterio")

# rasterio's own sample data / gdal_data if this build's rasterio carries them
# (the wheel layout does; the conda-forge layout keeps them in the environment
# instead, which mapmaker.spec handles separately).
datas = collect_data_files("rasterio")

# The GDAL/GEOS/PROJ DLLs. On a wheel install these live in rasterio.libs; on
# conda-forge they live in the environment's Library\bin and are picked up by
# PyInstaller's dependency analysis of the .pyd files.
binaries = collect_dynamic_libs("rasterio")
