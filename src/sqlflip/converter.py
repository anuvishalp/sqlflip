"""Convert a SQL query from one dialect to another.

This is a lightweight, rule-based converter. It handles the most common
differences (identifier quoting, row limiting, a handful of functions and data
types) and *warns* about constructs it cannot translate safely.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ._utils import mask_strings, unmask_strings
from .detector import DIALECTS, detect_dialect, normalize_dialect


@dataclass
class Conversion:
    dialect: str
    sql: str
    notes: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# 1. Identifier quoting:  [name]  `name`  "name"
# --------------------------------------------------------------------------
_QUOTE = {
    "postgresql": ('"', '"'),
    "standard": ('"', '"'),
    "mysql": ("`", "`"),
    "sqlserver": ("[", "]"),
}


def _requote(text: str, source: str, target: str) -> str:
    opener, closer = _QUOTE[target]
    if source == "sqlserver":
        patterns = [r"\[([^\]\x00]+)\]", r'"([^"\x00]+)"']
    elif source == "mysql":
        patterns = [r"`([^`]+)`"]
    else:
        patterns = [r'"([^"\x00]+)"']
    for pattern in patterns:
        text = re.sub(pattern, lambda m: "%s%s%s" % (opener, m.group(1), closer), text)
    return text


# --------------------------------------------------------------------------
# 2. Row limiting:  TOP n  /  LIMIT n [OFFSET m]  /  OFFSET m ROWS FETCH ...
# --------------------------------------------------------------------------
_TOP = re.compile(r"\bSELECT(\s+DISTINCT)?\s+TOP\s*\(?\s*(\d+)\s*\)?\s+", re.I)
_LIMIT_COMMA = re.compile(r"\s*\bLIMIT\s+(\d+)\s*,\s*(\d+)", re.I)
_LIMIT = re.compile(r"\s*\bLIMIT\s+(\d+)(?:\s+OFFSET\s+(\d+))?", re.I)
_OFFSET_FETCH = re.compile(
    r"\s*\bOFFSET\s+(\d+)\s+ROWS?(?:\s+FETCH\s+(?:FIRST|NEXT)\s+(\d+)\s+ROWS?\s+ONLY)?", re.I
)
_FETCH_ONLY = re.compile(r"\s*\bFETCH\s+(?:FIRST|NEXT)\s+(\d+)\s+ROWS?\s+ONLY", re.I)


def _cut(text: str, match) -> str:
    return text[: match.start()] + text[match.end():]


def _extract_limit(text: str) -> Tuple[str, Optional[int], Optional[int]]:
    """Remove any row-limit clause and return (text, limit, offset)."""
    limit = offset = None

    m = _TOP.search(text)
    if m:
        limit = int(m.group(2))
        text = text[: m.start()] + "SELECT" + (m.group(1) or "") + " " + text[m.end():]
        return text, limit, offset

    m = _LIMIT_COMMA.search(text)          # MySQL: LIMIT offset, count
    if m:
        return _cut(text, m), int(m.group(2)), int(m.group(1))

    m = _LIMIT.search(text)                # LIMIT n [OFFSET m]
    if m:
        off = int(m.group(2)) if m.group(2) else None
        return _cut(text, m), int(m.group(1)), off

    m = _OFFSET_FETCH.search(text)         # OFFSET m ROWS [FETCH NEXT n ROWS ONLY]
    if m:
        lim = int(m.group(2)) if m.group(2) else None
        return _cut(text, m), lim, int(m.group(1))

    m = _FETCH_ONLY.search(text)           # FETCH FIRST n ROWS ONLY
    if m:
        return _cut(text, m), int(m.group(1)), None

    return text, None, None


def _apply_limit(text: str, limit: Optional[int], offset: Optional[int], target: str) -> str:
    if limit is None and not offset:
        return text

    if target in ("postgresql", "mysql"):
        if target == "mysql" and limit is None:
            limit = 18446744073709551615   # MySQL needs a LIMIT to use OFFSET
        clause = ""
        if limit is not None:
            clause += " LIMIT %d" % limit
        if offset:
            clause += " OFFSET %d" % offset
        return text + clause

    if target == "standard":
        clause = ""
        if offset:
            clause += " OFFSET %d ROWS" % offset
        if limit is not None:
            clause += " FETCH NEXT %d ROWS ONLY" % limit
        return text + clause

    # SQL Server
    if not offset:
        return re.sub(
            r"^(\s*SELECT(?:\s+DISTINCT)?)\s+",
            lambda m: "%s TOP %d " % (m.group(1), limit),
            text, count=1, flags=re.I,
        )
    if not re.search(r"\bORDER\s+BY\b", text, re.I):
        text += " ORDER BY (SELECT NULL)"   # OFFSET/FETCH requires ORDER BY
    text += " OFFSET %d ROWS" % offset
    if limit is not None:
        text += " FETCH NEXT %d ROWS ONLY" % limit
    return text


# --------------------------------------------------------------------------
# 3. Functions
# --------------------------------------------------------------------------
_NOW = {"sqlserver": "GETDATE()", "mysql": "NOW()", "postgresql": "NOW()",
        "standard": "CURRENT_TIMESTAMP"}
_NULLFN = {"sqlserver": "ISNULL", "mysql": "IFNULL", "postgresql": "COALESCE",
           "standard": "COALESCE"}
_LENFN = {"sqlserver": "LEN", "mysql": "CHAR_LENGTH", "postgresql": "LENGTH",
          "standard": "CHAR_LENGTH"}


def _convert_functions(text: str, source: str, target: str) -> str:
    text = re.sub(r"\b(?:GETDATE|SYSDATETIME|NOW|CURRENT_TIMESTAMP)\s*\(\s*\)",
                  _NOW[target], text, flags=re.I)

    null_names = "IFNULL|ISNULL" if source == "sqlserver" else "IFNULL"
    text = re.sub(r"\b(?:%s)\s*\(" % null_names, _NULLFN[target] + "(", text, flags=re.I)

    text = re.sub(r"\b(?:LEN|LENGTH|CHAR_LENGTH|CHARACTER_LENGTH)\s*\(",
                  _LENFN[target] + "(", text, flags=re.I)
    return text


# --------------------------------------------------------------------------
# 4. Data types (only for CREATE / ALTER statements)
# --------------------------------------------------------------------------
_TYPES = {
    "sqlserver": [(r"\bBOOLEAN\b", "BIT"), (r"\bTIMESTAMP\b", "DATETIME2"),
                  (r"\bTEXT\b", "NVARCHAR(MAX)")],
    "mysql": [(r"\bN?VARCHAR\s*\(\s*MAX\s*\)", "TEXT"), (r"\bNVARCHAR\b", "VARCHAR"),
              (r"\bDATETIME2\b", "DATETIME"), (r"\bBIT\b", "BOOLEAN")],
    "postgresql": [(r"\bN?VARCHAR\s*\(\s*MAX\s*\)", "TEXT"), (r"\bNVARCHAR\b", "VARCHAR"),
                   (r"\b(?:DATETIME2|DATETIME)\b", "TIMESTAMP"), (r"\bBIT\b", "BOOLEAN"),
                   (r"\bTINYINT\b", "SMALLINT")],
}
_TYPES["standard"] = _TYPES["postgresql"]


def _convert_types(text: str, target: str) -> str:
    if not re.match(r"\s*(CREATE|ALTER)\b", text, re.I):
        return text
    for pattern, repl in _TYPES[target]:
        text = re.sub(pattern, repl, text, flags=re.I)
    return text


# --------------------------------------------------------------------------
# 5. Warnings for things we do NOT translate
# --------------------------------------------------------------------------
def _collect_notes(masked: str, source: str, target: str) -> List[str]:
    notes: List[str] = []

    def has(pattern: str) -> bool:
        return re.search(pattern, masked, re.I) is not None

    if has(r"::\s*\w+") and target != "postgresql":
        notes.append("PostgreSQL '::' casts were not converted - rewrite as CAST(expr AS type).")
    if has(r"\|\|") and target in ("mysql", "sqlserver"):
        notes.append("String concatenation with '||' was not converted - use CONCAT() "
                     "(MySQL / SQL Server) or '+' (SQL Server).")
    if source == "sqlserver" and target != "sqlserver" and has(r"\x00\d+\x00\s*\+|\+\s*\x00\d+\x00"):
        notes.append("String concatenation with '+' was not converted - use CONCAT() or '||'.")
    if has(r"\b(AUTO_INCREMENT|IDENTITY|SERIAL|BIGSERIAL)\b"):
        notes.append("Auto-increment columns differ (AUTO_INCREMENT / IDENTITY / SERIAL) - review manually.")
    if has(r"\b(GROUP_CONCAT|STRING_AGG)\s*\("):
        notes.append("GROUP_CONCAT / STRING_AGG are not converted - review manually.")
    if has(r"\b(DATEADD|DATE_ADD|DATEDIFF|DATE_FORMAT|TO_CHAR|CONVERT|INTERVAL)\b"):
        notes.append("Date/time functions differ a lot between dialects - review manually.")
    if has(r"(?<![\w@])@\w+|\$\d+"):
        notes.append("Variables / parameters (@name, $1) were not converted.")
    return notes


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def convert(query: str, target: str, source: Optional[str] = None) -> Conversion:
    """Convert `query` to the `target` dialect.

    If `source` is omitted the dialect is auto-detected.
    """
    target = normalize_dialect(target)
    body = (query or "").strip()
    if not body:
        raise ValueError("The query is empty.")
    src = normalize_dialect(source) if source else detect_dialect(body).dialect

    if src == target:
        return Conversion(target, body, [])

    masked, strings = mask_strings(body)
    notes = _collect_notes(masked, src, target)

    text = masked.rstrip()
    had_semicolon = text.endswith(";")
    text = text.rstrip(";").rstrip()

    text = _requote(text, src, target)
    text, limit, offset = _extract_limit(text)
    text = _apply_limit(text, limit, offset, target)
    text = _convert_functions(text, src, target)
    text = _convert_types(text, target)

    if had_semicolon:
        text += ";"
    return Conversion(target, unmask_strings(text, strings), notes)


def convert_all(query: str, source: Optional[str] = None) -> Dict[str, Conversion]:
    """Return the query in every supported dialect."""
    body = (query or "").strip()
    if not body:
        raise ValueError("The query is empty.")
    src = normalize_dialect(source) if source else detect_dialect(body).dialect
    return {d: convert(body, d, src) for d in DIALECTS}
