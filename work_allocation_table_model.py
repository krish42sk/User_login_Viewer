from PyQt5.QtCore import Qt, QAbstractTableModel, QVariant
from PyQt5.QtGui import QColor

class WorkAllocationTableModel(QAbstractTableModel):
    def __init__(
        self, data, headers, editable_fields=None, emp_id=None, user_role=None, table_name=None, project=None, original_headers=None, parent=None
    ):
        super().__init__(parent)
        self._data = data  # A list of row dicts
        self.header_labels = headers  # A list of column names (may have "▼")
        self.original_headers = original_headers or headers[:]  # <-- Add this line
        self.editable_fields = editable_fields or []
        self.emp_id = emp_id
        self.user_role = user_role
        self.table_name = table_name
        self.project = project

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self.header_labels)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        row = index.row()
        col = index.column()
        col_name = self.original_headers[col]
        value = self._data[row].get(col_name)
        if role == Qt.DisplayRole:
            return str(value) if value is not None else ""
        if role == Qt.BackgroundRole:
            if col_name not in self.editable_fields:
                return QColor(180, 180, 180)  # Light gray background
        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.header_labels[section]
        return super().headerData(section, orientation, role)

    def set_header_labels(self, labels: list):
        self.header_labels = labels
        self.headerDataChanged.emit(Qt.Horizontal, 0, len(labels) - 1)

    def set_header_label(self, index: int, label: str):
        if 0 <= index < len(self.header_labels):
            self.header_labels[index] = label
            self.headerDataChanged.emit(Qt.Horizontal, index, index)

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        col_name = self.header_labels[index.column()]
        if col_name in self.editable_fields:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role != Qt.EditRole:
            return False

        row = index.row()
        col = index.column()
        col_name = self.header_labels[col]

        # Optional: clean value (e.g. handle blank as None)
        if isinstance(value, str) and value.strip() == "":
            value = None

        self._data[row][col_name] = value
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    def update_row(self, row, updated_dict):
        """
        Update the data in the given row with values from updated_dict,
        and emit dataChanged for the updated row.
        """
        if 0 <= row < len(self._data):
            self._data[row].update(updated_dict)
            top_left = self.index(row, 0)
            bottom_right = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, Qt.EditRole])

    def update_row_by_sno(self, s_no, updated_dict):
        """
        Update the row with the given s_no using updated_dict.
        """
        for row, row_dict in enumerate(self._data):
            if str(row_dict.get("s_no")) == str(s_no):
                self.update_row(row, updated_dict)
                break
