from qgis.PyQt.QtWidgets import QMessageBox
import psycopg2
import select
import threading

# Import EDITABLE_FIELDS from your login dialog or config
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
def is_field_editable(role, field_name):
    editable_fields = EDITABLE_FIELDS.get(role, [])
    return field_name in editable_fields

# Improved: Listen for database edit conflicts in a thread-safe way
def listen_for_edits(current_user_role, db_config, db_user, db_password):
    """
    Start a background thread to listen for edit conflicts.
    db_config: dict with dbname, host, port
    db_user: username
    db_password: password
    """
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

            while True:
                if select.select([conn], [], [], 5) == ([conn], [], []):
                    conn.poll()
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        cell_data = notify.payload.split(",")
                        if len(cell_data) == 4:
                            row_id, column, user_editing, current_user = cell_data
                            if is_field_editable(current_user_role, column):
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
                print("✅ Database connection closed.")

    # Run listener in a daemon thread so it doesn't block the main UI
    thread = threading.Thread(target=_listen, daemon=True)
    thread.start()

# edit_buffer.committedWithConflicts.connect(self.on_conflict)  # <-- Remove or comment this line