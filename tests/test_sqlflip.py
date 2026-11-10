import unittest

from sqlflip import convert, convert_all, detect_dialect


class DetectTests(unittest.TestCase):
    def test_sqlserver(self):
        self.assertEqual(detect_dialect("SELECT TOP 10 [name] FROM [users]").dialect, "sqlserver")

    def test_mysql(self):
        self.assertEqual(detect_dialect("SELECT `name` FROM `users` LIMIT 5, 10").dialect, "mysql")

    def test_postgres(self):
        self.assertEqual(detect_dialect("SELECT name FROM users WHERE name ILIKE 'a%'").dialect, "postgresql")

    def test_plain_is_standard(self):
        d = detect_dialect("SELECT name FROM users WHERE id = 1")
        self.assertEqual(d.dialect, "standard")

    def test_ambiguous_limit(self):
        d = detect_dialect("SELECT name FROM users LIMIT 5")
        self.assertTrue(d.ambiguous)

    def test_strings_are_ignored(self):
        d = detect_dialect("SELECT 'TOP 5 [x] ILIKE' FROM users")
        self.assertEqual(d.dialect, "standard")


class ConvertTests(unittest.TestCase):
    Q = "SELECT TOP 10 [name], ISNULL([age], 0) FROM [users] ORDER BY [name]"

    def test_sqlserver_to_postgres(self):
        r = convert(self.Q, "postgresql")
        self.assertEqual(r.sql, 'SELECT "name", COALESCE("age", 0) FROM "users" ORDER BY "name" LIMIT 10')

    def test_sqlserver_to_mysql(self):
        r = convert(self.Q, "mysql")
        self.assertEqual(r.sql, "SELECT `name`, IFNULL(`age`, 0) FROM `users` ORDER BY `name` LIMIT 10")

    def test_mysql_offset_to_sqlserver(self):
        r = convert("SELECT `id` FROM `t` ORDER BY `id` LIMIT 5, 10", "tsql")
        self.assertEqual(r.sql, "SELECT [id] FROM [t] ORDER BY [id] OFFSET 5 ROWS FETCH NEXT 10 ROWS ONLY")

    def test_offset_without_order_by(self):
        r = convert("SELECT id FROM t LIMIT 10 OFFSET 20", "sqlserver", source="postgresql")
        self.assertIn("ORDER BY (SELECT NULL) OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY", r.sql)

    def test_string_literals_untouched(self):
        r = convert("SELECT TOP 3 'LIMIT 5 [x]' FROM [t]", "postgresql")
        self.assertEqual(r.sql, "SELECT 'LIMIT 5 [x]' FROM \"t\" LIMIT 3")

    def test_now_and_len(self):
        r = convert("SELECT LEN(name), GETDATE() FROM t", "postgresql", source="sqlserver")
        self.assertEqual(r.sql, "SELECT LENGTH(name), NOW() FROM t")

    def test_semicolon_kept(self):
        r = convert("SELECT TOP 1 * FROM t;", "mysql", source="sqlserver")
        self.assertEqual(r.sql, "SELECT * FROM t LIMIT 1;")

    def test_notes_for_cast(self):
        r = convert("SELECT id::text FROM t", "mysql", source="postgresql")
        self.assertTrue(r.notes)

    def test_convert_all_has_four_dialects(self):
        self.assertEqual(len(convert_all("SELECT 1")), 4)

    def test_empty_query(self):
        with self.assertRaises(ValueError):
            convert("   ", "mysql")


if __name__ == "__main__":
    unittest.main()
