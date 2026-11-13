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
        if "information_schema" in self.q: return [("align_owner", "t1")]
        return [(1, date(2026, 1, 2)), (2, Decimal("1.5"))]


class Conn:
    def cursor(self): return Cur()


class BackupTests(unittest.TestCase):
    def test_export_serialises_values(self):
        out = backup_neon.export_tables(Conn())
        self.assertEqual(out["align_owner.t1"]["columns"], ["id", "d"])
        self.assertEqual(out["align_owner.t1"]["schema"], "align_owner")
        self.assertEqual(out["align_owner.t1"]["rows"], [[1, "2026-01-02"], [2, "1.5"]])
        json.dumps(out)

    def test_missing_dsn_is_safe(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": ""}):
            self.assertEqual(backup_neon.main(["--out", tempfile.gettempdir()]), 2)

    def test_upload_without_credentials_does_not_print_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'align-neon-test.json.gz'
            path.write_bytes(b'x')
            with mock.patch.dict(os.environ, {'ALIGN_BACKUP_BUCKET': '', 'AWS_ACCESS_KEY_ID': 'secret-key', 'AWS_SECRET_ACCESS_KEY': ''}, clear=False):
                with mock.patch('sys.stderr') as err:
                    self.assertFalse(backup_neon.upload_backup(path))
            text = ''.join(str(call) for call in err.write.call_args_list)
            self.assertNotIn('secret-key', text)

    def test_restore_refuses_without_confirmation_and_hides_the_password(self):
        import restore_neon_backup
        self.assertEqual(restore_neon_backup.main(['backup.json.gz']), 2)
        self.assertEqual(
            restore_neon_backup.safe_target('postgresql://user:secret-pass@ep-example.eu-central-1.aws.neon.tech:5432/align'),
            'ep-example.eu-central-1.aws.neon.tech:5432/align',
        )
        commands = restore_neon_backup.commands({'tables': {'align_auth.beta_users': {
            'schema': 'align_auth', 'table': 'beta_users', 'columns': ['user_id'], 'rows': [['abc']],
        }}})
        self.assertEqual(commands, [('align_auth', 'beta_users', ['user_id'], [['abc']])])

    def test_prune_keeps_newest(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(5): (Path(d) / f"align-neon-2026010{i}.json.gz").write_text("x")
            backup_neon.prune(Path(d), 2)
            self.assertEqual(len(list(Path(d).glob("*.gz"))), 2)


if __name__ == "__main__":
    unittest.main()
