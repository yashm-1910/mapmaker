"""Runtime hook: point PROJ and GDAL at the data files bundled inside the build.

This is the frozen-build equivalent of what conda-forge's activate.d scripts do
for a Conda environment (see Mapmaker.bat's comment about GDAL_DATA/PROJ_DATA).
There is no environment to activate here, so the paths have to be set by hand,
and they have to be set *before* pyproj/rasterio/pyogrio load their native
libraries -- which is exactly what a PyInstaller runtime hook is for: it runs
after the bootloader has unpacked the bundle but before the entry script.

Without this, PROJ cannot find proj.db and every CRS transform fails; GDAL
without its data files fails while resolving projections in the basemap tiles.
Some of that failure happens in native code that aborts the process rather than
raising a catchable Python error, so a missing path here would look like the
window vanishing rather than an error message.

The proj_data/gdal_data folders exist only when the build was made from a Conda
environment, where one shared PROJ and one shared GDAL serve every package (see
the long comment in mapmaker.spec). A build made from wheels has no such folders,
because there each package vendors its own PROJ/GDAL and finds its data relative
to itself -- setting these variables in that case would force one package's
proj.db on all of them and break every transform. Hence the isdir() guards: they
are what makes this hook do nothing at all in the wheel case.

A path already set in the environment by the user wins: someone pointing at a
newer PROJ grid set is doing it deliberately, and silently overriding them would
be worse than trusting them.
"""
import os
import sys

_BUNDLE = getattr(sys, "_MEIPASS", None)

if _BUNDLE:
    _DATA_DIRS = {
        # PROJ reads PROJ_DATA (>=9.1) or PROJ_LIB (older); set both, since the
        # exact PROJ version comes from whatever conda-forge resolved at build time.
        "PROJ_DATA": os.path.join(_BUNDLE, "proj_data"),
        "PROJ_LIB": os.path.join(_BUNDLE, "proj_data"),
        "GDAL_DATA": os.path.join(_BUNDLE, "gdal_data"),
    }

    for _var, _path in _DATA_DIRS.items():
        if not os.environ.get(_var) and os.path.isdir(_path):
            os.environ[_var] = _path

    # pyproj caches its data directory at import time from its own search order,
    # which looks in the package's install location -- a path that does not exist
    # in the bundle. Setting it explicitly keeps pyproj from falling back to a
    # "proj.db not found" error even though the files are right there.
    if os.path.isdir(_DATA_DIRS["PROJ_DATA"]):
        try:
            import pyproj.datadir

            pyproj.datadir.set_data_dir(_DATA_DIRS["PROJ_DATA"])
        except Exception:
            pass  # env vars above are the primary mechanism; this is belt-and-braces

    # Certificate bundle for the HTTPS requests contextily makes to fetch basemap
    # tiles. requests finds certifi's bundle through certifi.where(), which resolves
    # relative to the package -- correct inside the bundle -- but GDAL/curl read
    # these variables instead, and an unset CURL_CA_BUNDLE makes tile fetches fail
    # with a certificate error on some machines.
    try:
        import certifi

        _ca = certifi.where()
        if os.path.isfile(_ca):
            os.environ.setdefault("SSL_CERT_FILE", _ca)
            os.environ.setdefault("CURL_CA_BUNDLE", _ca)
            os.environ.setdefault("GDAL_CURL_CA_BUNDLE", _ca)
    except Exception:
        pass

    # matplotlib writes a font cache on first run. Its default location is per-user
    # and writable, but MPLCONFIGDIR being unset on a locked-down machine makes it
    # print a warning to stderr -- which the GUI shows to the user as if something
    # went wrong. Pinning it to the user's own temp area keeps first-run quiet.
    os.environ.setdefault(
        "MPLCONFIGDIR",
        os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Mapmaker", "mpl-cache"),
    )
