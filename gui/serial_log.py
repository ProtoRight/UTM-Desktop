"""Scrollable serial log panel — shows raw lines from the Arduino."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton,
)

_MAX_LINES = 500


class SerialLog(QGroupBox):
    """Read-only, auto-scrolling plain-text log of all serial traffic."""

    def __init__(self, parent=None) -> None:
        super().__init__("Serial Log", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(_MAX_LINES)
        font = QFont("Consolas", 8)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._text.setFont(font)
        self._text.setFixedHeight(110)
        root.addWidget(self._text)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(55)
        clear_btn.clicked.connect(self._text.clear)
        btn_row.addWidget(clear_btn)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    def append(self, line: str) -> None:
        self._text.appendPlainText(line)
        self._text.moveCursor(QTextCursor.MoveOperation.End)
