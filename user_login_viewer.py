from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from .resources import *
from .login_dialog import LoginDialog, EDITABLE_FIELDS
import os.path
from qgis.core import QgsEditorWidgetSetup

import threading
from .conflict_listener import listen_for_edits

from PyQt5.QtCore import QTimer, QObject
from PyQt5.QtWidgets import QMessageBox
from datetime import datetime

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
        self.add_action(
            icon_path,
            text=self.tr(u'Open Work Allocation Panel'),
            callback=self.run,
            parent=self.iface.mainWindow())

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
            QMessageBox.critical(None, "Error", f"Failed to open login dialog:\n{e}")

    def on_login_success(self):
        try:
            self.is_logged_in = True
            self.set_editable_fields_for_role(getattr(self.login_dialog, 'designation', 'user'))
            self.setup_conflict_listener()
            self.sort_attribute_table_by_sno()
        except Exception as e:
            QMessageBox.critical(None, "Login Error", f"An error occurred after login:\n{e}")

    def on_logout(self):
        self.is_logged_in = False

    def set_editable_fields_for_role(self, role):
        layer = self.iface.activeLayer()
        if not layer:
            return

        editable_fields = EDITABLE_FIELDS.get(role, [])
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
        """Sort the attribute table by s_no column for the active layer."""
        layer = self.iface.activeLayer()
        if not layer or layer.type() != layer.VectorLayer:
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