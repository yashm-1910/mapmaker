"""PyInstaller hook for pyogrio -- geopandas 1.x's default vector I/O engine.

mapmaker builds its GeoDataFrames from Excel rows rather than reading shapefiles,
so pyogrio is never called directly; geopandas still imports it while working out
which engine is available, and a missing pyogrio turns that check into an import
error at startup. Its compiled modules are loaded by name, so they need listing
here for the same reason as rasterio's.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

hiddenimports = collect_submodules("pyogrio")
datas = collect_data_files("pyogrio")  # bundled gdal_data / proj_data on wheel installs
binaries = collect_dynamic_libs("pyogrio")
