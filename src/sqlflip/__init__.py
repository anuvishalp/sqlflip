"""sqlflip - detect a SQL query's dialect and view it in other dialects."""
from .converter import Conversion, convert, convert_all
from .detector import DIALECTS, DISPLAY_NAMES, Detection, detect_dialect

__version__ = "0.1.0"
__all__ = ["detect_dialect", "convert", "convert_all", "display",
           "Detection", "Conversion", "DIALECTS", "DISPLAY_NAMES"]


def display(query: str = "") -> None:
    """Open a window showing `query` in PostgreSQL, MySQL, SQL Server and standard SQL."""
    from .gui import show   # imported lazily so the library works without Tkinter
    show(query)
