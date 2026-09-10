"""mapmaker: QGIS-style map generation for wind energy datasets, driven by a single Excel workbook."""

import warnings

__version__ = "0.1.0"

# Harmless and not actionable: openpyxl just drops a newer data-validation format it doesn't
# support when reading a sheet; every value mapmaker reads from the workbook is unaffected.
warnings.filterwarnings(
    "ignore", message="Data Validation extension is not supported and will be removed",
    category=UserWarning,
)
