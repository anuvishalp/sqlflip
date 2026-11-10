"""Small helpers shared by the detector and the converter."""
import re
from typing import List, Tuple

_STRING_RE = re.compile(r"'(?:[^']|'')*'")


def mask_strings(sql: str) -> Tuple[str, List[str]]:
    """Replace every 'string literal' with a placeholder so regex rules
    never touch text that lives inside quotes."""
    strings: List[str] = []

    def _sub(match):
        strings.append(match.group(0))
        return "\x00%d\x00" % (len(strings) - 1)

    return _STRING_RE.sub(_sub, sql), strings


def unmask_strings(sql: str, strings: List[str]) -> str:
    """Put the original string literals back."""
    return re.sub(r"\x00(\d+)\x00", lambda m: strings[int(m.group(1))], sql)
