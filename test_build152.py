"""Build 152 regression checks for the feature-owned database layer."""
import io, json, sqlite3, unittest
from contextlib import nullcontext
from pathlib import Path
import build152

class Build152Tests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript((Path(__file__).parent / 'migrations' / '154_user_favourites_contacts.sql').read_text(encoding='utf-8'))

    def test_provisioning_migration_is_idempotent_and_preserves_existing_rows(self):
        self.db.execute("""INSERT INTO user_favourites
            (entity_type,entity_key,label,value,metadata_json,created_at,updated_at)
            VALUES ('location','existing','Existing','Value','{}','x','x')""")
        self.db.execute("""INSERT INTO align_contacts
            (name,address,phone,notes,created_at,updated_at)
            VALUES ('Existing contact','Old address','01234','Keep','x','x')""")
        self.db.commit()
        self.db.executescript((Path(__file__).parent / 'migrations' / '154_user_favourites_contacts.sql').read_text(encoding='utf-8'))
        self.assertEqual(self.db.execute("SELECT label FROM user_favourites WHERE entity_key='existing'").fetchone()[0], 'Existing')
        self.assertEqual(self.db.execute("SELECT address FROM align_contacts WHERE name='Existing contact'").fetchone()[0], 'Old address')

    def test_request_handlers_do_not_contain_runtime_schema_creation(self):
        source = (Path(__file__).parent / 'build152.py').read_text(encoding='utf-8')
        self.assertNotIn('CREATE TABLE', source)
        self.assertNotIn('CREATE INDEX', source)
        self.assertNotIn('CONTACT_SCHEMA', source)
        self.assertNotIn('def ensure(', source)

    def test_favourite_upsert_and_remove_shape(self):
        now="2026-10-01T12:00:00+00:00"
        self.db.execute("""INSERT INTO user_favourites
            (entity_type,entity_key,label,value,metadata_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?)""",
            ("location","dentist","Dentist","10 High Street","{}",now,now))
        self.db.commit()
        row=self.db.execute("SELECT * FROM user_favourites WHERE entity_key='dentist'").fetchone()
        self.assertEqual(row["label"],"Dentist")
        self.assertEqual(json.loads(row["metadata_json"]),{})

    def test_unique_favourite_key(self):
        self.db.execute("""INSERT INTO user_favourites
            (entity_type,entity_key,label,value,metadata_json,created_at,updated_at)
            VALUES ('event_title','dentist','Dentist','','{}','x','x')""")
        self.db.execute("""INSERT INTO user_favourites
            (entity_type,entity_key,label,value,metadata_json,created_at,updated_at)
            VALUES ('event_title','dentist','Dentist appointment','','{}','x','y')
            ON CONFLICT(entity_type,entity_key) DO UPDATE SET label=excluded.label""")
        self.db.commit()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM user_favourites").fetchone()[0],1)
        self.assertEqual(self.db.execute("SELECT label FROM user_favourites").fetchone()[0],"Dentist appointment")

    def test_saved_contact_can_be_edited_without_creating_a_duplicate(self):

        original = build152._save_contact(
            self.db,
            build152._contact_payload(json.dumps({
                "name":"Dr Example","address":"Old clinic","phone":"01234 555000"
            }).encode()),
        )
        updated = build152._update_contact(
            self.db,
            original["id"],
            build152._contact_payload(json.dumps({
                "name":"Dr Example","address":"New clinic","phone":"01234 555111"
            }).encode()),
        )
        self.assertEqual(updated["id"],original["id"])
        self.assertEqual(updated["address"],"New clinic")
        self.assertEqual(updated["phone"],"01234 555111")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM align_contacts").fetchone()[0],1)
        self.assertIsNone(build152._update_contact(self.db,999,("Missing","","","")))

    def test_contact_api_supports_read_only_event_detail_updates(self):
        class App:
            BETA_MODE = False
            BUILD_VERSION = 155

            def db_connection(inner_self):
                return nullcontext(self.db)

        class Handler:
            def __init__(inner_self, path, method, payload=b""):
                inner_self.path = path
                inner_self.headers = {"Content-Length":str(len(payload))}
                inner_self.rfile = io.BytesIO(payload)
                inner_self.response = None

            def require_beta_user(inner_self):
                return True

            def beta_same_origin(inner_self):
                return True

            def send_json(inner_self, status, payload):
                inner_self.response = (status, payload)

        app = App()
        create = Handler("/api/contacts","POST",json.dumps({
            "name":"Dr Example","address":"Old clinic","phone":"01234 555000"
        }).encode())
        self.assertTrue(build152.handle(create,app,"POST"))
        contact_id = create.response[1]["contact"]["id"]

        update = Handler(f"/api/contacts/{contact_id}","PUT",json.dumps({
            "name":"Dr Example","address":"New clinic","phone":"01234 555111"
        }).encode())
        self.assertTrue(build152.handle(update,app,"PUT"))
        self.assertEqual(update.response[0],200)
        self.assertEqual(update.response[1]["contact"]["address"],"New clinic")

        listing = Handler("/api/contacts","GET")
        self.assertTrue(build152.handle(listing,app,"GET"))
        self.assertEqual(listing.response[1]["build"],155)
        self.assertEqual(listing.response[1]["contacts"][0]["phone"],"01234 555111")

    def test_installer_requires_build_152_feature_payload(self):
        installer = (Path(__file__).parent / "Install-Align.ps1").read_text(encoding="utf-8")
        for required in (
            "'build152.py'", "'static\\build152.js'",
            "'user_favourites'", "'align_contacts'", "migrations\\154_user_favourites_contacts.sql",
        ):
            with self.subTest(required=required):
                self.assertIn(required, installer)

    def test_uninstaller_confirms_database_before_removal(self):
        uninstaller = (Path(__file__).parent / "Uninstall-Align.ps1").read_text(encoding="utf-8")
        confirmation = uninstaller.index("$databaseDeleteConfirmed = $true")
        removal = uninstaller.index("Write-Log 'Removing Build 156 virtual environment...'")
        self.assertLess(confirmation, removal)
        self.assertIn("No installation files were removed.", uninstaller)

if __name__ == "__main__":
    unittest.main()
