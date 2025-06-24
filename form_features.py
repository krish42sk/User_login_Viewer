from PyQt5.QtWidgets import QStyledItemDelegate, QDateEdit, QComboBox, QCalendarWidget, QUndoCommand
from PyQt5.QtCore import QDate, Qt, QEvent


class UndoRedoDelegate(QStyledItemDelegate):
    def __init__(self, table_view, cell_prev_values, dialog, parent=None):
        super().__init__(parent)
        self.table_view = table_view
        self.prev_value_dict = cell_prev_values
        self.dialog = dialog

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled

        # Resolve s_no and column name
        col_name = self.dialog.columns[index.column()]
        s_no_idx = self.dialog.columns.index("s_no")
        s_no = index.model().index(index.row(), s_no_idx).data()

        if not s_no or not col_name:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled

        # Let dialog decide based on (s_no, col_name)
        if self.dialog.is_cell_editable_by_id(s_no, col_name):
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable
        else:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled

    def createEditor(self, parent, option, index):
        value = index.model().data(index, Qt.DisplayRole)
        s_no_idx = self.dialog.columns.index("s_no")
        s_no = index.model().index(index.row(), s_no_idx).data()
        col_name = self.dialog.columns[index.column()]

        # Store value for undo tracking
        self.prev_value_dict[(s_no, col_name)] = value
        return super().createEditor(parent, option, index)

    def setModelData(self, editor, model, index):
        new_value = editor.text()
        col_name = self.dialog.columns[index.column()]
        s_no_idx = self.dialog.columns.index("s_no")
        s_no = index.model().index(index.row(), s_no_idx).data()

        prev_value = self.prev_value_dict.get((s_no, col_name), "")

        if new_value != prev_value:
            self.prev_value_dict[(s_no, col_name)] = new_value
            if not getattr(self.dialog, "_is_undo_redo", False):
                self.dialog.undo_stack.push(CellEditCommand(self.dialog, s_no, col_name, prev_value, new_value))

        model.setData(index, new_value, Qt.EditRole)


class ComboBoxDelegate(QStyledItemDelegate):
    def __init__(self, values, parent=None):
        super().__init__(parent)
        self.values = [""] + values  # Add empty as first option

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.addItems(self.values)
        return combo

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        idx = editor.findText(value)
        if idx >= 0:
            editor.setCurrentIndex(idx)
        else:
            editor.setCurrentIndex(0)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)

class DateDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QDateEdit(parent)
        editor.setCalendarPopup(True)
        editor.setDisplayFormat("yyyy-MM-dd")
        editor.installEventFilter(self)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if value:
            date = QDate.fromString(value, "yyyy-MM-dd")
            if not date.isValid():
                date = QDate()  # Invalid date
        else:
            date = QDate()  # Invalid date
        editor.setDate(date)

    def setModelData(self, editor, model, index):
        date = editor.date()
        # If the editor is blank or minimum, set as empty string
        if not date.isValid() or editor.text().strip() == "" or date == editor.minimumDate():
            model.setData(index, "", Qt.EditRole)
        else:
            model.setData(index, date.toString("yyyy-MM-dd"), Qt.EditRole)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Semicolon and event.modifiers() & Qt.ControlModifier:
                obj.setDate(QDate.currentDate())
                return True
        return super().eventFilter(obj, event)
    

class CellEditCommand(QUndoCommand):
    def __init__(self, dialog, s_no, col_name, old_value, new_value):
        super().__init__("Edit Cell")
        self.dialog = dialog
        self.s_no = s_no
        self.col_name = col_name
        self.old_value = old_value
        self.new_value = new_value

    def _find_model_index(self):
        """
        Returns the model index for (s_no, col_name)
        """
        model = self.dialog.model  # <-- This assumes model is stored in dialog
        try:
            s_no_idx = self.dialog.columns.index("s_no")
            col_idx = self.dialog.columns.index(self.col_name)
        except ValueError:
            return None

        for row in range(model.rowCount()):
            index = model.index(row, s_no_idx)
            if index.data() == self.s_no:
                return model.index(row, col_idx)
        return None

    def undo(self):
        self.dialog._is_undo_redo = True
        index = self._find_model_index()
        if index:
            model = self.dialog.model
            model.setData(index, "" if self.old_value is None else str(self.old_value), Qt.EditRole)
        self.dialog._is_undo_redo = False

    def redo(self):
        self.dialog._is_undo_redo = True
        index = self._find_model_index()
        if index:
            model = self.dialog.model
            model.setData(index, "" if self.new_value is None else str(self.new_value), Qt.EditRole)
            # Optional: force cache update
            self.dialog._cell_prev_values[(self.s_no, self.col_name)] = self.new_value
        self.dialog._is_undo_redo = False


class GroupEditCommand(QUndoCommand):
    def __init__(self, dialog, edits):
        super().__init__("Group Paste")
        self.dialog = dialog
        self.edits = edits  # List of (s_no, col_name, old_value, new_value)

    def _find_model_index(self, s_no, col_name):
        model = self.dialog.model
        try:
            s_no_idx = self.dialog.columns.index("s_no")
            col_idx = self.dialog.columns.index(col_name)
        except ValueError:
            return None

        for row in range(model.rowCount()):
            s_no_val = model.index(row, s_no_idx).data()
            if s_no_val == s_no:
                return model.index(row, col_idx)
        return None

    def undo(self):
        self.dialog._is_undo_redo = True
        for s_no, col_name, old_value, _ in reversed(self.edits):
            index = self._find_model_index(s_no, col_name)
            if index:
                self.dialog.model.setData(index, "" if old_value is None else str(old_value), Qt.EditRole)
                self.dialog._cell_prev_values[(s_no, col_name)] = old_value
        self.dialog._is_undo_redo = False

    def redo(self):
        self.dialog._is_undo_redo = True
        for s_no, col_name, _, new_value in self.edits:
            index = self._find_model_index(s_no, col_name)
            if index:
                self.dialog.model.setData(index, "" if new_value is None else str(new_value), Qt.EditRole)
                self.dialog._cell_prev_values[(s_no, col_name)] = new_value
        self.dialog._is_undo_redo = False

