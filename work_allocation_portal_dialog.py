from PyQt5.QtWidgets import (
    QDialog, QTableWidgetItem, QMessageBox, QStyledItemDelegate, QUndoStack, QUndoCommand
)
from PyQt5.QtWidgets import QStyledItemDelegate, QComboBox
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtCore import Qt, QEvent
import os
from PyQt5 import QtWidgets
from PyQt5 import uic
from .work_allocation_portal_viewer import Ui_Dialog
from .conflict_listener import PostgresListener, is_field_editable
import inspect
from PyQt5.QtWidgets import QApplication, QTableWidgetItem
from .db_handler import signal_bus
from qgis.core import QgsProject
from qgis.utils import iface
from qgis.core import QgsProject, QgsRectangle, QgsCoordinateTransform
#from .constants import EMP_ID_TO_NAME_FIELDS
from .constants import (
    EDITABLE_FIELDS,
    INTERSECTION_TYPE_VALUES, TURN_MANEUVER_EXTRACTION_TYPE_VALUES,
    RFDB_PRODUCTION_STATUS_VALUES, RFDB_QC_STATUS_VALUES,
    SILOC_STATUS_VALUES, DELIVERY_STATUS_VALUES, DATE_COLUMNS
)
from .form_features import UndoRedoDelegate, ComboBoxDelegate, DateDelegate


class NumericTableWidgetItem(QTableWidgetItem):
    def __init__(self, value):
        super().__init__(str(value))
        self.value = value
    def __lt__(self, other):
        try:
            return float(self.value) < float(other.value)
        except Exception:
            return str(self.value) < str(other.value)

class DateTableWidgetItem(QTableWidgetItem):
    def __init__(self, value):
        super().__init__(str(value))
        self.value = value
    def __lt__(self, other):
        try:
            from dateutil.parser import parse
            return parse(self.value) < parse(other.value)
        except Exception:
            return str(self.value) < str(other.value)

class CellEditCommand(QUndoCommand):
    def __init__(self, dialog, s_no, col_name, old_value, new_value):
        super().__init__("Edit Cell")
        self.dialog = dialog
        self.s_no = s_no
        self.col_name = col_name
        self.old_value = old_value
        self.new_value = new_value

    def _find_row_col(self):
        s_no_idx = self.dialog.columns.index("s_no")
        col_idx = self.dialog.columns.index(self.col_name)
        for row in range(self.dialog.ui.tableWidget.rowCount()):
            s_no_item = self.dialog.ui.tableWidget.item(row, s_no_idx)
            if s_no_item and s_no_item.text() == self.s_no:
                return row, col_idx
        return None, None

    def undo(self):
        print(f"[UNDO] Cell ({self.s_no}, {self.col_name}) reverting to '{self.old_value}'")
        self.dialog._is_undo_redo = True
        row, col = self._find_row_col()
        if row is not None and col is not None:
            item = self.dialog.ui.tableWidget.item(row, col)
            if item:
                self.dialog.ui.tableWidget.blockSignals(True)
                item.setText("" if self.old_value is None else str(self.old_value))
                self.dialog.ui.tableWidget.blockSignals(False)
                self.dialog.handle_cell_changed(row, col)
        self.dialog._is_undo_redo = False

    def redo(self):
        #print(f"[REDO] Cell ({self.s_no}, {self.col_name}) setting to '{self.new_value}'")
        self.dialog._is_undo_redo = True
        row, col = self._find_row_col()
        if row is not None and col is not None:
            item = self.dialog.ui.tableWidget.item(row, col)
            if item:
                self.dialog.ui.tableWidget.blockSignals(True)
                item.setText("" if self.new_value is None else str(self.new_value))
                self.dialog.ui.tableWidget.blockSignals(False)
                self.dialog.handle_cell_changed(row, col)
        self.dialog._is_undo_redo = False

class GroupEditCommand(QUndoCommand):
    def __init__(self, dialog, edits):
        super().__init__("Group Paste")
        self.dialog = dialog
        self.edits = edits  # List of (row, col, old_value, new_value)

    def _find_row_col(self, s_no, col_name):
        s_no_idx = self.dialog.columns.index("s_no")
        col_idx = self.dialog.columns.index(col_name)
        for row in range(self.dialog.ui.tableWidget.rowCount()):
            s_no_item = self.dialog.ui.tableWidget.item(row, s_no_idx)
            if s_no_item and s_no_item.text() == s_no:
                return row, col_idx
        return None, None

    def undo(self):
        self.dialog._is_undo_redo = True
        for s_no, col_name, old_value, new_value in reversed(self.edits):
            row, col = self._find_row_col(s_no, col_name)
            if row is not None and col is not None:
                item = self.dialog.ui.tableWidget.item(row, col)
                if item:
                    self.dialog.ui.tableWidget.blockSignals(True)
                    item.setText("" if old_value is None else str(old_value))
                    self.dialog.ui.tableWidget.blockSignals(False)
                    self.dialog.handle_cell_changed(row, col)
        self.dialog._is_undo_redo = False

    def redo(self):
        self.dialog._is_undo_redo = True
        for s_no, col_name, old_value, new_value in self.edits:
            row, col = self._find_row_col(s_no, col_name)
            if row is not None and col is not None:
                item = self.dialog.ui.tableWidget.item(row, col)
                if item:
                    self.dialog.ui.tableWidget.blockSignals(True)
                    item.setText("" if new_value is None else str(new_value))
                    self.dialog.ui.tableWidget.blockSignals(False)
                    self.dialog.handle_cell_changed(row, col)
        self.dialog._is_undo_redo = False

class FilterManager:
    """Manages per-column filtering using header ▼ icons (sorting remains enabled)."""

    def __init__(self, tableWidget):
        self.tableWidget = tableWidget
        self.filter_mode_enabled = False
        self._column_filters = {}
        self.original_headers = []
        self._filter_value_pool = {}  

    def create_filter(self):
        """Toggles filter mode by updating header text and activating section clicks."""
        # Save the current selection before toggling the filter
        selected_cells = self.tableWidget.parent().get_selected_cells_by_id()

        col_count = self.tableWidget.columnCount()

        if not self.filter_mode_enabled:
            # Store original header names
            self.original_headers = [
                self.tableWidget.horizontalHeaderItem(i).text()
                if self.tableWidget.horizontalHeaderItem(i) else f"Column {i}"
                for i in range(col_count)
            ]

            # Add ▼ icon to header labels
            for i in range(col_count):
                item = self.tableWidget.horizontalHeaderItem(i)
                if item and "▼" not in item.text():
                    item.setText(f"{item.text()} ▼")

            # Connect header clicks to open filter dialog
            self.tableWidget.horizontalHeader().sectionClicked.connect(self._handle_header_click)
            self.filter_mode_enabled = True

        else:
            # Remove filter mode: restore headers, disconnect, clear filters
            for i, orig in enumerate(self.original_headers):
                item = self.tableWidget.horizontalHeaderItem(i)
                if item:
                    # Remove both ▼ and 🔽 icons from header text
                    base = orig.replace(" ▼", "").replace("🔽", "")
                    item.setText(base)
            try:
                self.tableWidget.horizontalHeader().sectionClicked.disconnect(self._handle_header_click)
            except Exception:
                pass
            self.filter_mode_enabled = False
            self._column_filters.clear()
            self.apply_column_filters()
        self.update_header_icons()

        # Restore the selection after toggling the filter
        self.tableWidget.parent().restore_selection_by_id(selected_cells)

    def _handle_header_click(self, index):
        """Open column filter dialog when ▼ icon header is clicked."""
        if self.filter_mode_enabled:
            self.open_column_filter_dialog(index)

    def open_column_filter_dialog(self, index):
        """Open the custom UI dialog for filtering values in a specific column."""
        if index >= self.tableWidget.columnCount():
            return

        col_name = self.original_headers[index]
        current_filter = self._column_filters.get(col_name, None)

        # Helper for robust sorting
        def try_num(val):
            if val is None or str(val).strip() == "" or str(val).lower() == "none":
                return (0, float('-inf'))
            try:
                return (1, float(val))
            except (ValueError, TypeError):
                return (2, str(val))

        if col_name not in self._filter_value_pool:
            # --- Apply all filters except the one for this column ---
            filtered_rows = self.tableWidget.parent().get_filtered_rows_except(col_name)
            raw_values = [
                self.tableWidget.item(row, index).text()
                for row in filtered_rows
                if self.tableWidget.item(row, index)
            ]
            # Remove duplicates while preserving order
            seen = set()
            values = []
            for v in raw_values:
                if v not in seen:
                    seen.add(v)
                    values.append(v)
            values = sorted(values, key=try_num)
            self._filter_value_pool[col_name] = values
        else:
            values = self._filter_value_pool[col_name]

        # Load custom filter dialog
        ui_path = os.path.join(os.path.dirname(__file__), "custom_attribute_table_filter.ui")
        dialog = QtWidgets.QDialog(self.tableWidget)
        dialog.setModal(True)
        uic.loadUi(ui_path, dialog)
        dialog.setWindowTitle(f"Filter: {col_name}")

        # Remove the old listWidget from the layout if it exists
        layout = dialog.findChild(QtWidgets.QVBoxLayout, "verticalLayout")
        old_widget = dialog.findChild(QtWidgets.QListWidget, "listWidget")
        if old_widget and layout:
            layout.removeWidget(old_widget)
            old_widget.deleteLater()

        # Add your custom CheckableListWidget
        list_widget = self.tableWidget.parent().CheckableListWidget()
        list_widget.setObjectName("listWidget")
        list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        if layout:
            layout.insertWidget(1, list_widget)  # Insert after the search box

        # Populate the list_widget with checkable items
        for val in values:
            item = QtWidgets.QListWidgetItem(val)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if current_filter is not None:
                item.setCheckState(Qt.Checked if val in current_filter else Qt.Unchecked)
            else:
                item.setCheckState(Qt.Checked)
            list_widget.addItem(item)

        # Spacebar toggling is handled by your CheckableListWidget class

        # Hook up buttons
        select_all_btn = dialog.findChild(QtWidgets.QPushButton, "selectAllButton")
        clear_btn = dialog.findChild(QtWidgets.QPushButton, "clearButton")
        if select_all_btn:
            select_all_btn.clicked.connect(lambda: [list_widget.item(i).setCheckState(Qt.Checked) for i in range(list_widget.count())])
        if clear_btn:
            clear_btn.clicked.connect(lambda: [list_widget.item(i).setCheckState(Qt.Unchecked) for i in range(list_widget.count())])

        # Hook up search box
        search_box = dialog.findChild(QtWidgets.QLineEdit, "searchBox")
        if search_box:
            def filter_items(text):
                for i in range(list_widget.count()):
                    item = list_widget.item(i)
                    item.setHidden(text.lower() not in item.text().lower())
            search_box.textChanged.connect(filter_items)

        # Dialog button signals
        button_box = dialog.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
        if button_box:
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            checked_values = {list_widget.item(i).text() for i in range(list_widget.count()) if list_widget.item(i).checkState() == Qt.Checked}
            if checked_values and len(checked_values) < list_widget.count():
                self._column_filters[col_name] = checked_values
            else:
                self._column_filters.pop(col_name, None)
                self._filter_value_pool.pop(col_name, None)  # Remove pool if filter is cleared
            self.apply_column_filters()

    def apply_column_filters(self):
        """Apply the current filters to the table rows."""
        # Save the current selection before filtering
        selected_cells = self.tableWidget.parent().get_selected_cells_by_id()

        headers = [
            self.original_headers[i] if i < len(self.original_headers)
            else self.tableWidget.horizontalHeaderItem(i).text().replace(" ▼", "")
            for i in range(self.tableWidget.columnCount())
        ]

        for row in range(self.tableWidget.rowCount()):
            show_row = True
            for col_name, allowed_values in self._column_filters.items():
                try:
                    col_idx = headers.index(col_name)
                except ValueError:
                    continue
                item = self.tableWidget.item(row, col_idx)
                if item is None or item.text() not in allowed_values:
                    show_row = False
                    break
            self.tableWidget.setRowHidden(row, not show_row)

        if not self._column_filters:
            self._filter_value_pool.clear()
        self.update_header_icons()

        # Restore the selection after filtering
        self.tableWidget.parent().restore_selection_by_id(selected_cells)
            
    def update_header_icons(self):
        """Update header icons: show '▼' for normal, '🔽' for filtered columns, or plain if no filter."""
        for i in range(self.tableWidget.columnCount()):
            col_name = self.original_headers[i]
            item = self.tableWidget.horizontalHeaderItem(i)
            if item:
                base = col_name.replace(" ▼", "").replace("🔽", "")
                if self.filter_mode_enabled:
                    if col_name in self._column_filters:
                        item.setText(f"{base} 🔽")
                    else:
                        item.setText(f"{base} ▼")
                else:
                    # Filter mode is off: show plain header (no icons)
                    item.setText(base)
            

class WorkAllocationPortalViewerDialog(QDialog):

    columns = {
       '"public"."production_inputs"': [
            "geom", "s_no","project","wu_received_date","work_unit_id","length_mi","subcountry","rough_road_type",
            "rfdb_production_team_leader_emp_id","rfdb_production_team_leader_emp_name","rfdb_production_emp_id","rfdb_production_done_by","rfdb_allotted_date","rfdb_completed_date","rfdb_production_time_taken","rfdb_production_status",
            "rfdb_production_actual_road_type","rfdb_production_remarks","siloc_production_team_leader_emp_id","siloc_production_team_leader_emp_name","siloc_production_emp_id","siloc_production_done_by","siloc_production_allotted_date","siloc_production_completed_date","siloc_production_time_taken","siloc_production_sign_count","siloc_production_autodetection_status","siloc_production_status","siloc_production_remarks",
            "siloc_qc_team_leader_emp_id","siloc_qc_team_leader_emp_name","siloc_qc_emp_id","siloc_qc_done_by","siloc_qc_allotted_date","siloc_qc_completed_date","siloc_qc_time_taken","siloc_qc_sign_count","siloc_qc_status","siloc_qc_remarks",
            "rfdb_path_association_production_team_leader_emp_id","rfdb_path_association_production_team_leader_emp_name","rfdb_path_association_production_emp_id","rfdb_path_association_production_done_by","rfdb_path_association_production_allotted_date","rfdb_path_association_production_completed_date","rfdb_path_association_production_time_taken","rfdb_path_association_production_status","rfdb_path_association_production_remarks",
            "rfdb_qc_team_leader_emp_id","rfdb_qc_team_leader_emp_name","rfdb_qc_emp_id","rfdb_qc_done_by","rfdb_qc_allotted_date","rfdb_qc_completed_date","rfdb_qc_time_taken","rfdb_qc_status","rfdb_qc_remarks",
            "rfdb_attri_qc_team_leader_emp_id","rfdb_attri_qc_team_leader_emp_name","rfdb_attri_qc_emp_id","rfdb_attri_qc_done_by","rfdb_attri_qc_allotted_date","rfdb_attri_qc_completed_date","rfdb_attri_qc_time_taken","rfdb_attri_qc_status","rfdb_attri_qc_remarks",
            "rfdb_roadtype_qc_emp_id","rfdb_roadtype_qc_done_by","rfdb_roadtype_qc_allotted_date","rfdb_roadtype_qc_completed_date","rfdb_roadtype_qc_time_taken","rfdb_roadtype_qc_status","rfdb_roadtype_qc_remarks",
            "rfdb_qa_emp_id","rfdb_qa_done_by","rfdb_qa_allotted_date","rfdb_qa_completed_date","rfdb_qa_time_taken","rfdb_qa_status","rfdb_qa_remarks",
            "rfdb_path_association_qc_team_leader_emp_id","rfdb_path_association_qc_team_leader_emp_name","rfdb_path_association_qc_emp_id","rfdb_path_association_qc_done_by","rfdb_path_association_qc_allotted_date","rfdb_path_association_qc_completed_date","rfdb_path_association_qc_time_taken","rfdb_path_association_qc_status","rfdb_path_association_qc_remarks",
            "rfdb_qc_actual_road_type","delivery_status","delivered_date"
       ],
       '"public"."tm_production_inputs"': [        
            "geom", "s_no", "project", "wu_received_date", "wu_intersection_node_id", "associated_work_unit_ids",
            "subcountry", "priority", "intersection_type", "extracted_work_unit_id", "turn_maneuver_extraction_type",
            "auto_turn_maneuver_path_count", "manual_turn_maneuver_path_count", "production_total_tm_path_count",
            "production_intersection_type", "rfdb_production_team_leader_emp_id", "rfdb_production_team_leader_emp_name",
            "rfdb_production_emp_id", "rfdb_production_done_by", "rfdb_allotted_date",
            "rfdb_completed_date", "rfdb_production_extraction_time_taken", "rfdb_production_correction_time_taken",
            "rfdb_production_time_taken", "rfdb_production_status", "rfdb_ssd_jira_id", "rfdb_production_hold_reason",
            "rfdb_production_remarks", "rfdb_qc_team_leader_emp_id", "rfdb_qc_team_leader_emp_name", "rfdb_qc_emp_id",
            "rfdb_qc_done_by", "rfdb_qc_allotted_date", "rfdb_qc_completed_date", "rfdb_qc_first_review_time_taken",
            "rfdb_qc_second_review_time_taken", "rfdb_qc_time_taken", "rfdb_qc_total_tm_path_count",
            "rfdb_billing_intersection_type", "rfdb_qc_status", "rfdb_qc_total_errors_marked",
            "rfdb_qc_ssd_jira_id", "rfdb_qc_hold_reason", "rfdb_qc_remarks", "siloc_team_leader_emp_id",
            "siloc_team_leader_emp_name", "siloc_emp_id", "siloc_done_by", "siloc_allotted_date",
            "siloc_completed_date", "siloc_time_taken", "siloc_sign_count", "siloc_status", "siloc_remarks",
            "siloc_ssd_jira_id", "siloc_hold_reason", "delivery_plugin_version_used",
            "delivery_extraction_guide_used", "delivery_status", "delivery_date"
       ]
    }

    DROPDOWN_COLUMNS = {
        "intersection_type": INTERSECTION_TYPE_VALUES,
        "turn_maneuver_extraction_type": TURN_MANEUVER_EXTRACTION_TYPE_VALUES,
        "rfdb_production_status": RFDB_PRODUCTION_STATUS_VALUES,
        "rfdb_qc_status": RFDB_QC_STATUS_VALUES,
        "siloc_status": SILOC_STATUS_VALUES,
        "delivery_status": DELIVERY_STATUS_VALUES,
    }

    def __init__(self, db_handler, user_role, table_name, subcountry=None, emp_id=None, qgis_layer=None, parent=None):
        super().__init__(parent)
        self.db_handler = db_handler
        self.user_role = user_role
        self.table_name = table_name
        self.subcountry = subcountry
        self.emp_id = emp_id  # <-- set emp_id!
        self.qgis_layer = qgis_layer
        self.columns = self.columns.get(self.table_name, [])
        self.editable_fields = EDITABLE_FIELDS.get(self.table_name, {}).get(self.user_role, [])

        # --- Set project for row-wise restriction logic ---
        if self.table_name == '"public"."tm_production_inputs"':
            self.project = "turn_maneuver_project"
        elif self.table_name == '"public"."production_inputs"':
            self.project = "rfdb_project"
        else:
            self.project = None

        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        #self.ui.tableWidget.setEditTriggers(QtWidgets.QAbstractItemView.EditKeyPressed | QtWidgets.QAbstractItemView.SelectedClicked)

        self.setWindowTitle("Work Allocation Portal Viewer/Editor")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)
        signal_bus.logout_signal.connect(self.cleanup_on_logout)

        # Set icons
        icon_dir = os.path.join(os.path.dirname(__file__), "icon")
        self.ui.Save.setIcon(QIcon(os.path.join(icon_dir, "diskette.png")))
        self.ui.Refresh.setIcon(QIcon(os.path.join(icon_dir, "loading-arrow.png")))
        self.ui.Organize_columns.setIcon(QIcon(os.path.join(icon_dir, "task.png")))
        self.ui.Zoom_to_feature.setIcon(QIcon(os.path.join(icon_dir, "search.png")))
        self.ui.Create_filter.setIcon(QIcon(os.path.join(icon_dir, "filter.png")))

        # Set tooltips
        self.ui.Save.setToolTip("Save")
        self.ui.Refresh.setToolTip("Refresh")
        self.ui.Organize_columns.setToolTip("Organize Columns")
        self.ui.Zoom_to_feature.setToolTip("Zoom to Feature")
        self.ui.Create_filter.setToolTip("Filter")

        self.undo_stack = QUndoStack(self)
        self._cell_prev_values = {}
        self._is_undo_redo = False
        self._is_group_paste = False
        self.delegate = UndoRedoDelegate(self.ui.tableWidget, self._cell_prev_values)
        self.ui.tableWidget.setItemDelegate(self.delegate)

        self.ui.tableWidget.installEventFilter(self)
        self.ui.tableWidget.viewport().installEventFilter(self)

        self.ui.tableWidget.setDragDropMode(self.ui.tableWidget.NoDragDrop)
        self.ui.tableWidget.setDragEnabled(False)
        self.ui.tableWidget.setDropIndicatorShown(False)
        self.ui.tableWidget.setDefaultDropAction(Qt.IgnoreAction)

        
        self.quoted_table = self.table_name
        try:
            self.schema, self.table = self.table_name.replace('"', '').split('.')
        except ValueError:
            QMessageBox.critical(self, "Error", f"Invalid table format: {self.table_name}")
            self.schema, self.table = "public", "production_inputs"

        self.quoted_table = self.table_name  # Already quoted form is used for all SQL
        self.col_types = {}  # Will be filled once
        self._suppress_cell_changed = False
        self._suppress_invalid_empid_popup = False
        self.load_column_types()

        self.refresh_table()
        self.ui.Refresh.clicked.connect(self.refresh_table)
        self.ui.tableWidget.cellChanged.connect(self.handle_cell_changed)
        self.ui.Organize_columns.clicked.connect(self.organize_columns)
        self.ui.Zoom_to_feature.clicked.connect(self.zoom_to_selected_row_on_map)
        self.ui.Create_filter.clicked.connect(self.create_filter)
        self._suppress_invalid_empid_popup = False

        self.filter_manager = FilterManager(self.ui.tableWidget)

        # PostgreSQL listener for real-time updates
        dsn = self.db_handler.get_dsn()
        self.pg_listener = PostgresListener(dsn, "production_inputs_update")
        self.pg_listener.notified.connect(self.handle_db_notify)

        self.combo_delegates = {}
        for col_idx, field_name in enumerate(self.columns):
            if field_name in self.DROPDOWN_COLUMNS:
                delegate = ComboBoxDelegate(self.DROPDOWN_COLUMNS[field_name], self.ui.tableWidget)
                self.ui.tableWidget.setItemDelegateForColumn(col_idx, delegate)
                self.combo_delegates[field_name] = delegate

        # Date columns (add this block)
        date_delegate = DateDelegate(self.ui.tableWidget)
        for col_idx, field_name in enumerate(self.columns):
            if field_name in DATE_COLUMNS:
                self.ui.tableWidget.setItemDelegateForColumn(col_idx, date_delegate)

    def create_filter(self):
        """Toggles the filter UI."""
        self.filter_manager.create_filter()

    def get_selected_cells_by_id(self):
        """Return a list of (s_no, col_name) for all selected cells."""
        selected = []
        s_no_idx = self.columns.index("s_no")
        for item in self.ui.tableWidget.selectedItems():
            row = item.row()
            col = item.column()
            s_no_item = self.ui.tableWidget.item(row, s_no_idx)
            if s_no_item:
                s_no = s_no_item.text()
                col_name = self.columns[col]
                selected.append((s_no, col_name))
        #print(f"[DEBUG] Selected cells: {selected}")  # Debug line
        return selected

    def get_selected_cell_values(self):
        """Return a list of (s_no, col_name, value) for all selected cells."""
        selected = []
        s_no_idx = self.columns.index("s_no")
        for item in self.ui.tableWidget.selectedItems():
            row = item.row()
            col = item.column()
            s_no_item = self.ui.tableWidget.item(row, s_no_idx)
            if s_no_item:
                s_no = s_no_item.text()
                col_name = self.columns[col]
                value = item.text() if item else ""
                selected.append((s_no, col_name, value))
        #print(f"[DEBUG] Selected cell values: {selected}")  # Debug line
        return selected

    def get_filtered_rows_except(self, exclude_col_name):
        headers = self.columns  # Use original column names
        filtered_rows = []
        for row in range(self.ui.tableWidget.rowCount()):
            match = True
            for col_name, allowed_values in self.filter_manager._column_filters.items():
                if col_name == exclude_col_name:
                    continue
                try:
                    col_idx = headers.index(col_name)
                except ValueError:
                    continue  # Skip if column not found
                item = self.ui.tableWidget.item(row, col_idx)
                if item is None or item.text() not in allowed_values:
                    match = False
                    break
            if match:
                filtered_rows.append(row)
        return filtered_rows

    def refresh_table(self):
        if not self.columns:
            QMessageBox.critical(self, "Error", "No columns defined for the selected table.")
            return
        print(f"[DEBUG] Fetching data from table: {self.quoted_table}")  # <-- Add this line
        # stack = inspect.stack()  # Get the name of the calling function      #[DEBUG]
        # print("[DEBUG] Refresh Triggered by stack:")                         #[DEBUG]
        # for frame in stack[1:4]:  # Show up to 3 levels above                #[DEBUG]
        #     print(f"  called by: {frame.function} (line {frame.lineno})")    #[DEBUG]
        self.ui.tableWidget.blockSignals(True)
        self.ui.tableWidget.setSortingEnabled(False)
        self.ui.tableWidget.horizontalHeader().setSectionsClickable(True)

        cur = self.db_handler.conn.cursor()

        # Fetch column types (unchanged)
        format_str = ','.join(['%s'] * len(self.columns))
        query = f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            AND column_name IN ({format_str})
            ORDER BY ordinal_position
        """
        params = [self.schema, self.table] + self.columns
        cur.execute(query, params)
        column_info = cur.fetchall()
        self.col_types = {name: dtype for name, dtype in column_info}

        # Fetch actual data, filtered by subcountry if set
        if self.subcountry and self.subcountry != "All subcountry":
            sql = f"SELECT {', '.join(self.columns)} FROM {self.quoted_table} WHERE subcountry = %s ORDER BY s_no"
            cur.execute(sql, (self.subcountry,))
        else:
            sql = f"SELECT {', '.join(self.columns)} FROM {self.quoted_table} ORDER BY s_no"
            cur.execute(sql)
        data = cur.fetchall()
        cur.close()

        columns = self.columns

        self.ui.tableWidget.setColumnCount(len(columns))
        self.ui.tableWidget.setHorizontalHeaderLabels(columns)
        self.ui.tableWidget.setRowCount(0)
        self.ui.tableWidget.setRowCount(len(data))

        for row_idx, row in enumerate(data):
            # Build a dict of column_name: value for this row
            row_data = {self.columns[c]: row[c] for c in range(len(self.columns))}
            for col_idx, value in enumerate(row):
                field_name = columns[col_idx]
                dtype = self.col_types.get(field_name, "text")

                if field_name == "s_no":
                    item = NumericTableWidgetItem(value)
                elif dtype in ("integer", "numeric", "double precision"):
                    item = NumericTableWidgetItem(value)
                elif dtype in ("date", "timestamp without time zone"):
                    item = DateTableWidgetItem(value)
                else:
                    item = QTableWidgetItem("" if value is None else str(value))

                # Row/column-wise editability check
                if not is_field_editable(
                        self.user_role,
                        field_name,
                        row_data,
                        getattr(self, "emp_id", None),
                        project=getattr(self, "project", None),
                        table_name=self.table_name  # <-- pass the table name!
                    ):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setBackground(QColor(180, 180, 180))  # Gray out

                self.ui.tableWidget.setItem(row_idx, col_idx, item)

        for col_name in ("geom", "last_updated"):
            if col_name in self.columns:
                idx = self.columns.index(col_name)
                self.ui.tableWidget.setColumnHidden(idx, True)

        self.ui.tableWidget.setVerticalHeaderLabels([str(i + 1) for i in range(len(data))])
        self.ui.tableWidget.blockSignals(False)
        self.ui.tableWidget.setSortingEnabled(False)
        self.ui.tableWidget.horizontalHeader().setSectionsClickable(True)

    def handle_db_notify(self, payload):
        """
        Update only the affected rows in the table when a NOTIFY is received.
        The payload is expected to be a comma‑separated string of primary keys (s_no).
        For each s_no, the entire row (all columns in self.columns) is fetched from the DB
        and the corresponding table row is updated.
        """
        # Split payload assuming comma-separated s_no values.
        updated_ids = [id.strip() for id in str(payload).split(",") if id.strip()]
        if not updated_ids:
            return

        for updated_s_no in updated_ids:
            try:
                cur = self.db_handler.conn.cursor()
                cur.execute(
                    f"SELECT {', '.join(self.columns)} FROM {self.quoted_table} WHERE s_no = %s",
                    (updated_s_no,)
                )
                row_data = cur.fetchone()
                cur.close()
                if not row_data:
                    continue  # No record found for this s_no
            except Exception as e:
                print(f"[DEBUG] Error fetching update for s_no {updated_s_no}: {e}")
                continue

            # Find the row(s) in the table with this s_no.
            s_no_idx = self.columns.index("s_no")
            target_rows = []
            for row in range(self.ui.tableWidget.rowCount()):
                item = self.ui.tableWidget.item(row, s_no_idx)
                if item and item.text() == updated_s_no:
                    target_rows.append(row)

            # Update each matching row with new data.
            for target_row in target_rows:
                self.ui.tableWidget.blockSignals(True)
                for col_idx, new_value in enumerate(row_data):
                    item = self.ui.tableWidget.item(target_row, col_idx)
                    if not item:
                        from PyQt5.QtWidgets import QTableWidgetItem
                        item = QTableWidgetItem("")
                        self.ui.tableWidget.setItem(target_row, col_idx, item)
                    item.setText("" if new_value is None else str(new_value))
                self.ui.tableWidget.blockSignals(False)

    def handle_cell_changed(self, row, col):
        item = self.ui.tableWidget.item(row, col)
        if item is None:
            print(f"[DEBUG] handle_cell_changed: No item at ({row}, {col})")
            return

        widget = self.ui.tableWidget.cellWidget(row, col)
        if isinstance(widget, QComboBox):
            new_value = widget.currentText()
        else:
            new_value = item.text()

        field_name = self.columns[col]
        col_type = self.col_types.get(field_name, "").lower()

        if (
            new_value is None
            or str(new_value).strip() == ""
            or str(new_value).strip().lower() == "none"
        ):
            new_value = None

        prev_value = self._cell_prev_values.get((row, col), "")
        print(f"[DEBUG] handle_cell_changed: ({row}, {col}) field='{field_name}' prev='{prev_value}' new='{new_value}'")

        if prev_value == new_value:
            print(f"[DEBUG] handle_cell_changed: No change detected for ({row}, {col})")
            return

        if not getattr(self, "_is_undo_redo", False) and not getattr(self, "_is_group_paste", False):
            s_no_item = self.ui.tableWidget.item(row, self.columns.index("s_no"))
            if s_no_item:
                s_no = s_no_item.text()
                col_name = self.columns[col]
                self.undo_stack.push(CellEditCommand(self, s_no, col_name, prev_value, new_value))

        # --- Normal field update ---
        s_no_item = self.ui.tableWidget.item(row, self.columns.index("s_no"))
        if not s_no_item or not s_no_item.text():
            print(f"[DEBUG] handle_cell_changed: No s_no found for row {row}")
            return

        s_no = s_no_item.text()
        try:
            print(f"[DEBUG] handle_cell_changed: Updating DB: field={field_name}, value={new_value}, s_no={s_no}")
            cur = self.db_handler.conn.cursor()
            cur.execute(
                f"UPDATE {self.quoted_table} SET {field_name} = %s WHERE s_no = %s",
                (new_value, s_no)
            )
            self.db_handler.conn.commit()
            cur.execute(f"NOTIFY production_inputs_update, '{s_no}';")
            cur.close()
            print(f"[DEBUG] handle_cell_changed: DB update successful for s_no={s_no}, field={field_name}")
        except Exception as e:
            print(f"[DEBUG] handle_cell_changed: DB update failed: {e}")
            QMessageBox.critical(self, "Update Error", f"Failed to update {field_name}: {e}")
            self.refresh_table()

        self._cell_prev_values[(row, col)] = new_value
   
    def copy_cell_values(self):
        """Copy only the values of selected cells to the clipboard, and store metadata mapping in memory."""
        selected_cells = self.get_selected_cell_values()  # [(s_no, col_name, value), ...]
        if not selected_cells:
            #print("[DEBUG] No cells selected for copying.")
            return
        values_only = [value for _, _, value in selected_cells]
        QApplication.clipboard().setText("\n".join(values_only))
        # Store the selection mapping for structured paste
        self._structured_clipboard = [(s_no, col_name) for s_no, col_name, _ in selected_cells]
        # print(f"[DEBUG] Copied values: {values_only}")
        # print(f"[DEBUG] Structured mapping: {self._structured_clipboard}")

    def paste_cell_values(self):
        """Paste clipboard values into the currently selected cells using the current selection mapping."""
        text = QApplication.clipboard().text()
        if not text:
            #print("[DEBUG] Clipboard is empty.")
            return

        rows = [line.split('\t') for line in text.splitlines()]
        selected_cells = self.get_selected_cells_by_id()  # [(s_no, col_name), ...]
        if not selected_cells:
            #print("[DEBUG] No cells selected for pasting.")
            return

        group_edits = []
        self._is_group_paste = True
        s_no_idx = self.columns.index("s_no")

        num_clip_rows = len(rows)
        num_clip_cols = max(len(r) for r in rows) if rows else 1

        for i, (s_no, col_name) in enumerate(selected_cells):
            row_in_clip = i // num_clip_cols % num_clip_rows
            col_in_clip = i % num_clip_cols
            new_value = rows[row_in_clip][col_in_clip % len(rows[row_in_clip])]
            col_idx = self.columns.index(col_name)

            # --- Dropdown value validation ---
            if col_name in self.DROPDOWN_COLUMNS:
                allowed = self.DROPDOWN_COLUMNS[col_name] + [""]
                if new_value not in allowed:
                    continue  # Skip invalid value
            # ---------------------------------

            for row in range(self.ui.tableWidget.rowCount()):
                s_no_item = self.ui.tableWidget.item(row, s_no_idx)
                if s_no_item and s_no_item.text() == s_no:
                    # Only paste if cell is editable
                    if not self.is_cell_editable(row, col_idx):
                        continue  # Skip non-editable cells
                    item = self.ui.tableWidget.item(row, col_idx)
                    if item is None:
                        item = QTableWidgetItem("")
                        self.ui.tableWidget.setItem(row, col_idx, item)
                    old_value = item.text()
                    item.setText(new_value)
                    group_edits.append((s_no, col_name, old_value, new_value))
                    self.handle_cell_changed(row, col_idx)
                    break

        self._is_group_paste = False

        if group_edits:
            #print(f"[DEBUG] Pasted changes: {group_edits}")
            self.undo_stack.push(GroupEditCommand(self, group_edits))

    def undo(self):
        print("[UNDO] Triggered")
        self.undo_stack.undo()

    def redo(self):
        print("[REDO] Triggered")
        self.undo_stack.redo()

    def eventFilter(self, obj, event):
        if obj == self.ui.tableWidget and event.type() == QEvent.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            if key == Qt.Key_C and modifiers & Qt.ControlModifier:
                # Use copy_cell_values for basic copying
                self.copy_cell_values()
                return True
            elif key == Qt.Key_V and modifiers & Qt.ControlModifier:
                # Use paste_cell_values for basic pasting
                self.paste_cell_values()
                return True
            elif key == Qt.Key_Z and modifiers & Qt.ControlModifier:
                self.undo()
                return True
            elif key == Qt.Key_Y and modifiers & Qt.ControlModifier:
                self.redo()
                return True
            elif key in (Qt.Key_Delete, Qt.Key_Backspace):
                # Collect all edits for group undo/redo
                group_edits = []
                for item in self.ui.tableWidget.selectedItems():
                    row, col = item.row(), item.column()
                    if self.is_cell_editable(row, col):
                        prev_value = item.text()
                        # Always process, even if prev_value is "" or "None"
                        item.setText("")
                        self.handle_cell_changed(row, col)  # Update DB immediately
                        s_no_item = self.ui.tableWidget.item(row, self.columns.index("s_no"))
                        if s_no_item:
                            s_no = s_no_item.text()
                            col_name = self.columns[col]
                            group_edits.append((s_no, col_name, prev_value, ""))
                            
                if group_edits:
                    self.undo_stack.push(GroupEditCommand(self, group_edits))
                return True
        return super().eventFilter(obj, event)

    def sort_by_sno(self):
        if "s_no" in self.columns:
            s_no_idx = self.columns.index("s_no")
            self.ui.tableWidget.sortItems(s_no_idx, Qt.AscendingOrder)
    
    def cleanup_on_logout(self):
        if hasattr(self, "pg_listener"):
            try:
                self.pg_listener.close()
            except Exception as e:
                print(f"Failed to close pg_listener: {e}")
    
    def load_column_types(self):
        if not self.columns:
            QMessageBox.critical(self, "Error", "No columns defined for the selected table.")
            return

        cur = self.db_handler.conn.cursor()
        format_str = ','.join(['%s'] * len(self.columns))

        query = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            AND column_name IN ({})
            ORDER BY ordinal_position
        """.format(format_str)

        cur.execute(query, [self.schema, self.table] + self.columns)
        self.col_types = {name: dtype for name, dtype in cur.fetchall()}
        cur.close()

    def is_cell_editable(self, row, col):
        field_name = self.columns[col]
        # Build row_data as a dict of column_name: value for this row
        row_data = {self.columns[c]: self.ui.tableWidget.item(row, c).text() for c in range(self.ui.tableWidget.columnCount())}
        # Pass project name if available (set self.project in __init__ if needed)
        return is_field_editable(
            self.user_role,
            field_name,
            row_data,
            getattr(self, "emp_id", None),
            project=getattr(self, "project", None),
            table_name=self.table_name  # <-- pass the table name!
        )


    class CheckableListWidget(QtWidgets.QListWidget):
        def keyPressEvent(self, event):
            if event.key() == Qt.Key_Space:
                selected = self.selectedItems()
                if selected:
                    focused = self.currentItem()
                    if focused is not None:
                        new_state = Qt.Unchecked if focused.checkState() == Qt.Checked else Qt.Checked
                        for item in selected:
                            item.setCheckState(new_state)
                return
            super().keyPressEvent(event)

    def organize_columns(self):
        """Display a dialog to let users reorder and show/hide columns."""
        # Show all columns, not just visible ones
        all_cols = [
            self.ui.tableWidget.horizontalHeaderItem(i).text().replace(" ▼", "")
            for i in range(self.ui.tableWidget.columnCount())
        ]

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Organize Columns")
        dialog.resize(400, 700)
        layout = QtWidgets.QVBoxLayout(dialog)

        search = QtWidgets.QLineEdit()
        search.setPlaceholderText("Search columns...")
        layout.addWidget(search)
        btn_row = QtWidgets.QHBoxLayout()
        select_all_btn = QtWidgets.QPushButton("Select All")
        clear_btn = QtWidgets.QPushButton("Clear")
        btn_row.addWidget(select_all_btn)
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

        list_widget = self.CheckableListWidget()
        list_widget.setDragDropMode(QtWidgets.QAbstractItemView.NoDragDrop)
        list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        layout.addWidget(list_widget)

        info_label = QtWidgets.QLabel("Tip: Select multiple columns with Shift/Ctrl, then press Space to check/uncheck all selected.")
        layout.insertWidget(1, info_label)

        def populate_list():
            list_widget.clear()
            search_text = search.text().lower()
            for i, col in enumerate(all_cols):
                if search_text in col.lower():
                    item = QtWidgets.QListWidgetItem(col)
                    item.setFlags(
                        item.flags()
                        | Qt.ItemIsUserCheckable
                        | Qt.ItemIsEnabled
                        | Qt.ItemIsDragEnabled
                        | Qt.ItemIsSelectable
                    )
                    # Check if column is visible
                    if not self.ui.tableWidget.isColumnHidden(i):
                        item.setCheckState(Qt.Checked)
                    else:
                        item.setCheckState(Qt.Unchecked)
                    list_widget.addItem(item)

        populate_list()
        search.textChanged.connect(populate_list)

        select_all_btn.clicked.connect(lambda: [list_widget.item(i).setCheckState(Qt.Checked) for i in range(list_widget.count())])
        clear_btn.clicked.connect(lambda: [list_widget.item(i).setCheckState(Qt.Unchecked) for i in range(list_widget.count())])

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(btn_box)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)

        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return

        # Apply visibility and order
        visibility = {}
        new_order = []
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            col_name = item.text()
            new_order.append(col_name)
            visibility[col_name] = item.checkState() == Qt.Checked

        # Set visibility for all columns
        for i, col in enumerate(all_cols):
            self.ui.tableWidget.setColumnHidden(i, not visibility.get(col, False))

        # Reorder columns
        header = self.ui.tableWidget.horizontalHeader()
        for target_idx, col_name in enumerate(new_order):
            current_idx = header.visualIndex(all_cols.index(col_name))
            header.moveSection(current_idx, target_idx)

        def on_item_changed(item):
            if not list_widget.hasFocus():
                return  # avoid recursion when programmatically changing check state
            state = item.checkState()
            for selected_item in list_widget.selectedItems():
                if selected_item is not item:
                    selected_item.setCheckState(state)

        list_widget.itemChanged.connect(on_item_changed)

    def zoom_to_selected_row_on_map(self):
        """Zoom QGIS map canvas to the geometry of the selected row in the table."""
        # Get the selected row
        selected_items = self.ui.tableWidget.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Zoom", "Please select a row to zoom to.")
            return

        # Find the s_no of the selected row (assuming s_no is unique)
        s_no_idx = self.columns.index("s_no")
        row = selected_items[0].row()
        s_no_item = self.ui.tableWidget.item(row, s_no_idx)
        if not s_no_item:
            QMessageBox.warning(self, "Zoom", "Could not determine the selected row's s_no.")
            return
        s_no = s_no_item.text()
        print(f"[DEBUG] Zoom requested for s_no: {s_no}")

        # Use the stored QGIS layer reference
        layer = self.qgis_layer
        if not layer:
            QMessageBox.warning(self, "Zoom", "Editable layer not found in QGIS.")
            return

        print(f"[DEBUG] Using layer: {layer.name()}")

        # Find the feature by s_no
        expr = f'"s_no" = {s_no}'
        features = layer.getFeatures(expr)
        feature = next(features, None)
        if not feature:
            QMessageBox.warning(self, "Zoom", f"No feature found in layer for s_no={s_no}.")
            return
        if not feature.hasGeometry():
            QMessageBox.warning(self, "Zoom", "Feature geometry not found for the selected row.")
            return
        
        geom = feature.geometry()
        bbox = geom.boundingBox()
        # Transform bbox to map CRS if needed
        layer_crs = layer.crs()
        map_crs = QgsProject.instance().crs()
        if layer_crs != map_crs:
            transform = QgsCoordinateTransform(layer_crs, map_crs, QgsProject.instance())
            bbox = transform.transformBoundingBox(bbox)
        # If geometry is a point, expand the bbox a bit
        if geom.type() == 0:  # 0 = Point
            buffer = 0.0005  # Adjust as needed for your CRS
            bbox = QgsRectangle(
                bbox.xMinimum() - buffer, bbox.yMinimum() - buffer,
                bbox.xMaximum() + buffer, bbox.yMaximum() + buffer
            )

        iface.mapCanvas().setExtent(bbox)
        iface.mapCanvas().refresh()

        # Select the feature in the layer
        layer.removeSelection()
        layer.selectByIds([feature.id()])

        print(f"[DEBUG] Feature found, geometry: {feature.geometry().asWkt()[:100]}...")

        iface.mapCanvas().setExtent(feature.geometry().boundingBox())
        iface.mapCanvas().refresh()

    def restore_selection_by_id(self, selected_cells):
        """Restore selection given a list of (s_no, col_name)."""
        self.ui.tableWidget.clearSelection()
        s_no_idx = self.columns.index("s_no")
        for row in range(self.ui.tableWidget.rowCount()):
            s_no_item = self.ui.tableWidget.item(row, s_no_idx)
            if not s_no_item:
                continue
            s_no = s_no_item.text()
            for (sel_s_no, sel_col_name) in selected_cells:
                if s_no == sel_s_no and sel_col_name in self.columns:
                    col = self.columns.index(sel_col_name)
                    item = self.ui.tableWidget.item(row, col)
                    if item:
                        item.setSelected(True)

    def filter_to_snos(self, s_no_list):
        """Show only rows with s_no in s_no_list. If list is empty, show nothing."""
        if not hasattr(self, 'columns') or not hasattr(self.ui, 'tableWidget'):
            return
        if "s_no" not in self.columns:
            return
        s_no_set = set(map(str, s_no_list))
        s_no_idx = self.columns.index("s_no")
        for row in range(self.ui.tableWidget.rowCount()):
            s_no_item = self.ui.tableWidget.item(row, s_no_idx)
            if not s_no_item or s_no_item.text() not in s_no_set:
                self.ui.tableWidget.setRowHidden(row, True)
            else:
                self.ui.tableWidget.setRowHidden(row, False)
        # If no selection, hide all rows
        if not s_no_set:
            for row in range(self.ui.tableWidget.rowCount()):
                self.ui.tableWidget.setRowHidden(row, True)


