import json
import os
import unittest
import uuid

from langchain_core.messages import HumanMessage, message_to_dict

from db_manager import DatabaseManager


class DatabaseContextTests(unittest.TestCase):
    def setUp(self):
        suffix = uuid.uuid4().hex
        self.db_files = [
            os.path.abspath(f".test_context_main_{suffix}.db"),
            os.path.abspath(f".test_context_storage_{suffix}.db"),
        ]
        self.main_db, self.storage_db = self.db_files
        self.db = DatabaseManager(self.main_db, self.storage_db)

    def tearDown(self):
        for db_file in self.db_files:
            for path in (db_file, f"{db_file}-shm", f"{db_file}-wal"):
                if os.path.exists(path):
                    os.remove(path)

    def insert_message(self, session_id: str, text: str):
        payload = json.dumps(message_to_dict(HumanMessage(content=text)))
        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO storage.message_store (session_id, message) VALUES (?, ?)",
                (session_id, payload)
            )
            conn.commit()

    def test_summary_defaults_to_empty_context(self):
        self.assertEqual(self.db.get_session_summary("missing"), ("", 0))

    def test_summary_upsert_replaces_existing_context(self):
        self.db.upsert_session_summary("session-1", "first", 3)
        self.db.upsert_session_summary("session-1", "second", 7)

        self.assertEqual(self.db.get_session_summary("session-1"), ("second", 7))

    def test_recent_message_rows_after_returns_chronological_subset(self):
        for index in range(5):
            self.insert_message("session-1", f"message {index}")

        rows = self.db.get_recent_message_rows_after("session-1", 0, 2)

        self.assertEqual(len(rows), 2)
        self.assertLess(rows[0][0], rows[1][0])
        self.assertIn("message 3", rows[0][1])
        self.assertIn("message 4", rows[1][1])


if __name__ == "__main__":
    unittest.main()
