"""Serial log panel: scrollable raw output + manual serial input field."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QLineEdit, QLabel,
)

_MAX_LINES = 500


class SerialLog(QGroupBox):
    """Read-only auto-scrolling log of all serial traffic, plus a manual send field."""

    command_entered = pyqtSignal(str)   # emitted when user sends a manual command

    def __init__(self, parent=None) -> None:
        super().__init__("Serial Log", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Log text area
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(_MAX_LINES)
        font = QFont("Consolas", 8)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._text.setFont(font)
        root.addWidget(self._text, 1)

        # Bottom row: manual input + send + clear
        bottom_row = QHBoxLayout()
        bottom_row.addWidget(QLabel("Send:"))
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type command and press Enter or click Send…")
        self._input.returnPressed.connect(self._on_send)
        bottom_row.addWidget(self._input, 1)
        send_btn = QPushButton("Send")
        send_btn.setFixedWidth(50)
        send_btn.clicked.connect(self._on_send)
        bottom_row.addWidget(send_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(50)
        clear_btn.clicked.connect(self._text.clear)
        bottom_row.addWidget(clear_btn)
        root.addLayout(bottom_row)

    def _on_send(self) -> None:
        text = self._input.text().strip()
        if text:
            self.command_entered.emit(text)
            self._input.clear()

    # ------------------------------------------------------------------
    def append(self, line: str) -> None:
        self._text.appendPlainText(line)
        self._text.moveCursor(QTextCursor.MoveOperation.End)
