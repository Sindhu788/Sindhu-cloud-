from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QGroupBox, QInputDialog, QMessageBox, QSplitter,
)

from backtest_engine import strategy_library as lib


class StrategyLibraryTab(QWidget):
    """Browse/search/tag/favourite/rename/duplicate/delete saved
    strategies, with version history. `on_load(strategy_id)` is called
    when the CEO picks "Load into Builder"."""

    def __init__(self, on_load=None):
        super().__init__()
        self.on_load = on_load
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by name or tag...")
        self.search_edit.textChanged.connect(self.refresh)
        search_row.addWidget(self.search_edit)
        left.addLayout(search_row)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        left.addWidget(self.list_widget, stretch=1)

        buttons = QHBoxLayout()
        self.btn_load = QPushButton("Load into Builder")
        self.btn_favourite = QPushButton("★ Toggle Favourite")
        self.btn_rename = QPushButton("Rename")
        self.btn_duplicate = QPushButton("Duplicate")
        self.btn_delete = QPushButton("Delete")
        for b in (self.btn_load, self.btn_favourite, self.btn_rename, self.btn_duplicate, self.btn_delete):
            buttons.addWidget(b)
        left.addLayout(buttons)

        self.btn_load.clicked.connect(self._on_load)
        self.btn_favourite.clicked.connect(self._on_favourite)
        self.btn_rename.clicked.connect(self._on_rename)
        self.btn_duplicate.clicked.connect(self._on_duplicate)
        self.btn_delete.clicked.connect(self._on_delete)

        left_widget = QWidget()
        left_widget.setLayout(left)

        right = QVBoxLayout()
        right.addWidget(QLabel("Version History"))
        self.version_list = QListWidget()
        right.addWidget(self.version_list)
        right_widget = QWidget()
        right_widget.setLayout(right)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    def refresh(self):
        query = self.search_edit.text().strip()
        self.list_widget.clear()
        for meta in lib.search(query):
            star = "★ " if meta.get("favourite") else ""
            tags = f" [{', '.join(meta['tags'])}]" if meta.get("tags") else ""
            item = QListWidgetItem(f"{star}{meta['name']}{tags}")
            item.setData(Qt.UserRole, meta["id"])
            self.list_widget.addItem(item)

    def _selected_id(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _on_selection_changed(self, current, _previous):
        self.version_list.clear()
        if current is None:
            return
        strategy_id = current.data(Qt.UserRole)
        for v in lib.version_history(strategy_id):
            self.version_list.addItem(f"v{v['version']} -- {v['modified_at']}")

    def _on_load(self):
        strategy_id = self._selected_id()
        if strategy_id and self.on_load:
            self.on_load(strategy_id)

    def _on_favourite(self):
        strategy_id = self._selected_id()
        if not strategy_id:
            return
        meta = next((m for m in lib.list_all() if m["id"] == strategy_id), None)
        if meta:
            lib.set_favourite(strategy_id, not meta.get("favourite", False))
            self.refresh()

    def _on_rename(self):
        strategy_id = self._selected_id()
        if not strategy_id:
            return
        meta = next((m for m in lib.list_all() if m["id"] == strategy_id), None)
        new_name, ok = QInputDialog.getText(self, "Rename Strategy", "New name:", text=meta["name"] if meta else "")
        if ok and new_name.strip():
            lib.rename(strategy_id, new_name.strip())
            self.refresh()

    def _on_duplicate(self):
        strategy_id = self._selected_id()
        if strategy_id:
            lib.duplicate(strategy_id)
            self.refresh()

    def _on_delete(self):
        strategy_id = self._selected_id()
        if not strategy_id:
            return
        confirm = QMessageBox.question(self, "Delete Strategy", "Delete this strategy permanently?")
        if confirm == QMessageBox.Yes:
            lib.delete(strategy_id)
            self.refresh()
