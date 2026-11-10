"""Command-line interface:  sqlflip "SELECT TOP 5 * FROM users" """
import argparse
import sys

from .converter import convert, convert_all
from .detector import DIALECTS, DISPLAY_NAMES, detect_dialect, normalize_dialect


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="sqlflip", description="Detect a query's SQL dialect and convert it.")
    parser.add_argument("query", nargs="?", help="SQL text (or use --file / pipe via stdin)")
    parser.add_argument("-f", "--file", help="read the query from a file")
    parser.add_argument("--from", dest="source", help="source dialect (default: auto-detect)")
    parser.add_argument("--to", dest="target", help="show only this target dialect")
    parser.add_argument("--gui", action="store_true", help="open the display window")
    args = parser.parse_args(argv)

    query = args.query
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            query = fh.read()
    elif query is None and not sys.stdin.isatty():
        query = sys.stdin.read()

    if args.gui or not query:
        from .gui import show
        show(query or "")
        return 0

    detection = detect_dialect(query)
    source = normalize_dialect(args.source) if args.source else detection.dialect
    print("Detected : %s" % detection)
    if args.source:
        print("Using    : %s" % DISPLAY_NAMES[source])
    print()

    if args.target:
        results = {normalize_dialect(args.target): convert(query, args.target, source)}
    else:
        results = convert_all(query, source)

    for d, res in results.items():
        print("--- %s %s---" % (DISPLAY_NAMES[d], "(source) " if d == source else ""))
        print(res.sql)
        for note in res.notes:
            print("  ! " + note)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
