"""Test threshold settings panel — user-adjustable completion/safety limits and chord window."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox, QFormLayout, QDoubleSpinBox, QSpinBox, QLabel,
    QVBoxLayout, QHBoxLayout, QComboBox,
)

import settings as cfg

_ARDUINO_NOTE = (
    "Hard-set in Arduino firmware.\n"
    "Will become configurable in a future firmware update."
)

# Standard chord presets: label → (eps1, eps2, standard_name)
CHORD_PRESETS: dict[str, tuple[float, float, str] | None] = {
    "ISO 178  (0.05 % → 0.25 %)":      (0.0005, 0.0025, "ISO 178"),
    "ASTM D790  (0.10 % → 0.30 %)":    (0.0010, 0.0030, "ASTM D790"),
    "ISO 527  (0.05 % → 0.25 %)":      (0.0005, 0.0025, "ISO 527"),
    "ISO 527 wide  (0.05 % → 0.50 %)": (0.0005, 0.0050, "ISO 527 wide"),
    "ASTM E111  (0.10 % → 0.30 %)":    (0.0010, 0.0030, "ASTM E111"),
    "Custom":                            None,
}


class SettingsPanel(QGroupBox):
    """Threshold and limit settings read at test-start time."""

    chord_changed = pyqtSignal()   # emitted when chord bounds change — trigger recalculation

    def __init__(self, parent=None) -> None:
        super().__init__("Test Settings", parent)
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(4)
        root.setContentsMargins(6, 6, 6, 6)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(5)

        def dsb(lo, hi, step, suffix, decimals=1) -> QDoubleSpinBox:
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setSingleStep(step)
            sb.setSuffix(suffix)
            sb.setDecimals(decimals)
            return sb

        def isb(lo, hi) -> QSpinBox:
            sb = QSpinBox()
            sb.setRange(lo, hi)
            return sb

        # --- Arduino-controlled limits (display only) ---
        self._travel = dsb(1, 500, 1, " mm")
        self._load   = dsb(1, 9999, 10, " kg")
        self._travel.setValue(cfg.get("travel_limit_mm"))
        self._load.setValue(cfg.get("load_limit_kg"))
        self._travel.setEnabled(False)
        self._load.setEnabled(False)
        self._travel.setToolTip(_ARDUINO_NOTE)
        self._load.setToolTip(_ARDUINO_NOTE)

        arduino_note = QLabel("⚠  Travel & load limits are set in Arduino firmware")
        arduino_note.setWordWrap(True)
        arduino_note.setStyleSheet("color: #888; font-size: 8pt; font-style: italic;")

        form.addRow("Travel limit:", self._travel)
        form.addRow("Load limit:", self._load)
        root.addLayout(form)
        root.addWidget(arduino_note)

        # --- Software fracture detection ---
        sep = QLabel("— Fracture detection (software) —")
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sep.setStyleSheet("color: #555; font-size: 8pt;")
        root.addWidget(sep)

        drop_form = QFormLayout()
        drop_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        drop_form.setSpacing(5)

        self._drop_pct = dsb(1, 99, 1, " %")
        self._drop_win = isb(3, 100)
        self._drop_pct.setValue(cfg.get("load_drop_pct"))
        self._drop_win.setValue(int(cfg.get("load_drop_window")))

        self._drop_pct.setToolTip(
            "Stop the test when load drops this percentage from\n"
            "the rolling peak within the sample window."
        )
        self._drop_win.setToolTip("Number of samples over which the drop is evaluated.")

        drop_form.addRow("Load drop  ≥:", self._drop_pct)
        drop_form.addRow("Over  N  samples:", self._drop_win)
        root.addLayout(drop_form)

        self._drop_pct.valueChanged.connect(lambda v: cfg.set("load_drop_pct", v))
        self._drop_win.valueChanged.connect(lambda v: cfg.set("load_drop_window", v))

        # --- Chord window ---
        chord_sep = QLabel("— Modulus chord window —")
        chord_sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chord_sep.setStyleSheet("color: #555; font-size: 8pt;")
        root.addWidget(chord_sep)

        chord_form = QFormLayout()
        chord_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        chord_form.setSpacing(5)

        self._chord_preset = QComboBox()
        for label in CHORD_PRESETS:
            self._chord_preset.addItem(label)
        chord_form.addRow("Standard / preset:", self._chord_preset)

        self._chord_eps1 = dsb(0.01, 10.0, 0.05, " %", decimals=3)
        self._chord_eps2 = dsb(0.01, 10.0, 0.05, " %", decimals=3)
        self._chord_eps1.setToolTip("Lower strain bound for chord modulus measurement.")
        self._chord_eps2.setToolTip("Upper strain bound for chord modulus measurement.")
        chord_form.addRow("Lower ε₁:", self._chord_eps1)
        chord_form.addRow("Upper ε₂:", self._chord_eps2)

        chord_note = QLabel(
            "Affects modulus calculation only. Change takes effect\n"
            "immediately on existing data (via Recalculate)."
        )
        chord_note.setWordWrap(True)
        chord_note.setStyleSheet("color: #666; font-size: 8pt; font-style: italic;")

        root.addLayout(chord_form)
        root.addWidget(chord_note)

        # Initialise from saved settings
        self._loading = True
        saved_std = cfg.get("chord_standard")
        preset_idx = 0
        for idx, (lbl, val) in enumerate(CHORD_PRESETS.items()):
            if val and val[2] == saved_std:
                preset_idx = idx
                break
            elif val is None and saved_std == "Custom":
                preset_idx = idx
                break
        self._chord_preset.setCurrentIndex(preset_idx)
        self._chord_eps1.setValue(float(cfg.get("chord_eps1")) * 100.0)
        self._chord_eps2.setValue(float(cfg.get("chord_eps2")) * 100.0)
        self._loading = False
        self._on_preset_changed(preset_idx)

        self._chord_preset.currentIndexChanged.connect(self._on_preset_changed)
        self._chord_eps1.valueChanged.connect(self._on_custom_changed)
        self._chord_eps2.valueChanged.connect(self._on_custom_changed)

    # ------------------------------------------------------------------
    def _on_preset_changed(self, idx: int) -> None:
        label = self._chord_preset.itemText(idx)
        preset = CHORD_PRESETS.get(label)
        is_custom = (preset is None)
        self._chord_eps1.setEnabled(is_custom)
        self._chord_eps2.setEnabled(is_custom)
        if not is_custom:
            self._loading = True
            self._chord_eps1.setValue(preset[0] * 100.0)
            self._chord_eps2.setValue(preset[1] * 100.0)
            self._loading = False
            cfg.set("chord_eps1", preset[0])
            cfg.set("chord_eps2", preset[1])
            cfg.set("chord_standard", preset[2])
            if not self._loading:
                self.chord_changed.emit()

    def _on_custom_changed(self) -> None:
        if self._loading:
            return
        eps1 = self._chord_eps1.value() / 100.0
        eps2 = self._chord_eps2.value() / 100.0
        if eps2 <= eps1:
            return
        cfg.set("chord_eps1", eps1)
        cfg.set("chord_eps2", eps2)
        cfg.set("chord_standard", "Custom")
        self.chord_changed.emit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def travel_limit_mm(self) -> float:
        return self._travel.value()

    @property
    def load_limit_kg(self) -> float:
        return self._load.value()

    @property
    def load_drop_pct(self) -> float:
        return self._drop_pct.value()

    @property
    def load_drop_window(self) -> int:
        return self._drop_win.value()
