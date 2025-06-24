from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QTimer, QObject, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QFileDialog, QDialog, QVBoxLayout, QLabel, QComboBox, QDialogButtonBox
from qgis.core import QgsEditorWidgetSetup, QgsProject
from qgis.core import QgsVectorLayer



from .resources import *
from .login_dialog import LoginDialog, EDITABLE_FIELDS
from .work_allocation_portal_dialog import WorkAllocationPortalViewerDialog
from .conflict_listener import listen_for_edits, is_field_editable
from .db_handler import signal_bus, set_shared_db_handler
import gc

import os.path
import pandas as pd
import threading
from datetime import datetime
import binascii
from shapely import wkt
from shapely.geometry import MultiLineString


class UserLoginViewer:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(self.plugin_dir, 'i18n', f'UserLoginViewer_{locale}.qm')

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&UserLoginViewer')
        self.toolbar = self.iface.addToolBar(u'UserLoginViewer')
        self.toolbar.setObjectName(u'UserLoginViewer')

        self.pluginIsActive = False

        # Initialize login dialog
        self.login_dialog = LoginDialog()
        self.login_dialog.login_successful.connect(self.on_login_success)
        self.login_dialog.logout_requested.connect(self.on_logout)
        self.is_logged_in = False

        self.selected_feature_dialog = None  # <-- Add this line

    def tr(self, message):
        return QCoreApplication.translate('UserLoginViewer', message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)
        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        portal_icon_path = os.path.join(self.plugin_dir, 'portal_icon.png')
        csv_icon_path = os.path.join(self.plugin_dir, 'csv_icon.png')
        feature_selection_icon = os.path.join(self.plugin_dir, 'icon', 'feature-selection.png')
        select_state_icon = os.path.join(self.plugin_dir, 'icon', 'select-state.png')

        # Always enabled
        self.work_allocation_panel_action = self.add_action(
            icon_path,
            text=self.tr(u'Open Work Allocation Login Panel'),
            callback=self.run,
            parent=self.iface.mainWindow(),
            enabled_flag=True
        )
        # Grayed out by default, use portal_icon.png
        self.work_allocation_viewer_action = self.add_action(
            portal_icon_path,
            text=self.tr(u'Work Allocation Portal Viewer'),
            callback=self.show_work_allocation_portal_viewer,
            parent=self.iface.mainWindow(),
            enabled_flag=False
        )
        # Grayed out by default, use csv_icon.png
        self.upload_csv_action = self.add_action(
            csv_icon_path,
            text=self.tr(u'Upload CSV'),
            callback=self.upload_csv_dialog,
            parent=self.iface.mainWindow(),
            enabled_flag=False
        )

        # Add "Select state" submenu action
        self.select_state_action = self.add_action(
            select_state_icon,
            text=self.tr(u'Select state'),
            callback=self.show_select_state_dialog,
            parent=self.iface.mainWindow(),
            enabled_flag=True
        )

        self.login_dialog.portal_viewer_enable.connect(self.work_allocation_viewer_action.setEnabled)

        #No submenu implementation
        # self.open_selected_feature_dialog_action = QAction(QIcon(feature_selection_icon), "Show Selected Feature", self.iface.mainWindow())
        # self.open_selected_feature_dialog_action.triggered.connect(self.show_selected_feature_dialog)
        # self.iface.registerMainWindowAction(self.open_selected_feature_dialog_action, "Shift+F8")
        # self.actions.append(self.open_selected_feature_dialog_action)

        #For submenu implementation comment out the above block(No submenu implementation) and (Unregister the Shift+F8 shortcut action)
        self.open_selected_feature_dialog_action = QAction(QIcon(feature_selection_icon), "Show Selected Feature", self.iface.mainWindow())
        self.open_selected_feature_dialog_action.setShortcut("Shift+F8")
        self.open_selected_feature_dialog_action.triggered.connect(self.show_selected_feature_dialog)
        self.iface.addPluginToMenu(self.menu, self.open_selected_feature_dialog_action)
        self.toolbar.addAction(self.open_selected_feature_dialog_action)

    def show_work_allocation_panel(self):
        self.login_dialog.setModal(True)
        self.login_dialog.show()

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.tr(u'&UserLoginViewer'), action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

        # Unregister the Shift+F8 shortcut action
        #self.iface.unregisterMainWindowAction(self.open_selected_feature_dialog_action)

    def run(self):
        try:
            if self.is_logged_in:
                reply = QMessageBox.question(None, "Logout", "Do you want to logout?", QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.login_dialog.logout()
            else:
                self.login_dialog.setModal(True)
                self.login_dialog.show()
                QTimer.singleShot(0, self.sort_attribute_table_by_sno)
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to open login dialog:\n{e}")

    def on_login_success(self):
        try:
            self.is_logged_in = True
            self.set_editable_fields_for_role(getattr(self.login_dialog, 'designation', 'user'))
            self.setup_conflict_listener()
            self.sort_attribute_table_by_sno()
            # Set db_handler from login dialog if available
            if hasattr(self.login_dialog, 'db_handler'):
                self.db_handler = self.login_dialog.db_handler
            else:
                self.db_handler = None

            # --- Show Select State Dialog ---
            subcountries = self.db_handler.fetch_unique_subcountries(self.login_dialog.selected_table)
            dlg = SelectStateDialog(subcountries, self.iface.mainWindow())
            while True:
                if dlg.exec_() == QDialog.Accepted:
                    selected_subcountry = dlg.selected_subcountry()
                    if selected_subcountry == "All subcountry":
                        self.selected_subcountry = None
                    else:
                        self.selected_subcountry = selected_subcountry
                    break  # Exit the loop, proceed with login
                else:
                    QMessageBox.warning(None, "State Required", "You should select any state to proceed.")
                    # Loop again until user selects a state

            # Now load the layer for the selected subcountry
            self.load_project_layer_with_subcountry()

            designation = getattr(self.login_dialog, 'designation', '').lower()
            selected_table = getattr(self.login_dialog, 'selected_table', '')
            if selected_table == '"public"."tm_production_inputs"':
                # For TM project, always enable
                self.work_allocation_viewer_action.setEnabled(True)
                self.upload_csv_action.setEnabled(False)
            elif designation.endswith('leaders'):
                self.work_allocation_viewer_action.setEnabled(True)
                # Enable Upload CSV only for grand_leaders
                if designation == 'grand_leaders':
                    self.upload_csv_action.setEnabled(True)
                else:
                    self.upload_csv_action.setEnabled(False)
            else:
                self.work_allocation_viewer_action.setEnabled(False)
                self.upload_csv_action.setEnabled(False)
        except Exception as e:
            QMessageBox.critical(None, "Login Error", f"An error occurred after login:\n{e}")

    def on_logout(self):
        self.is_logged_in = False
        self.work_allocation_viewer_action.setEnabled(False)
        self.upload_csv_action.setEnabled(False)

        # Close the portal viewer dialog if open
        if hasattr(self, "work_allocation_dialog") and self.work_allocation_dialog is not None:
            self.work_allocation_dialog.close()
            self.work_allocation_dialog = None

        # Properly close and cleanup DB connection and QGIS layers
        if hasattr(self, "db_handler") and self.db_handler is not None:
            try:
                # Attempt to remove the current layer if present
                if self.login_dialog.current_layer:
                    try:
                        # Clear focus from layer in UI to ensure full removal
                        self.iface.layerTreeView().setCurrentLayer(None)

                        # Remove the layer from the project
                        QgsProject.instance().removeMapLayer(self.login_dialog.current_layer.id())
                        self.login_dialog.current_layer = None
                    except Exception as e:
                        print(f"Error removing layer: {e}")

                # Cleanup database connection
                self.db_handler.cleanup()
                self.db_handler = None
                set_shared_db_handler(None)

                # Notify all other components to cleanup
                signal_bus.logout_signal.emit()

            except Exception as e:
                print(f"Error cleaning up DB handler or QGIS layer: {e}")

        # Refresh map canvas and repaint
        try:
            self.iface.mapCanvas().refresh()
            layer = self.iface.activeLayer()
            if layer:
                layer.triggerRepaint()
        except Exception as e:
            print(f"Error refreshing QGIS after logout: {e}")

        # Force garbage collection to clean lingering QGIS/Postgres refs
        gc.collect()

    def set_editable_fields_for_role(self, role):
        layer = getattr(self.login_dialog, 'current_layer', None)
        if not layer:
            return

        table_name = getattr(self.login_dialog, 'selected_table', None)
        editable_fields = EDITABLE_FIELDS.get(table_name, {}).get(role, [])
        self._reverting_attr = False

        for idx, field in enumerate(layer.fields()):
            try:
                layer.setEditorWidgetSetup(idx, QgsEditorWidgetSetup('TextEdit', {}))
            except Exception as e:
                print(f"Error setting editor widget for field {field.name()}: {e}")

        def on_attr_changed(fid, idx, value):
            if getattr(self, '_reverting_attr', False):
                return

            try:
                field_name = layer.fields()[idx].name()
                feature = layer.getFeature(fid)

                print(f"[DEBUG] Checking editable: role={role}, field={field_name}")

                if field_name not in editable_fields:
                    self._reverting_attr = True
                    layer.blockSignals(True)
                    original_value = feature[field_name]
                    layer.changeAttributeValue(fid, idx, original_value)
                    layer.blockSignals(False)
                    def show_warning():
                        QMessageBox.warning(None, "Edit Not Allowed", f"You don't have the privilege to edit '{field_name}'.")
                        self._reverting_attr = False
                    QTimer.singleShot(0, show_warning)
                    return

                last_updated = feature['last_updated'] if 'last_updated' in feature.fields().names() else None
                if last_updated:
                    if isinstance(last_updated, str):
                        try:
                            last_updated_dt = datetime.fromisoformat(last_updated)
                        except Exception:
                            last_updated_dt = None
                    else:
                        last_updated_dt = last_updated
                else:
                    last_updated_dt = None

                now = datetime.now()
                if last_updated_dt and last_updated_dt >= now:
                    self._reverting_attr = True
                    layer.blockSignals(True)
                    original_value = feature[field_name]
                    layer.changeAttributeValue(fid, idx, original_value)
                    layer.blockSignals(False)
                    def show_warning():
                        QMessageBox.warning(None, "Edit Not Allowed", "This row was updated recently by another user. Please refresh and try again.")
                        self._reverting_attr = False
                    QTimer.singleShot(0, show_warning)
                    return

                QTimer.singleShot(0, self.sort_attribute_table_by_sno)
            except Exception as e:
                print(f"Error in attribute change handler: {e}")

        try:
            layer.attributeValueChanged.disconnect()
        except Exception:
            pass
        try:
            layer.attributeValueChanged.connect(on_attr_changed)
        except Exception as e:
            print(f"Error connecting attributeValueChanged: {e}")

    def sort_attribute_table_by_sno(self):
        """Sort the attribute table by s_no column for the plugin's loaded vector layer."""
        # Use the layer loaded by your plugin, not iface.activeLayer()
        layer = getattr(self.login_dialog, 'current_layer', None)
        if not layer or not layer.isValid() or layer.type() != layer.VectorLayer:
            return
        try:
            config = layer.attributeTableConfig()
            if 's_no' in [f.name() for f in layer.fields()]:
                config.setSortExpression('s_no')
                config.setSortOrder(0)  # 0 = AscendingOrder, 1 = DescendingOrder
                layer.setAttributeTableConfig(config)
            else:
                print("Field 's_no' not found for sorting.")
        except Exception as e:
            print(f"Error sorting attribute table: {e}")

    def setup_conflict_listener(self):
        """Attach a conflict listener to the active layer."""
        layer = self.iface.activeLayer()
        if not layer:
            return

        class ConflictListener(QObject):
            def __init__(self, layer, plugin_instance, parent=None):
                super().__init__(parent)
                self.layer = layer
                self.plugin_instance = plugin_instance
                self._buffer_connected = False
                try:
                    self.layer.editingStarted.connect(self.on_editing_started)
                    self.layer.editingStopped.connect(self.on_editing_stopped)
                    self.layer.committedFeaturesAdded.connect(self.on_committed)
                    self.layer.committedFeaturesRemoved.connect(self.on_committed)
                    self.layer.committedAttributeValuesChanges.connect(self.on_committed)
                except Exception as e:
                    print(f"Error connecting conflict listener signals: {e}")

            def on_editing_started(self):
                try:
                    edit_buffer = self.layer.editBuffer()
                    if edit_buffer and not self._buffer_connected:
                        self._buffer_connected = True
                except Exception as e:
                    print(f"Error in on_editing_started: {e}")

            def on_editing_stopped(self):
                try:
                    edit_buffer = self.layer.editBuffer()
                    if edit_buffer and self._buffer_connected:
                        self._buffer_connected = False
                    print("Editing stopped.")
                except Exception as e:
                    print(f"Error in on_editing_stopped: {e}")

            def on_committed(self, *args):
                print("Edits committed.")
                QTimer.singleShot(0, self.plugin_instance.sort_attribute_table_by_sno)

            def on_conflict(self, conflicts):
                QMessageBox.warning(None, "Edit Conflict", "A conflict occurred while saving edits. Please refresh and try again.")

        self._conflict_listener = ConflictListener(layer, self, parent=None)

    def show_work_allocation_portal_viewer(self):
        if not self.is_logged_in or not hasattr(self, 'db_handler') or self.db_handler is None:
            QMessageBox.warning(None, "Access Denied", "You must log in as a leader to access this feature.")
            return

        # Prevent duplicate forms
        if hasattr(self, "work_allocation_dialog") and self.work_allocation_dialog is not None:
            if self.work_allocation_dialog.isVisible():
                self.work_allocation_dialog.raise_()
                self.work_allocation_dialog.activateWindow()
                return
            else:
                # Clean up reference if dialog was closed
                self.work_allocation_dialog = None

        user_role = getattr(self.login_dialog, 'designation', 'user')
        table_name = getattr(self.login_dialog, 'selected_table', 'public.production_inputs')
        self.work_allocation_dialog = WorkAllocationPortalViewerDialog(
            self.db_handler, user_role, table_name, subcountry=self.selected_subcountry,
            emp_id=getattr(self.login_dialog, "emp_id", None),  
            qgis_layer=self.login_dialog.current_layer,  # <-- pass the QGIS layer!
            parent=self.iface.mainWindow()
        )
        self.work_allocation_dialog.show()
        self.work_allocation_dialog.destroyed.connect(lambda: setattr(self, "work_allocation_dialog", None))

    def upload_csv_dialog(self):
        #file_path, _ = QFileDialog.getOpenFileName(self, "Select CSV File", "", "CSV Files (*.csv)")
        file_path, _ = QFileDialog.getOpenFileName(self.iface.mainWindow(), "Select CSV File", "", "CSV Files (*.csv)")
        if not file_path:
            return
        # Get table name from login dialog
        table_name = getattr(self.login_dialog, 'selected_table', 'public.production_inputs')
        mandatory_columns = [
            "geom", "s_no", "project", "wu_received_date", "work_unit_id",
            "length_mi", "subcountry", "rough_road_type"
        ]

        try:
            df = pd.read_csv(file_path)
        except Exception as e:
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
                if '.' in table_name:
                    schema, table = table_name.split('.')
                    uri = f'table="{schema}"."{table}" (geom) sql='
                else:
                    uri = f'table="{table_name}" (geom) sql='
                cur.execute(f"SELECT s_no, work_unit_id FROM {tbl}")
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
                    cur.execute(f"""
                        INSERT INTO {tbl}
                        (geom, s_no, project, wu_received_date, work_unit_id, length_mi, subcountry, rough_road_type)
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

        # Open the viewer/editor for the uploaded data
        table_name = getattr(self.login_dialog, 'selected_table', 'public.production_inputs')
        user_role = getattr(self.login_dialog, 'designation', 'user')
        self.work_allocation_dialog = WorkAllocationPortalViewerDialog(self.db_handler, user_role, table_name, parent=self.iface.mainWindow())
        self.work_allocation_dialog.show()

    def show_select_state_dialog(self):
        try:
            subcountries = self.db_handler.fetch_unique_subcountries('"public"."tm_production_inputs"')
            print("Fetched subcountries:", subcountries)
        except Exception as e:
            print("Error fetching subcountries:", e)
            subcountries = []

        # Placeholder for the select state dialog implementation
        dlg = SelectStateDialog(subcountries, self.iface.mainWindow())
        if dlg.exec_() == QDialog.Accepted:
            selected_subcountry = dlg.selected_subcountry()
            if selected_subcountry == "All subcountry":
                self.selected_subcountry = None
            else:
                self.selected_subcountry = selected_subcountry
                
            # Reload the layer and portal viewer for the new state!
            self.reload_layer_and_portal_viewer()
        else:
            print("State selection cancelled.")

    def open_select_state_dialog(self):
        # Fetch unique subcountry values from DB
        subcountries = self.db_handler.fetch_unique_subcountries('"public"."tm_production_inputs"')
        print("Fetched subcountries:", subcountries)
        dlg = SelectStateDialog(subcountries, self)
        if dlg.exec_() == QDialog.Accepted:
            selected = dlg.selected_subcountry()
            if selected == "All subcountry":
                self.selected_subcountry = None
            else:
                self.selected_subcountry = selected
            self.reload_layer_and_portal_viewer()

    def load_project_layer_with_subcountry(self):
        table_name = getattr(self.login_dialog, 'selected_table', 'public.production_inputs')
        designation = getattr(self.login_dialog, 'designation', 'user')
        config = self.login_dialog.Databases[self.login_dialog.selected_Database]
        username = self.login_dialog.emp_id
        password = self.login_dialog.db_password

        # Build SQL filter for subcountry
        sql_filter = ""
        if self.selected_subcountry:
            sql_filter = f"sql=\"subcountry\" = '{self.selected_subcountry}'"
        else:
            sql_filter = "sql="

        uri = (
            f"dbname='{config['dbname']}' host={config['host']} port={config['port']} "
            f"user='{username}' password='{password}' key='work_unit_id' sslmode=disable "
            f'table={table_name}(geom) {sql_filter}'
        )

        layer = QgsVectorLayer(uri, f"{designation}(Editable)", "postgres")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            self.login_dialog.current_layer = layer
            self.sort_attribute_table_by_sno()
            self.set_editable_fields_for_role(self.login_dialog.designation)  # <-- Add this line
        else:
            QMessageBox.critical(None, "Layer Error", "Failed to load the layer for the selected state.")

    def reload_layer_and_portal_viewer(self):
        # Just update the filter on the existing layer
        if self.login_dialog.current_layer:
            if self.selected_subcountry:
                expr = f"subcountry = '{self.selected_subcountry}'"
                self.login_dialog.current_layer.setSubsetString(expr)
            else:
                self.login_dialog.current_layer.setSubsetString("")  # Show all

        # Optionally, refresh or reopen the portal viewer if needed
        if hasattr(self, "work_allocation_dialog") and self.work_allocation_dialog is not None:
            self.work_allocation_dialog.close()
            self.work_allocation_dialog = None
        # Optionally, reopen the portal viewer automatically:
        # self.show_work_allocation_portal_viewer()

    def show_selected_feature_dialog(self):
        print("[DEBUG] Selected feature dialog triggered")
        # Prevent duplicate dialog
        if self.selected_feature_dialog is not None:
            self.selected_feature_dialog.raise_()
            self.selected_feature_dialog.activateWindow()
            return

        layer = self.iface.activeLayer()
        if not layer:
            QMessageBox.information(self.iface.mainWindow(), "No Layer", "Please select a vector layer.")
            return

        # Always open the dialog, even if nothing is selected
        self.selected_feature_dialog = WorkAllocationPortalViewerDialog(
            self.db_handler,
            getattr(self.login_dialog, 'designation', 'user'),
            getattr(self.login_dialog, 'selected_table', ''),
            subcountry=self.selected_subcountry,
            emp_id=getattr(self.login_dialog, "emp_id", None),
            qgis_layer=layer,
            parent=self.iface.mainWindow()
        )
        self.selected_feature_dialog.setWindowTitle("Selected Feature(s) Data")
        self.selected_feature_dialog.show()

        # Filter to current selection (may be empty)
        self.update_selected_feature_dialog()

        # Connect to selection changed signal
        layer.selectionChanged.connect(self.update_selected_feature_dialog)

        # Handle dialog close
        def on_close():
            try:
                layer.selectionChanged.disconnect(self.update_selected_feature_dialog)
            except Exception:
                pass
            self.selected_feature_dialog = None

        self.selected_feature_dialog.finished.connect(on_close)
        self.selected_feature_dialog.rejected.connect(on_close)
        self.selected_feature_dialog.destroyed.connect(on_close)

    def update_selected_feature_dialog(self):
        if not self.selected_feature_dialog:
            return
        layer = self.iface.activeLayer()
        if not layer:
            self.selected_feature_dialog.filter_to_snos([])
            return
        s_no_idx = layer.fields().indexFromName("s_no")
        selected_snos = [f["s_no"] for f in layer.selectedFeatures() if s_no_idx != -1]
        self.selected_feature_dialog.filter_to_snos(selected_snos)

    # def filter_to_snos(self, s_no_list):
    #     """Show only rows with s_no in s_no_list. If list is empty, show nothing."""
    #     s_no_set = set(map(str, s_no_list))
    #     s_no_idx = self.columns.index("s_no")
    #     for row in range(self.ui.tableWidget.rowCount()):
    #         s_no_item = self.ui.tableWidget.item(row, s_no_idx)
    #         if not s_no_item or s_no_item.text() not in s_no_set:
    #             self.ui.tableWidget.setRowHidden(row, True)
    #         else:
    #             self.ui.tableWidget.setRowHidden(row, False)
    #     # If no selection, hide all rows
    #     if not s_no_set:
    #         for row in range(self.ui.tableWidget.rowCount()):
    #             self.ui.tableWidget.setRowHidden(row, True)

class SelectStateDialog(QDialog):
    def __init__(self, subcountry_list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select State")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select subcountry:"))
        self.combo = QComboBox()
        self.combo.addItem("All subcountry")
        self.combo.addItems(sorted(subcountry_list))
        layout.addWidget(self.combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

    def selected_subcountry(self):
        return self.combo.currentText()

