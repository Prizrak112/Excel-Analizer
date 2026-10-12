"""
Виджет просмотра и редактирования Python-кода.
С подсветкой синтаксиса.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QLabel, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QRect, QSize, Signal
from PySide6.QtGui import (
    QFont, QColor, QSyntaxHighlighter,
    QTextCharFormat, QTextCursor, QPainter
)


# ============================================================
# Подсветка синтаксиса Python
# ============================================================

class PythonHighlighter(QSyntaxHighlighter):
    """Простая подсветка Python-синтаксиса."""
    
    def __init__(self, document, theme):
        super().__init__(document)
        self.theme = theme
        self._rules = []
        self._build_rules()
    
    def _build_rules(self):
        is_dark = self.theme.is_dark
        
        # Ключевые слова
        keyword_color = QColor("#C678DD") if is_dark else QColor("#A626A4")
        keywords = [
            "and", "as", "assert", "break", "class", "continue", "def",
            "del", "elif", "else", "except", "False", "finally", "for",
            "from", "global", "if", "import", "in", "is", "lambda", "None",
            "nonlocal", "not", "or", "pass", "raise", "return", "True",
            "try", "while", "with", "yield", "async", "await"
        ]
        fmt_kw = QTextCharFormat()
        fmt_kw.setForeground(keyword_color)
        fmt_kw.setFontWeight(QFont.Bold)
        for kw in keywords:
            self._rules.append((f"\\b{kw}\\b", fmt_kw))
        
        # Строки
        string_color = QColor("#98C379") if is_dark else QColor("#50A14F")
        fmt_str = QTextCharFormat()
        fmt_str.setForeground(string_color)
        self._rules.append((r'"[^"\\]*(\\.[^"\\]*)*"', fmt_str))
        self._rules.append((r"'[^'\\]*(\\.[^'\\]*)*'", fmt_str))
        self._rules.append((r'""".*?"""', fmt_str))
        self._rules.append((r"'''.*?'''", fmt_str))
        
        # Комментарии
        comment_color = QColor("#5C6370") if is_dark else QColor("#A0A1A7")
        fmt_com = QTextCharFormat()
        fmt_com.setForeground(comment_color)
        fmt_com.setFontItalic(True)
        self._rules.append((r"#[^\n]*", fmt_com))
        
        # Числа
        number_color = QColor("#D19A66") if is_dark else QColor("#986801")
        fmt_num = QTextCharFormat()
        fmt_num.setForeground(number_color)
        self._rules.append((r"\b\d+\.?\d*\b", fmt_num))
        
        # Декораторы
        fmt_dec = QTextCharFormat()
        fmt_dec.setForeground(QColor("#61AFEF"))
        self._rules.append((r"@\w+", fmt_dec))
        
        # Функции (вызовы)
        func_color = QColor("#61AFEF") if is_dark else QColor("#4078F2")
        fmt_func = QTextCharFormat()
        fmt_func.setForeground(func_color)
        self._rules.append((r"\b\w+(?=\()", fmt_func))
    
    def highlightBlock(self, text):
        import re
        for pattern, fmt in self._rules:
            for match in re.finditer(pattern, text):
                self.setFormat(
                    match.start(),
                    match.end() - match.start(),
                    fmt
                )


# ============================================================
# Редактор кода
# ============================================================

class CodeEditorWidget(QWidget):
    """Виджет для отображения и редактирования кода."""
    
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._current_file_path = None
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Верхняя панель
        top_bar = QWidget()
        top_bar.setStyleSheet(f"""
            background: {self.theme.bg_card};
            border-bottom: 1px solid {self.theme.border};
        """)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 8, 12, 8)
        top_layout.setSpacing(8)
        
        # Заголовок
        self.label_info = QLabel("🐍 Сгенерированный Python-скрипт")
        self.label_info.setStyleSheet(f"""
            color: {self.theme.text_main};
            font-size: 12px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        top_layout.addWidget(self.label_info)
        top_layout.addStretch()
        
        # Кнопка обновить
        self.btn_refresh = QPushButton("🔄 Обновить")
        self.btn_refresh.setFixedHeight(28)
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setStyleSheet(self._button_style(secondary=True))
        top_layout.addWidget(self.btn_refresh)
        
        # Кнопка копировать
        self.btn_copy = QPushButton("📋 Копировать")
        self.btn_copy.setFixedHeight(28)
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.setStyleSheet(self._button_style(secondary=True))
        top_layout.addWidget(self.btn_copy)
        
        # Кнопка сохранить
        self.btn_save = QPushButton("💾 Сохранить .py")
        self.btn_save.setFixedHeight(28)
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setStyleSheet(self._button_style(primary=True))
        top_layout.addWidget(self.btn_save)
        
        layout.addWidget(top_bar)
        
        # Редактор
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(False)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.Monospace)
        self.editor.setFont(font)
        
        self._apply_editor_style()
        
        # Подсветка
        self.highlighter = PythonHighlighter(self.editor.document(), self.theme)
        
        # Отступы — 4 пробела
        self.editor.setTabStopDistance(4 * self.editor.fontMetrics().horizontalAdvance(' '))
        
        layout.addWidget(self.editor, stretch=1)
        
        # Статус-бар
        bottom_bar = QWidget()
        bottom_bar.setStyleSheet(f"""
            background: {self.theme.bg_panel};
            border-top: 1px solid {self.theme.border};
        """)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(12, 4, 12, 4)
        
        self.label_status = QLabel("Готово")
        self.label_status.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 11px;
            background: transparent;
            border: none;
        """)
        bottom_layout.addWidget(self.label_status)
        bottom_layout.addStretch()
        
        self.label_lines = QLabel("0 строк")
        self.label_lines.setStyleSheet(f"""
            color: {self.theme.text_muted};
            font-size: 11px;
            background: transparent;
            border: none;
        """)
        bottom_layout.addWidget(self.label_lines)
        
        layout.addWidget(bottom_bar)
    
    def _button_style(self, primary=False, secondary=False) -> str:
        if primary:
            return f"""
                QPushButton {{
                    background: {self.theme.primary};
                    color: {self.theme.text_inverse};
                    border: none;
                    padding: 0 14px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: 600;
                }}
                QPushButton:hover {{ background: #6ea800; }}
            """
        return f"""
            QPushButton {{
                background: {self.theme.bg_panel};
                color: {self.theme.text_main};
                border: 1px solid {self.theme.border};
                padding: 0 14px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {self.theme.primary_hover};
                border-color: {self.theme.primary};
            }}
        """
    
    def _apply_editor_style(self):
        self.editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {self.theme.bg_card};
                color: {self.theme.text_main};
                border: none;
                padding: 12px;
                selection-background-color: {self.theme.primary_hover};
                selection-color: {self.theme.primary};
            }}
        """)
    
    # ============================================================
    # Публичные методы
    # ============================================================
    
    def set_code(self, code: str):
        """Установить код."""
        self.editor.setPlainText(code)
        lines = code.count("\n") + 1
        self.label_lines.setText(f"{lines} строк")
        self.label_status.setText("Скрипт обновлён")
    
    def get_code(self) -> str:
        """Получить текущий код."""
        return self.editor.toPlainText()
    
    def set_theme(self, theme):
        """Сменить тему."""
        self.theme = theme
        self._apply_editor_style()
        self.highlighter = PythonHighlighter(self.editor.document(), self.theme)
    
    def copy_to_clipboard(self):
        """Копировать код в буфер обмена."""
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.editor.toPlainText())
        self.label_status.setText("📋 Скопировано в буфер")
    
    def save_to_file(self, default_name: str = "script.py") -> bool:
        """Сохранить в файл."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить Python-скрипт",
            default_name,
            "Python файлы (*.py);;Все файлы (*.*)"
        )
        
        if not path:
            return False
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
            self.label_status.setText(f"💾 Сохранено: {path}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить:\n\n{e}")
            return False