import psycopg2
import logging
from contextlib import contextmanager

logger = logging.getLogger("DbHandler")

class NotConnectedException(Exception):
    pass

class DisconnectedCursor:
    def execute(self, *args, **kwargs):
        raise psycopg2.OperationalError('Server is currently disconnected.')
    def __getattr__(self, item):
        raise psycopg2.OperationalError('Server is currently disconnected.')

class DbHandler:
    def __init__(self, db_config, user, password):
        self.db_config = db_config
        self.user = user
        self.password = password
        self.conn = None
        self.is_cleaned_up = False

    def connect(self):
        if self.is_cleaned_up:
            raise NotConnectedException("Connection cleaned up.")
        if self.conn and not self.conn.closed:
            return self.conn
        try:
            self.conn = psycopg2.connect(
                dbname=self.db_config["dbname"],
                user=self.user,
                password=self.password,
                host=self.db_config["host"],
                port=self.db_config["port"]
            )
            logger.info("Connected to DB: %s", self.db_config["dbname"])
        except psycopg2.Error as e:
            logger.error("DB connection failed: %s", e)
            raise
        return self.conn

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
                    (self.user, exclude_pid)
                )
            else:
                cur.execute(
                    "SELECT pid FROM pg_stat_activity WHERE usename = %s",
                    (self.user,)
                )
            return [row[0] for row in cur.fetchall()]

    def terminate_sessions(self, pids):
        if self.user.lower() != "postgres":
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
                logger.warning("Cursor error: %s (attempt %d/%d)", e, attempt+1, retries)
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

    # Optional: context manager for read-only transaction
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