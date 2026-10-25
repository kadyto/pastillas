import os
import tempfile
import unittest
from pathlib import Path

from app.db import StorageError, connect, initialize


class StorageTests(unittest.TestCase):
    def test_new_folder_creates_persistent_database(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data" / "pastillas.sqlite"
            initialize(str(path))
            with connect(str(path)) as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 6)
            self.assertTrue(path.is_file())

    @unittest.skipUnless(hasattr(os, "getuid") and os.getuid() != 0, "Requiere un usuario sin privilegios")
    def test_unwritable_folder_has_actionable_error_and_no_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "data"
            parent.mkdir()
            parent.chmod(0o500)
            try:
                with self.assertRaises(StorageError) as caught:
                    initialize(str(parent / "pastillas.sqlite"))
                message = str(caught.exception)
                self.assertIn("UID:GID", message)
                self.assertIn("DATA_DIR", message)
                self.assertIn(str(parent), message)
                self.assertFalse((parent / "pastillas.sqlite").exists())
            finally:
                parent.chmod(0o700)

    @unittest.skipUnless(hasattr(os, "getuid") and os.getuid() != 0, "Requiere un usuario sin privilegios")
    def test_unwritable_existing_database_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pastillas.sqlite"
            initialize(str(path))
            original = path.read_bytes()
            path.chmod(0o400)
            try:
                with self.assertRaises(StorageError):
                    initialize(str(path))
                self.assertEqual(path.read_bytes(), original)
            finally:
                path.chmod(0o600)

    def test_database_path_cannot_be_a_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(StorageError, "archivo, no a una carpeta"):
                initialize(folder)


if __name__ == "__main__":
    unittest.main()
