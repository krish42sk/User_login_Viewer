from qgis.PyQt.QtWidgets import QMessageBox
import psycopg2
import select
import threading
from PyQt5.QtCore import QTimer, pyqtSignal, QObject
from .db_handler import signal_bus

# Import EDITABLE_FIELDS from login dialog or config
from .login_dialog import EDITABLE_FIELDS

# Function to show a GUI warning in QGIS
def show_conflict_warning(user_editing, row_id, column):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Warning)
    msg.setText(f"⚠️ Conflict: User {user_editing} is editing cell ({row_id}, {column}). Please wait.")
    msg.setWindowTitle("Edit Conflict Warning")
    msg.exec_()

# Function to show a privilege error in QGIS
def show_privilege_error(column):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Critical)
    msg.setText(f"❌ You do not have privilege to edit the column '{column}'.")
    msg.setWindowTitle("Permission Denied")
    msg.exec_()

# Function to check if a field is editable by the user role
def is_field_editable(role, field_name, row_data=None, user_emp_id=None, project=None, table_name=None):
    # Use table_name for lookup
    editable_fields = []
    if table_name:
        editable_fields = EDITABLE_FIELDS.get(table_name, {}).get(role, [])
    else:
        editable_fields = EDITABLE_FIELDS.get(role, [])


    if field_name not in editable_fields:
        return False

    # Grand leaders: no row-wise restriction
    if role == "grand_leaders":
        return True

    # Row-wise restriction maps
    rfdb_leader_col_map = {
        'rfdb_production_leaders': 'rfdb_production_team_leader_emp_id',
        'siloc_production_leaders': 'siloc_production_team_leader_emp_id',
        'siloc_qc_leaders': 'siloc_qc_team_leader_emp_id',
        'rfdb_qc_leaders': 'rfdb_qc_team_leader_emp_id',
        'rfdb_attri_qc_leaders': 'rfdb_attri_qc_team_leader_emp_id',
        'rfdb_path_association_qc_leaders': 'rfdb_path_association_qc_team_leader_emp_id'
    }
    tm_leader_col_map = {
        'rfdb_production_leaders': 'rfdb_production_team_leader_emp_id',
        'rfdb_qc_leaders': 'rfdb_qc_team_leader_emp_id',
        'rfdb_production_users': 'rfdb_production_emp_id',
        'rfdb_qc_users': 'rfdb_qc_emp_id',
        'siloc_qc_leaders': 'siloc_team_leader_emp_id',
        'siloc_production_leaders': 'siloc_team_leader_emp_id',
        'siloc_production_users': 'siloc_emp_id',
        'siloc_qc_users': 'siloc_emp_id'
    }

    # Select the correct map based on project
    leader_col = None
    if project == "turn_maneuver_project":
        leader_col = tm_leader_col_map.get(role)
    else:
        leader_col = rfdb_leader_col_map.get(role)

    if leader_col and row_data and user_emp_id is not None:
        leader_emp_id = row_data.get(leader_col)
        return str(leader_emp_id) == str(user_emp_id)
    return True  # If no row restriction, allow

class PostgresListener(QObject):
    notified = pyqtSignal(str)  # You can pass payload if needed

    def __init__(self, dsn, channel):
        super().__init__()
        self.conn = psycopg2.connect(dsn)
        self.conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        self.cur = self.conn.cursor()
        self.cur.execute(f"LISTEN {channel};")
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_notify)
        self.timer.start(1000)  # Check every second

    def close(self):
        try:
            self.timer.stop()
            self.cur.close()
            self.conn.close()
            print("✅ Listener connection closed")
        except Exception as e:
            print(f"Error closing listener: {e}")


    def check_notify(self):
        self.conn.poll()
        while self.conn.notifies:
            notify = self.conn.notifies.pop(0)
            self.notified.emit(notify.payload)

# Improved: Listen for database edit conflicts in a thread-safe way
def listen_for_edits(current_user_role, db_config, db_user, db_password):
    """
    Start a background thread to listen for edit conflicts.
    This version can be cleanly shut down via logout signal.
    """
    stop_event = threading.Event()
    signal_bus.logout_signal.connect(stop_event.set)

    def _listen():
        conn = None
        cursor = None
        try:
            conn = psycopg2.connect(
                dbname=db_config["dbname"],
                user=db_user,
                password=db_password,
                host=db_config["host"],
                port=db_config["port"]
            )
            conn.autocommit = True
            cursor = conn.cursor()
            cursor.execute("LISTEN edit_conflict;")
            print("🔍 Listening for conflicts in QGIS...")

            while not stop_event.is_set():
                if select.select([conn], [], [], 5) == ([conn], [], []):
                    conn.poll()
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        cell_data = notify.payload.split(",")
                        if len(cell_data) == 4:
                            row_id, column, user_editing, current_user = cell_data
                            if is_field_editable(
                                current_user_role,
                                column,
                                table_name=db_config.get("table_name"),
                                project=db_config.get("project")
                            ):
                                print(f"⚠️ Conflict detected: User {user_editing} is editing ({row_id}, {column}).")
                                show_conflict_warning(user_editing, row_id, column)
                            else:
                                print(f"❌ No privilege to edit column: {column}")
                                show_privilege_error(column)
                        else:
                            print("⚠️ Received malformed notification:", notify.payload)

        except psycopg2.Error as e:
            print(f"❌ Database error: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
                print("✅ Conflict listener DB connection closed.")

    thread = threading.Thread(target=_listen, daemon=True)
    thread.start()


