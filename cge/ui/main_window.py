from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QPixmap
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QComboBox, QListWidget, QListWidgetItem, QMessageBox,
    QGroupBox, QFormLayout, QRadioButton, QButtonGroup, QSplitter,
    QSpinBox, QTabWidget, QLineEdit, QScrollArea
)

from PIL.ImageQt import ImageQt

from ..core.schema import SheetSpec
from ..core.catalog import scan_catalog, Catalog, item_variant_supports_body, get_body_base_paths
from ..core.util_images import make_checkerboard
from ..core.project import CGEProject, SlotSelection
from ..core.compositor import resolve_layers, compose_frame
from ..core.exporters_png import export_png_sheet
from ..core.exporters_gif import export_gif_actions
from ..core.exporters_apng import export_apng_actions
from ..core.util_paths import safe_filename


def _norm(s: str) -> str:
    return (s or "").strip().lower()


_SLOT_EMOJI = {
    "back": "🎒",
    "ears": "👂",
    "eyes": "👁️",
    "face": "😊",
    "facial_hair": "🧔",
    "feet": "👟",
    "hair": "💇",
    "hands": "✋",
    "head": "🧢",
    "items": "📦",
    "jewelry": "💎",
    "legs": "👖",
    "nose": "👃",
    "torso": "👕",
}

_ALL_COSMETICS_SLOTS = ("ears", "eyes", "face", "facial_hair", "hair", "hands", "jewelry", "nose")
_ALL_WEARABLES_SLOTS = ("back", "feet", "hands", "head", "items", "legs", "torso")


class MainWindow(QMainWindow):
    def __init__(self, assets_root: Path):
        super().__init__()
        self.setWindowTitle("GandalfHardcore Character Generator")
        self.resize(1200, 800)

        self.project_path: Optional[Path] = None
        self.project = CGEProject()
        self.sheet_spec = SheetSpec.canonical()

        self.assets_root = Path(assets_root).resolve()
        self.catalog: Catalog = scan_catalog(self.assets_root)
        self._undo_history: list = []

        # Animation timer for preview
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._on_anim_tick)

        self._build_ui()
        self._populate_bodies_dropdown()
        self.on_new_project()

    def closeEvent(self, e):
        try:
            self.anim_timer.stop()
        except Exception:
            pass
        super().closeEvent(e)

    def _build_ui(self):
        # Menu
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")

        act_new = QAction("&New", self)
        act_new.triggered.connect(self.on_new_project)
        file_menu.addAction(act_new)

        act_load = QAction("&Load .cge...", self)
        act_load.triggered.connect(self.on_load_project)
        file_menu.addAction(act_load)

        act_save = QAction("&Save", self)
        act_save.triggered.connect(self.on_save_project)
        file_menu.addAction(act_save)

        act_saveas = QAction("Save &As...", self)
        act_saveas.triggered.connect(self.on_saveas_project)
        file_menu.addAction(act_saveas)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter, 1)

        # Left panel
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(8, 8, 8, 8)

        grp = QGroupBox("Project")
        form = QFormLayout(grp)
        self.cmb_body = QComboBox()
        self.cmb_body.currentTextChanged.connect(self.on_body_changed)
        form.addRow("Body:", self.cmb_body)

        self.cmb_body_base = QComboBox()
        self.cmb_body_base.currentTextChanged.connect(self.on_body_base_changed)
        form.addRow("Base:", self.cmb_body_base)

        self.dir_group = QButtonGroup(self)
        self.rb_left = QRadioButton("Left")
        self.rb_right = QRadioButton("Right")
        self.rb_left.setChecked(True)
        self.dir_group.addButton(self.rb_left)
        self.dir_group.addButton(self.rb_right)
        self.rb_left.toggled.connect(self.on_direction_changed)
        self.rb_right.toggled.connect(self.on_direction_changed)

        dir_row = QWidget()
        dir_l = QHBoxLayout(dir_row)
        dir_l.setContentsMargins(0, 0, 0, 0)
        dir_l.addWidget(self.rb_left)
        dir_l.addWidget(self.rb_right)
        form.addRow("Facing:", dir_row)
        left_l.addWidget(grp)

        btn_row = QWidget()
        btn_l = QHBoxLayout(btn_row)
        btn_l.setContentsMargins(0, 0, 0, 0)
        self.btn_new = QPushButton("New")
        self.btn_load = QPushButton("Load")
        self.btn_save = QPushButton("Save")
        self.btn_new.clicked.connect(self.on_new_project)
        self.btn_load.clicked.connect(self.on_load_project)
        self.btn_save.clicked.connect(self.on_save_project)
        btn_l.addWidget(self.btn_new)
        btn_l.addWidget(self.btn_load)
        btn_l.addWidget(self.btn_save)
        left_l.addWidget(btn_row)

        grp_prev = QGroupBox("Preview Frame")
        prev_form = QFormLayout(grp_prev)

        self.cmb_action = QComboBox()
        for a in self.sheet_spec.row_actions:
            self.cmb_action.addItem(a.action)
        self.cmb_action.currentTextChanged.connect(self._on_action_changed)
        prev_form.addRow("Action:", self.cmb_action)

        self.spin_frame = QSpinBox()
        self.spin_frame.setRange(0, 9)
        self.spin_frame.valueChanged.connect(self._refresh_preview)
        prev_form.addRow("Frame:", self.spin_frame)

        # Start/Stop animation
        self.btn_start_anim = QPushButton("Start")
        self.btn_stop_anim = QPushButton("Stop")
        self.btn_start_anim.clicked.connect(self.on_start_animation)
        self.btn_stop_anim.clicked.connect(self.on_stop_animation)
        anim_row = QWidget()
        anim_l = QHBoxLayout(anim_row)
        anim_l.setContentsMargins(0, 0, 0, 0)
        anim_l.addWidget(self.btn_start_anim)
        anim_l.addWidget(self.btn_stop_anim)
        prev_form.addRow("Animation:", anim_row)

        left_l.addWidget(grp_prev)

        grp_categories = QGroupBox("Categories")
        categories_l = QVBoxLayout(grp_categories)
        categories_l.setContentsMargins(6, 6, 6, 6)
        self.categories_tabs = QTabWidget()
        self.cosmetics_buttons_container = QWidget()
        self.cosmetics_buttons_layout = QVBoxLayout(self.cosmetics_buttons_container)
        self.cosmetics_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.cosmetics_buttons_layout.setSpacing(4)
        cosmetics_scroll = QScrollArea()
        cosmetics_scroll.setWidget(self.cosmetics_buttons_container)
        cosmetics_scroll.setWidgetResizable(True)
        cosmetics_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.categories_tabs.addTab(cosmetics_scroll, "Cosmetics")
        self.wearables_buttons_container = QWidget()
        self.wearables_buttons_layout = QVBoxLayout(self.wearables_buttons_container)
        self.wearables_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.wearables_buttons_layout.setSpacing(4)
        wearables_scroll = QScrollArea()
        wearables_scroll.setWidget(self.wearables_buttons_container)
        wearables_scroll.setWidgetResizable(True)
        wearables_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.categories_tabs.addTab(wearables_scroll, "Wearables")
        categories_l.addWidget(self.categories_tabs, 1)
        self.category_button_group = QButtonGroup(self)
        self.category_button_group.setExclusive(True)
        left_l.addWidget(grp_categories, 1)

        splitter.addWidget(left)

        # Middle panel
        mid = QWidget()
        mid_l = QVBoxLayout(mid)
        mid_l.setContentsMargins(8, 8, 8, 8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search items…")
        self.search.textChanged.connect(self._refresh_catalog_ui)
        mid_l.addWidget(self.search)

        self.tabs_slots = QTabWidget()
        self.tabs_slots.tabBar().hide()
        mid_l.addWidget(self.tabs_slots, 1)

        self.btn_undo = QPushButton("Undo last cosmetic/wearable")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self._undo_last)
        mid_l.addWidget(self.btn_undo)

        splitter.addWidget(mid)

        # Right panel
        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(8, 8, 8, 8)

        self.preview = QLabel("No preview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(340)
        self.preview.setStyleSheet("QLabel { background:#111; color:#ddd; border:1px solid #333; }")
        right_l.addWidget(self.preview)

        grp_export = QGroupBox("Export")
        exp_l = QVBoxLayout(grp_export)

        self.btn_export_png = QPushButton("Export PNG Sheet")
        self.btn_export_png.clicked.connect(self.on_export_png)
        self.btn_export_gif = QPushButton("Export GIFs (per action)")
        self.btn_export_gif.clicked.connect(self.on_export_gif)
        self.btn_export_apng = QPushButton("Export APNGs (per action)")
        self.btn_export_apng.clicked.connect(self.on_export_apng)

        exp_l.addWidget(self.btn_export_png)
        exp_l.addWidget(self.btn_export_gif)
        exp_l.addWidget(self.btn_export_apng)

        fps_box = QGroupBox("FPS (per action)")
        fps_form = QFormLayout(fps_box)
        self.fps_spins: Dict[str, QSpinBox] = {}
        defaults = [("idle", 8), ("walk", 12), ("run", 16), ("jump", 12), ("fall", 12), ("swing", 14), ("die", 10)]
        for action, default in defaults:
            sp = QSpinBox()
            sp.setRange(1, 60)
            sp.setValue(default)
            sp.valueChanged.connect(self._restart_anim_if_running)
            self.fps_spins[action] = sp
            fps_form.addRow(action, sp)
        exp_l.addWidget(fps_box)

        right_l.addWidget(grp_export)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)

    def _populate_bodies_dropdown(self):
        self.cmb_body.blockSignals(True)
        self.cmb_body.clear()
        for body_id in sorted(self.catalog.bodies.keys()):
            self.cmb_body.addItem(body_id)
        self.cmb_body.blockSignals(False)

    def _populate_base_dropdown(self):
        self.cmb_body_base.blockSignals(True)
        self.cmb_body_base.clear()
        body = _norm(self.cmb_body.currentText().strip())
        b = self.catalog.bodies.get(body)
        self.cmb_body_base.addItem("base")
        if b and b.base_variants:
            for vid in sorted(b.base_variants.keys()):
                self.cmb_body_base.addItem(vid)
        self.cmb_body_base.blockSignals(False)

    def _get_base_paths(self):
        body = _norm(self.cmb_body.currentText().strip())
        base = self.cmb_body_base.currentText().strip() or "base"
        return get_body_base_paths(self.catalog, body, base)

    def _set_status(self, msg: str):
        self.statusBar().showMessage(msg.replace("\n", "  "))

    def _on_action_changed(self):
        self._sync_action_frame_limits()
        self._restart_anim_if_running()
        self._refresh_preview()

    def _restart_anim_if_running(self):
        if self.anim_timer.isActive():
            self.on_start_animation()

    def on_start_animation(self):
        action = self.cmb_action.currentText()
        sp = self.fps_spins.get(action)
        fps = sp.value() if sp else 12
        interval_ms = int(1000 / max(1, fps))
        self.anim_timer.start(interval_ms)

    def on_stop_animation(self):
        self.anim_timer.stop()

    def _on_anim_tick(self):
        action = self.cmb_action.currentText()
        try:
            row = self.sheet_spec.row_for_action(action)
            maxf = max(1, self.sheet_spec.frames_for_row(row))
        except Exception:
            maxf = 1
        self.spin_frame.setValue((self.spin_frame.value() + 1) % maxf)

    def on_new_project(self):
        self.on_stop_animation()
        self.project_path = None
        self.project = CGEProject()
        self._undo_history.clear()
        self.catalog = scan_catalog(self.assets_root)
        self._populate_bodies_dropdown()
        if self.catalog.bodies:
            self.project.body = sorted(self.catalog.bodies.keys())[0]
            self.cmb_body.setCurrentText(self.project.body)
        self.project.direction = "left"
        self.project.body_base = "base"
        self.rb_left.setChecked(True)
        all_slots = sorted(set(_ALL_COSMETICS_SLOTS + _ALL_WEARABLES_SLOTS) | set(self.catalog.all_slots()))
        self.project.slots = {slot: None for slot in all_slots}
        self._populate_base_dropdown()
        self._refresh_catalog_ui()
        self._refresh_preview()
        self._set_status("New project.")

    def on_body_changed(self, body_id: str):
        self.project.body = _norm(body_id)
        self._populate_base_dropdown()
        self._refresh_catalog_ui()
        self._refresh_preview()

    def on_body_base_changed(self, base_id: str):
        self.project.body_base = (base_id or "base").strip().lower()
        self._refresh_preview()

    def on_direction_changed(self):
        self.project.direction = "right" if self.rb_right.isChecked() else "left"
        self._refresh_preview()

    def on_load_project(self):
        self.on_stop_animation()
        path_str, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "Project (*.cge)")
        if not path_str:
            return
        path = Path(path_str)
        try:
            self.project = CGEProject.load(path)
            self.project_path = path
            self._undo_history.clear()
            self.assets_root = self.project.resolved_assets_root(self.project_path)
            self.catalog = scan_catalog(self.assets_root)
            self.sheet_spec = self.project.sheet or SheetSpec.canonical()
            self._populate_bodies_dropdown()

            body_norm = _norm(self.project.body)
            if body_norm in self.catalog.bodies:
                self.cmb_body.setCurrentText(body_norm)
                self.project.body = body_norm

            self._populate_base_dropdown()
            base_norm = _norm(self.project.body_base)
            if self.cmb_body_base.findText(base_norm, Qt.MatchFlag.MatchFixedString) >= 0:
                self.cmb_body_base.setCurrentText(base_norm)
            self.project.body_base = base_norm or "base"

            self.rb_right.setChecked(self.project.direction == "right")
            self.rb_left.setChecked(self.project.direction != "right")

            self._refresh_catalog_ui()
            self._refresh_preview()
            self._set_status(f"Loaded: {path.name}")
        except Exception as e:
            QMessageBox.critical(self, "Load Failed", f"Could not load project:\n{e}")

    def on_save_project(self):
        if self.project_path is None:
            return self.on_saveas_project()
        try:
            self._sync_project_from_ui()
            self.project.save(self.project_path)
            self._set_status(f"Saved: {self.project_path.name}")
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Could not save project:\n{e}")

    def on_saveas_project(self):
        path_str, _ = QFileDialog.getSaveFileName(self, "Save Project As", "", "Project (*.cge)")
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != ".cge":
            path = path.with_suffix(".cge")
        try:
            self._sync_project_from_ui()
            self.project.save(path)
            self.project_path = path
            self._set_status(f"Saved: {path.name}")
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Could not save project:\n{e}")

    def _sync_project_from_ui(self):
        if self.project_path is not None:
            try:
                self.project.assets_root = str(Path(self.assets_root).relative_to(self.project_path.parent))
            except Exception:
                self.project.assets_root = str(self.assets_root)
        else:
            self.project.assets_root = str(self.assets_root)

        self.project.sheet = self.sheet_spec
        self.project.body = _norm(self.cmb_body.currentText().strip())
        self.project.body_base = (self.cmb_body_base.currentText().strip() or "base").lower()
        self.project.direction = "right" if self.rb_right.isChecked() else "left"

    def _project_name_guess(self) -> str:
        return self.project_path.stem if self.project_path else "cge_export"

    def _choose_export_dir(self) -> Optional[Path]:
        path_str = QFileDialog.getExistingDirectory(self, "Choose Export Folder")
        return Path(path_str) if path_str else None

    def _ensure_ready_for_export(self) -> bool:
        if not self.catalog.bodies:
            QMessageBox.warning(self, "No Bodies", "No bodies found in assets/bodies/* (need base.png).")
            return False
        if not self.project.body or self.project.body not in self.catalog.bodies:
            QMessageBox.warning(self, "No Body Selected", "Select a body before exporting.")
            return False
        return True

    def _resolved_layers_for_current(self):
        selections = {}
        for slot, sel in self.project.slots.items():
            selections[slot] = None if sel is None else (sel.item, sel.variant)
        return resolve_layers(self.catalog, self.project.body, selections)

    def _remove_slot(self, slot: str):
        self.project.slots[slot] = None
        self._refresh_preview()

    def _apply_selection(self, slot: str, item_id: str, variant_id: str):
        self._undo_history.append((slot, self.project.slots.get(slot)))
        self.project.slots[slot] = SlotSelection(item=item_id, variant=variant_id)
        self._apply_excludes_for(slot, item_id)
        self.btn_undo.setEnabled(True)
        QTimer.singleShot(0, self._refresh_after_apply)

    def _undo_last(self):
        if not self._undo_history:
            return
        slot, prev = self._undo_history.pop()
        self.project.slots[slot] = prev
        self.btn_undo.setEnabled(len(self._undo_history) > 0)
        current_slot = self.tabs_slots.tabText(self.tabs_slots.currentIndex()) if self.tabs_slots.count() else None
        self._refresh_catalog_ui(preserve_slot=current_slot)
        self._refresh_preview()

    def _refresh_after_apply(self):
        current_slot = self.tabs_slots.tabText(self.tabs_slots.currentIndex()) if self.tabs_slots.count() else None
        self._refresh_catalog_ui(preserve_slot=current_slot)
        self._refresh_preview()

    def _apply_excludes_for(self, slot: str, item_id: str):
        item = self.catalog.items.get(slot, {}).get(item_id)
        if not item or not item.excludes:
            return
        excluded = set(item.excludes)
        for s, sel in list(self.project.slots.items()):
            if sel and sel.item in excluded:
                self.project.slots[s] = None

    def _make_slot_tab(self, slot: str):
        """Build a single slot tab with one list of all options; click to apply."""
        tab = QWidget()
        tab_l = QVBoxLayout(tab)
        tab_l.setContentsMargins(6, 6, 6, 6)

        lst_options = QListWidget()

        def _on_option_clicked():
            sel = lst_options.currentItem()
            if not sel:
                return
            data = sel.data(Qt.ItemDataRole.UserRole)
            if data is None:
                if self.project.slots.get(slot) is None:
                    return
                self._undo_history.append((slot, self.project.slots.get(slot)))
                self.project.slots[slot] = None
                self.btn_undo.setEnabled(True)
                QTimer.singleShot(0, self._refresh_after_apply)
                return
            item_id, variant_id = data
            cur = self.project.slots.get(slot)
            if cur and cur.item == item_id and cur.variant == variant_id:
                return
            self._apply_selection(slot, item_id, variant_id)

        lst_options.currentItemChanged.connect(lambda *_: _on_option_clicked())

        tab_l.addWidget(lst_options, 1)
        return tab, lst_options

    def _refresh_catalog_ui(self, preserve_slot: Optional[str] = None):
        self.tabs_slots.clear()
        self.tabs_slots.tabBar().hide()

        for btn in self.category_button_group.buttons():
            self.category_button_group.removeButton(btn)
        for layout in (self.cosmetics_buttons_layout, self.wearables_buttons_layout):
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        search = self.search.text().strip().lower()
        current_body = _norm(self.cmb_body.currentText().strip())

        catalog_slots = set(self.catalog.all_slots())
        all_slots = sorted(set(_ALL_COSMETICS_SLOTS + _ALL_WEARABLES_SLOTS) | catalog_slots)

        for idx, slot in enumerate(all_slots):
            tab, lst_options = self._make_slot_tab(slot)

            none_item = QListWidgetItem("— None —")
            none_item.setData(Qt.ItemDataRole.UserRole, None)
            lst_options.addItem(none_item)

            cur = self.project.slots.get(slot)
            lst_options.blockSignals(True)
            for item_id, item in sorted(self.catalog.items.get(slot, {}).items()):
                if search and (search not in item_id.lower() and search not in " ".join(item.tags).lower()):
                    continue
                if current_body and item.variants:
                    if not any(item_variant_supports_body(item, vid, current_body) for vid in item.variants.keys()):
                        continue
                for variant_id in sorted(item.variants.keys()):
                    if current_body and not item_variant_supports_body(item, variant_id, current_body):
                        continue
                    if len(item.variants) == 1 and variant_id == "default":
                        label = item_id
                    else:
                        label = f"{item_id}: {variant_id}"
                    opt = QListWidgetItem(label)
                    opt.setData(Qt.ItemDataRole.UserRole, (item_id, variant_id))
                    lst_options.addItem(opt)
                    if cur and cur.item == item_id and cur.variant == variant_id:
                        lst_options.setCurrentItem(opt)
            if cur is None:
                lst_options.setCurrentRow(0)
            lst_options.blockSignals(False)

            self.tabs_slots.addTab(tab, slot)

            slot_items = self.catalog.items.get(slot, {})
            if slot in _ALL_COSMETICS_SLOTS:
                source = "cosmetics"
            elif slot in _ALL_WEARABLES_SLOTS:
                source = "wearables"
            else:
                source = "cosmetics" if slot_items and next(iter(slot_items.values())).source == "cosmetics" else "wearables"
            layout = self.cosmetics_buttons_layout if source == "cosmetics" else self.wearables_buttons_layout

            emoji = _SLOT_EMOJI.get(slot, "📦")
            btn = QPushButton(f"{emoji}  {slot.replace('_', ' ').title()}")
            btn.setCheckable(True)
            btn.setProperty("slot", slot)
            if preserve_slot == slot or (preserve_slot is None and idx == 0):
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, s=slot: self._show_category(s))
            self.category_button_group.addButton(btn)
            layout.addWidget(btn)

        if preserve_slot:
            for i in range(self.tabs_slots.count()):
                if self.tabs_slots.tabText(i) == preserve_slot:
                    self.tabs_slots.setCurrentIndex(i)
                    break
        else:
            self.tabs_slots.setCurrentIndex(0)
        self._sync_action_frame_limits()

    def _show_category(self, slot: str):
        for i in range(self.tabs_slots.count()):
            if self.tabs_slots.tabText(i) == slot:
                self.tabs_slots.setCurrentIndex(i)
                break

    def _sync_action_frame_limits(self):
        action = self.cmb_action.currentText()
        try:
            row = self.sheet_spec.row_for_action(action)
            maxf = max(0, self.sheet_spec.frames_for_row(row) - 1)
            self.spin_frame.setMaximum(maxf)
            if self.spin_frame.value() > maxf:
                self.spin_frame.setValue(0)
        except Exception:
            self.spin_frame.setMaximum(9)

    def _refresh_preview(self):
        if not self.catalog.bodies:
            self.preview.setText("No bodies found.\nCreate assets/bodies/<body_id>/base.png")
            return

        body = _norm(self.cmb_body.currentText().strip())
        if not body or body not in self.catalog.bodies:
            self.preview.setText("Select a body.")
            return

        self.project.body = body
        self._sync_action_frame_limits()

        action = self.cmb_action.currentText()
        row = self.sheet_spec.row_for_action(action)
        col = self.spin_frame.value()

        layers = self._resolved_layers_for_current()
        base_left, base_right = self._get_base_paths()

        img = compose_frame(
            sheet_spec=self.sheet_spec,
            base_left=base_left,
            base_right=base_right,
            layers=layers,
            direction=self.project.direction,
            row=row,
            col=col,
            use_explicit_right=bool(self.project.options.get("use_explicit_right_if_available", True)),
            flip_fallback=bool(self.project.options.get("fallback_flip_for_right", True)),
        )
        cell_w, cell_h = self.sheet_spec.cell_w, self.sheet_spec.cell_h
        checkerboard = make_checkerboard(cell_w, cell_h)
        checkerboard.alpha_composite(img)
        qim = ImageQt(checkerboard)
        pix = QPixmap.fromImage(qim)
        pix = pix.scaled(pix.width() * 4, pix.height() * 4, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
        self.preview.setPixmap(pix)

        warnings = []
        for slot, sel in self.project.slots.items():
            if not sel:
                continue
            item = self.catalog.items.get(slot, {}).get(sel.item)
            if not item:
                warnings.append(f"{slot}: missing item {sel.item}")
                continue
            if not item_variant_supports_body(item, sel.variant, body):
                warnings.append(f"{slot}: {sel.item}/{sel.variant} unsupported for {body}")
        self._set_status("\n".join(warnings) if warnings else "Ready.")

    def on_export_png(self):
        if not self._ensure_ready_for_export():
            return
        out_dir = self._choose_export_dir()
        if not out_dir:
            return
        project_name = safe_filename(self._project_name_guess())
        body = self.project.body
        direction = self.project.direction
        layers = self._resolved_layers_for_current()
        base_left, base_right = self._get_base_paths()
        out_path = out_dir / f"{project_name}__{body}__{direction}.png"
        export_png_sheet(
            out_path=out_path,
            sheet_spec=self.sheet_spec,
            base_left=base_left,
            base_right=base_right,
            layers=layers,
            direction=direction,
            use_explicit_right=bool(self.project.options.get("use_explicit_right_if_available", True)),
            flip_fallback=bool(self.project.options.get("fallback_flip_for_right", True)),
        )
        QMessageBox.information(self, "Export PNG", f"Exported:\n{out_path}")

    def on_export_gif(self):
        if not self._ensure_ready_for_export():
            return
        out_dir = self._choose_export_dir()
        if not out_dir:
            return
        project_name = safe_filename(self._project_name_guess())
        body = self.project.body
        direction = self.project.direction
        layers = self._resolved_layers_for_current()
        base_left, base_right = self._get_base_paths()
        fps = {k: sp.value() for k, sp in self.fps_spins.items()}
        paths = export_gif_actions(
            out_dir=out_dir,
            project_name=f"{project_name}__{body}",
            sheet_spec=self.sheet_spec,
            base_left=base_left,
            base_right=base_right,
            layers=layers,
            direction=direction,
            fps=fps,
        )
        QMessageBox.information(self, "Export GIF", "Exported GIFs:\n" + "\n".join(str(p) for p in paths))

    def on_export_apng(self):
        if not self._ensure_ready_for_export():
            return
        out_dir = self._choose_export_dir()
        if not out_dir:
            return
        project_name = safe_filename(self._project_name_guess())
        body = self.project.body
        direction = self.project.direction
        layers = self._resolved_layers_for_current()
        base_left, base_right = self._get_base_paths()
        fps = {k: sp.value() for k, sp in self.fps_spins.items()}
        try:
            paths = export_apng_actions(
                out_dir=out_dir,
                project_name=f"{project_name}__{body}",
                sheet_spec=self.sheet_spec,
                base_left=base_left,
                base_right=base_right,
                layers=layers,
                direction=direction,
                fps=fps,
            )
        except Exception as e:
            QMessageBox.critical(self, "Export APNG Failed", f"APNG export failed:\n{e}\n\nTry: pip install apng")
            return
        QMessageBox.information(self, "Export APNG", "Exported APNGs:\n" + "\n".join(str(p) for p in paths))
