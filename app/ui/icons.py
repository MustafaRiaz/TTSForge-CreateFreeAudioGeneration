"""Original 24-unit outline icons, rendered as vectors in the current theme."""
from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QIconEngine, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QPushButton

# Shared grid, rounded caps and a consistent 1.7-unit stroke.
PATHS = {
    "studio": '<path d="M4 10v4m4-8v12m4-15v18m4-15v12m4-8v4"/>',
    "queue": '<path d="M4 6h12M4 12h9M4 18h9m5-6v8m-4-4h8"/>',
    "folder": '<path d="M3 7V5h7l2 2h9v13H3z"/>',
    "voice": '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6 11v1a6 6 0 0 0 12 0v-1M12 18v3m-3 0h6"/>',
    "history": '<path d="M3 4v5h5m-5 0a9 9 0 1 1 0 6M12 7v5l3 2"/>',
    "sliders": '<path d="M4 7h4m4 0h8M4 17h10m4 0h2"/><circle cx="10" cy="7" r="2"/><circle cx="16" cy="17" r="2"/>',
    "batch": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "settings": '<path d="m9 3-1 3-3 1 1 3-2 2 2 2-1 3 3 1 1 3h6l1-3 3-1-1-3 2-2-2-2 1-3-3-1-1-3z"/><circle cx="12" cy="12" r="3"/>',
    "model": '<path d="m12 3 9 5v9l-9 5-9-5V8zm0 10 9-5M12 13 3 8m9 5v9M7.5 5.5l9 5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
    "play": '<path d="m8 4 12 8-12 8z"/>',
    "pause": '<path d="M8 5v14M16 5v14"/>',
    "stop": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "save": '<path d="M4 3h13l4 4v14H3V3zm3 0v6h10V3M7 21v-8h10v8"/>',
    "import": '<path d="M12 3v12m-4-4 4 4 4-4M4 15v6h16v-6"/>',
    "export": '<path d="M12 15V3m-4 4 4-4 4 4M4 15v6h16v-6"/>',
    "focus": '<path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6"/>',
    "refresh": '<path d="M20 4v5h-5M4 20v-5h5m11-6a8 8 0 0 0-14-3m-2 9a8 8 0 0 0 14 3"/>',
    "text": '<path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
    "trash": '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
    "plus": '<path d="M12 4v16M4 12h16"/>',
    "check": '<path d="m4 12 5 5L20 6"/>',
    "close": '<path d="m5 5 14 14M19 5 5 19"/>',
    "undo": '<path d="M8 4 3 9l5 5M3 9h11a6 6 0 0 1 0 12"/>',
    "redo": '<path d="m16 4 5 5-5 5m5-5H10a6 6 0 0 0 0 12"/>',
    "star": '<path d="m12 3 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z"/>',
    "up": '<path d="M12 20V4m-7 7 7-7 7 7"/>',
    "down": '<path d="M12 4v16m-7-7 7 7 7-7"/>',
}

class OutlineIconEngine(QIconEngine):
    def __init__(self, name, primary=False):
        super().__init__()
        self.name, self.primary = name, primary

    def clone(self):
        return OutlineIconEngine(self.name, self.primary)

    def paint(self, painter, rect, mode, state):
        dark = QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128
        color = '#bac3d2' if dark else '#556177'
        if self.primary:
            color = '#ffffff'
        if state == QIcon.State.On:
            color = '#a18bff' if dark else '#6952ce'
        if mode == QIcon.Mode.Disabled:
            color = '#626c7c' if dark else '#9ba4b4'
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{PATHS[self.name]}</svg>'
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        side = min(rect.width(), rect.height())
        target = QRectF(rect.x()+(rect.width()-side)/2, rect.y()+(rect.height()-side)/2, side, side)
        renderer.render(painter, target)

    def pixmap(self, size, mode, state):
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        self.paint(painter, pixmap.rect(), mode, state)
        painter.end()
        return pixmap


def icon(name, primary=False):
    return QIcon(OutlineIconEngine(name, primary))


NAV_ICONS = dict(zip(
    ('Studio', 'Queue', 'Projects', 'Voices', 'History', 'Audio Tools', 'Batch', 'Settings', 'Model Manager', 'About'),
    ('studio', 'queue', 'folder', 'voice', 'history', 'sliders', 'batch', 'settings', 'model', 'info'),
))


def command_icon(text):
    text = text.lower()
    for prefixes, name in (
        (('generate', 'batch generate', 'regenerate'), 'studio'),
        (('play', 'replay', 'preview', 'resume', 'test pronunciation'), 'play'),
        (('pause', 'insert 500'), 'pause'), (('stop',), 'stop'),
        (('save',), 'save'), (('import', 'download', 'paste'), 'import'),
        (('export',), 'export'), (('browse', 'open', 'reference'), 'folder'),
        (('focus', 'exit focus'), 'focus'), (('retry', 'refresh', 'convert'), 'refresh'),
        (('script tools', 'normalize', 'adjust', 'fade', 'a/b', 'merge'), 'sliders'),
        (('find', 'detect'), 'search'), (('delete', 'clear', 'remove'), 'trash'),
        (('add to queue',), 'queue'), (('new', 'add'), 'plus'),
        (('verify', 'use in studio'), 'check'), (('cancel',), 'close'),
        (('undo',), 'undo'), (('redo',), 'redo'), (('toggle favorite',), 'star'),
        (('move up',), 'up'), (('move down',), 'down'), (('edit chapters',), 'text'),
    ):
        if text.startswith(prefixes):
            return name
    return None


def decorate_buttons(root):
    """Keep text labels for clarity; add visual cues without new dependencies."""
    for button in root.findChildren(QPushButton):
        name = NAV_ICONS.get(button.text()) if button.objectName() == 'navBtn' else command_icon(button.text())
        if name:
            button.setIcon(icon(name, button.objectName() in ('primaryButton', 'dangerButton')))
            button.setIconSize(QSize(18, 18))
        if button.menu():
            for action in button.menu().actions():
                name = command_icon(action.text())
                if name:
                    action.setIcon(icon(name))
