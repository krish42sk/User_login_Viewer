from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from .resources import *
from .login_dialog import LoginDialog, EDITABLE_FIELDS
from .custom_attribute_table import CustomAttributeTable
import os.path
from qgis.core import QgsEditorWidgetSetup, QgsMapLayer
import threading
from .conflict_listener import listen_for_edits, is_field_editable, show_conflict_warning, show_privilege_error

from PyQt5.QtCore import QTimer, QObject, Qt
from PyQt5.QtWidgets import QMessageBox, QFrame
from datetime import datetime
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        self.login_dialog.login_successful.connect(self.on_login_successful)
        self.login_dialog.logout_requested.connect(self.on_logout)
        self.is_logged_in = False

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
        portal_icon_path = os.path.join(self.plugin_dir, 'table.png')
        csv_icon_path = os.path.join(self.plugin_dir, 'csv_icon.png')

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
            text=self.tr(u'custom_attribute_table'),
            callback=self.show_custom_attribute_table,
            parent=self.iface.mainWindow(),
            enabled_flag=False  # This should be set to True after login!
        )
        # Grayed out by default, use csv_icon.png
        self.upload_csv_action = self.add_action(
            csv_icon_path,
            text=self.tr(u'Upload CSV'),
            callback=self.login_dialog.upload_csv_dialog,  # Use the method from LoginDialog
            parent=self.iface.mainWindow(),
            enabled_flag=False
        )

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.tr(u'&UserLoginViewer'), action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

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
            logger.exception("Failed to open login dialog")
            QMessageBox.critical(None, "Error", f"Failed to open login dialog:\n{e}")

    def on_login_successful(self, db_handler):
        self.is_logged_in = True
        self.db_handler = db_handler
        self.set_editable_fields_for_role(getattr(self.login_dialog, 'designation', 'user'))
        self.setup_conflict_listener()
        self.sort_attribute_table_by_sno()

        designation = getattr(self.login_dialog, 'designation', '').lower()
        if designation.endswith('leaders'):
            self.work_allocation_viewer_action.setEnabled(True)
            if designation == 'grand_leaders':
                self.upload_csv_action.setEnabled(True)
            else:
                self.upload_csv_action.setEnabled(False)
        else:
            self.work_allocation_viewer_action.setEnabled(False)
            self.upload_csv_action.setEnabled(False)

    def on_logout(self):
        self.is_logged_in = False
        self.work_allocation_viewer_action.setEnabled(False)
        self.upload_csv_action.setEnabled(False)
        # Refresh QGIS to update UI and layers after logout
        try:
            self.iface.mapCanvas().refresh()
            layer = self.iface.activeLayer()
            if layer:
                layer.triggerRepaint()
        except Exception as e:
            logger.error(f"Error refreshing QGIS after logout: {e}")

    def set_editable_fields_for_role(self, role):
        layer = self.iface.activeLayer()
        if not layer:
            QMessageBox.warning(None, "No Layer", "No active layer found.")
            return

        editable_fields = EDITABLE_FIELDS.get(role, [])
        self._reverting_attr = False

        for idx, field in enumerate(layer.fields()):
            try:
                layer.setEditorWidgetSetup(idx, QgsEditorWidgetSetup('TextEdit', {}))
            except Exception as e:
                logger.error(f"Error setting editor widget for field {field.name()}: {e}")

        def on_attr_changed(fid, idx, value):
            if getattr(self, '_reverting_attr', False):
                return

            try:
                field_name = layer.fields()[idx].name()
                feature = layer.getFeature(fid)

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

                last_updated = feature['last_updated']
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
                logger.exception(f"Error in attribute change handler: {e}")

        try:
            layer.attributeValueChanged.disconnect()
        except Exception:
            pass
        try:
            layer.attributeValueChanged.connect(on_attr_changed)
        except Exception as e:
            print(f"Error connecting attributeValueChanged: {e}")

    def sort_attribute_table_by_sno(self):
        """Sort the attribute table by s_no column for the active layer."""
        layer = self.iface.activeLayer()
        if not layer or layer.type() != QgsMapLayer.VectorLayer:
            return
        try:
            config = layer.attributeTableConfig()
            if 's_no' in [f.name() for f in layer.fields()]:
                config.setSortExpression('s_no')
                config.setSortOrder(0)  # 0 = AscendingOrder, 1 = DescendingOrder
                layer.setAttributeTableConfig(config)
            else:
                logger.error("Field 's_no' not found for sorting.")
        except Exception as e:
            print(f"Error sorting attribute table: {e}")

    def setup_conflict_listener(self):
        """Start the background conflict listener after login."""
        # Example: get DB config from self.login_dialog or settings
        db_config = self.login_dialog.db_config
        db_user = self.login_dialog.db_user
        db_password = self.login_dialog.db_password
        role = getattr(self.login_dialog, 'designation', 'user')
        listen_for_edits(role, db_config, db_user, db_password)

    def show_work_allocation_panel(self):
        """Show the login dialog as the work allocation panel."""
        self.login_dialog.setModal(True)
        self.login_dialog.show()

    def show_custom_attribute_table(self):
        designation = getattr(self.login_dialog, "designation", "").lower()
        if not self.is_logged_in or not designation:
            QMessageBox.warning(None, "No Role", "User role not set. Please login again.")
            return
        if not hasattr(self, "db_handler") or self.db_handler is None:
            QMessageBox.critical(None, "DB Error", "Database handler is not set!")
            return
        # Only allow leaders to access the table
        if not designation.endswith("leaders"):
            QMessageBox.warning(None, "Access Denied", "You do not have permission to access the attribute table.")
            return
        editable_fields = EDITABLE_FIELDS.get(designation, [])
        self.table_frame = CustomAttributeTable(
            db_handler=self.db_handler,
            editable_fields=editable_fields,
            df=getattr(self.login_dialog, "df", None),
            designation=designation,
            parent=self.iface.mainWindow()
        )
        self.table_frame.show()
        print("Rows in table:", self.table_frame.tableWidget.rowCount())
