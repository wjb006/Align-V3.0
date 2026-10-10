import json, tempfile, unittest, backup_neon, os
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock


class Cur:
    def __init__(self): self.q = None; self.description = []
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, q):
        self.q = q
        if "information_schema" not in q:
            self.description = [mock.Mock(), mock.Mock()]
            self.description[0].name = "id"; self.description[1].name = "d"
    def fetchall(self):
        if "information_schema" in self.q: return [("t1",)]
        return [(1, date(2026, 1, 2)), (2, Decimal("1.5"))]


class Conn:
    def cursor(self): return Cur()


class BackupTests(unittest.TestCase):
    def test_export_serialises_values(self):
        out = backup_neon.export_tables(Conn())
        self.assertEqual(out["t1"]["columns"], ["id", "d"])
        self.assertEqual(out["t1"]["rows"], [[1, "2026-01-02"], [2, "1.5"]])
        json.dumps(out)

    def test_missing_dsn_is_safe(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": ""}):
            self.assertEqual(backup_neon.main(["--out", tempfile.gettempdir()]), 2)

    def test_prune_keeps_newest(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(5): (Path(d) / f"align-neon-2026010{i}.json.gz").write_text("x")
            backup_neon.prune(Path(d), 2)
            self.assertEqual(len(list(Path(d).glob("*.gz"))), 2)


if __name__ == "__main__":
    unittest.main()
