from PyQt5.QtWidgets import (
    QDialog, QLabel, QLineEdit, QComboBox, QPushButton, QHBoxLayout,
    QVBoxLayout, QMessageBox, QFormLayout, QDialogButtonBox, QFrame, QToolButton, QFileDialog
)
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
import pandas as pd
import psycopg2
from qgis.core import QgsVectorLayer, Qgis, QgsProject
from qgis.utils import iface
from .constants import EDITABLE_FIELDS
from .work_allocation_portal_dialog import WorkAllocationPortalViewerDialog
from .db_handler import DbHandler
from .conflict_listener import is_field_editable
import logging
import sip
import threading
import os
from shapely import wkt
from shapely.geometry import MultiLineString
import binascii
import traceback
from .db_handler import set_shared_db_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class LoginDialog(QDialog):
    login_successful = pyqtSignal()
    logout_requested = pyqtSignal()
    portal_viewer_enable = pyqtSignal(bool)
    

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login")
        self.setFixedWidth(400)
        self.conn = None
        self.designation = None
        self.current_layer = None
        self.conflict_listener = None
        self._is_logging_out = False
        self.db_handler = None  # Set after login

        self.Databases = {
            "RFDB_Server": {
                "dbname": "RFDB_Server",
                "host": "192.168.12.35",
                "port": "5432"
            }
        }

        self.df = self.fetch_credentials()
        if not self.df.empty:
            self.df["processed_employee_id"] = self.df["employee_id"].astype(str).str.strip()
        self.setup_ui()
        self.connect_events()
        QgsProject.instance().layersRemoved.connect(self.on_layers_removed)

    def fetch_credentials(self):
        try:
            url = "https://docs.google.com/spreadsheets/d/1RqcD7rATpNDdWa_pFtZXgVYqyXbcaesMd21XdWx_9L0/export?format=csv&gid=0"
            df = pd.read_csv(url)
            return df
        except Exception as e:
            logger.exception("Could not fetch credentials")
            QMessageBox.critical(self, "Error", f"Could not fetch credentials:\n{e}")
            return pd.DataFrame()
        

    def setup_ui(self):
        layout = QVBoxLayout()

        heading = QLabel("WORK ALLOCATION PORTAL")
        heading.setFont(QFont("Arial", 12, QFont.Bold))
        heading.setAlignment(Qt.AlignCenter)
        layout.addWidget(heading)
        layout.addWidget(self.horizontal_line())

        form_layout = QFormLayout()

        self.Database_dropdown = QComboBox()
        self.Database_dropdown.addItems(["select a Server"] + list(self.Databases.keys()))
        form_layout.addRow("Server:", self.Database_dropdown)

        # Add table selection dropdown
        self.table_dropdown = QComboBox()
        self.table_dropdown.addItems(["select a Project", "rfdb_project", "turn_maneuver_project"])
        form_layout.addRow("Project:", self.table_dropdown)

        # Store selected table name for later use
        self.selected_table = None

        # Update selected_table when table_dropdown changes
        def on_table_changed(index):
            table_option = self.table_dropdown.currentText()
            if table_option == "rfdb_project":
                self.selected_table = '''"public"."production_inputs"'''
            elif table_option == "turn_maneuver_project":
                self.selected_table = '''"public"."tm_production_inputs"'''
            else:
                self.selected_table = None

        self.table_dropdown.currentIndexChanged.connect(on_table_changed)
        # Initialize selected_table
        on_table_changed(self.table_dropdown.currentIndex())

        self.emp_id_input = QLineEdit()
        form_layout.addRow("Employee ID:", self.emp_id_input)

        self.name_label = QLabel("-")
        form_layout.addRow("Name:", self.name_label)

        self.designation_label = QLabel("-")
        form_layout.addRow("Designation:", self.designation_label)         

        password_layout = QHBoxLayout()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        # Eye icon toggle for password visibility using emoji
        self.toggle_eye = QToolButton(self)
        self.toggle_eye.setText("👁️‍🗨️")  # Closed eye emoji for hidden
        self.toggle_eye.setCheckable(True)
        self.toggle_eye.setChecked(False)
        self.toggle_eye.setToolTip("Show/Hide Password")

        password_layout.addWidget(self.password_input)
        password_layout.addWidget(self.toggle_eye)
        form_layout.addRow("Password:", password_layout)

        layout.addLayout(form_layout)

        button_layout = QHBoxLayout()
        self.reset_button = QPushButton("Reset")
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()
        button_layout.addWidget(self.button_box)

        layout.addLayout(button_layout)

        # Add after self.button_box in setup_ui
        # self.csv_upload_button = QPushButton()
        # icon_path_2 = os.path.join(os.path.dirname(__file__), 'csv_icon.png')
        # self.csv_upload_button.setIcon(QIcon(icon_path_2))
        # self.csv_upload_button.setText("Upload CSV")
        # self.csv_upload_button.setVisible(False)  # Only show for grand_leaders
        # layout.addWidget(self.csv_upload_button)

        self.setLayout(layout)

    def connect_events(self):
        self.emp_id_input.textChanged.connect(self.update_designation)
        self.toggle_eye.toggled.connect(self.toggle_password_visibility)
        self.reset_button.clicked.connect(self.reset_form)
        self.button_box.accepted.connect(self.validate_login)
        self.button_box.rejected.connect(self.reject)
        self.reset_button.clicked.connect(self.refresh_layer)
        #self.csv_upload_button.clicked.connect(self.upload_csv_dialog)

    def update_designation(self):
            emp_id = self.emp_id_input.text().strip()
            self.df["employee_id"] = self.df["employee_id"].astype(str).str.strip()
            match = self.df[self.df["employee_id"] == emp_id]
            if not match.empty:
                name = match.iloc[0]["name"]
                designation = match.iloc[0]["category"]
                self.name_label.setText(str(name))
                self.designation_label.setText(str(designation))
            else:
                self.name_label.setText("-")
                self.designation_label.setText("-")

            if "employee_id" in self.df.columns:
                self.df["employee_id"] = self.df["employee_id"].astype(str).str.strip()
            else:
                logger.warning("Column 'employee_id' is missing in the DataFrame.")
            emp_id = self.emp_id_input.text().strip()
            emp_id = self.emp_id_input.text().strip()
            if "processed_employee_id" not in self.df.columns:
                self.df["processed_employee_id"] = self.df["employee_id"].astype(str).str.strip()
            match = self.df[self.df["processed_employee_id"] == emp_id]
            match = self.df[self.df["employee_id"] == emp_id]
            if not match.empty:
                designation = match.iloc[0]["category"]
                self.designation_label.setText(str(designation))    
    

    def horizontal_line(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def toggle_password_visibility(self, checked):
        if checked:
            self.password_input.setEchoMode(QLineEdit.Normal)
            self.toggle_eye.setIcon(QIcon.fromTheme("visibility"))
        else:
            self.password_input.setEchoMode(QLineEdit.Password)
            self.toggle_eye.setIcon(QIcon.fromTheme("visibility-off"))

    def reset_form(self):
        self.Database_dropdown.setCurrentIndex(0)
        self.emp_id_input.clear()
        self.password_input.clear()
        self.name_label.setText("-")
        self.designation_label.setText("-")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.toggle_eye.setChecked(False)

    def validate_login(self):
        emp_id = self.emp_id_input.text().strip()
        password = self.password_input.text().strip()
        Database_name = self.Database_dropdown.currentText()

        if Database_name.lower() == "select a database":
            QMessageBox.warning(self, "Error", "Please select a valid Database.")
            return

        if self.df.empty:
            QMessageBox.warning(self, "Error", "Credentials not loaded.")
            return

        # Special case for admin and 17224: treat as grand_leaders
        if emp_id.lower() == "postgres" or emp_id == "17224":
            self.designation = "grand_leaders"
            self.emp_id = emp_id
            self.db_password = password
            self.selected_Database = Database_name

            conn = self.connect_to_db(Database_name, emp_id, password)
            if conn:
                QMessageBox.information(self, "Success", "Login successful!")
                self.login_successful.emit()
                self.reset_form()
                self.accept()
            else:
                QMessageBox.critical(self, "Connection Error", "Database connection failed.")
            return
               
        # Normal user/leader logic
        self.df["employee_id"] = self.df["employee_id"].astype(str).str.strip()
        self.df["password"] = self.df["password"].astype(str).str.strip()

        match = self.df[
            (self.df["employee_id"] == emp_id) &
            (self.df["password"] == password)
        ]

        if not match.empty:
            self.designation = str(match.iloc[0]["category"]).lower()
            self.emp_id = emp_id
            self.db_password = password
            self.selected_Database = Database_name

            conn = self.connect_to_db(Database_name, emp_id, password)
            if conn:
                # print(f"[DEBUG] self.selected_table: {self.selected_table}")
                # print(f"[DEBUG] self.designation: {self.designation}")
                # print(f"[DEBUG] Editable roles: {list(EDITABLE_FIELDS.get(self.selected_table, {}).keys())}")
                QMessageBox.information(self, "Success", "Login successful!")
                self.login_successful.emit()
                self.reset_form()
                self.accept()
                
            else:
                QMessageBox.critical(self, "Connection Error", "Database connection failed.")
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid Employee ID or Password.")
            self.password_input.clear()
            logger.warning("Failed login attempt for Employee ID: %s", emp_id)

    def update_feature(layer, fid, name_field, employee_name):
        try:
            if not layer.isEditable():
                layer.startEditing()
            f = layer.getFeature(fid)
            f[name_field] = employee_name
            layer.updateFeature(f)
            layer.commitChanges()
            layer.triggerRepaint()
            # Force attribute table to reload
            try:
                dlg = iface.attributeTableDialog(layer)
                if dlg:
                    dlg.reload()  # This is more robust than viewport().update()
            except Exception as e:
                print(f"Attribute table refresh error: {e}")
        except Exception as e:
            print(f"Error updating feature: {e}")



    def connect_to_db(self, selected_db, username, password):
        if selected_db not in self.Databases:
            QMessageBox.critical(self, "Error", f"Database '{selected_db}' not found in configuration.")
            return None

        config = self.Databases[selected_db]
        db = DbHandler(config, username, password)
        db.selected_table = self.selected_table
        self.db_handler = db
        set_shared_db_handler(self.db_handler)

        try:
            # Get current backend PID and check for other sessions
            current_pid = db.get_current_pid()
            active_sessions = db.get_active_sessions(exclude_pid=current_pid)
        except Exception as e:
            logger.exception("DB error during session check")
            QMessageBox.critical(self, "Connection Error", f"Database error:\n{e}")
            db.cleanup()
            return None

        # Handle existing active sessions
        if active_sessions:
            if username.lower() == "postgres":
                logger.warning(f"Active session exists for superuser '{username}'")

                response = QMessageBox.question(
                    self, "Connection Limit",
                    f"You are already connected ({len(active_sessions)} sessions).\n"
                    "Do you want to terminate them and continue?",
                    QMessageBox.Yes | QMessageBox.No
                )

                if response == QMessageBox.Yes:
                    try:
                        db.terminate_sessions(active_sessions)
                        # Re-check to confirm termination
                        if db.get_active_sessions(exclude_pid=current_pid):
                            logger.error("Could not terminate all previous sessions.")
                            QMessageBox.critical(self, "Error", "Could not terminate all previous sessions. Please try again later.")
                            db.cleanup()
                            return None
                        QMessageBox.information(self, "Sessions Terminated", "Previous sessions have been terminated.")
                    except Exception as e:
                        logger.error("Failed to terminate sessions: %s", e)
                        QMessageBox.critical(self, "Error", f"Failed to terminate previous sessions:\n{e}")
                        db.cleanup()
                        return None
                else:
                    QMessageBox.information(self, "Connection Cancelled", "Login cancelled due to active sessions.")
                    db.cleanup()
                    return None
            else:
                logger.warning(f"Active session exists for user '{username}'")
                QMessageBox.warning(
                    self, "Active Session",
                    f"You are already connected ({len(active_sessions)} session(s)).\n"
                    "Please close your previous session before logging in."
                )
                db.cleanup()
                return None

        # Try final connection
        try:
            self.conn = db.connect()
            logger.info("✅ Connected to %s successfully!", selected_db)
            return self.conn
        except Exception as e:
            logger.error("Database connection failed: %s", e)
            QMessageBox.critical(self, "Connection Error", f"Database connection failed:\n{e}")
            db.cleanup()
            return None


    def load_editable_layer(self, designation, selected_db, username, password):
        config = self.Databases[selected_db]
        quoted_tbl = self.selected_table
        print(f"[DEBUG] Loading layer from table: {quoted_tbl}")  # <-- Add this line
        uri = (
                f"dbname='{config['dbname']}' host={config['host']} port={config['port']} "
                f"user='{username}' password='{password}' key='work_unit_id' sslmode=disable "
                f"options='-c app.current_user_emp_id={username}' "
                f'table={quoted_tbl}(geom) sql='
            )

        layer = QgsVectorLayer(uri, "{designation}(Editable)", "postgres")
        layer = QgsVectorLayer(uri, f"{designation}(Editable)", "postgres")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.sort_attribute_table_by_sno(layer)
            self.current_layer = layer
            # Attach conflict listener
            self.conflict_listener = ConflictListener(layer, self)
            # Always sort after any edit
            layer.committedAttributeValuesChanges.connect(lambda *args: self.sort_attribute_table_by_sno(layer))
            layer.committedFeaturesAdded.connect(lambda *args: self.sort_attribute_table_by_sno(layer))
            layer.committedFeaturesRemoved.connect(lambda *args: self.sort_attribute_table_by_sno(layer))
            # --- Auto-populate Employee Name ---
            layer.attributeValueChanged.connect(self.on_production_employee_id_changed)
            return True
        else:
            print("❌ Error loading editable layer: Layer is not valid.")
            return False

    # Mapping of emp_id fields to their corresponding name fields
    EMP_ID_TO_NAME_FIELD = {
        "rfdb_production_emp_id": "rfdb_production_done_by",
        "siloc_production_emp_id": "siloc_production_done_by",
        "siloc_qc_emp_id": "siloc_qc_done_by",
        "rfdb_path_association_production_emp_id": "rfdb_path_association_production_done_by",
        "rfdb_qc_emp_id": "rfdb_qc_done_by",
        "rfdb_attri_qc_emp_id": "rfdb_attri_qc_done_by",
        "rfdb_roadtype_qc_emp_id": "rfdb_roadtype_qc_done_by",
        "rfdb_qa_emp_id": "rfdb_qa_done_by",
        "rfdb_path_association_qc_emp_id": "rfdb_path_association_qc_done_by"
    }

    def on_production_employee_id_changed(self, fid, attr_map):
        layer = self.current_layer
        if not layer or not layer.isValid():
            print("Layer is not valid or not set.")
            return

        for emp_id_field, name_field in self.EMP_ID_TO_NAME_FIELD.items():
            if emp_id_field in attr_map:
                employee_id = attr_map[emp_id_field]
                try:
                    feature = layer.getFeature(fid)
                except Exception as e:
                    print(f"Error fetching feature: {e}")
                    continue
                if feature[name_field] or not employee_id:
                    continue

                def fetch_and_update(emp_id=employee_id, name_field=name_field, fid=fid):
                    try:
                        employee_name = self.fetch_employee_name(emp_id)
                        if not employee_name:
                            return
                        def update_feature():
                            try:
                                if not layer.isEditable():
                                    layer.startEditing()
                                f = layer.getFeature(fid)
                                f[name_field] = employee_name
                                layer.updateFeature(f)
                                layer.commitChanges()
                                layer.triggerRepaint()
                                try:
                                    dlg = iface.attributeTableDialog(layer)
                                    if dlg:
                                        dlg.reload()
                                except Exception as e:
                                    print(f"Attribute table refresh error: {e}")
                            except Exception as e:
                                print(f"Error updating feature: {e}")
                        QTimer.singleShot(0, update_feature)
                    except Exception as e:
                        print(f"Error fetching employee name for {emp_id_field}: {e}")

                threading.Thread(target=fetch_and_update).start()

    def load_readonly_layer(self, selected_db, username, password, designation):
        print(f"[DEBUG] Loading read-only layer for {designation} from table: \"public\".\"users_views\"")
        try:
            config = self.Databases[selected_db]
            uri = (
                f"dbname='{config['dbname']}' host={config['host']} port={config['port']} "
                f"user='{username}' password='{password}' key='work_unit_id' sslmode=disable "
                f'table="public"."users_views" (geom) sql='
            )
            layer = QgsVectorLayer(uri, f"{designation} (Read Only)", "postgres")

            if layer.isValid():
                layer.setReadOnly(True)
                QgsProject.instance().addMapLayer(layer)
                self.sort_attribute_table_by_sno(layer)
                self.current_layer = layer
                return True
            else:
                print("❌ Error loading read-only layer: Layer is not valid.")
                QMessageBox.warning(self, "Layer Error", "Failed to load the read-only layer.")
                return False
        except Exception as e:
            print(f"Error in load_readonly_layer: {e}")
            QMessageBox.critical(self, "Error", f"Error loading read-only layer:\n{e}")
            return False

    def get_user_role(self):
        return self.designation if self.designation else "user"

    def logout(self):
        if self._is_logging_out:
            return
        self._is_logging_out = True

        # Remove current layer from QGIS if loaded
        if self.current_layer:
            QgsProject.instance().removeMapLayer(self.current_layer.id())
        self.current_layer = None

        # Close database connection if open
        if self.conn:
            self.conn.close()
            self.conn = None

        self.reset_form()  # Clear form fields
        QMessageBox.information(self, "Logout", "Logged out and disconnected from database.")
        self.logout_requested.emit()
        self._is_logging_out = False

    def on_layers_removed(self, layer_ids):
        try:
            if self.current_layer and not sip.isdeleted(self.current_layer):
                if not QgsProject.instance().mapLayer(self.current_layer.id()):
                    if self.conn:
                        self.conn.close()
                        self.conn = None
                    self.reset_form()  # Clear form fields
                    QMessageBox.information(self, "Layers Removed", "Layer Removed, disconnected from database.")
                    self.logout_requested.emit()
                    self._is_logging_out = False
            else:
                self.current_layer = None
        except RuntimeError:
            # The layer has already been deleted, just clean up references
            self.current_layer = None
            if self.conn:
                self.conn.close()
                self.conn = None
            self.reset_form()
            QMessageBox.information(self, "Layers Removed", "Layer Removed, disconnected from database.")
            self.logout_requested.emit()
            self._is_logging_out = False

    def save_edits(self, field_name, value):
        # Use the shared is_field_editable function
        table_name = self.selected_table
        if not is_field_editable(self.designation, field_name, table_name=table_name):
            QMessageBox.warning(self, "Permission Denied", f"You do not have privilege to edit '{field_name}'.")
            return
        # ...proceed to save the value...
        self.refresh_layer()

    def refresh_layer(self):
        if hasattr(self, 'current_layer') and self.current_layer:
            self.current_layer.triggerRepaint()
            self.sort_attribute_table_by_sno(self.current_layer)

    def sort_attribute_table_by_sno(self, layer=None):
        # Use the provided layer, or fallback to self.current_layer
        if layer is None:
            layer = getattr(self, 'current_layer', None)
        if not layer or not layer.isValid() or layer.type() != layer.VectorLayer:
            return
        try:
            idx = layer.fields().indexFromName('s_no')
            if idx != -1:
                # Sorting logic if needed
                pass
            else:
                print("Field 's_no' not found for sorting.")
        except Exception as e:
            print(f"Error sorting attribute table: {e}")

    # Example: Fetching something with retries and logging
    def fetch_employee_name(self, emp_id):
        """Fetch the employee name for a given employee ID from the database."""
        config = self.Databases[self.selected_Database]
        db = DbHandler(config, self.emp_id, self.db_password)
        db.selected_table = self.selected_table
        try:
            with db.get_cursor_with_retries() as cur:
                cur.execute("SELECT employee_name FROM public.employee WHERE employee_id = %s", (emp_id,))
                result = cur.fetchone()
                if result:
                    logger.info("Fetched employee name for %s: %s", emp_id, result[0])
                return result[0] if result else None
        except Exception as e:
            logger.exception("Error fetching employee name for %s", emp_id)
            QMessageBox.critical(self, "Error", f"Error fetching employee name:\n{e}")
            return None
        finally:
            db.cleanup()

    #upload_csv_dialog placeholder previous implementation

    def open_portal_viewer(self):
        dlg = WorkAllocationPortalViewerDialog(self.db_handler, self.designation, self.selected_table, self)
        dlg.exec_()



class ConflictListener(QObject):
    """Listens for edit conflicts and notifies the user."""
    def __init__(self, layer, parent=None):
        super().__init__(parent)
        self.layer = layer
        self._connected = False
        self.layer.editingStarted.connect(self.on_editing_started)
        self.layer.editingStopped.connect(self.on_editing_stopped)
        self.layer.committedFeaturesAdded.connect(self.on_committed)
        self.layer.committedFeaturesRemoved.connect(self.on_committed)
        self.layer.committedAttributeValuesChanges.connect(self.on_committed)
        # Do NOT connect to editBuffer().committedWithConflicts here!

    def on_editing_started(self):
        print("Editing started.")
        edit_buffer = self.layer.editBuffer()
        if edit_buffer and not self._connected:
            # if Qgis.QGIS_VERSION_INT >= 33400:  # QGIS 3.34.0 or newer
            #     edit_buffer.committedWithConflicts.connect(self.on_conflict)
            #     self._connected = True
            pass  # Remove this line if your QGIS version supports committedWithConflicts

    def on_editing_stopped(self):
        print("Editing stopped.")
        edit_buffer = self.layer.editBuffer()
        # Remove the following block if your QGIS version does not support committedWithConflicts
        # if edit_buffer and self._connected:
        #     try:
        #         edit_buffer.committedWithConflicts.disconnect(self.on_conflict)
        #     except Exception:
        #         pass
        #     self._connected = False

    def on_committed(self, *args):
        print("Edits committed.")

    def on_conflict(self, conflicts):
        QMessageBox.warning(None, "Edit Conflict", "A conflict occurred while saving edits. Please refresh and try again.")

    def handle_logout(self):
        if hasattr(self, "work_allocation_dialog") and self.work_allocation_dialog is not None:
            self.work_allocation_dialog.close()
            self.work_allocation_dialog = None

    def upload_csv_dialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        file_name, _ = QFileDialog.getOpenFileName(self, "Open CSV File", "", "CSV Files (*.csv);;All Files (*)", options=options)
        if file_name:
            self.process_csv_file(file_name)

    def process_csv_file(self, file_path):
        try:
            # Read the CSV file
            df = pd.read_csv(file_path)
            if df.empty:
                QMessageBox.warning(self, "Empty CSV", "The selected CSV file is empty.")
                return

            # Show a preview dialog
            preview_dialog = QDialog(self)
            preview_dialog.setWindowTitle("CSV Preview")
            layout = QVBoxLayout(preview_dialog)

            table_view = QTableView(preview_dialog)
            model = PandasModel(df)
            table_view.setModel(model)
            layout.addWidget(table_view)

            # Add a button to confirm import
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, preview_dialog)
            layout.addWidget(button_box)

            button_box.accepted.connect(preview_dialog.accept)
            button_box.rejected.connect(preview_dialog.reject)

            preview_dialog.resize(800, 600)
            preview_dialog.exec_()

            # If accepted, proceed with the import
            if preview_dialog.result() == QDialog.Accepted:
                self.import_csv_data(df)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while processing the CSV file:\n{e}")

    def import_csv_data(self, df):
        if self.db_handler is None:
            QMessageBox.warning(self, "Database Error", "Not connected to any database.")
            return

        # Basic validation: Check for required columns
        required_columns = ["geom", "s_no", "project", "wu_received_date", "work_unit_id", "length_mi", "subcountry", "rough_road_type"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            QMessageBox.warning(self, "CSV Validation", f"The CSV file is missing the following required columns:\n{', '.join(missing_columns)}")
            return

        # Confirm with the user before truncating
        response = QMessageBox.question(
            self, "Confirm Truncate",
            "This action will truncate the existing data in the table. Do you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if response == QMessageBox.Yes:
            try:
                # Truncate the existing data in the table
                tbl = self.selected_table if self.selected_table else '"public"."production_inputs"'
                with self.db_handler.get_cursor_with_retries() as cur:
                    cur.execute(f"TRUNCATE TABLE {tbl} CASCADE")
                    self.db_handler.conn.commit()
                QMessageBox.information(self, "Success", "Existing data truncated successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to truncate table:\n{e}")
                return

        # Insert the new data
        try:
            tbl = self.selected_table if self.selected_table else '"public"."production_inputs"'
            with self.db_handler.get_cursor_with_retries() as cur:
                for _, row in df.iterrows():
                    cur.execute(f"""
                        INSERT INTO {tbl}
                        (geom, s_no, project, wu_received_date, work_unit_id, length_mi, subcountry, rough_road_type)
                        VALUES (
                            ST_SetSRID(ST_GeomFromWKB(decode(%s, 'hex')), 4326),
                            %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (row["geom"], row["s_no"], row["project"], row["wu_received_date"], row["work_unit_id"], row["length_mi"], row["subcountry"], row["rough_road_type"]))
                self.db_handler.conn.commit()
            QMessageBox.information(self, "Success", "Data imported successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import data:\n{e}")


