from PyQt5.QtWidgets import QStyledItemDelegate, QDateEdit, QComboBox, QCalendarWidget
from PyQt5.QtCore import QDate, Qt, QEvent


class UndoRedoDelegate(QStyledItemDelegate):
    def __init__(self, parent, prev_value_dict):
        super().__init__(parent)
        self.prev_value_dict = prev_value_dict

    def flags(self, index):
        row = index.row()
        col = index.column()
        dialog = self.parent().parent()
        if hasattr(dialog, "is_cell_editable") and dialog.is_cell_editable(row, col):
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable
        else:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled

    def createEditor(self, parent, option, index):
        row = index.row()
        col = index.column()
        value = index.model().data(index)
        self.prev_value_dict[(row, col)] = value
        #print(f"[DELEGATE PRE-EDIT] Cell ({row}, {col}) previous value: {value}")
        return super().createEditor(parent, option, index)

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

