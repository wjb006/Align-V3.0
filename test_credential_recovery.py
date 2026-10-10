import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from cryptography.fernet import Fernet
import app
from beta_support import BetaStore, BetaError

class CredentialRecoveryTests(unittest.TestCase):
    def store(self, root):
        store = object.__new__(BetaStore)
        store.secret_file = Path(root) / 'beta_secret.key'
        return store

    def test_persistent_key_decrypts_after_new_runtime(self):
        key = Fernet.generate_key().decode()
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b, patch.dict('os.environ', {'ALIGN_DATABASE_BACKEND':'postgres','ALIGN_CREDENTIAL_KEY':key}):
            first, second = self.store(a), self.store(b)
            encrypted = first._fernet().encrypt(b'test-only-credential')
            self.assertEqual(second._fernet().decrypt(encrypted), b'test-only-credential')
            self.assertFalse(first.secret_file.exists())
            self.assertFalse(second.secret_file.exists())

    def test_hosted_missing_or_invalid_key_never_generates_local_file(self):
        for key in ('', 'invalid-key'):
            with tempfile.TemporaryDirectory() as root, patch.dict('os.environ', {'ALIGN_DATABASE_BACKEND':'postgres','ALIGN_CREDENTIAL_KEY':key}):
                store = self.store(root)
                with self.assertRaises(BetaError) as caught: store._fernet()
                self.assertEqual(caught.exception.code, 'credential_key_unavailable')
                self.assertFalse(store.secret_file.exists())

    def test_local_file_key_remains_compatible(self):
        with tempfile.TemporaryDirectory() as root, patch.dict('os.environ', {'ALIGN_DATABASE_BACKEND':'sqlite','ALIGN_CREDENTIAL_KEY':''}):
            store = self.store(root)
            token = store._fernet().encrypt(b'local-test')
            self.assertEqual(store._fernet().decrypt(token), b'local-test')

    def test_unreadable_saved_credentials_do_not_block_bootstrap_data(self):
        for code in ('credential_error', 'credential_key_unavailable'):
            store = MagicMock()
            store.load_icloud.side_effect = BetaError('private upstream details', code)
            with patch.object(app, 'beta_store', return_value=store), patch.dict(app.BETA_ICLOUD_MANAGERS, {}, clear=True):
                manager = app.beta_icloud_manager({'user_id':'test-owner'})
                status = app.public_icloud_data(manager)
                self.assertFalse(status['connected'])
                self.assertTrue(status['reconnect_required'])
                self.assertNotIn('private', status['message'])
                self.assertIs(app.beta_icloud_manager({'user_id':'test-owner'}), manager)
                store.clear_icloud.assert_not_called()
                self.assertIsNone(manager.client)

if __name__ == '__main__': unittest.main()
