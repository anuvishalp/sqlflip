# sqlflip

Paste a SQL query and `sqlflip` will:

1. **Detect** which dialect it is written in - PostgreSQL, MySQL, SQL Server (T-SQL) or standard SQL.
2. **Convert** it to the other dialects (identifier quoting, `TOP` / `LIMIT` / `OFFSET .. FETCH`,
   `GETDATE()` / `NOW()`, `ISNULL` / `IFNULL` / `COALESCE`, `LEN` / `LENGTH`, common data types).
3. **Display** all versions in a small window (Tkinter, no extra dependencies).

> T-SQL is the language of SQL Server, so `tsql` and `sqlserver` mean the same thing.

## Install

```bash
pip install sqlflip
```

(On Linux you may also need `sudo apt install python3-tk` for the window.)

## Use in Python

```python
from sqlflip import detect_dialect, convert, convert_all, display

q = "SELECT TOP 10 [name], ISNULL([age], 0) FROM [users] ORDER BY [name]"

print(detect_dialect(q))            # SQL Server (T-SQL) (confidence: high)
print(convert(q, "postgresql").sql) # SELECT "name", COALESCE("age", 0) FROM "users" ORDER BY "name" LIMIT 10
print(convert(q, "mysql").sql)      # SELECT `name`, IFNULL(`age`, 0) FROM `users` ORDER BY `name` LIMIT 10

for dialect, result in convert_all(q).items():
    print(dialect, "->", result.sql, result.notes)

display(q)                          # opens the window
```

## Command line

```bash
sqlflip "SELECT TOP 5 * FROM users"
sqlflip "SELECT * FROM users LIMIT 5, 10" --to sqlserver
sqlflip --gui
```

## Limitations

This is a lightweight, rule-based tool - **not** a full SQL parser. Always review the output.
Constructs it cannot safely translate (e.g. `::` casts, `||` / `+` string concatenation,
auto-increment columns, `GROUP_CONCAT` / `STRING_AGG`, date functions, variables) are left as-is
and reported in `result.notes`. Detection is heuristic: a query such as `SELECT * FROM t LIMIT 5`
is valid in both PostgreSQL and MySQL, so it is reported as ambiguous.

## Publish to PyPI

```bash
pip install build twine
python -m build
twine upload dist/*        # username: __token__   password: <your API token>
```
