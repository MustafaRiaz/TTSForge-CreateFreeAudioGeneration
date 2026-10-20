"""Bounded, searchable popup for large voice catalogs."""
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QVBoxLayout,
)
from app.ui.icons import icon


class VoiceComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Voice")
        self.popup = QFrame(self, Qt.WindowType.Popup)
        self.popup.setObjectName("voicePicker")
        layout = QVBoxLayout(self.popup)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search voices, languages, or models…")
        self.search.setAccessibleName("Search voices")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.results = QListWidget()
        self.results.setAccessibleName("Matching voices")
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.summary = QLabel()
        self.summary.setObjectName("muted")
        layout.addWidget(self.search)
        layout.addWidget(self.results, 1)
        layout.addWidget(self.summary)
        self.search.textChanged.connect(self._filter)
        self.results.itemClicked.connect(self._choose)
        self.search.installEventFilter(self)
        self.results.installEventFilter(self)

    def showPopup(self):  # noqa: N802
        self.search.clear()
        self._filter()
        screen = self.screen().availableGeometry()
        width = min(max(self.width(), 360), 620, screen.width() - 16)
        height = min(390, screen.height() - 16)
        below = self.mapToGlobal(QPoint(0, self.height() + 6))
        above = self.mapToGlobal(QPoint(0, -height - 6))
        y = below.y() if below.y() + height <= screen.bottom() else above.y()
        x = max(screen.left() + 8, min(below.x(), screen.right() - width - 8))
        y = max(screen.top() + 8, min(y, screen.bottom() - height - 8))
        self.popup.setGeometry(x, y, width, height)
        self.popup.show()
        self.search.setFocus(Qt.FocusReason.PopupFocusReason)

    def hidePopup(self):  # noqa: N802
        self.popup.hide()
        super().hidePopup()

    def _filter(self):
        query = self.search.text().casefold().split()
        self.results.clear()
        current = None
        total = 0
        for row in range(self.count()):
            if not self.itemData(row):
                continue
            total += 1
            text = self.itemText(row)
            if not all(token in text.casefold() for token in query):
                continue
            item = QListWidgetItem(icon("voice"), text)
            item.setData(Qt.ItemDataRole.UserRole, row)
            item.setToolTip(text)
            self.results.addItem(item)
            if row == self.currentIndex():
                current = item
        count = self.results.count()
        if current:
            self.results.setCurrentItem(current)
            self.results.scrollToItem(current)
        elif count:
            self.results.setCurrentRow(0)
        self.summary.setText(
            f"{count} of {total} voices · ↑ ↓ to navigate · Enter to select" if count
            else "No matching voices. Try another search." if total
            else "Install a voice in Model Manager to get started."
        )

    def _choose(self, item):
        if item is None:
            return
        row = item.data(Qt.ItemDataRole.UserRole)
        self.setCurrentIndex(row)
        self.activated.emit(row)
        self.hidePopup()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.hidePopup()
                self.setFocus(Qt.FocusReason.PopupFocusReason)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._choose(self.results.currentItem())
                return True
            if watched is self.search and key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                step = 1 if key == Qt.Key.Key_Down else -1
                row = max(0, min(self.results.count() - 1, self.results.currentRow() + step))
                self.results.setCurrentRow(row)
                return True
        return super().eventFilter(watched, event)
