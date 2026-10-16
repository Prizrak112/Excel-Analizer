"""Конструктор отчётов: подвкладки Дизайн / Код / Экспорт + своё меню."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QPushButton,
    QInputDialog, QTabWidget, QLabel, QMessageBox,
)
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtCore import Qt

from src.core.block_factory import BLOCK_TYPES, RenderContext, render_report
from src.core.report_model import Report, ReportBlock
from src.core.preview_server import PreviewServer
from src.core.code_generator import generate_report_script, ReportCodeGenerator
from src.core.bug_reporter import BugReporter
import base64
from src.core.assets_loader import tabulator_css, canvas_datagrid_js
from src.ui.canvas import Canvas
from src.ui.layers_tree import LayersTree
from src.ui.block_inspector import BlockInspector
from src.ui.blocks_palette import BlocksPalette
from src.ui.code_editor import CodeEditorWidget
from src.ui.toast import ToastManager
from src.ui.rich_text_dialog import RichTextDialog, clean_qt_html
from src.ui.rich_text_toolbar import RichTextToolbar


class ConstructorTab(QWidget):
    """Вкладка «🎨 Конструктор» со своим меню."""

    def __init__(self, theme, report: Report, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.report = report
        self.current_data = None
        self._sel_block: str | None = None
        self._sel_section: str | None = None
        self._preview = PreviewServer()

        self._build_ui()
        BugReporter.register_context_provider(self._collect_bug_context)
        self._refresh_all()

    def _on_block_delete(self, block_id: str):
        if block_id.startswith("__section__"):
            section_id = block_id[len("__section__"):]
            self.report.remove_section(section_id)
            if self._sel_section == section_id:
                self._sel_section = None
            self._sel_block = None
            self.inspector.show_empty()
            self._refresh_all()
            ToastManager.info("Раздел удалён", "", self.theme)
            return

        found = self.report.find_block_parent(block_id)
        if found is None:
            return
        _, parent_list, block = found
        parent_list.remove(block)

        if self._sel_block == block_id:
            self._sel_block = None
            self.inspector.show_empty()

        self._refresh_all()
        ToastManager.info("Блок удалён", "", self.theme)

    # ============================================================
    # Редактирование текста (двойной клик / ПКМ)
    # ============================================================

    def _on_edit_text_requested(self, block_id: str):
        found = self.report.find_block(block_id)
        if found is None:
            return
        _, block = found

        if block.type not in ("paragraph", "list", "section_title"):
            return

        cfg = block.config or {}

        if block.type == "section_title":
            html = cfg.get("title", "") or ""
            if not cfg.get("raw_html"):
                html = f"<p>{_esc_html(html)}</p>" if html else ""

        elif block.type == "paragraph":
            html = cfg.get("text", "") or ""
            if not cfg.get("raw_html"):
                html = f"<p>{_esc_html(html)}</p>" if html else ""

        elif block.type == "list":
            html = cfg.get("html", "") or ""
            if not html:
                items = cfg.get("items") or []
                if items:
                    li = "".join(f"<li>{_esc_html(x)}</li>" for x in items)
                    html = f"<ul>{li}</ul>"

        dlg = RichTextDialog(
            self.theme,
            kind=block.type,
            initial_html=html,
            parent=self,
        )
        if dlg.exec() != RichTextDialog.Accepted:
            return

        new_html = dlg.result_html

        new_cfg = dict(cfg)
        if block.type == "section_title":
            new_cfg["title"] = new_html
            new_cfg["raw_html"] = True
        elif block.type == "paragraph":
            new_cfg["text"] = new_html
            new_cfg["raw_html"] = True
        elif block.type == "list":
            new_cfg["html"] = new_html
            new_cfg["raw_html"] = True
            items = _html_to_items(new_html)
            new_cfg["items"] = items

        block.config = new_cfg

        self._refresh_all()
        self._push_preview()
        ToastManager.success("Текст обновлён", "", self.theme)

    # ============================================================
    # Инлайн-редактирование (сигналы от Canvas)
    # ============================================================

    def _on_editor_focus_in(self, block_id: str):
        if hasattr(self, "_focus_out_timer") and self._focus_out_timer.isActive():
            self._focus_out_timer.stop()

        w = self.canvas._widgets.get(block_id) if hasattr(self.canvas, "_widgets") else None
        if w is None:
            return
        rich_editor = None
        if hasattr(w, "inline_editor"):
            try:
                rich_editor = w.inline_editor()
            except Exception:
                rich_editor = None
        if rich_editor is not None:
            self.rich_toolbar.set_editor(rich_editor)

    def _on_editor_focus_out(self, block_id: str):
        pass

    def _on_editor_content_changed(self, block_id: str, html: str):
        found = self.report.find_block(block_id)
        if found is None:
            return
        _, block = found

        cleaned = clean_qt_html(html)

        cfg = dict(block.config or {})
        if block.type == "paragraph":
            cfg["text"] = cleaned
            cfg["raw_html"] = True
        elif block.type == "list":
            cfg["html"] = cleaned
            cfg["raw_html"] = True
            cfg["items"] = _html_to_items_from_html(cleaned)
        else:
            return

        block.config = cfg

        self._refresh_report_code()
        self._push_preview_debounced()

    # ============================================================
    # Построение
    # ============================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self._apply_subtabs_style()

        self.tabs.addTab(self._build_design_tab(), "🎨   Дизайн")
        self.tabs.addTab(self._build_code_tab(),   "🐍   Код")
        self.tabs.addTab(self._build_export_tab(), "📤   Экспорт")

        root.addWidget(self.tabs)

    def _build_design_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_preview_bar())

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setHandleWidth(1)

        self.palette = BlocksPalette(self.theme, BLOCK_TYPES)
        self.palette.block_requested.connect(self._on_add_block)
        self._splitter.addWidget(self.palette)

        self.layers = LayersTree(self.theme)
        self.layers.block_selected.connect(self._on_block_selected)
        self.layers.section_selected.connect(self._on_section_selected)
        self._splitter.addWidget(self.layers)

        self.canvas = Canvas(self.theme)
        self.canvas.block_clicked.connect(self._on_block_selected)
        self.canvas.section_clicked.connect(self._on_section_selected)
        self.canvas.block_moved.connect(self._on_block_moved)
        self.canvas.block_merge_requested.connect(self._on_block_merge_requested)
        self.canvas.block_live_resized.connect(self._on_block_live_resized)
        self.canvas.block_resized.connect(self._on_block_resized)
        self.canvas.block_position_changed.connect(self._on_block_position_changed)
        self.canvas.empty_clicked.connect(self._on_add_section)

        self.canvas.block_delete_requested.connect(self._on_block_delete)
        self.canvas.block_duplicate_requested.connect(self._on_block_duplicate)
        self.canvas.block_move_up_requested.connect(self._on_block_move_up)
        self.canvas.block_move_down_requested.connect(self._on_block_move_down)
        self.canvas.block_edit_text_requested.connect(self._on_edit_text_requested)
        self.canvas.block_focus_in.connect(self._on_editor_focus_in)
        self.canvas.block_focus_out.connect(self._on_editor_focus_out)
        self.canvas.block_content_changed.connect(self._on_editor_content_changed)
        self._splitter.addWidget(self.canvas)

        self.inspector = BlockInspector(self.theme)
        self.inspector.config_changed.connect(self._on_config_changed)
        self.inspector.unmerge_requested.connect(self._on_unmerge_requested)
        self._splitter.addWidget(self.inspector)

        self._splitter.setSizes([200, 210, 720, 330])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setStretchFactor(2, 1)
        self._splitter.setStretchFactor(3, 0)
        self._splitter.setCollapsible(0, True)
        self._splitter.setCollapsible(1, True)
        self._splitter.setCollapsible(3, True)
        root.addWidget(self._splitter, stretch=1)

        QShortcut(QKeySequence("Ctrl+P"), self, activated=self._on_preview)
        QShortcut(QKeySequence("Delete"), self, activated=self._on_delete_selected)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_add_section)

        return w

    def _build_preview_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(40)
        bar.setStyleSheet(
            f"background:{self.theme.bg_panel}; "
            f"border-bottom:1px solid {self.theme.border};"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(8)

        self.rich_toolbar = RichTextToolbar(self.theme, bar)
        lay.addWidget(self.rich_toolbar)

        lay.addStretch()

        b_bug = QPushButton("🐞  Баг-репорт")
        b_bug.setCursor(Qt.PointingHandCursor)
        b_bug.setToolTip("Сохранить диагностический отчёт в папку bug_reports/")
        b_bug.setStyleSheet(_btn_qss(self.theme, primary=False))
        b_bug.clicked.connect(self._on_manual_bug_report)
        lay.addWidget(b_bug)

        b_prev = QPushButton("👁  Предпросмотр")
        b_prev.setCursor(Qt.PointingHandCursor)
        b_prev.setStyleSheet(_btn_qss(self.theme, primary=True))
        b_prev.clicked.connect(self._on_preview)
        lay.addWidget(b_prev)

        return bar

    # ============================================================
    # Подвкладка Код
    # ============================================================

    def _build_code_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.code_view = CodeEditorWidget(self.theme)
        self.code_view.btn_refresh.clicked.connect(self._refresh_report_code)
        self.code_view.btn_copy.clicked.connect(self.code_view.copy_to_clipboard)
        self.code_view.btn_save.clicked.connect(self._save_report_code)

        root.addWidget(self.code_view)
        return w

    def _refresh_report_code(self):
        if not self.report.sections:
            self.code_view.set_code(
                "# Отчёт пока пуст\n"
                "# Добавьте разделы и блоки в подвкладке «Дизайн»"
            )
            return

        file_name = "data.xlsx"
        sheet_name = 0
        if self.current_data is not None:
            file_name = getattr(self.current_data, "filepath", None) or getattr(self.current_data, "file_path", "data.xlsx")
            sheet_name = getattr(self.current_data, "sheet_name", 0) or 0

        code = generate_report_script(
            report_model=self.report,
            file_name=str(file_name),
            sheet_name=sheet_name,
        )
        self.code_view.set_code(code)

    def _collect_bug_context(self) -> dict:
        df = getattr(self.current_data, "dataframe", None) if self.current_data else None
        df_info = {"loaded": False}
        if df is not None:
            df_info = {
                "loaded": True,
                "rows": len(df),
                "columns": {str(c): str(t) for c, t in df.dtypes.items()},
            }
        sections_dump = [
            {
                "id": s.id,
                "title": s.title,
                "blocks": [ReportCodeGenerator._serialize_block(b) for b in s.blocks],
            }
            for s in getattr(self.report, "sections", [])
        ]
        return {
            "dataframe_info": df_info,
            "report_state": {"title": self.report.title, "sections": sections_dump},
            "generated_code": self.code_view.toPlainText() if hasattr(self.code_view, "toPlainText") else "",
        }

    def _on_manual_bug_report(self):
        path = BugReporter.capture_exception(
            RuntimeError("Manual Bug Report Snapshot"),
            where="ConstructorTab (кнопка Баг-репорт)",
        )
        if path:
            ToastManager.info("Баг-репорт сохранён", str(path), self.theme)

    def _save_report_code(self):
        if not self.report.sections:
            ToastManager.info("Отчёт пуст", "Нечего сохранять", self.theme)
            return
        self.code_view.save_to_file("report_generator.py")

    # ============================================================
    # Подвкладка Экспорт
    # ============================================================

    def _build_export_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet(
            f"background:{self.theme.bg_panel}; border-bottom:1px solid {self.theme.border};"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(8)

        b_prev = QPushButton("👁  Открыть в браузере")
        b_prev.setCursor(Qt.PointingHandCursor)
        b_prev.setStyleSheet(_btn_qss(self.theme))
        b_prev.clicked.connect(self._on_preview)
        lay.addWidget(b_prev)

        b_save = QPushButton("💾  Сохранить HTML")
        b_save.setCursor(Qt.PointingHandCursor)
        b_save.setStyleSheet(_btn_qss(self.theme, primary=True))
        b_save.clicked.connect(self._on_export_html)
        lay.addWidget(b_save)

        lay.addStretch()
        root.addWidget(bar)

        stub = QLabel(
            "📤  Экспорт автономного HTML\n\n"
            "Здесь появится сохранение отчёта в единый HTML-файл,\n"
            "который можно открыть в любом браузере без интернета."
        )
        stub.setAlignment(Qt.AlignCenter)
        stub.setStyleSheet(
            f"color:{self.theme.text_muted}; font-size:13px; padding:60px;"
        )
        root.addWidget(stub, stretch=1)

        return w

    def _on_export_html(self):
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path

        if self.report.is_empty():
            ToastManager.info(
                "Отчёт пуст",
                "Добавьте хотя бы один блок в подвкладке «Дизайн»",
                self.theme,
            )
            return

        default_name = (self.report.title or "report") + ".html"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Сохранить HTML-отчёт", default_name,
            "HTML файлы (*.html);;Все файлы (*)",
        )
        if not filepath:
            return
        if not filepath.lower().endswith(".html"):
            filepath += ".html"

        df = None
        if self.current_data is not None:
            try:
                df = self.current_data.dataframe
            except AttributeError:
                df = None

        try:
            total = 0
            if df is not None:
                try:
                    total = len(df)
                except Exception:
                    total = 0

            if total > 50_000:
                reply = QMessageBox.question(
                    self, "Большая таблица",
                    f"В таблице {total:,} строк.\n\n"
                    f"HTML-файл получится очень большим (десятки МБ) "
                    f"и будет тормозить браузер.\n\n"
                    f"Продолжить экспорт?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return

            ctx = RenderContext(dataframe=df, preview_limit=0)
            body = render_report(self.report, ctx)
            html = _wrap_html(body, self.report.title or "Отчёт")
            Path(filepath).write_text(html, encoding="utf-8")
            ToastManager.success("HTML сохранён", filepath, self.theme)
            self._preview.open_in_browser()
        except Exception as e:
            import traceback
            traceback.print_exc()
            ToastManager.error(
                "Ошибка сохранения", f"{type(e).__name__}: {e}", self.theme,
            )

    # ============================================================
    # Публичное
    # ============================================================

    def set_data(self, data):
        self.current_data = data
        df = None
        if data is not None:
            try:
                df = data.dataframe
            except AttributeError:
                df = None
        self.inspector.set_dataframe(df)
        self._refresh_canvas()
        self._refresh_report_code()
        try:
            self._push_preview()
        except Exception:
            pass

    def show_export_tab(self):
        self.tabs.setCurrentIndex(2)

    def show_code_tab(self):
        self.tabs.setCurrentIndex(1)

    # ============================================================
    # Действия над блоками
    # ============================================================

    def _on_add_section(self):
        title, ok = QInputDialog.getText(
            self, "Новый раздел", "Название:", text="Новый раздел"
        )
        if not ok or not title.strip():
            return
        s = self.report.add_section(title.strip(), "📊")
        self._sel_section = s.id
        self._sel_block = None
        self._refresh_all()

    def _on_add_block(self, block_type: str):
        target = None
        if self._sel_section:
            target = self.report.get_section(self._sel_section)
        if target is None and self._sel_block:
            found = self.report.find_block(self._sel_block)
            if found:
                target = found[0]
        if target is None:
            if not self.report.sections:
                target = self.report.add_section("Раздел 1", "📊")
            else:
                target = self.report.sections[0]

        cfg = _default_config(block_type)
        block = ReportBlock.create(block_type, cfg)
        target.add_block(block)

        self._sel_block = block.id
        self._sel_section = target.id
        self._refresh_all()
        self._on_block_selected(block.id)

    def _on_delete_selected(self):
        if self._sel_block:
            found = self.report.find_block_parent(self._sel_block)
            if found:
                sec, parent_list, blk = found
                parent_list.remove(blk)
                self._sel_block = None
                self.inspector.show_empty()
                self._refresh_all()
                return
        if self._sel_section:
            self.report.remove_section(self._sel_section)
            self._sel_section = None
            self._sel_block = None
            self.inspector.show_empty()
            self._refresh_all()
            return
        ToastManager.info("Ничего не выбрано", "", self.theme)

    def _on_block_selected(self, block_id: str):
        self._sel_block = block_id
        self._sel_section = None
        found = self.report.find_block(block_id)
        if found is None:
            return
        _, block = found
        self.canvas.select_block(block_id)
        self.layers.select_block(block_id)
        self.inspector.show_block(block)
        self._push_preview()

    def _on_block_moved(self, block_id: str, target_section_id: str, new_index: int):
        ok = self.report.move_block_across(block_id, target_section_id, new_index)
        if not ok:
            return
        self._sel_block = block_id
        self._sel_section = target_section_id
        self._refresh_all()
        self._on_block_selected(block_id)

    def _on_block_merge_requested(self, source_id: str, target_id: str):
        ok = self.report.merge_blocks(source_id, target_id, layout="row")
        if not ok:
            return
        self._sel_block = None
        self._sel_section = None
        self._refresh_all()
        ToastManager.success(
            "Блоки объединены",
            "Теперь они стоят рядом в контейнере.",
            self.theme,
        )

    def _on_unmerge_requested(self, block_id: str):
        if self.report.unmerge_container(block_id):
            self._sel_block = None
            self.inspector.show_empty()
            self._refresh_all()
            ToastManager.success("Контейнер разбит", "Блоки возвращены на холст", self.theme)

    def _on_block_live_resized(self, block_id: str, width_pct: int, min_height_px: int):
        """Мгновенно двигает ползунок и спинбокс в инспекторе, пока пользователь тянет за угол."""
        found = self.report.find_block(block_id)
        if found is not None:
            _, block = found
            cfg = dict(block.config or {})
            cfg["width"] = width_pct
            cfg["min_height"] = min_height_px
            block.config = cfg
            if self._sel_block != block_id:
                self._sel_block = block_id
                self.inspector.show_block(block)
        self.inspector.sync_live_geometry(block_id, width_pct, min_height_px)

    def _on_block_resized(self, block_id: str, width_pct: int, min_height_px: int):
        """Фиксирует итоговый размер после отпускания мыши, обновляет код и предпросмотр."""
        found = self.report.find_block(block_id)
        if found is None:
            return
        _, block = found
        cfg = dict(block.config or {})
        cfg["width"] = width_pct
        cfg["min_height"] = min_height_px
        block.config = cfg
        self.inspector.sync_live_geometry(block_id, width_pct, min_height_px)
        self._refresh_report_code()
        self._push_preview()

    def _on_block_position_changed(self, block_id: str, align: str, offset_x: int):
        """Реакция на смену положения блока в пространстве страницы (лево / центр / право / сдвиг X)."""
        found = self.report.find_block(block_id)
        if found is None:
            return
        _, block = found
        cfg = dict(block.config or {})
        cfg["align"] = align
        cfg["offset_x"] = offset_x
        block.config = cfg
        if self._sel_block == block_id:
            self.inspector.show_block(block)
        self._refresh_report_code()
        self._push_preview()

    # ---------- Контекстное меню ----------

    def _on_block_duplicate(self, block_id: str):
        if block_id.startswith("__section__"):
            return
        found = self.report.find_block_parent(block_id)
        if found is None:
            return
        _, parent_list, block = found

        import copy
        new_block = ReportBlock.create(block.type, copy.deepcopy(block.config or {}))

        idx = parent_list.index(block)
        parent_list.insert(idx + 1, new_block)

        self._sel_block = new_block.id
        self._refresh_all()
        self._on_block_selected(new_block.id)
        ToastManager.info("Блок дублирован", "", self.theme)

    def _on_block_move_up(self, block_id: str):
        if block_id.startswith("__section__"):
            return
        found = self.report.find_block_parent(block_id)
        if found is None:
            return
        _, parent_list, block = found
        idx = parent_list.index(block)
        if idx <= 0:
            return
        parent_list[idx], parent_list[idx - 1] = parent_list[idx - 1], parent_list[idx]
        self._refresh_all()
        self._on_block_selected(block_id)

    def _on_block_move_down(self, block_id: str):
        if block_id.startswith("__section__"):
            return
        found = self.report.find_block_parent(block_id)
        if found is None:
            return
        _, parent_list, block = found
        idx = parent_list.index(block)
        if idx >= len(parent_list) - 1:
            return
        parent_list[idx], parent_list[idx + 1] = parent_list[idx + 1], parent_list[idx]
        self._refresh_all()
        self._on_block_selected(block_id)

    def _on_section_selected(self, section_id: str):
        self._sel_section = section_id
        self._sel_block = None
        sec = self.report.get_section(section_id)
        if sec is not None:
            self.inspector.show_section(sec)
        self.canvas.select_block(None)

    def _on_config_changed(self, _block_id: str):
        self.layers.rebuild(self.report)
        if self._sel_block:
            self.layers.select_block(self._sel_block)
        self._refresh_canvas()
        self._refresh_report_code()
        self._push_preview_debounced()

    def _on_preview(self):
        self._push_preview(open_browser=True)

    def _push_preview(self, open_browser=False):
        try:
            df = None
            if self.current_data is not None:
                try:
                    df = self.current_data.dataframe
                except AttributeError:
                    df = None
            ctx = RenderContext(dataframe=df, preview_limit=1000)
            body = render_report(self.report, ctx)
            html = _wrap_html(body, self.report.title or "Отчёт")
            if open_browser:
                self._preview.open_in_browser()
            self._preview.show(html)
        except Exception as e:
            print(f"[Constructor] preview error: {e}")
            BugReporter.capture_exception(e, where="ConstructorTab._push_preview")

    def _push_preview_debounced(self):
        if not hasattr(self, "_preview_timer"):
            from PySide6.QtCore import QTimer
            self._preview_timer = QTimer(self)
            self._preview_timer.setSingleShot(True)
            self._preview_timer.setInterval(400)
            self._preview_timer.timeout.connect(self._push_preview)
        self._preview_timer.start()

    def _refresh_all(self):
        self.layers.rebuild(self.report)
        self._refresh_canvas()
        if self._sel_block:
            self.layers.select_block(self._sel_block)
        try:
            self._refresh_report_code()
        except Exception as e:
            print(f"[Constructor] code gen error: {e}")
        try:
            self._push_preview()
        except Exception:
            pass

    def _refresh_canvas(self):
        df = None
        if self.current_data is not None:
            try:
                df = self.current_data.dataframe
            except AttributeError:
                df = None
        self.canvas.rebuild(self.report, df)
        if self._sel_block:
            self.canvas.select_block(self._sel_block)

    # ============================================================
    # Стили подвкладок
    # ============================================================

    def _apply_subtabs_style(self):
        t = self.theme
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {t.bg_card};
                top: -1px;
            }}
            QTabWidget::tab-bar {{
                alignment: left;
                left: 12px;
            }}
            QTabBar {{
                background: {t.bg_page};
                qproperty-drawBase: 0;
            }}
            QTabBar::tab {{
                background: {t.bg_panel};
                color: {t.text_muted};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 18px;
                margin: 6px 6px 6px 0px;
                font-size: 13px;
                font-weight: 600;
                min-height: 20px;
            }}
            QTabBar::tab:hover:!selected {{
                background: {t.bg_hover};
                color: {t.text_main};
                border: 1px solid {t.primary};
            }}
            QTabBar::tab:selected {{
                background: {t.primary_hover};
                color: {t.text_main};
                border: 1px solid {t.primary};
            }}
        """)


# ============================================================
# Утилиты
# ============================================================

def _btn_qss(theme, primary=False):
    t = theme
    if primary:
        bg, color, border, hover = t.primary, t.text_inverse, "none", "#9ade4f"
    else:
        bg, color = t.bg_card, t.text_main
        border, hover = f"1px solid {t.border}", t.bg_hover
    return f"""
        QPushButton {{
            background:{bg}; color:{color}; border:{border};
            border-radius:6px; padding:6px 14px;
            font-size:12px; font-weight:600; min-height:22px;
        }}
        QPushButton:hover {{ background:{hover}; }}
    """


def _html_to_items_from_html(html: str) -> list[str]:
    import re
    if not html:
        return []
    found = re.findall(r"<li[^>]*>(.*?)</li>", html, flags=re.IGNORECASE | re.DOTALL)
    out = []
    for raw in found:
        text = re.sub(r"<[^>]+>", "", raw)
        text = (text.replace("&nbsp;", " ")
                    .replace("&amp;", "&")
                    .replace("&lt;", "<")
                    .replace("&gt;", ">")
                    .strip())
        if text:
            out.append(text)
    return out


def _esc_html(text) -> str:
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _html_to_items(html: str) -> list[str]:
    return _html_to_items_from_html(html)


def _default_config(block_type: str) -> dict:
    if block_type == "section_title":
        return {"title": "Заголовок", "width": 100}
    if block_type == "paragraph":
        return {"text": "Новый параграф. Отредактируйте его на холсте.", "width": 100, "align": "left", "offset_x": 0}
    if block_type == "list":
        return {"items": ["Первый пункт", "Второй пункт", "Третий пункт"], "width": 100, "align": "left", "offset_x": 0}
    if block_type == "divider":
        return {}
    if block_type == "kpi_row":
        return {
            "cards": [
                {"label": "Выручка", "value": "1 000 000", "accent": True},
                {"label": "Клиентов", "value": "42", "accent": False},
            ],
            "width": 100,
            "align": "left",
            "offset_x": 0,
        }
    if block_type == "data_table":
        return {"max_rows": 20, "width": 100, "align": "left", "offset_x": 0}
    if block_type == "plotly_chart":
        return {
            "title": "График данных",
            "chart_type": "bar",
            "x_col": "",
            "y_col": "",
            "agg": "sum",
            "sort_by": "value_desc",
            "top_n": 12,
            "row_start": 0,
            "row_limit": 0,
            "palette": "corporate",
            "bg_color": "#ffffff",
            "legend_pos": "right",
            "show_legend": True,
            "show_values": True,
            "show_grid": True,
            "width": 100,
            "min_height": 260,
            "align": "left",
            "offset_x": 0,
        }
    return {"width": 100, "align": "left", "offset_x": 0}


def _wrap_html(body: str, title: str) -> str:
    tab_css = tabulator_css()
    tab_js = canvas_datagrid_js()
    tab_js_b64 = base64.b64encode(tab_js.encode("utf-8")).decode("ascii")

    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><title>{title}</title>
<style>
    {tab_css}
    *{{box-sizing:border-box}}
    
    /* Жестко ограничиваем SVG-графики Plotly размерами их контейнеров */
    .js-plotly-plot, .plot-container, .user-select-none {{
        width: 100% !important;
        max-width: 100% !important;
    }}
    .main-svg {{
        width: 100% !important;
        height: auto !important;
    }}

    body{{margin:0;padding:0;font-family:Arial,sans-serif;
         background:#f5f7f9;color:#222}}

    .layout-row{{
        display:flex;
        gap:14px;
        align-items:flex-start;
        flex-wrap:wrap;
        margin-bottom:0;
    }}
    .container-row{{
        display: flex;
        flex-wrap: wrap; /* Автоматический перенос графиков на новую строку, если не помещаются */
        align-items: stretch;
        gap: 16px;
        width: 100%;
        box-sizing: border-box;
        background: #f8fafc;
        border: 2px dashed #94a3b8;
        border-radius: 10px;
        padding: 14px;
    }}
    .container-column{{
        display: flex;
        flex-direction: column;
        gap: 16px;
        width: 100%;
        box-sizing: border-box;
        background: #f8fafc;
        border: 2px dashed #94a3b8;
        border-radius: 10px;
        padding: 14px;
    }}

    h1.section-title{{
        color:#003F0B;
        font-size:1.8rem;
        font-weight:700;
        margin:25px 0 10px 0;
        padding-bottom:8px;
        border-bottom:2px solid #87C800;
        scroll-margin-top: 25px;
    }}
    .block{{margin-bottom:0; display:block; min-width:0; width:100%;}}
    .block-card{{background:#fff;border:1px solid #e0e0e5;border-radius:10px;padding:20px;min-width:0;width:100%;}}

    .kpi-row{{display:flex;gap:16px;flex-wrap:wrap}}
    .kpi-card{{flex:1 1 120px;background:#fff;border:1px solid #e0e0e5;
              border-radius:10px;padding:16px}}
    .kpi-value{{font-size:26px;font-weight:700}}
    .kpi-value.accent{{color:#2bb24c}}
    .kpi-label{{color:#666;font-size:12px;margin-top:4px}}

    .section-divider{{height:1px;background:#ddd;margin:20px 0}}

    .paragraph p{{margin:0 0 8px; line-height:1.5}}
    .paragraph b, .list-rich b{{font-weight:700}}
    .paragraph i, .list-rich i{{font-style:italic}}
    .paragraph u, .list-rich u{{text-decoration:underline}}
    .paragraph s, .list-rich s{{text-decoration:line-through}}
    .paragraph ul, .list-rich ul{{margin:6px 0 8px 0; padding-left:22px}}
    .paragraph ol, .list-rich ol{{margin:6px 0 8px 0; padding-left:24px}}
    .paragraph li, .list-rich li{{margin:2px 0; line-height:1.5}}
    .block-list{{margin:0;padding-left:22px}}

    .report-toc{{
        position:fixed;
        left:0; top:0;
        width:260px;
        height:100vh;
        background:#ffffff;
        border-right:1px solid #e0e0e0;
        overflow-y:auto;
        padding:20px;
        box-shadow:2px 0 5px rgba(0,0,0,0.05);
        z-index:100;
    }}
    .report-toc h2{{
        font-size:1.3rem;
        margin:0 0 20px 0;
        color:#003F0B;
        border-bottom:2px solid #87C800;
        padding-bottom:8px;
    }}
    .report-toc ul{{list-style:none;padding-left:0;margin:0;}}
    .report-toc ul li{{margin:6px 0;}}
    .toc-item{{
        text-decoration:none;
        color:#195532;
        font-weight:500;
        font-size:13px;
        display:block;
        padding:4px 8px;
        border-radius:4px;
        transition:background 0.2s;
        cursor:pointer;
    }}
    .toc-item:hover{{background:#e9f5e9;color:#003F0B;}}
    .toc-item.active{{background:#87C800;color:#ffffff;font-weight:bold;}}

    .report-content{{
        margin-left:260px;
        padding:20px 30px 40px;
        max-width:calc(100% - 260px);
    }}
    .section-anchor{{scroll-margin-top:20px;}}

    @media (max-width: 768px) {{
        .report-toc{{
            position:static;
            width:100%;
            height:auto;
            border-right:none;
            border-bottom:1px solid #e0e0e0;
            margin-bottom:15px;
        }}
        .report-content{{margin-left:0;width:100%;padding:15px;}}
    }}
</style>
<script src="data:text/javascript;base64,{tab_js_b64}"></script>
</head>
<body>
{body}
<script>
(function() {{
    var items = document.querySelectorAll('.toc-item');
    var isScrolling = false;
    var scrollTimeout = null;

    items.forEach(function(item) {{
        item.addEventListener('click', function(e) {{
            e.preventDefault();
            var targetId = this.getAttribute('data-target');
            var target = document.getElementById(targetId);
            if (target) {{
                isScrolling = true;
                items.forEach(function(i) {{ i.classList.remove('active'); }});
                this.classList.add('active');
                target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                clearTimeout(scrollTimeout);
                scrollTimeout = setTimeout(function() {{ isScrolling = false; }}, 800);
            }}
        }});
    }});

    var sections = [];
    items.forEach(function(item) {{
        var id = item.getAttribute('data-target');
        var el = document.getElementById(id);
        if (el) sections.push({{ el: el, item: item }});
    }});

    window.addEventListener('scroll', function() {{
        if (isScrolling) return;
        var scrollY = window.pageYOffset + 100;
        var current = sections[0];
        sections.forEach(function(s) {{
            if (s.el.offsetTop <= scrollY) {{ current = s; }}
        }});
        items.forEach(function(i) {{ i.classList.remove('active'); }});
        if (current) {{ current.item.classList.add('active'); }}
    }});
}})();
</script>
</body></html>"""