import sqlite3
import uuid
import logging
from datetime import datetime
from config import config

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, main_db=config.MAIN_DB, storage_db=config.STORAGE_DB):
        self.main_db = main_db
        self.storage_db = storage_db
        self._init_db()

    def get_connection(self):
        """Returns a configured SQLite connection with WAL and the attached storage DB."""
        conn = sqlite3.connect(self.main_db, check_same_thread=False)
        # Enable Write-Ahead Logging for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        # Attach the storage database for large blobs
        conn.execute(f"ATTACH DATABASE '{self.storage_db}' AS storage")
        return conn

    def _init_db(self):
        try:
            with self.get_connection() as conn:
                # Main metadata
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        chat_id INTEGER PRIMARY KEY,
                        active_session_id TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        chat_id INTEGER,
                        session_name TEXT,
                        created_at TIMESTAMP,
                        FOREIGN KEY(chat_id) REFERENCES users(chat_id)
                    )
                """)
                # Message store in storage.db
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS storage.message_store (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT,
                        message TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Create index separately
                conn.execute("CREATE INDEX IF NOT EXISTS storage.msg_session_idx ON message_store (session_id)")
                conn.commit()
            logger.info("Databases initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize databases: {e}")
            raise

    def get_or_create_user(self, chat_id: int) -> str:
        """Gets active session ID for user, creating user and default session if none exists."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT active_session_id FROM users WHERE chat_id = ?", (chat_id,))
            row = cursor.fetchone()
            if not row:
                # Create default session
                session_id = str(uuid.uuid4())
                conn.execute("INSERT INTO users (chat_id, active_session_id) VALUES (?, ?)", (chat_id, session_id))
                conn.execute(
                    "INSERT INTO sessions (session_id, chat_id, session_name, created_at) VALUES (?, ?, ?, ?)",
                    (session_id, chat_id, "Default Session", datetime.now())
                )
                conn.commit()
                return session_id
            return row[0]

    def get_active_session(self, chat_id: int) -> str:
        """Returns the active session for a chat_id."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT active_session_id FROM users WHERE chat_id = ?", (chat_id,))
            row = cursor.fetchone()
            return row[0] if row else None

    def set_active_session(self, chat_id: int, session_id: str):
        """Sets the active session ID for a given user."""
        with self.get_connection() as conn:
            conn.execute("UPDATE users SET active_session_id = ? WHERE chat_id = ?", (session_id, chat_id))
            conn.commit()

    def create_new_session(self, chat_id: int, name: str = None) -> str:
        """Creates a new session for a user and sets it as active."""
        session_id = str(uuid.uuid4())
        name = name or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, chat_id, session_name, created_at) VALUES (?, ?, ?, ?)",
                (session_id, chat_id, name, datetime.now())
            )
            # Ensure the user exists, if they don't, this update will do nothing unless user exists.
            # Best practice: insert or ignore first
            conn.execute("INSERT OR IGNORE INTO users (chat_id, active_session_id) VALUES (?, ?)", (chat_id, session_id))
            conn.execute("UPDATE users SET active_session_id = ? WHERE chat_id = ?", (session_id, chat_id))
            conn.commit()
        return session_id

    def list_sessions(self, chat_id: int):
        """Retrieves all sessions for a specific user."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT session_id, session_name FROM sessions WHERE chat_id = ? ORDER BY created_at DESC", 
                (chat_id,)
            )
            return cursor.fetchall()

    def delete_session(self, session_id: str):
        """Deletes a session from metadata and its chat history from storage."""
        with self.get_connection() as conn:
            # Delete messages first from attached db
            conn.execute("DELETE FROM storage.message_store WHERE session_id = ?", (session_id,))
            # Delete session metadata
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            # If the deleted session was the active one, we should probably handle it,
            # but for simplicity we let the bot handle assigning a new one or the user creating one.
            conn.execute("UPDATE users SET active_session_id = NULL WHERE active_session_id = ?", (session_id,))
            conn.commit()
