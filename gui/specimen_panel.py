"""Specimen information panel — material name, sample ID, geometry, dimensions."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QDoubleSpinBox, QStackedWidget,
    QSizePolicy,
)

from calculations import SpecimenData
from gui.geometry_preview import GeometryPreview


class SpecimenPanel(QGroupBox):
    """Left-panel section for entering specimen metadata and dimensions."""

    def __init__(self, parent=None) -> None:
        super().__init__("Specimen", parent)
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # --- Identity ---
        id_form = QFormLayout()
        id_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        id_form.setSpacing(4)
        self._material = QLineEdit()
        self._material.setPlaceholderText("e.g. PLA, Aluminium 6061")
        self._sample_id = QLineEdit()
        self._sample_id.setPlaceholderText("e.g. Sample_01")
        id_form.addRow("Material:", self._material)
        id_form.addRow("Sample ID:", self._sample_id)
        root.addLayout(id_form)

        # --- Test type ---
        tt_row = QHBoxLayout()
        tt_row.addWidget(QLabel("Test type:"))
        self._test_type = QComboBox()
        self._test_type.addItems(["3-Point Bend", "Tensile"])
        tt_row.addWidget(self._test_type, 1)
        root.addLayout(tt_row)

        # --- Cross-section selector ---
        cs_row = QHBoxLayout()
        cs_row.addWidget(QLabel("Cross-section:"))
        self._cs_type = QComboBox()
        self._cs_type.addItems(["Rectangular", "Circular (solid)", "Hollow tube"])
        cs_row.addWidget(self._cs_type, 1)
        root.addLayout(cs_row)

        # --- Geometry preview ---
        self._preview = GeometryPreview()
        root.addWidget(self._preview)

        # --- Dimension fields (stacked by geometry type) ---
        self._dim_stack = QStackedWidget()
        self._dim_stack.addWidget(self._build_rect_dims())      # index 0
        self._dim_stack.addWidget(self._build_circular_dims())  # index 1
        self._dim_stack.addWidget(self._build_hollow_dims())    # index 2
        root.addWidget(self._dim_stack)

        # --- Test-specific field (span or gauge length) ---
        self._test_specific_stack = QStackedWidget()
        self._test_specific_stack.addWidget(self._build_span_field())        # 0: 3PT
        self._test_specific_stack.addWidget(self._build_gauge_field())       # 1: tensile
        root.addWidget(self._test_specific_stack)

        # --- Connections ---
        self._cs_type.currentIndexChanged.connect(self._on_cs_changed)
        self._test_type.currentIndexChanged.connect(self._on_test_changed)

    # ------------------------------------------------------------------
    # Sub-form builders
    # ------------------------------------------------------------------

    def _spinbox(self, suffix=" mm", decimals=2, max_val=9999.0) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setDecimals(decimals)
        sb.setRange(0.0, max_val)
        sb.setSuffix(suffix)
        sb.setSingleStep(0.5)
        return sb

    def _form(self) -> tuple[QWidget, QFormLayout]:
        w = QWidget()
        f = QFormLayout(w)
        f.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        f.setContentsMargins(0, 0, 0, 0)
        f.setSpacing(4)
        return w, f

    def _build_rect_dims(self) -> QWidget:
        w, f = self._form()
        self._rect_b = self._spinbox()
        self._rect_d = self._spinbox()
        f.addRow("Width  b:", self._rect_b)
        f.addRow("Thickness  d:", self._rect_d)
        return w

    def _build_circular_dims(self) -> QWidget:
        w, f = self._form()
        self._circ_d = self._spinbox()
        f.addRow("Diameter  d:", self._circ_d)
        return w

    def _build_hollow_dims(self) -> QWidget:
        w, f = self._form()
        self._hol_D = self._spinbox()
        self._hol_d = self._spinbox()
        f.addRow("Outer dia.  D:", self._hol_D)
        f.addRow("Inner dia.  d:", self._hol_d)
        return w

    def _build_span_field(self) -> QWidget:
        w, f = self._form()
        self._span = self._spinbox()
        f.addRow("Support span  L:", self._span)
        return w

    def _build_gauge_field(self) -> QWidget:
        w, f = self._form()
        self._gauge = self._spinbox()
        f.addRow("Gauge length  L₀:", self._gauge)
        return w

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_cs_changed(self, idx: int) -> None:
        self._dim_stack.setCurrentIndex(idx)
        geoms = ["rectangular", "circular", "hollow"]
        self._preview.set_geometry(geoms[idx])

    def _on_test_changed(self, idx: int) -> None:
        self._test_specific_stack.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_specimen_data(self) -> SpecimenData:
        """Collect all fields into a SpecimenData instance."""
        cs_map = {0: "rectangular", 1: "circular", 2: "hollow"}
        tt_map = {0: "3PT", 1: "TENSILE"}
        cs = cs_map[self._cs_type.currentIndex()]
        tt = tt_map[self._test_type.currentIndex()]

        sd = SpecimenData(
            material=self._material.text().strip(),
            sample_id=self._sample_id.text().strip(),
            test_type=tt,
            geometry=cs,
        )
        if cs == "rectangular":
            sd.width_mm = self._rect_b.value()
            sd.thickness_mm = self._rect_d.value()
        elif cs == "circular":
            sd.diameter_mm = self._circ_d.value()
        elif cs == "hollow":
            sd.outer_dia_mm = self._hol_D.value()
            sd.inner_dia_mm = self._hol_d.value()

        if tt == "3PT":
            sd.span_mm = self._span.value()
        else:
            sd.gauge_length_mm = self._gauge.value()

        return sd
