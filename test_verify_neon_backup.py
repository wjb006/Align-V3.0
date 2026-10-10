import gzip, json, tempfile, unittest
from pathlib import Path
import verify_neon_backup as v


class VerifyTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "align-neon-20260101T000000Z.json.gz"
            with gzip.open(p, "wt", encoding="utf-8") as f:
                json.dump({"tables": {"a b": {"columns": ["id", "meta"], "rows": [[1, {"x": 1}], [2, None]]}}}, f)
            report, bad = v.verify(p)
            self.assertEqual(report["a b"], (2, 2))
            self.assertEqual(bad, [])
            self.assertEqual(v.newest(d), p)


if __name__ == "__main__":
    unittest.main()
