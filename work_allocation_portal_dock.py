from PyQt5.QtWidgets import QDockWidget, QWidget, QTableWidgetItem
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt
import os
from .work_allocation_portal_viewer import Ui_Dialog

class WorkAllocationPortalViewerDock(QDockWidget):
    def __init__(self, db_handler, iface, parent=None):
        super().__init__("Work Allocation Portal Viewer/Editor", parent)
        self.setObjectName("WorkAllocationPortalViewerDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetClosable)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)

        # Create a QWidget to hold the UI
        self.main_widget = QWidget()
        self.ui = Ui_Dialog()
        self.ui.setupUi(self.main_widget)
        self.setWidget(self.main_widget)

        # Set icons
        icon_dir = os.path.join(os.path.dirname(__file__), "icon")
        self.ui.Save.setIcon(QIcon(os.path.join(icon_dir, "diskette.png")))
        self.ui.Refresh.setIcon(QIcon(os.path.join(icon_dir, "loading-arrow.png")))
        self.ui.Organize_columns.setIcon(QIcon(os.path.join(icon_dir, "task.png")))
        self.ui.Zoom_to_feature.setIcon(QIcon(os.path.join(icon_dir, "search.png")))
        self.ui.Create_filter.setIcon(QIcon(os.path.join(icon_dir, "filter.png")))

        # Fetch and display data
        data = db_handler.fetch_work_units()
        cur = db_handler.conn.cursor()
        cur.execute("SELECT * FROM production_input LIMIT 1")
        columns = [desc[0] for desc in cur.description]
        cur.close()

        self.ui.tableWidget.setColumnCount(len(columns))
        self.ui.tableWidget.setHorizontalHeaderLabels(columns)
        self.ui.tableWidget.setRowCount(len(data))

        for row_idx, row in enumerate(data):
            for col_idx, value in enumerate(row):
                self.ui.tableWidget.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))

        # Hide geom column
        if "geom" in columns:
            geom_idx = columns.index("geom")
            self.ui.tableWidget.setColumnHidden(geom_idx, True)

        # Set vertical header numbers (row numbers)
        self.ui.tableWidget.setVerticalHeaderLabels([str(i+1) for i in range(self.ui.tableWidget.rowCount())])

        # Add the dock widget to QGIS main window
        iface.addDockWidget(Qt.BottomDockWidgetArea, self)

    def showEvent(self, event):
        super().showEvent(event)
        if self.isFloating():
            flags = self.windowFlags()
            # Add Minimize and Maximize buttons
            self.setWindowFlags(flags | Qt.WindowMinMaxButtonsHint | Qt.Window)
            self.show()