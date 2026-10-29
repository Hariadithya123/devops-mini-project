
import io
import os
import shutil
import sqlite3
import tempfile
import unittest

import app as app_module
from app import app, init_db


class NotesPortalTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.upload_path = os.path.join(self.temp_dir.name, "uploads")
        os.makedirs(self.upload_path, exist_ok=True)

        self.original_db = app_module.DATABASE
        self.original_upload = app_module.UPLOAD_FOLDER
        self.original_config_db = app.config.get("DATABASE")
        self.original_config_upload = app.config["UPLOAD_FOLDER"]
        self.original_testing = app.config.get("TESTING", False)

        app_module.DATABASE = self.db_path
        app_module.UPLOAD_FOLDER = self.upload_path
        app.config["UPLOAD_FOLDER"] = self.upload_path
        app.config["TESTING"] = True

        init_db()
        self.client = app.test_client()

    def tearDown(self):
        # Close the test client's session and restore application settings.
        self.client = None
        app_module.DATABASE = self.original_db
        app_module.UPLOAD_FOLDER = self.original_upload
        app.config["UPLOAD_FOLDER"] = self.original_config_upload
        app.config["TESTING"] = self.original_testing

        # Ensure SQLite connections to the test database are closed.
        # get_db() must close its connection in a finally block.
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA wal_checkpoint(FULL)")
        except sqlite3.Error:
            pass

        # Retry cleanup if Windows temporarily locks a test file.
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            shutil.rmtree(self.temp_dir.name, ignore_errors=True)

    def register_and_login(self, username="student1"):
        self.client.post(
            "/register",
            data={"username": username, "password": "secret123"}
        )
        return self.client.post(
            "/login",
            data={"username": username, "password": "secret123"},
            follow_redirects=True
        )

    def test_home_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"NoteNest", response.data)

    def test_register_login_upload_download_delete(self):
        self.register_and_login()

        response = self.client.post(
            "/upload",
            data={
                "title": "Operating Systems Unit 1",
                "subject": "Operating Systems",
                "semester": "3",
                "unit": "Unit 1",
                "file": (
                    io.BytesIO(b"%PDF-1.4 sample"),
                    "notes.pdf"
                )
            },
            content_type="multipart/form-data",
            follow_redirects=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"shared successfully", response.data)

        with app_module.get_db() as conn:
            note_id = conn.execute(
                "SELECT id FROM notes"
            ).fetchone()["id"]

        download_response = self.client.get(f"/download/{note_id}")
        self.assertEqual(download_response.status_code, 200)
        self.assertIn(b"%PDF-1.4 sample", download_response.data)
        download_response.close()

        delete_response = self.client.post(
            f"/delete/{note_id}",
            follow_redirects=True
        )
        self.assertEqual(delete_response.status_code, 200)

        with app_module.get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM notes"
            ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_upload_requires_login(self):
        response = self.client.post(
            "/upload",
            data={},
            follow_redirects=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_reject_non_pdf(self):
        self.register_and_login()

        response = self.client.post(
            "/upload",
            data={
                "title": "Test",
                "subject": "OS",
                "semester": "3",
                "unit": "Unit 1",
                "file": (io.BytesIO(b"hello"), "notes.txt")
            },
            content_type="multipart/form-data",
            follow_redirects=True
        )

        self.assertIn(b"Only PDF", response.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
