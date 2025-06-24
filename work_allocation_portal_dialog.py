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
from PyQt5.QtWidgets import QApplication
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
from .form_features import UndoRedoDelegate, ComboBoxDelegate, DateDelegate, CellEditCommand, GroupEditCommand
from .work_allocation_table_model import WorkAllocationTableModel  
from PyQt5.QtWidgets import QTableView
from PyQt5.QtCore import QSortFilterProxyModel, QItemSelectionModel
from .column_filter_proxy_model import ColumnFilterProxyModel



# class NumericTableWidgetItem(QTableWidgetItem):
#     def __init__(self, value):
#         super().__init__(str(value))
#         self.value = value

#     def __lt__(self, other):
#         try:
#             return float(self.value) < float(other.value)
#         except Exception:
#             return str(self.value) < str(other.value)

# class DateTableWidgetItem(QTableWidgetItem):
#     def __init__(self, value):
#         super().__init__(str(value))
#         self.value = value
#     def __lt__(self, other):
#         try:
#             from dateutil.parser import parse
#             return parse(self.value) < parse(other.value)
#         except Exception:
#             return str(self.value) < str(other.value)


class FilterManager:
    """Manages per-column filtering using header ▼ icons (sorting remains enabled)."""

    def __init__(self, tableView, model):
        self.tableView = tableView
        self.model = model
        self.filter_mode_enabled = False
        self._column_filters = {}
        self.original_headers = list(model.header_labels)
        self._filter_value_pool = {}

    def create_filter(self):
        selected_cells = self.tableView.parent().get_selected_cells_by_id()

        if not self.filter_mode_enabled:
            # Add ▼ to headers
            self.original_headers = list(self.model.header_labels)
            self.model.set_header_labels([f"{h} ▼" for h in self.original_headers])
            self.tableView.horizontalHeader().sectionClicked.connect(self._handle_header_click)
            self.filter_mode_enabled = True
        else:
            # Reset header labels and filters
            self.model.set_header_labels(self.original_headers)
            try:
                self.tableView.horizontalHeader().sectionClicked.disconnect(self._handle_header_click)
            except Exception:
                pass
            self.filter_mode_enabled = False
            self._column_filters.clear()
            self.apply_column_filters()
        self.update_header_icons()
        self.tableView.clearSelection()

    def _handle_header_click(self, index):
        if self.filter_mode_enabled:
            self.tableView.clearSelection()  # <-- Add this line
            self.open_column_filter_dialog(index)

    def open_column_filter_dialog(self, index):
        if index >= len(self.model.header_labels):
            return

        col_name = self.original_headers[index]
        current_filter = self._column_filters.get(col_name, None)

        def try_num(val):
            if val is None or str(val).strip() == "" or str(val).lower() == "none":
                return (0, float('-inf'))
            try:
                return (1, float(val))
            except (ValueError, TypeError):
                return (2, str(val))

        if col_name not in self._filter_value_pool:
            filtered_rows = self.tableView.parent().get_filtered_rows_except(col_name)
            raw_values = [
                str(self.model.index(row, index).data())
                for row in filtered_rows
            ]
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

        ui_path = os.path.join(os.path.dirname(__file__), "custom_attribute_table_filter.ui")
        dialog = QtWidgets.QDialog(self.tableView)
        dialog.setModal(True)
        uic.loadUi(ui_path, dialog)
        dialog.setWindowTitle(f"Filter: {col_name}")

        layout = dialog.findChild(QtWidgets.QVBoxLayout, "verticalLayout")
        old_widget = dialog.findChild(QtWidgets.QListWidget, "listWidget")
        if old_widget and layout:
            layout.removeWidget(old_widget)
            old_widget.deleteLater()

        list_widget = self.tableView.parent().CheckableListWidget()
        list_widget.setObjectName("listWidget")
        list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        if layout:
            layout.insertWidget(1, list_widget)

        for val in values:
            item = QtWidgets.QListWidgetItem(val)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if current_filter is not None:
                item.setCheckState(Qt.Checked if val in current_filter else Qt.Unchecked)
            else:
                item.setCheckState(Qt.Checked)
            list_widget.addItem(item)

        select_all_btn = dialog.findChild(QtWidgets.QPushButton, "selectAllButton")
        clear_btn = dialog.findChild(QtWidgets.QPushButton, "clearButton")
        if select_all_btn:
            select_all_btn.clicked.connect(lambda: [list_widget.item(i).setCheckState(Qt.Checked) for i in range(list_widget.count())])
        if clear_btn:
            clear_btn.clicked.connect(lambda: [list_widget.item(i).setCheckState(Qt.Unchecked) for i in range(list_widget.count())])

        search_box = dialog.findChild(QtWidgets.QLineEdit, "searchBox")
        if search_box:
            def filter_items(text):
                for i in range(list_widget.count()):
                    item = list_widget.item(i)
                    item.setHidden(text.lower() not in item.text().lower())
            search_box.textChanged.connect(filter_items)

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
                self._filter_value_pool.pop(col_name, None)
            self.apply_column_filters()

    def apply_column_filters(self):
        # Save selection BEFORE filtering
        self._pre_filter_selection = self.tableView.parent().get_selected_cells_by_id()

        # Build filters as {col_index: set(allowed_values)}
        filters = {}
        for col_name, allowed_values in self._column_filters.items():
            col_idx = self.original_headers.index(col_name)
            filters[col_idx] = allowed_values
        self.tableView.model().set_column_filters(filters)  # Use the proxy model's method

        if not self._column_filters:
            self._filter_value_pool.clear()
        self.update_header_icons()

        # Only restore selection if there was a user selection before filtering
        if hasattr(self, "_pre_filter_selection") and self._pre_filter_selection:
            #print("[DEBUG]Restoring selection:", self._pre_filter_selection)
            self.tableView.parent().restore_selection_by_id(self._pre_filter_selection)
        else:
            print("Clearing selection")
            self.tableView.clearSelection()

    def update_header_icons(self):
        for i, col_name in enumerate(self.original_headers):
            base = col_name.replace(" ▼", "").replace("🔽", "")
            if self.filter_mode_enabled:
                if col_name in self._column_filters:
                    self.model.set_header_label(i, f"{base} 🔽")
                else:
                    self.model.set_header_label(i, f"{base} ▼")
            else:
                self.model.set_header_label(i, base)
        

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
        self.emp_id = emp_id
        self.qgis_layer = qgis_layer
        self.columns = self.columns.get(self.table_name, [])
        self.editable_fields = EDITABLE_FIELDS.get(self.table_name, {}).get(self.user_role, [])

        self.project = {
            '"public"."tm_production_inputs"': "turn_maneuver_project",
            '"public"."production_inputs"': "rfdb_project"
        }.get(self.table_name, None)

        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

        # --- Hide and remove the old QTableWidget ---
        self.ui.tableWidget.hide()
        self.ui.verticalLayout.removeWidget(self.ui.tableWidget)
        self.ui.tableWidget.deleteLater()

        # Now add your new QTableView
        self.ui.tableView = QTableView(self)
        self.ui.verticalLayout.insertWidget(0, self.ui.tableView)

        self.setWindowTitle("Work Allocation Portal Viewer/Editor")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)
        signal_bus.logout_signal.connect(self.cleanup_on_logout)

        self.ui.tableView.setSelectionBehavior(QTableView.SelectItems)
        self.ui.tableView.setSelectionMode(QTableView.ExtendedSelection)

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

        # Undo/redo & editing setup
        self.undo_stack = QUndoStack(self)
        self._cell_prev_values = {}
        self._is_undo_redo = False
        self._is_group_paste = False

        # Delegate setup
        self.delegate = UndoRedoDelegate(self.ui.tableView, self._cell_prev_values, self)
        self.ui.tableView.setItemDelegate(self.delegate)

        self.ui.tableView.installEventFilter(self)
        self.ui.tableView.viewport().installEventFilter(self)

        self.ui.tableView.setDragDropMode(QTableView.NoDragDrop)
        self.ui.tableView.setDragEnabled(False)
        self.ui.tableView.setDropIndicatorShown(False)
        self.ui.tableView.setDefaultDropAction(Qt.IgnoreAction)

        self.quoted_table = self.table_name
        try:
            self.schema, self.table = self.table_name.replace('"', '').split('.')
        except ValueError:
            QMessageBox.critical(self, "Error", f"Invalid table format: {self.table_name}")
            self.schema, self.table = "public", "production_inputs"

        self.col_types = {}
        self._suppress_cell_changed = False
        self._suppress_invalid_empid_popup = False
        self.model = None
        self.proxy_model = None

        self.load_column_types()
        self.refresh_table()

        self.ui.Refresh.clicked.connect(self.refresh_table)
        self.ui.Organize_columns.clicked.connect(self.organize_columns)
        self.ui.Zoom_to_feature.clicked.connect(self.zoom_to_selected_row_on_map)
        self.ui.Create_filter.clicked.connect(self.create_filter)

        self.filter_manager = FilterManager(self.ui.tableView, self.model)

        # PostgreSQL listener
        dsn = self.db_handler.get_dsn()
        self.pg_listener = PostgresListener(dsn, "production_inputs_update")
        self.pg_listener.notified.connect(self.handle_db_notify)

        # Combo box delegates
        self.combo_delegates = {}
        for col_idx, field_name in enumerate(self.columns):
            if field_name in self.DROPDOWN_COLUMNS:
                delegate = ComboBoxDelegate(self.DROPDOWN_COLUMNS[field_name], self.ui.tableView)
                self.ui.tableView.setItemDelegateForColumn(col_idx, delegate)
                self.combo_delegates[field_name] = delegate

        # Date column delegates
        date_delegate = DateDelegate(self.ui.tableView)
        for col_idx, field_name in enumerate(self.columns):
            if field_name in DATE_COLUMNS:
                self.ui.tableView.setItemDelegateForColumn(col_idx, date_delegate)

    def create_filter(self):
        """Toggles the filter UI."""
        self.filter_manager.create_filter()

    def get_selected_cells_by_id(self):
        """Return a list of (s_no, col_name) for all selected cells."""
        selected = []
        indexes = self.ui.tableView.selectedIndexes()
        s_no_idx = self.columns.index("s_no")

        for index in indexes:
            row, col = index.row(), index.column()
            s_no = str(self.model.index(row, s_no_idx).data())
            col_name = self.columns[col]
            selected.append((s_no, col_name))

        return selected

    def get_selected_cell_values(self):
        """Return a list of (s_no, col_name, value) for all selected cells."""
        selected = []
        indexes = self.ui.tableView.selectedIndexes()
        s_no_idx = self.columns.index("s_no")

        for index in indexes:
            row, col = index.row(), index.column()
            s_no = str(self.model.index(row, s_no_idx).data())
            col_name = self.columns[col]
            value = str(self.model.index(row, col).data())
            selected.append((s_no, col_name, value))

        return selected

    def get_filtered_rows_except(self, exclude_col_name):
        """Return row indices that pass all filters except the given column."""
        headers = self.columns
        filtered_rows = []
        for row in range(self.model.rowCount()):
            match = True
            for col_name, allowed_values in self.filter_manager._column_filters.items():
                if col_name == exclude_col_name:
                    continue
                try:
                    col_idx = headers.index(col_name)
                except ValueError:
                    continue
                value = self.model.index(row, col_idx).data()
                if value not in allowed_values:
                    match = False
                    break
            if match:
                filtered_rows.append(row)
        return filtered_rows


    def refresh_table(self):
        if not self.columns:
            QMessageBox.critical(self, "Error", "No columns defined for the selected table.")
            return

        print(f"[DEBUG] Fetching data from table: {self.quoted_table}")

        cur = self.db_handler.conn.cursor()

        # --- Fetch column types ---
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

        # --- Fetch data ---
        if self.subcountry and self.subcountry != "All subcountry":
            sql = f"SELECT {', '.join(self.columns)} FROM {self.quoted_table} WHERE subcountry = %s ORDER BY s_no"
            cur.execute(sql, (self.subcountry,))
        else:
            sql = f"SELECT {', '.join(self.columns)} FROM {self.quoted_table} ORDER BY s_no"
            cur.execute(sql)

        data = cur.fetchall()
        cur.close()

        # --- Convert data to dict list ---
        row_dicts = []
        for row in data:
            row_data = {self.columns[c]: row[c] for c in range(len(self.columns))}
            row_dicts.append(row_data)

        # --- Initialize model ---
        self.model = WorkAllocationTableModel(
            data=row_dicts,
            headers=self.columns,
            editable_fields=self.editable_fields,
            emp_id=self.emp_id,
            user_role=self.user_role,
            table_name=self.table_name,
            project=self.project,
            original_headers=self.columns  # <-- Pass the original column names here
        )

        # --- Connect dataChanged signal to your handler ---
        self.model.dataChanged.connect(self.on_data_changed)

        self.proxy_model = ColumnFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)

        self.ui.tableView.setModel(self.proxy_model)
        self.ui.tableView.setSortingEnabled(False)

        if hasattr(self, "filter_manager"):
            self.filter_manager.model = self.model

        # --- Hide certain columns ---
        for col_name in ("geom", "last_updated"):
            if col_name in self.columns:
                idx = self.columns.index(col_name)
                self.ui.tableView.setColumnHidden(idx, True)

        # --- Set header labels (optional with proxy) ---
        for i, col in enumerate(self.columns):
            self.ui.tableView.setColumnWidth(i, 120)
            if col in self.DROPDOWN_COLUMNS:
                delegate = ComboBoxDelegate(self.DROPDOWN_COLUMNS[col], self.ui.tableView)
                self.ui.tableView.setItemDelegateForColumn(i, delegate)
            elif col in DATE_COLUMNS:
                delegate = DateDelegate(self.ui.tableView)
                self.ui.tableView.setItemDelegateForColumn(i, delegate)

        self.ui.tableView.viewport().update()


    def handle_db_notify(self, payload):
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
                    continue
            except Exception as e:
                print(f"[DEBUG] Error fetching update for s_no {updated_s_no}: {e}")
                continue

            updated_dict = {self.columns[c]: row_data[c] for c in range(len(self.columns))}

            # Update the model row if s_no matches
            for row in range(self.model.rowCount()):
                index = self.model.index(row, self.columns.index("s_no"))
                s_no_value = self.model.data(index, Qt.DisplayRole)
                if s_no_value == updated_s_no:
                    self.model.update_row(row, updated_dict)


    def handle_cell_changed(self, row, col):
        index = self.model.index(row, col)
        item = self.model.data(index, Qt.DisplayRole)

        new_value = item
        field_name = self.columns[col]
        col_type = self.col_types.get(field_name, "").lower()

        if new_value in [None, "", "none", "None"]:
            new_value = None

        s_no_index = self.model.index(row, self.columns.index("s_no"))
        s_no = self.model.data(s_no_index, Qt.DisplayRole)
        col_name = self.columns[col]
        prev_value = self._cell_prev_values.get((s_no, col_name), "")

        if prev_value == new_value and not getattr(self, "_is_undo_redo", False):
            return

        if not getattr(self, "_is_undo_redo", False) and not getattr(self, "_is_group_paste", False):
            self.undo_stack.push(CellEditCommand(self, s_no, col_name, prev_value, new_value))

        try:
            cur = self.db_handler.conn.cursor()
            cur.execute(
                f"UPDATE {self.quoted_table} SET {field_name} = %s WHERE s_no = %s",
                (new_value, s_no)
            )
            self.db_handler.conn.commit()
            cur.execute(f"NOTIFY production_inputs_update, '{s_no}';")
            cur.close()
        except Exception as e:
            QMessageBox.critical(self, "Update Error", f"Failed to update {field_name}: {e}")
            self.refresh_table()

        self._cell_prev_values[(s_no, col_name)] = new_value

   
    def copy_cell_values(self):
        """Copy only the values of selected cells to the clipboard, and store metadata mapping in memory."""
        selected_indexes = self.ui.tableView.selectedIndexes()
        if not selected_indexes:
            return

        selected_cells = []
        for index in selected_indexes:
            row = index.row()
            col = index.column()
            s_no_index = self.model.index(row, self.columns.index("s_no"))
            s_no = self.model.data(s_no_index, Qt.DisplayRole)
            col_name = self.columns[col]
            value = self.model.data(index, Qt.DisplayRole)
            selected_cells.append((s_no, col_name, value))

        values_only = [value for _, _, value in selected_cells]
        QApplication.clipboard().setText("\n".join(values_only))
        self._structured_clipboard = [(s_no, col_name) for s_no, col_name, _ in selected_cells]


    def paste_cell_values(self):
        """Paste clipboard values into the currently selected cells using the current selection mapping."""
        text = QApplication.clipboard().text()
        if not text:
            return

        rows = [line.split('\t') for line in text.splitlines()]
        selected_indexes = self.ui.tableView.selectedIndexes()
        if not selected_indexes:
            return

        selected_cells = []
        for index in selected_indexes:
            row = index.row()
            col = index.column()
            s_no_index = self.model.index(row, self.columns.index("s_no"))
            s_no = self.model.data(s_no_index, Qt.DisplayRole)
            col_name = self.columns[col]
            selected_cells.append((s_no, col_name))

        group_edits = []
        self._is_group_paste = True

        num_clip_rows = len(rows)
        num_clip_cols = max(len(r) for r in rows) if rows else 1

        for i, (s_no, col_name) in enumerate(selected_cells):
            row_in_clip = i // num_clip_cols % num_clip_rows
            col_in_clip = i % num_clip_cols
            new_value = rows[row_in_clip][col_in_clip % len(rows[row_in_clip])]
            col_idx = self.columns.index(col_name)

            # Dropdown validation
            if col_name in self.DROPDOWN_COLUMNS:
                allowed = self.DROPDOWN_COLUMNS[col_name] + [""]
                if new_value not in allowed:
                    continue  # Skip invalid

            for row in range(self.model.rowCount()):
                s_no_index = self.model.index(row, self.columns.index("s_no"))
                if self.model.data(s_no_index) == s_no:
                    if not self.is_cell_editable(row, col_idx):
                        continue

                    index = self.model.index(row, col_idx)
                    old_value = self.model.data(index, Qt.DisplayRole)
                    self.model.setData(index, new_value, Qt.EditRole)
                    group_edits.append((s_no, col_name, old_value, new_value))
                    self.handle_cell_changed(row, col_idx)
                    break

        self._is_group_paste = False

        if group_edits:
            self.undo_stack.push(GroupEditCommand(self, group_edits))

    def is_cell_editable_by_id(self, s_no, col_name):
        """
        Return True if the cell identified by s_no and col_name is editable.
        Used by delegates that work on QModelIndex.
        """
        for row in range(self.ui.tableWidget.model().rowCount()):
            s_no_idx = self.columns.index("s_no")
            s_no_item = self.ui.tableWidget.model().index(row, s_no_idx).data()
            if s_no_item == s_no:
                col_idx = self.columns.index(col_name)
                return self.is_cell_editable(row, col_idx)
        return False

    def undo(self):
        print("[UNDO] Triggered")
        self.undo_stack.undo()

    def redo(self):
        print("[REDO] Triggered")
        self.undo_stack.redo()

    def eventFilter(self, obj, event):
        if obj == self.ui.tableView and event.type() == QEvent.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            if key == Qt.Key_C and modifiers & Qt.ControlModifier:
                self.copy_cell_values()
                return True
            elif key == Qt.Key_V and modifiers & Qt.ControlModifier:
                self.paste_cell_values()
                return True
            elif key == Qt.Key_Z and modifiers & Qt.ControlModifier:
                self.undo()
                return True
            elif key == Qt.Key_Y and modifiers & Qt.ControlModifier:
                self.redo()
                return True
            elif key in (Qt.Key_Delete, Qt.Key_Backspace):
                group_edits = []
                indexes = self.ui.tableView.selectedIndexes()
                self.ui.tableView.blockSignals(True)
                for index in indexes:
                    row = index.row()
                    col = index.column()
                    if self.is_cell_editable(row, col):
                        old_value = self.model.data(index, Qt.DisplayRole)
                        self.model.setData(index, "", Qt.EditRole)
                        s_no_index = self.model.index(row, self.columns.index("s_no"))
                        s_no = self.model.data(s_no_index, Qt.DisplayRole)
                        col_name = self.columns[col]
                        group_edits.append((s_no, col_name, old_value, ""))
                self.ui.tableView.blockSignals(False)
                if group_edits:
                    self.undo_stack.push(GroupEditCommand(self, group_edits))
                return True
        return super().eventFilter(obj, event)

    def sort_by_sno(self):
        if "s_no" in self.columns:
            s_no_idx = self.columns.index("s_no")
            self.ui.tableView.sortByColumn(s_no_idx, Qt.AscendingOrder)
    
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
        row_data = {
            self.columns[c]: self.model.data(self.model.index(row, c), Qt.DisplayRole)
            for c in range(len(self.columns))
        }
        return is_field_editable(
            self.user_role,
            field_name,
            row_data,
            getattr(self, "emp_id", None),
            project=getattr(self, "project", None),
            table_name=self.table_name
        )
    
    def on_data_changed(self, topLeft, bottomRight, roles):
        for row in range(topLeft.row(), bottomRight.row() + 1):
            for col in range(topLeft.column(), bottomRight.column() + 1):
                self.handle_cell_changed(row, col)

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
        """Display a dialog to let users reorder and show/hide columns in QTableView."""
        all_cols = self.columns[:]

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

        info_label = QtWidgets.QLabel(
            "Tip: Select multiple columns with Shift/Ctrl, then press Space to check/uncheck all selected."
        )
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
                    # Column visibility
                    if not self.ui.tableView.isColumnHidden(i):
                        item.setCheckState(Qt.Checked)
                    else:
                        item.setCheckState(Qt.Unchecked)
                    list_widget.addItem(item)

        populate_list()
        search.textChanged.connect(populate_list)

        select_all_btn.clicked.connect(
            lambda: [list_widget.item(i).setCheckState(Qt.Checked) for i in range(list_widget.count())]
        )
        clear_btn.clicked.connect(
            lambda: [list_widget.item(i).setCheckState(Qt.Unchecked) for i in range(list_widget.count())]
        )

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(btn_box)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)

        def on_item_changed(item):
            if not list_widget.hasFocus():
                return
            state = item.checkState()
            for selected_item in list_widget.selectedItems():
                if selected_item is not item:
                    selected_item.setCheckState(state)

        list_widget.itemChanged.connect(on_item_changed)

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

        # Set visibility
        for i, col_name in enumerate(all_cols):
            is_visible = visibility.get(col_name, False)
            col_idx = self.columns.index(col_name)
            self.ui.tableView.setColumnHidden(col_idx, not is_visible)

        # Reorder columns
        header = self.ui.tableView.horizontalHeader()
        for target_idx, col_name in enumerate(new_order):
            original_idx = self.columns.index(col_name)
            current_visual_idx = header.visualIndex(original_idx)
            if current_visual_idx != target_idx:
                header.moveSection(current_visual_idx, target_idx)

    def zoom_to_selected_row_on_map(self):
        """Zoom QGIS map canvas to the geometry of the selected row in the table."""
        selected_indexes = self.ui.tableView.selectedIndexes()
        if not selected_indexes:
            QMessageBox.information(self, "Zoom", "Please select a row to zoom to.")
            return

        s_no_idx = self.columns.index("s_no")
        selected_row = selected_indexes[0].row()
        s_no = self.model.index(selected_row, s_no_idx).data()
        if not s_no:
            QMessageBox.warning(self, "Zoom", "Could not determine the selected row's s_no.")
            return

        print(f"[DEBUG] Zoom requested for s_no: {s_no}")
        layer = self.qgis_layer
        if not layer:
            QMessageBox.warning(self, "Zoom", "Editable layer not found in QGIS.")
            return
        print(f"[DEBUG] Using layer: {layer.name()}")

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
        layer_crs = layer.crs()
        map_crs = QgsProject.instance().crs()
        if layer_crs != map_crs:
            transform = QgsCoordinateTransform(layer_crs, map_crs, QgsProject.instance())
            bbox = transform.transformBoundingBox(bbox)

        if geom.type() == 0:  # Point
            buffer = 0.0005
            bbox = QgsRectangle(
                bbox.xMinimum() - buffer, bbox.yMinimum() - buffer,
                bbox.xMaximum() + buffer, bbox.yMaximum() + buffer
            )

        iface.mapCanvas().setExtent(bbox)
        iface.mapCanvas().refresh()
        layer.removeSelection()
        layer.selectByIds([feature.id()])
        iface.mapCanvas().setExtent(feature.geometry().boundingBox())
        iface.mapCanvas().refresh()

    def restore_selection_by_id(self, selected_cells):
        """Restore selection given a list of (s_no, col_name)."""
        self.ui.tableView.clearSelection()
        s_no_idx = self.columns.index("s_no")
        selection_model = self.ui.tableView.selectionModel()
        already_selected = set()
        for row in range(self.model.rowCount()):
            s_no = self.model.index(row, s_no_idx).data()
            for sel_s_no, sel_col_name in selected_cells:
                if s_no == sel_s_no and sel_col_name in self.columns:
                    col = self.columns.index(sel_col_name)
                    index = self.model.index(row, col)
                    if (row, col) not in already_selected:
                        selection_model.select(index, QItemSelectionModel.Select)
                        already_selected.add((row, col))

    def filter_to_snos(self, s_no_list):
        """Show only rows with s_no in s_no_list. If list is empty, show nothing."""
        if not hasattr(self, 'columns') or not hasattr(self.ui, 'tableView'):
            return
        if "s_no" not in self.columns:
            return

        s_no_set = set(map(str, s_no_list))
        s_no_idx = self.columns.index("s_no")

        for row in range(self.model.rowCount()):
            s_no = self.model.index(row, s_no_idx).data()
            hide = (not s_no or s_no not in s_no_set)
            self.ui.tableView.setRowHidden(row, hide)

        if not s_no_set:
            for row in range(self.model.rowCount()):
                self.ui.tableView.setRowHidden(row, True)


