from PyQt5.QtCore import QSortFilterProxyModel

class ColumnFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.column_filters = {}  # {col_index: set(allowed_values)}

    def set_column_filters(self, filters):
        self.column_filters = filters
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        for col_idx, allowed_values in self.column_filters.items():
            index = model.index(source_row, col_idx, source_parent)
            value = str(index.data())
            if value not in allowed_values:
                return False
        return True