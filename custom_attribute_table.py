from PyQt5.QtWidgets import QFrame, QTableWidgetItem, QMessageBox, QShortcut, QApplication
from PyQt5.QtGui import QIcon, QColor, QKeySequence
from PyQt5.QtCore import QTimer, Qt
import os
from PyQt5 import uic, QtWidgets
from .constants import EDITABLE_FIELDS
from .db_handler import DbHandler
import logging

logger = logging.getLogger(__name__)

class CustomAttributeTable(QFrame):
    def __init__(self, db_handler, editable_fields=None, df=None, designation=None, parent=None):
        super().__init__(parent)
        self.editable_fields = editable_fields or []
        self.frame = QFrame()
        self.tableWidget = None  # Will be assigned after loading UI
        self.df = df
        self.designation = designation
        self.db_handler = db_handler

        if not db_handler:
            QMessageBox.critical(self, "Error", "Database handler is not set.")
            raise ValueError("db_handler cannot be None")

        # Load UI
        ui_path = os.path.join(os.path.dirname(__file__), "Work_Allocation_Portal_Viewer.ui")
        uic.loadUi(ui_path, self.frame)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.frame)
        self.setLayout(layout)

        self.tableWidget = self.frame.tableWidget
        self._column_filters = {}
        self.filter_mode_enabled = False
        self.edit_mode_enabled = False
        self.original_headers = []
        self.undo_stack = []
        self.redo_stack = []

        self.clipboard_manager = CustomAttributeTable.ClipboardManager(self.tableWidget, self.editable_fields)

        self.setup_icons()
        self.setup_shortcuts()
        self.connect_signals()
        self.setup_timer()
        self.setup_table_behavior()
        self.populate_table()
        
    def setup_icons(self):
        icon_dir = os.path.join(os.path.dirname(__file__), "icons")
        self.frame.Save.setIcon(QIcon(os.path.join(icon_dir, "diskette.png")))
        self.frame.Refresh.setIcon(QIcon(os.path.join(icon_dir, "loading-arrow.png")))
        self.frame.Organize_columns.setIcon(QIcon(os.path.join(icon_dir, "task.png")))
        self.frame.Zoom_to_feature.setIcon(QIcon(os.path.join(icon_dir, "search.png")))
        self.frame.Create_filter.setIcon(QIcon(os.path.join(icon_dir, "filter.png")))

    def setup_shortcuts(self):
        shortcuts = [
            (QKeySequence("Ctrl+S"), self.save_edits),
            (QKeySequence("Ctrl+R"), self.populate_table),
            (QKeySequence("Ctrl+O"), self.organize_columns),
            (QKeySequence("Ctrl+F"), self.create_filter),
            (QKeySequence("Ctrl+C"), self.clipboard_manager.copy_selection),
            (QKeySequence("Ctrl+V"), self.clipboard_manager.paste_selection),
            (QKeySequence("Ctrl+Z"), self.clipboard_manager.undo),
            (QKeySequence("Ctrl+Y"), self.clipboard_manager.redo),
        ]
        for seq, slot in shortcuts:
            sc = QShortcut(seq, self)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(slot)
    def connect_signals(self):
        self.frame.Save.clicked.connect(self.save_edits)
        self.frame.Refresh.clicked.connect(self.populate_table)
        self.frame.Organize_columns.clicked.connect(self.organize_columns)
        self.frame.Create_filter.clicked.connect(self.create_filter)
        self.frame.Zoom_to_feature.clicked.connect(self.zoom_to_feature)
        self.frame.Edit.clicked.connect(self.enable_edit_mode)
        self.tableWidget.cellChanged.connect(self.track_edit)
        self.tableWidget.horizontalHeader().sectionClicked.connect(self.open_column_filter_dialog)

    def setup_timer(self):
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(60000)
        self.refresh_timer.timeout.connect(self.auto_refresh_table)

    def setup_table_behavior(self):
        self.tableWidget.setAlternatingRowColors(True)
        self.tableWidget.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)
        self.tableWidget.setStyleSheet("QTableWidget { font-size: 11pt; }")
        self.setWindowFlags(Qt.Window)
        self.undo_stack = []
        self.redo_stack = []
        # ✅ Enable sorting
        self.tableWidget.setSortingEnabled(True)
        self.tableWidget.horizontalHeader().sortIndicatorChanged.connect(self.apply_column_filters)

    
    def populate_table(self):
        """Load data from the database and populate the table."""
        self.refresh_timer.stop()
        try:
            with self.db_handler.get_cursor_with_retries() as cur:
                if cur is None:
                    raise Exception("Database connection is unavailable.")
                cur.execute("""SELECT 
                        s_no, project, wu_received_date, work_unit_id, length_mi, subcountry, rough_road_type,
                        rfdb_production_emp_id, rfdb_production_done_by, rfdb_allotted_date, rfdb_completed_date,
                        rfdb_production_time_taken, rfdb_production_status, rfdb_production_remarks,
                        siloc_production_emp_id, siloc_production_done_by, siloc_production_allotted_date, 
                        siloc_production_completed_date, siloc_production_time_taken, siloc_production_sign_count,
                        siloc_production_autodetection_status, siloc_production_status, siloc_production_remarks,
                        siloc_qc_emp_id, siloc_qc_done_by, siloc_qc_allotted_date, siloc_qc_completed_date, 
                        siloc_qc_time_taken, siloc_qc_sign_count, siloc_qc_status, siloc_qc_remarks,
                        rfdb_path_association_production_emp_id, rfdb_path_association_production_done_by, 
                        rfdb_path_association_production_allotted_date, rfdb_path_association_production_completed_date,
                        rfdb_path_association_production_time_taken, rfdb_path_association_production_status, 
                        rfdb_path_association_production_remarks, rfdb_qc_emp_id, rfdb_qc_done_by, rfdb_qc_allotted_date, 
                        rfdb_qc_completed_date, rfdb_qc_time_taken, rfdb_qc_status, rfdb_qc_remarks,
                        rfdb_attri_qc_emp_id, rfdb_attri_qc_done_by, rfdb_attri_qc_allotted_date, rfdb_attri_qc_completed_date,
                        rfdb_attri_qc_time_taken, rfdb_attri_qc_status, rfdb_attri_qc_remarks,
                        rfdb_roadtype_qc_emp_id, rfdb_roadtype_qc_done_by, rfdb_roadtype_qc_allotted_date, 
                        rfdb_roadtype_qc_completed_date, rfdb_roadtype_qc_time_taken, rfdb_roadtype_qc_status, 
                        rfdb_roadtype_qc_remarks, rfdb_qa_emp_id, rfdb_qa_done_by, rfdb_qa_allotted_date, 
                        rfdb_qa_completed_date, rfdb_qa_time_taken, rfdb_qa_status, rfdb_qa_remarks,
                        rfdb_path_association_qc_emp_id, rfdb_path_association_qc_done_by, 
                        rfdb_path_association_qc_allotted_date, rfdb_path_association_qc_completed_date, 
                        rfdb_path_association_qc_time_taken, rfdb_path_association_qc_status, rfdb_path_association_qc_remarks,
                        delivery_status, delivered_date
                    FROM public.production_input
                    ORDER BY s_no ASC""")
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
        except Exception as e:
            logger.exception("Failed to load data")
            QMessageBox.critical(self, "Database Error", str(e))
            return

        self.tableWidget.blockSignals(True)
        self.tableWidget.clear()
        self.tableWidget.setRowCount(len(rows))
        self.tableWidget.setColumnCount(len(columns))
        self.tableWidget.setHorizontalHeaderLabels(columns)

        self.tableWidget.setSortingEnabled(False)
        int_columns = {"s_no", "work_unit_id"}  # Add all integer column names here

        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                col_name = columns[col_idx]
                if col_name in int_columns:
                    item = IntSortTableWidgetItem(str(value))
                else:
                    item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, str(value))
                if col_name in self.editable_fields:
                    item.setBackground(Qt.white)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setBackground(QColor(230, 230, 230))
                self.tableWidget.setItem(row_idx, col_idx, item)

        self.tableWidget.resizeColumnsToContents()
        self.tableWidget.blockSignals(False)

        # ✅ Re-enable sorting
        self.tableWidget.setSortingEnabled(True)
        self.refresh_timer.start()


    def track_edit(self, row, col):
        item = self.tableWidget.item(row, col)
        if not item:
            return
        col_name = self.tableWidget.horizontalHeaderItem(col).text().replace(" 🔽", "")
        if col_name not in self.editable_fields:
            return
        old_value = item.data(Qt.UserRole)
        new_value = item.text()
        if old_value != new_value:
            self.clipboard_manager.undo_stack.append((row, col, old_value, new_value))
            self.clipboard_manager.redo_stack.clear()
    def save_edits(self):
        """Save edited fields to the database."""
        changed = []

        # Get header labels to dynamically find 's_no'
        headers = [self.tableWidget.horizontalHeaderItem(i).text() for i in range(self.tableWidget.columnCount())]
        try:
            s_no_col_index = headers.index("s_no")
        except ValueError:
            QMessageBox.critical(self, "Error", "'s_no' column not found in table headers.")
            return

        for row in range(self.tableWidget.rowCount()):
            for col in range(self.tableWidget.columnCount()):
                item = self.tableWidget.item(row, col)
                if not item:
                    continue
                col_name = headers[col]
                if col_name in self.editable_fields:
                    original = item.data(Qt.UserRole)
                    current = item.text()
                    if current != original:
                        changed.append((row, col_name, current))

        if not changed:
            QMessageBox.information(self, "Save", "No changes to save.")
            return

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)

            with self.db_handler.get_cursor_with_retries() as cur:
                for row, col_name, new_value in changed:
                    s_no_item = self.tableWidget.item(row, s_no_col_index)
                    if not s_no_item:
                        raise ValueError(f"Missing 's_no' value at row {row}")

                    s_no_text = s_no_item.text()
                    try:
                        s_no = int(s_no_text)
                    except ValueError:
                        raise ValueError(f"Invalid 's_no' format: {s_no_text!r} (expected integer)")

                    # Convert "None" or "" to None for database NULL
                    if new_value is None or str(new_value).strip() in ("", "None"):
                        new_value_db = None
                    else:
                        new_value_db = new_value

                    query = f"UPDATE public.production_input SET {col_name} = %s WHERE s_no = %s"
                    cur.execute(query, (new_value_db, s_no))

                #self.db_handler.commit()   #psycopg2 explicit commit

            QMessageBox.information(self, "Success", "Changes saved successfully.")

            # Exit edit mode, restart auto-refresh
            self.edit_mode_enabled = False
            self.tableWidget.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            if not self.filter_mode_enabled:
                self.refresh_timer.start()
            self.populate_table()

        except Exception as e:
            if hasattr(self.db_handler, 'conn') and self.db_handler.conn:
                self.db_handler.conn.rollback()
            logger.exception("Error saving edits")
            QMessageBox.critical(self, "Save Error", f"An error occurred: {e}")
        finally:
            QApplication.restoreOverrideCursor() 

    def auto_refresh_table(self):
        if self.isVisible():
            self.populate_table()
    def create_filter(self):
        """Toggle column filter mode with 🔽 emoji in headers."""
        col_count = self.tableWidget.columnCount()
        if not self.filter_mode_enabled:
            self.refresh_timer.stop()
            self.original_headers = [self.tableWidget.horizontalHeaderItem(i).text() for i in range(col_count)]
            for i in range(col_count):
                header = self.tableWidget.horizontalHeaderItem(i)
                header.setText(f"{header.text()} 🔽")
            self.filter_mode_enabled = True
            self.tableWidget.horizontalHeader().sectionClicked.connect(self.open_column_filter_dialog)
        else:
            for i in range(col_count):
                self.tableWidget.horizontalHeaderItem(i).setText(self.original_headers[i])
            self.filter_mode_enabled = False
            self._column_filters.clear()
            self.apply_column_filters()
            try:
                self.tableWidget.horizontalHeader().sectionClicked.disconnect(self.open_column_filter_dialog)
            except Exception:
                pass

    def open_column_filter_dialog(self, index):
        """Open the custom filter UI for the selected column."""

        if not self.filter_mode_enabled:
            return

        col_name = self.original_headers[index]

        # We'll filter values only from rows currently visible (already filtered rows)
        values = sorted({
            self.tableWidget.item(row, index).text()
            for row in range(self.tableWidget.rowCount())
            if not self.tableWidget.isRowHidden(row) and self.tableWidget.item(row, index)
        })

        ui_path = os.path.join(os.path.dirname(__file__), "custom_attribute_table_filter.ui")
        dialog = QtWidgets.QDialog(self)
        dialog.setModal(True)  # Make the dialog modal
        uic.loadUi(ui_path, dialog)
        dialog.setWindowTitle(f"Filter: {col_name}")

        scroll_area = dialog.findChild(QtWidgets.QScrollArea, "scrollArea")
        contents = scroll_area.findChild(QtWidgets.QWidget, "scrollAreaWidgetContents")
        layout = contents.findChild(QtWidgets.QVBoxLayout, "checkBoxLayout")

        # Clear existing checkboxes from layout (now layout is defined)
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        checkboxes = []
        for val in values:
            cb = QtWidgets.QCheckBox(val)
            cb.setChecked(True)
            layout.addWidget(cb)
            checkboxes.append(cb)

        dialog.findChild(QtWidgets.QPushButton, "selectAllButton").clicked.connect(
            lambda: [cb.setChecked(True) for cb in checkboxes]
        )
        dialog.findChild(QtWidgets.QPushButton, "clearButton").clicked.connect(
            lambda: [cb.setChecked(False) for cb in checkboxes]
        )

        search_box = dialog.findChild(QtWidgets.QLineEdit, "searchBox")
        search_box.textChanged.connect(
            lambda text: [cb.setVisible(text.lower() in cb.text().lower()) for cb in checkboxes]
        )

        button_box = dialog.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            selected = {cb.text() for cb in checkboxes if cb.isChecked()}
            if selected and len(selected) < len(checkboxes):
                self._column_filters[col_name] = selected
            else:
                self._column_filters.pop(col_name, None)
            self.apply_column_filters()


    def apply_column_filters(self):
        """Apply all active column filters, respecting sort and multi-column filtering."""
        if not hasattr(self, "_column_filters"):
            self._column_filters = {}

        headers = [
            self.tableWidget.horizontalHeaderItem(i).text().replace(" 🔽", "")
            for i in range(self.tableWidget.columnCount())
        ]

        # Start by showing all rows
        for row in range(self.tableWidget.rowCount()):
            self.tableWidget.setRowHidden(row, False)

        # Now apply all filters in sequence
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



    def organize_columns(self):
        """Display a dialog to let users reorder and show/hide only currently visible columns."""
        # Only include columns that are currently visible (not hidden)
        cols = [
            self.tableWidget.horizontalHeaderItem(i).text().replace(" 🔽", "")
            for i in range(self.tableWidget.columnCount())
            if not self.tableWidget.isColumnHidden(i)
        ]
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Organize Columns")
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
        
        list_widget = QtWidgets.QListWidget()
        list_widget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        layout.addWidget(list_widget)

        def populate_list():
            list_widget.clear()
            search_text = search.text().lower()
            for col in cols:
                if search_text in col.lower():
                    item = QtWidgets.QListWidgetItem(col)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                    hidden = False  # All in cols are visible
                    item.setCheckState(Qt.Checked)
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

        # Only update columns that are in the visible list
        all_cols = [self.tableWidget.horizontalHeaderItem(i).text().replace(" 🔽", "") for i in range(self.tableWidget.columnCount())]
        for i, col in enumerate(all_cols):
            if col in visibility:
                idx = all_cols.index(col)
                self.tableWidget.setColumnHidden(idx, not visibility[col])

        header = self.tableWidget.horizontalHeader()
        for target_idx, col_name in enumerate(new_order):
            current_idx = header.visualIndex(all_cols.index(col_name))
            header.moveSection(current_idx, target_idx)
    def zoom_to_feature(self):
        """Allow user to search for a value in any column and zoom to its row."""
        cols = [self.tableWidget.horizontalHeaderItem(i).text().replace(" 🔽", "") for i in range(self.tableWidget.columnCount())]
        col, ok = QtWidgets.QInputDialog.getItem(self, "Find Feature", "Select column to search:", cols, 0, False)
        if not ok or not col:
            return
        value, ok_val = QtWidgets.QInputDialog.getText(self, "Find", f"Enter value to find in '{col}':")
        if not ok_val or not value:
            return
        col_idx = cols.index(col)
        for row in range(self.tableWidget.rowCount()):
            item = self.tableWidget.item(row, col_idx)
            if item and item.text() == value:
                self.tableWidget.selectRow(row)
                self.tableWidget.scrollToItem(item)
                return
        QMessageBox.information(self, "Not Found", f"'{value}' not found in column '{col}'.")

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts for copy and paste."""
        try:
            if event.matches(QKeySequence.Copy):
                self.clipboard_manager.copy_selection()
            elif event.matches(QKeySequence.Paste):
                self.clipboard_manager.paste_selection()
            else:
                super().keyPressEvent(event)
        except Exception as e:
            logger.exception("KeyPress error")
            super().keyPressEvent(event)    

    def showEvent(self, event):
        super().showEvent(event)
        if not self.refresh_timer.isActive():
            if not self.filter_mode_enabled and not self.edit_mode_enabled:
                 self.refresh_timer.start()


    def closeEvent(self, event):
        if self.refresh_timer.isActive():
            self.refresh_timer.stop()
        super().closeEvent(event)

    def enable_edit_mode(self):
        self.edit_mode_enabled = True
        self.refresh_timer.stop()
        self.tableWidget.setEditTriggers(
            self.tableWidget.DoubleClicked | self.tableWidget.SelectedClicked | self.tableWidget.EditKeyPressed
        )
        QMessageBox.information(self, "Edit Mode", "Edit mode is ON. Make changes and click Save to apply.")
    def get_filtered_rows_except(self, exclude_col_name):
        headers = [self.tableWidget.horizontalHeaderItem(i).text().replace(" 🔽", "") 
                for i in range(self.tableWidget.columnCount())]
        filtered_rows = []
        for row in range(self.tableWidget.rowCount()):
            match = True
            for col_name, allowed_values in self._column_filters.items():
                if col_name == exclude_col_name:
                    continue
                col_idx = headers.index(col_name)
                item = self.tableWidget.item(row, col_idx)
                if item is None or item.text() not in allowed_values:
                    match = False
                    break
            if match:
                filtered_rows.append(row)
        return filtered_rows
    
    class ClipboardManager:
        """Handles copy-paste operations with undo/redo support using Qt clipboard."""
        
        def __init__(self, table_widget, editable_fields):
            self.tableWidget = table_widget
            self.editable_fields = editable_fields
            self.undo_stack = []
            self.redo_stack = []

        def copy_selection(self):
            """Copy selected cells to clipboard."""
            selected = self.tableWidget.selectedIndexes()
            if not selected:
                return

            rows = sorted(set(idx.row() for idx in selected))
            cols = sorted(set(idx.column() for idx in selected))
            text = ""

            for r in rows:
                line = []
                for c in cols:
                    item = self.tableWidget.item(r, c)
                    line.append(item.text() if item else "")
                text += "\t".join(line) + "\n"

            QApplication.clipboard().setText(text.strip())

        def paste_selection(self):
            """Paste clipboard contents into selected cells."""
            text = QApplication.clipboard().text().strip()
            if not text:
                return

            start_indexes = self.tableWidget.selectedIndexes()
            if not start_indexes:
                return

            start_row, start_col = start_indexes[0].row(), start_indexes[0].column()
            rows = [line.split('\t') for line in text.split('\n')]

            batch_undo = []
            single_action = None

            # Single-cell copy, paste to multiple cells
            if len(rows) == 1 and len(rows[0]) == 1 and len(start_indexes) > 1:
                value = rows[0][0]
                for idx in start_indexes:
                    col_name = self.tableWidget.horizontalHeaderItem(idx.column()).text().replace(" 🔽", "")
                    if col_name in self.editable_fields:
                        item = self.tableWidget.item(idx.row(), idx.column())
                        old_value = item.text() if item else ""
                        self.tableWidget.setItem(idx.row(), idx.column(), QTableWidgetItem(value))
                        batch_undo.append((idx.row(), idx.column(), old_value, value))

                self.undo_stack.append(batch_undo)
                self.redo_stack.clear()
                return

            # Regular paste operation
            for r, row_vals in enumerate(rows):
                for c, val in enumerate(row_vals):
                    row_idx, col_idx = start_row + r, start_col + c
                    if row_idx < self.tableWidget.rowCount() and col_idx < self.tableWidget.columnCount():
                        col_name = self.tableWidget.horizontalHeaderItem(col_idx).text().replace(" 🔽", "")
                        if col_name in self.editable_fields:
                            item = self.tableWidget.item(row_idx, col_idx)
                            old_value = item.text() if item else ""
                            self.tableWidget.setItem(row_idx, col_idx, QTableWidgetItem(val))

                            if len(rows) > 1 or len(row_vals) > 1:
                                batch_undo.append((row_idx, col_idx, old_value, val))
                            else:
                                single_action = (row_idx, col_idx, old_value, val)

            # Track batch vs. single action in undo stack
            if batch_undo:
                self.undo_stack.append(batch_undo)
                self.redo_stack.clear()
            elif single_action:
                self.undo_stack.append([single_action])
                self.redo_stack.clear()

        def undo(self):
            """Undo the last change."""
            if not self.undo_stack:
                QMessageBox.information(self.tableWidget, "Undo", "Nothing to undo.")
                return

            last_batch = self.undo_stack.pop()
            for row, col, old_val, new_val in last_batch:
                item = self.tableWidget.item(row, col)
                if item:
                    item.setText(old_val)

            self.redo_stack.append(last_batch)

        def redo(self):
            """Redo the last undone action."""
            if not self.redo_stack:
                QMessageBox.information(self.tableWidget, "Redo", "Nothing to redo.")
                return

            last_batch = self.redo_stack.pop()
            for row, col, old_val, new_val in last_batch:
                item = self.tableWidget.item(row, col)
                if item:
                    item.setText(new_val)

            self.undo_stack.append(last_batch)

class IntSortTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            return int(self.text()) < int(other.text())
        except ValueError:
            return self.text() < other.text()

