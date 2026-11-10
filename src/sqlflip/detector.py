"""Detect which SQL dialect a query is written in."""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ._utils import mask_strings

# Order matters: it is also the tie-break order and the tab order in the GUI.
DIALECTS = ("postgresql", "mysql", "sqlserver", "standard")

DISPLAY_NAMES = {
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "sqlserver": "SQL Server (T-SQL)",
    "standard": "Standard SQL",
}

# T-SQL *is* the language of SQL Server, so both names map to "sqlserver".
_ALIASES = {
    "postgresql": "postgresql", "postgres": "postgresql", "pg": "postgresql",
    "psql": "postgresql", "plpgsql": "postgresql",
    "mysql": "mysql", "mariadb": "mysql",
    "sqlserver": "sqlserver", "sql server": "sqlserver", "sql_server": "sqlserver",
    "tsql": "sqlserver", "t-sql": "sqlserver", "mssql": "sqlserver",
    "standard": "standard", "sql": "standard", "ansi": "standard",
}


def normalize_dialect(name: str) -> str:
    key = (name or "").strip().lower()
    if key not in _ALIASES:
        raise ValueError(
            "Unknown dialect %r. Use one of: postgresql, mysql, sqlserver "
            "(or tsql), standard (or sql)." % name
        )
    return _ALIASES[key]


# (dialect, regex, weight, human-readable label)
_RULES: List[Tuple[str, str, int, str]] = [
    # ---- SQL Server / T-SQL ------------------------------------------------
    ("sqlserver", r"\bSELECT\s+(DISTINCT\s+)?TOP\s*\(?\s*\d+", 3, "SELECT TOP n"),
    ("sqlserver", r"(?<![\w\)\]])\[[A-Za-z_][\w ]*\]", 3, "[bracket] identifiers"),
    ("sqlserver", r"\bGETDATE\s*\(|\bSYSDATETIME\s*\(", 3, "GETDATE()"),
    ("sqlserver", r"\bISNULL\s*\([^,()]+,", 2, "ISNULL(a, b)"),
    ("sqlserver", r"\bLEN\s*\(", 2, "LEN()"),
    ("sqlserver", r"\bDATEADD\s*\(", 2, "DATEADD()"),
    ("sqlserver", r"\bNVARCHAR\b|\bDATETIME2\b|\bUNIQUEIDENTIFIER\b|\bNEWID\s*\(", 2, "SQL Server data types"),
    ("sqlserver", r"\bWITH\s*\(\s*NOLOCK\s*\)", 3, "WITH (NOLOCK)"),
    ("sqlserver", r"\bIDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)", 3, "IDENTITY(1,1)"),
    ("sqlserver", r"\bOFFSET\s+\d+\s+ROWS?\s+FETCH\b", 2, "OFFSET .. FETCH NEXT"),
    ("sqlserver", r"\bdbo\.", 2, "dbo. schema"),
    ("sqlserver", r"\bSET\s+NOCOUNT\b|\bEXEC(UTE)?\s+\w", 3, "EXEC / SET NOCOUNT"),
    ("sqlserver", r"\b(FROM|INTO|JOIN)\s+#\w+", 3, "#temp tables"),
    ("sqlserver", r"\bCONVERT\s*\(\s*\w+(\(\s*\w+\s*\))?\s*,", 2, "CONVERT(type, x)"),
    ("sqlserver", r"(?<![\w@])@\w+", 1, "@variables"),
    ("sqlserver", r"\bSTRING_AGG\s*\(", 1, "STRING_AGG()"),
    # ---- MySQL -------------------------------------------------------------
    ("mysql", r"`[^`]+`", 3, "`backtick` identifiers"),
    ("mysql", r"\bLIMIT\s+\d+\s*,\s*\d+", 3, "LIMIT offset, count"),
    ("mysql", r"\bIFNULL\s*\(", 2, "IFNULL()"),
    ("mysql", r"\bAUTO_INCREMENT\b", 3, "AUTO_INCREMENT"),
    ("mysql", r"\bENGINE\s*=", 3, "ENGINE="),
    ("mysql", r"\b(CURDATE|CURTIME|UNIX_TIMESTAMP)\s*\(", 2, "CURDATE()/CURTIME()"),
    ("mysql", r"\bGROUP_CONCAT\s*\(", 3, "GROUP_CONCAT()"),
    ("mysql", r"\bON\s+DUPLICATE\s+KEY\s+UPDATE\b", 3, "ON DUPLICATE KEY UPDATE"),
    ("mysql", r"\bINSERT\s+IGNORE\b", 3, "INSERT IGNORE"),
    ("mysql", r"\bDATE_FORMAT\s*\(", 2, "DATE_FORMAT()"),
    ("mysql", r"^\s*SHOW\s+(TABLES|DATABASES|COLUMNS)\b", 2, "SHOW TABLES"),
    ("mysql", r"\bUNSIGNED\b|\bTINYINT\s*\(", 2, "MySQL data types"),
    ("mysql", r"\bLIMIT\s+\d+", 1, "LIMIT n"),
    ("mysql", r"\bNOW\s*\(\s*\)", 1, "NOW()"),
    ("mysql", r"(?<![\w@])@\w+", 1, "@variables"),
    # ---- PostgreSQL --------------------------------------------------------
    ("postgresql", r"::\s*\w+", 3, ":: type cast"),
    ("postgresql", r"\bILIKE\b", 3, "ILIKE"),
    ("postgresql", r"\bRETURNING\b", 3, "RETURNING"),
    ("postgresql", r"\b(BIG)?SERIAL\b", 3, "SERIAL"),
    ("postgresql", r"\$\d+", 3, "$1 parameters"),
    ("postgresql", r"\bGENERATE_SERIES\s*\(", 3, "GENERATE_SERIES()"),
    ("postgresql", r"\bJSONB\b", 3, "JSONB"),
    ("postgresql", r"\bARRAY\s*\[", 3, "ARRAY[...]"),
    ("postgresql", r"\bON\s+CONFLICT\b", 3, "ON CONFLICT"),
    ("postgresql", r"\bTO_CHAR\s*\(|\bTO_DATE\s*\(", 2, "TO_CHAR()/TO_DATE()"),
    ("postgresql", r"\bSTRING_AGG\s*\(", 2, "STRING_AGG()"),
    ("postgresql", r"\|\|", 1, "|| concatenation"),
    ("postgresql", r"\bLIMIT\s+\d+", 1, "LIMIT n"),
    ("postgresql", r"\bNOW\s*\(\s*\)", 1, "NOW()"),
    # ---- Standard SQL ------------------------------------------------------
    ("standard", r"\bFETCH\s+FIRST\s+\d+\s+ROWS?\s+ONLY\b", 2, "FETCH FIRST n ROWS ONLY"),
    ("standard", r"\bCURRENT_TIMESTAMP\b", 1, "CURRENT_TIMESTAMP"),
    ("standard", r"\bCOALESCE\s*\(", 1, "COALESCE()"),
    ("standard", r"\|\|", 1, "|| concatenation"),
]

_COMPILED = [(d, re.compile(p, re.I | re.M), w, lbl) for d, p, w, lbl in _RULES]


@dataclass
class Detection:
    dialect: str                      # best guess
    candidates: List[str]             # all dialects tied for first place
    scores: Dict[str, int]
    evidence: List[Tuple[str, str]] = field(default_factory=list)
    confidence: str = "low"           # low / medium / high

    @property
    def display_name(self) -> str:
        return DISPLAY_NAMES[self.dialect]

    @property
    def ambiguous(self) -> bool:
        return len(self.candidates) > 1

    def __str__(self) -> str:
        if self.ambiguous:
            names = " or ".join(DISPLAY_NAMES[c] for c in self.candidates)
            return "Ambiguous: could be %s (confidence: low)" % names
        return "%s (confidence: %s)" % (self.display_name, self.confidence)


def detect_dialect(query: str) -> Detection:
    """Guess the SQL dialect of `query` by scoring dialect-specific syntax."""
    masked, _ = mask_strings(query)
    scores = {d: 0 for d in DIALECTS}
    evidence: List[Tuple[str, str]] = []

    for dialect, rx, weight, label in _COMPILED:
        if rx.search(masked):
            scores[dialect] += weight
            evidence.append((dialect, label))

    top = max(scores.values())
    if top == 0:
        # Nothing dialect-specific found -> plain SQL that runs almost anywhere.
        return Detection("standard", ["standard"], scores, [], "low")

    candidates = [d for d in DIALECTS if scores[d] == top]
    second = sorted(scores.values(), reverse=True)[1]
    if len(candidates) > 1:
        confidence = "low"
    elif top >= 3 and top >= 2 * second:
        confidence = "high"
    else:
        confidence = "medium"
    return Detection(candidates[0], candidates, scores, evidence, confidence)
