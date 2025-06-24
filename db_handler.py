import psycopg2
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class NotConnectedException(Exception):
    pass

class DisconnectedCursor:
    def execute(self, *args, **kwargs):
        raise psycopg2.OperationalError('Server is currently disconnected.')
    def __getattr__(self, item):
        raise psycopg2.OperationalError('Server is currently disconnected.')

class DbHandler:
    """Only DB connection/session/transaction logic here."""
    def __init__(self, config, username, password):
        self.config = config
        self.username = username
        self.password = password
        self.conn = None
        self.is_cleaned_up = False

    def connect(self):
        """Establish and return a psycopg2 connection."""
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
        except psycopg2.Error as e:
            logger.error("DB connection failed: %s", e)
            raise
        return self.conn

    def close(self):
        """Close the DB connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("DB connection closed.")

    def cleanup(self):
        """Cleanup handler and close connection."""
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
        """Get a DB cursor with retry logic."""
        for attempt in range(retries):
            try:
                conn = self.connect()
                conn.autocommit = autocommit
                cur = conn.cursor()
                yield cur
                cur.close()
                break
            except (psycopg2.Error, NotConnectedException) as e:
                logger.warning("Cursor error: %s (attempt %d/%d)", e, attempt+1, retries)
                self.close()
                if attempt == retries - 1:
                    logger.error("Returning DisconnectedCursor after retries.")
                    yield DisconnectedCursor()
                else:
                    continue
            except Exception as e:
                logger.error("Unexpected error in cursor operation: %s", e)
                raise
            finally:
                if 'cur' in locals() and not cur.closed:
                    cur.close()

    @contextmanager
    def transaction(self):
        """Context manager for a DB transaction."""
        conn = self.connect()
        try:
            yield conn
            conn.commit()
            logger.info("Transaction committed.")
        except Exception as e:
            conn.rollback()
            logger.exception("Transaction rolled back due to: %s", e)
            raise

    @contextmanager
    def read_only_transaction(self):
        """Context manager for a read-only transaction."""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY;")
            yield conn
            conn.commit()
            logger.info("Read-only transaction committed.")
        except Exception as e:
            conn.rollback()
            logger.exception("Read-only transaction rolled back: %s", e)
            raise

