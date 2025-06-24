from PyQt5 import uic
from PyQt5.QtWidgets import (
    QDialog, QLabel, QLineEdit, QComboBox, QPushButton, QHBoxLayout,
    QVBoxLayout, QMessageBox, QFormLayout, QDialogButtonBox, QFrame, QToolButton, QFileDialog, QTableWidgetItem, QAction, QHeaderView, QAbstractScrollArea
)
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
import pandas as pd
import psycopg2
from qgis.core import QgsVectorLayer, Qgis, QgsProject
from qgis.utils import iface
from .db_handler import DbHandler
from .constants import EDITABLE_FIELDS
from .custom_attribute_table import CustomAttributeTable
from .conflict_listener import is_field_editable, show_privilege_error

import logging
import sip
import threading
import os
from shapely import wkt
from shapely.geometry import MultiLineString
import binascii
import traceback

logger = logging.getLogger(__name__)



class LoginDialog(QDialog):
    login_successful = pyqtSignal(object)  # Accepts db_handler as argument
    logout_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login")
        self.setFixedWidth(400)
        self.conn = None
        self.designation = None
        self.current_layer = None
        self.conflict_listener = None
        self._is_logging_out = False

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
        self.Database_dropdown.addItems(["select a Database"] + list(self.Databases.keys()))
        form_layout.addRow("Database:", self.Database_dropdown)

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
        self.csv_upload_button = QPushButton()
        icon_path_2 = os.path.join(os.path.dirname(__file__), 'csv_icon.png')
        self.csv_upload_button.setIcon(QIcon(icon_path_2))
        self.csv_upload_button.setText("Upload CSV")
        self.csv_upload_button.setVisible(False)  # Only show for grand_leaders
        layout.addWidget(self.csv_upload_button)

        self.setLayout(layout)

    def connect_events(self):
        self.emp_id_input.textChanged.connect(self.update_designation)
        self.toggle_eye.toggled.connect(self.toggle_password_visibility)
        self.reset_button.clicked.connect(self.reset_form)
        self.button_box.accepted.connect(self.validate_login)
        self.button_box.rejected.connect(self.reject)
        self.reset_button.clicked.connect(self.refresh_layer)
        self.csv_upload_button.clicked.connect(self.upload_csv_dialog)

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
                success = self.load_editable_layer(self.designation, Database_name, emp_id, password)
                if success:
                    QMessageBox.information(self, "Success", "Login and layer loading successful!")
                    self.db_handler = DbHandler(self.Databases[self.selected_Database], self.emp_id, self.db_password)
                    self.db_handler.connect()
                    self.login_successful.emit(self.db_handler)
                    self.reset_form()
                    self.accept()
                    self.csv_upload_button.setVisible(True)
                else:
                    QMessageBox.warning(self, "Layer Error", "Connected, but failed to load the layer.")
            else:
                QMessageBox.critical(self, "Connection Error", "Database connection failed.")
            return

        # Normal user/leader logic
        self.df["employee_id"] = self.df["employee_id"].astype(str).str.strip()
        self.df["password"] = self.df["password"].astype(str).str.strip()
        self.df["processed_employee_id"] = self.df["employee_id"]

        match = self.df[
            (self.df["employee_id"] == emp_id) &
            (self.df["password"] == password)
        ]

        if not match.empty:
            self.designation = str(match.iloc[0]["category"]).lower()  # Ensure this matches EDITABLE_FIELDS keys
            self.emp_id = emp_id
            self.db_password = password
            self.selected_Database = Database_name

            conn = self.connect_to_db(Database_name, emp_id, password)
            if conn:
                if self.designation in EDITABLE_FIELDS:
                    success = self.load_editable_layer(self.designation, Database_name, emp_id, password)
                    if success and self.current_layer:
                        self.current_layer.setName(f"{self.designation} (Editable)")
                else:
                    # Set layer name to include designation after login
                    success = self.load_readonly_layer(Database_name, emp_id, password, designation=self.designation)
                    if success and self.current_layer:
                        self.current_layer.setName(f"{self.designation} (Read Only)")
                if success:
                    QMessageBox.information(self, "Success", "Login and layer loading successful!")
                    # After successful login, before emitting login_successful:
                    self.db_config = self.Databases[self.selected_Database]
                    self.db_user = self.emp_id
                    self.db_password = self.db_password
                    self.db_handler = DbHandler(self.Databases[self.selected_Database], self.emp_id, self.db_password)
                    self.db_handler.connect()
                    self.login_successful.emit(self.db_handler)
                    self.reset_form()
                    self.accept()
                else:
                    QMessageBox.warning(self, "Layer Error", "Connected, but failed to load the layer.")
            else:
                QMessageBox.critical(self, "Connection Error", "Database connection failed.")
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid Employee ID or Password.")
            self.csv_upload_button.setVisible(False)
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
        try:
            current_pid = db.get_current_pid()
            active_sessions = db.get_active_sessions(exclude_pid=current_pid)
        except Exception as e:
            logger.exception("DB error")
            QMessageBox.critical(self, "Connection Error", f"Database error:\n{e}")
            db.cleanup()
            return None

        if active_sessions:
            if username.lower() == "postgres":
                response = QMessageBox.question(
                    self, "Connection Limit",
                    f"You are already connected ({len(active_sessions)} session(s)).\n"
                    "Do you want to end previous session(s) and continue?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if response == QMessageBox.Yes:
                    try:
                        db.terminate_sessions(active_sessions)
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
                logger.warning("Active session exists for user %s", username)
                QMessageBox.warning(
                    self, "Active Session",
                    f"You are already connected ({len(active_sessions)} session(s)).\n"
                    "Please close your previous session before logging in."
                )
                db.cleanup()
                return None

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
        uri = (
            f"dbname='{config['dbname']}' host={config['host']} port={config['port']} "
            f"user='{username}' password='{password}' key='work_unit_id' sslmode=disable "
            f'table="public"."production_input" (geom) sql='
        )
        # Set layer name with designation and (Editable)
        layer_name = f"{designation} (Editable)"
        layer = QgsVectorLayer(uri, layer_name, "postgres")

        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.current_layer = layer
            if "_leaders" in self.designation:
                # Do NOT call self.show_custom_attribute_table() here
                return True
            else:
                self.show_custom_attribute_table()
                return True
        else:
            print("❌ Error loading editable layer: Layer is not valid.")
            return False

    def show_custom_attribute_table(self):
        if not self.is_logged_in or not getattr(self.login_dialog, "designation", None):
            QMessageBox.warning(None, "No Role", "User role not set. Please login again.")
            return
        if not hasattr(self, "db_handler") or self.db_handler is None:
            QMessageBox.critical(None, "DB Error", "Database handler is not set!")
            return
        editable_fields = EDITABLE_FIELDS.get(self.login_dialog.designation, [])
        self.table_frame = CustomAttributeTable(
            db_handler=self.db_handler,
            editable_fields=editable_fields,
            df=getattr(self.login_dialog, "df", None),
            designation=getattr(self.login_dialog, "designation", None),
            parent=self.iface.mainWindow()
        )
        self.table_frame.show()
        print("Rows in table:", self.table_frame.tableWidget.rowCount())

    def load_readonly_layer(self, selected_db, username, password, designation):
        try:
            config = self.Databases[selected_db]
            uri = (
                f"dbname='{config['dbname']}' host={config['host']} port={config['port']} "
                f"user='{username}' password='{password}' key='work_unit_id' sslmode=disable "
                f'table="public"."users_views" (geom) sql='
            )
            # Set layer name with designation and (Read Only)
            layer_name = f"{designation} (Read Only)"
            layer = QgsVectorLayer(uri, layer_name, "postgres")

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
                    QMessageBox.information(self, "Logout", "Logged out and disconnected from database.")
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
            QMessageBox.information(self, "Logout", "Logged out and disconnected from database.")
            self.logout_requested.emit()
            self._is_logging_out = False


    def save_edits(self, field_name, value):
        if not is_field_editable(self.designation, field_name):
            show_privilege_error(field_name)
            return
        # ...proceed to save the value...
        self.refresh_layer()

    def refresh_layer(self):
        if hasattr(self, 'current_layer') and self.current_layer:
            self.current_layer.triggerRepaint()
            self.sort_attribute_table_by_sno(self.current_layer)

    def sort_attribute_table_by_sno(self, layer):
        try:
            idx = layer.fields().indexFromName('S_no')
            if idx != -1:
                iface.showAttributeTable(layer)
                dlg = iface.attributeTableDialog(layer)
                if dlg:
                    view = dlg.tableView()
                    view.sortByColumn(idx, Qt.AscendingOrder)
            else:
                print("Field 'S_no' not found for sorting.")
        except Exception as e:
            print(f"Error sorting attribute table: {e}")

    # Example: Fetching something with retries and logging
    def fetch_employee_name(self, emp_id):
        """Fetch the employee name for a given employee ID from the database."""
        config = self.Databases[self.selected_Database]
        db = DbHandler(config, self.emp_id, self.db_password)
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

    def upload_csv_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select CSV File", "", "CSV Files (*.csv)")
        if not file_path:
            return

        mandatory_columns = [
            "geom", "s_no", "project", "wu_received_date", "work_unit_id",
            "length_mi", "subcountry", "rough_road_type"
        ]

        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            logger.exception("Failed to read CSV")
            QMessageBox.critical(self, "CSV Error", f"Failed to read CSV:\n{e}")
            return

        # Check mandatory columns
        missing = [col for col in mandatory_columns if col not in df.columns]
        if missing:
            QMessageBox.critical(self, "CSV Error", f"Missing columns: {', '.join(missing)}")
            return

        # Check not null
        for col in mandatory_columns:
            if df[col].isnull().any():
                QMessageBox.critical(self, "CSV Error", f"Column '{col}' contains null values.")
                return

        # Check geom column is WKT and convert to WKB (MultiLineString, 4326)
        wkb_geoms = []
        for idx, wkt_str in enumerate(df["geom"]):
            try:
                geom = wkt.loads(wkt_str)
                if not isinstance(geom, MultiLineString):
                    raise ValueError("Geometry is not MultiLineString")
                # WKB hex, SRID 4326
                wkb_hex = binascii.hexlify(geom.wkb).decode()
                wkb_geoms.append(wkb_hex)
            except Exception as e:
                QMessageBox.critical(self, "CSV Error", f"Row {idx+1}: Invalid geometry: {e}")
                return
        df["geom_wkb"] = wkb_geoms

        # Connect as admin/superuser
        config = self.Databases[self.selected_Database]
        db = DbHandler(config, self.emp_id, self.db_password)
        try:
            with db.get_cursor_with_retries() as cur:
                # Check s_no and work_unit_id uniqueness
                cur.execute("SELECT s_no, work_unit_id FROM public.production_input")
                existing = cur.fetchall()
                existing_sno = set(row[0] for row in existing)
                existing_wu = set(row[1] for row in existing)
                for idx, row in df.iterrows():
                    if row["s_no"] in existing_sno:
                        QMessageBox.critical(self, "CSV Error", f"s_no '{row['s_no']}' already exists.")
                        return
                    if row["work_unit_id"] in existing_wu:
                        QMessageBox.critical(self, "CSV Error", f"work_unit_id '{row['work_unit_id']}' already exists.")
                        return

                # Insert rows
                for idx, row in df.iterrows():
                    cur.execute("""
                        INSERT INTO public.production_input
                        (geom, s_no, Database, wu_received_date, work_unit_id, length_mi, subcountry, rough_road_type)
                        VALUES (
                            ST_SetSRID(ST_GeomFromWKB(decode(%s, 'hex')), 4326),
                            %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        row["geom_wkb"], row["s_no"], row["Database"], row["wu_received_date"],
                        row["work_unit_id"], row["length_mi"], row["subcountry"], row["rough_road_type"]
                    ))
                db.conn.commit()
        except Exception as e:
            db.conn.rollback()
            logger.exception("CSV upload failed")
            QMessageBox.critical(self, "Upload Error", f"Failed to upload CSV:\n{e}")
        finally:
            db.cleanup()

    def add_csv_toolbar_action(self):
        if hasattr(self, 'csv_action') and self.csv_action:
            return
        icon_path = os.path.join(os.path.dirname(__file__), 'csv_icon.png')
        self.csv_action = QAction(QIcon(icon_path), "Upload CSV", iface.mainWindow())
        self.csv_action.triggered.connect(self.on_csv_icon_triggered)
        iface.addPluginToMenu("CSV", self.csv_action)
        iface.addToolBarIcon(self.csv_action)

    def add_leader_toolbar_action(self):
        if hasattr(self, 'leader_action') and self.leader_action:
            return
        icon_path = os.path.join(os.path.dirname(__file__), 'table.png')
        self.leader_action = QAction(QIcon(icon_path), "Open Attribute Table", iface.mainWindow())
        self.leader_action.triggered.connect(self.on_table_icon_triggered)
        iface.addPluginToMenu("Leader Tools", self.leader_action)
        iface.addToolBarIcon(self.leader_action)
        
    def remove_csv_toolbar_action(self):
        if hasattr(self, 'csv_action') and self.csv_action:
            iface.removePluginMenu("CSV", self.csv_action)
            iface.removeToolBarIcon(self.csv_action)
            self.csv_action = None

    def remove_leader_toolbar_action(self):
        if hasattr(self, 'leader_action') and self.leader_action:
            iface.removePluginMenu("Leader Tools", self.leader_action)
            iface.removeToolBarIcon(self.leader_action)
            self.leader_action = None
    def on_table_icon_triggered(self):
        if not hasattr(self, "db_handler") or self.db_handler is None:
            QMessageBox.warning(self, "No DB", "No database handler available.")
            return
        editable_fields = EDITABLE_FIELDS.get(self.designation, [])
        from .custom_attribute_table import CustomAttributeTable
        dlg = CustomAttributeTable(
            db_handler=self.db_handler,
            editable_fields=editable_fields,
            df=getattr(self, "df", None),
            designation=getattr(self, "designation", None),
            parent=self
        )
        dlg.show()

    def on_csv_icon_triggered(self):
        if self.designation != "grand_leaders":
            QMessageBox.warning(self, "Access Denied", "Only grand_leaders can upload CSV.")
            return
        self.upload_csv_dialog()

    def handle_login(self):
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
                success = self.load_editable_layer(self.designation, Database_name, emp_id, password)
                if success:
                    QMessageBox.information(self, "Success", "Login and layer loading successful!")
                    # Emit db_handler for main plugin/controller
                    self.db_handler = DbHandler(self.Databases[Database_name], emp_id, password)
                    self.db_handler.connect()
                    self.login_successful.emit(self.db_handler)
                    self.reset_form()
                    self.accept()
                    self.csv_upload_button.setVisible(True)
                else:
                    QMessageBox.warning(self, "Layer Error", "Connected, but failed to load the layer.")
            else:
                QMessageBox.critical(self, "Connection Error", "Database connection failed.")
            return

        # Normal user/leader logic
        self.df["employee_id"] = self.df["employee_id"].astype(str).str.strip()
        self.df["password"] = self.df["password"].astype(str).str.strip()
        self.df["processed_employee_id"] = self.df["employee_id"]

        match = self.df[
            (self.df["employee_id"] == emp_id) &
            (self.df["password"] == password)
        ]

        if not match.empty:
            self.designation = str(match.iloc[0]["category"]).lower()  # Ensure this matches EDITABLE_FIELDS keys
            self.emp_id = emp_id
            self.db_password = password
            self.selected_Database = Database_name

            conn = self.connect_to_db(Database_name, emp_id, password)
            if conn:
                if self.designation in EDITABLE_FIELDS:
                    success = self.load_editable_layer(self.designation, Database_name, emp_id, password)
                    if success and self.current_layer:
                        self.current_layer.setName(f"{self.designation} (Editable)")
                else:
                    # Set layer name to include designation after login
                    success = self.load_readonly_layer(Database_name, emp_id, password, designation=self.designation)
                    if success and self.current_layer:
                        self.current_layer.setName(f"{self.designation} (Read Only)")
                if success:
                    QMessageBox.information(self, "Success", "Login and layer loading successful!")
                    # After successful login, before emitting login_successful:
                    self.db_config = self.Databases[self.selected_Database]
                    self.db_user = self.emp_id
                    self.db_password = self.db_password
                    self.db_handler = DbHandler(self.Databases[self.selected_Database], self.emp_id, self.db_password)
                    self.db_handler.connect()
                    self.login_successful.emit(self.db_handler)
                    self.reset_form()
                    self.accept()
                else:
                    QMessageBox.warning(self, "Layer Error", "Connected, but failed to load the layer.")
            else:
                QMessageBox.critical(self, "Connection Error", "Database connection failed.")
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid Employee ID or Password.")
            self.csv_upload_button.setVisible(False)
            self.password_input.clear()
            logger.warning("Failed login attempt for Employee ID: %s", emp_id)





