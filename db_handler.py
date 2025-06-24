import psycopg2
import logging
from contextlib import contextmanager
from PyQt5.QtCore import QObject, pyqtSignal

# Removed erroneous use of 'self' outside of a class or method.

logger = logging.getLogger(__name__)


# --- Signal Bus for Logout ---
class SignalBus(QObject):
    logout_signal = pyqtSignal()

signal_bus = SignalBus()


# --- Singleton Access for Shared DbHandler ---
_db_handler_instance = None

def set_shared_db_handler(instance):
    global _db_handler_instance
    _db_handler_instance = instance

def get_shared_db_handler():
    return _db_handler_instance


# --- Custom Exceptions ---
class NotConnectedException(Exception):
    pass

class DisconnectedCursor:
    def execute(self, *args, **kwargs):
        raise psycopg2.OperationalError('Server is currently disconnected.')

    def __getattr__(self, item):
        raise psycopg2.OperationalError('Server is currently disconnected.')


# --- Main DB Handler ---
class DbHandler:
    def __init__(self, config, username, password):
        self.config = config
        self.username = username
        self.password = password
        self.conn = None
        self.is_cleaned_up = False
        self.selected_table = None

    def connect(self):
        if self.is_cleaned_up:
            raise NotConnectedException("Connection cleaned up.")
        if self.conn and not self.conn.closed:
            return self.conn
        try:
            self.conn = psycopg2.connect(
                dbname=self.config['dbname'],
                host=self.config['host'],
                port=self.config['port'],
                user=self.username,
                password=self.password
            )
            logger.info("Connected to DB: %s", self.config["dbname"])
            # Set session variable after connection
            if hasattr(self, "emp_id") and self.emp_id:
                self.set_session_emp_id(self.username)
        except psycopg2.Error as e:
            logger.error("DB connection failed: %s", e)
            raise
        return self.conn
    
    def set_session_emp_id(self, emp_id):
        """Set the session variable for the current user's employee ID."""
        if not self.conn or self.conn.closed:
            raise NotConnectedException("Not connected to the database.")
        with self.conn.cursor() as cur:
            cur.execute("SET app.current_user_emp_id = %s", (str(emp_id),))
            self.conn.commit()
        logger.info("Session variable app.current_user_emp_id set to %s", emp_id)

    def is_connected(self):
        return self.conn is not None and not self.conn.closed

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("DB connection closed.")

    def cleanup(self):
        self.is_cleaned_up = True
        self.close()

    def get_current_pid(self):
        with self.get_cursor_with_retries() as cur:
            cur.execute("SELECT pg_backend_pid()")
            return cur.fetchone()[0]

    def get_active_sessions(self, exclude_pid=None):
        with self.get_cursor_with_retries() as cur:
            if exclude_pid:
                cur.execute(
                    "SELECT pid FROM pg_stat_activity WHERE usename = %s AND pid != %s",
                    (self.username, exclude_pid)
                )
            else:
                cur.execute(
                    "SELECT pid FROM pg_stat_activity WHERE usename = %s",
                    (self.username,)
                )
            return [row[0] for row in cur.fetchall()]

    def terminate_sessions(self, pids):
        if self.username.lower() != "postgres":
            raise PermissionError("Only superuser can terminate sessions.")
        with self.get_cursor_with_retries() as cur:
            for pid in pids:
                cur.execute("SELECT pg_terminate_backend(%s)", (pid,))
            self.conn.commit()
            logger.info("Terminated sessions: %s", pids)

    @contextmanager
    def get_cursor_with_retries(self, retries=2, autocommit=True):
        for attempt in range(retries):
            try:
                conn = self.connect()
                conn.autocommit = autocommit
                cur = conn.cursor()
                yield cur
                cur.close()
                break
            except (psycopg2.Error, NotConnectedException) as e:
                logger.warning("Cursor error: %s (attempt %d/%d)", e, attempt + 1, retries)
                self.close()
                if attempt == retries - 1:
                    logger.error("Returning DisconnectedCursor after retries.")
                    yield DisconnectedCursor()
                else:
                    continue

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            yield conn
            conn.commit()
            logger.info("Transaction committed.")
        except Exception as e:
            conn.rollback()
            logger.error("Transaction rolled back due to: %s", e)
            raise

    @contextmanager
    def read_only_transaction(self):
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY;")
            yield conn
            conn.commit()
            logger.info("Read-only transaction committed.")
        except Exception as e:
            conn.rollback()
            logger.error("Read-only transaction rolled back: %s", e)
            raise

    def fetch_work_units(self, table_name, subcountry=None):
        conn = self.connect()
        with conn.cursor() as cur:
            # Handle schema.table or just table
            if '.' in table_name.replace('"', ''):
                schema, table = [s.strip('"') for s in table_name.split('.')]
                base_query = f'SELECT * FROM "{schema}"."{table}"'
            else:
                base_query = f'SELECT * FROM "{table_name}"'
            params = []
            if subcountry:
                base_query += " WHERE subcountry = %s"
                params.append(subcountry)
            cur.execute(base_query, params)
            return cur.fetchall()

    def fetch_unique_subcountries(self, table_name):
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(f'SELECT DISTINCT subcountry FROM {table_name}')
            return [row[0] for row in cur.fetchall() if row[0] is not None]

    def get_dsn(self):
        return (
            f"dbname={self.config['dbname']} "
            f"user={self.username} "
            f"password={self.password} "
            f"host={self.config['host']} "
            f"port={self.config['port']}"
        )
