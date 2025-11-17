"""Relise Tracking Desktop Client
================================

This module contains a single-file PySide6 port of the Relise Tracking mobile
app logic.  It ships a responsive corporate UI that mirrors the scanning,
history, error review, and camera placeholder flows present in the mobile
version while staying comfortable on Windows desktops.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List

from PySide6 import QtCore, QtGui, QtWidgets


@dataclass
class ScanRecord:
    package_id: str
    status: str
    location: str
    operator: str
    timestamp: datetime = field(default_factory=datetime.now)
    notes: str = ""

    def to_row(self) -> List[str]:
        return [
            self.timestamp.strftime("%H:%M:%S"),
            self.package_id,
            self.status,
            self.location,
            self.operator,
            self.notes or "—",
        ]


class AccentButton(QtWidgets.QPushButton):
    def __init__(self, label: str, *, accent: str = "#0078D4") -> None:
        super().__init__(label)
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.setMinimumHeight(42)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {accent};
                border-radius: 12px;
                border: none;
                color: white;
                font-size: 15px;
                font-weight: 600;
                padding: 8px 18px;
            }}
            QPushButton:disabled {{
                background-color: #94BFE2;
            }}
            QPushButton:hover {{
                background-color: {QtGui.QColor(accent).lighter(110).name()};
            }}
            QPushButton:pressed {{
                background-color: {QtGui.QColor(accent).darker(115).name()};
            }}
            """
        )


class Card(QtWidgets.QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("card")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setStyleSheet(
            "#card {"
            "background-color: #FFFFFF;"
            "border-radius: 20px;"
            "padding: 28px;"
            "box-shadow: 0px 20px 60px rgba(15,23,42,0.08);"
            "}"
        )


class LoginPanel(Card):
    login_requested = QtCore.Signal(str)

    def __init__(self) -> None:
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(18)

        headline = QtWidgets.QLabel("Relise Tracking")
        headline.setAlignment(QtCore.Qt.AlignLeft)
        headline.setStyleSheet(
            "font-size: 32px; font-weight: 700; color: #0F172A;"
        )
        layout.addWidget(headline)

        subtitle = QtWidgets.QLabel("Единое рабочее место оператора")
        subtitle.setStyleSheet(
            "color: #475569; font-size: 16px; line-height: 1.4;"
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.operator_field = QtWidgets.QLineEdit()
        self.operator_field.setPlaceholderText("Логин")
        self.operator_field.setMinimumHeight(46)
        self.operator_field.setClearButtonEnabled(True)
        layout.addWidget(self.operator_field)

        self.password_field = QtWidgets.QLineEdit()
        self.password_field.setEchoMode(QtWidgets.QLineEdit.Password)
        self.password_field.setPlaceholderText("Пароль")
        self.password_field.setMinimumHeight(46)
        layout.addWidget(self.password_field)

        self.shift_combo = QtWidgets.QComboBox()
        self.shift_combo.addItems(["Утренняя смена", "Дневная", "Ночная"])
        self.shift_combo.setMinimumHeight(46)
        layout.addWidget(self.shift_combo)

        self.remember = QtWidgets.QCheckBox("Запомнить рабочее место")
        layout.addWidget(self.remember)

        login_btn = AccentButton("Войти в систему", accent="#2563EB")
        login_btn.clicked.connect(self._emit_login)
        layout.addWidget(login_btn)

        self.operator_field.returnPressed.connect(self._emit_login)
        self.password_field.returnPressed.connect(self._emit_login)

    def _emit_login(self) -> None:
        username = self.operator_field.text().strip()
        if username:
            self.login_requested.emit(username)


class NavigationButton(QtWidgets.QPushButton):
    def __init__(self, label: str, icon: str | None = None) -> None:
        super().__init__(label)
        if icon:
            self.setIcon(QtGui.QIcon(str(Path(icon))))
            self.setIconSize(QtCore.QSize(20, 20))
        self.setCheckable(True)
        self.setMinimumHeight(48)
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.setStyleSheet(
            """
            QPushButton {
                border: none;
                border-radius: 12px;
                color: #0F172A;
                font-size: 15px;
                font-weight: 600;
                padding: 8px 14px;
                text-align: left;
            }
            QPushButton:checked {
                background: rgba(37,99,235,0.12);
                color: #1D4ED8;
            }
            QPushButton:hover {
                background: rgba(15,23,42,0.08);
            }
            """
        )


class ScannerPage(Card):
    scan_registered = QtCore.Signal(ScanRecord)
    error_registered = QtCore.Signal(ScanRecord)

    def __init__(self) -> None:
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(18)

        title = QtWidgets.QLabel("Сканирование отправлений")
        title.setStyleSheet("font-size: 24px; font-weight: 600; color: #0F172A;")
        layout.addWidget(title)

        subtitle = QtWidgets.QLabel(
            "Сканируйте штрихкод сканером или камерой устройства. Ввод"
            " вручную также поддерживается."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #475569; font-size: 15px;")
        layout.addWidget(subtitle)

        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        layout.addLayout(form)

        self.package_field = QtWidgets.QLineEdit()
        self.package_field.setPlaceholderText("Штрихкод / номер отправления")
        self.package_field.setMinimumHeight(46)
        form.addWidget(self.package_field, 0, 0, 1, 2)

        self.location_field = QtWidgets.QLineEdit()
        self.location_field.setPlaceholderText("Склад / зона")
        self.location_field.setMinimumHeight(46)
        form.addWidget(self.location_field, 1, 0)

        self.note_field = QtWidgets.QLineEdit()
        self.note_field.setPlaceholderText("Комментарий (необязательно)")
        self.note_field.setMinimumHeight(46)
        form.addWidget(self.note_field, 1, 1)

        self.operator_combo = QtWidgets.QComboBox()
        self.operator_combo.addItems([
            "Оператор 1",
            "Оператор 2",
            "Инспектор",
        ])
        self.operator_combo.setMinimumHeight(46)
        form.addWidget(self.operator_combo, 2, 0)

        self.status_combo = QtWidgets.QComboBox()
        self.status_combo.addItems([
            "Готов к отправке",
            "Доставлено",
            "В обработке",
        ])
        self.status_combo.setMinimumHeight(46)
        form.addWidget(self.status_combo, 2, 1)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch()

        confirm_btn = AccentButton("Подтвердить доставку", accent="#10B981")
        confirm_btn.clicked.connect(self._confirm)
        btns.addWidget(confirm_btn)

        issue_btn = AccentButton("Зафиксировать ошибку", accent="#DC2626")
        issue_btn.clicked.connect(self._flag_issue)
        btns.addWidget(issue_btn)

        layout.addLayout(btns)

        self.package_field.returnPressed.connect(self._confirm)

    def _build_record(self) -> ScanRecord | None:
        package = self.package_field.text().strip()
        if not package:
            return None
        record = ScanRecord(
            package_id=package,
            status=self.status_combo.currentText(),
            location=self.location_field.text().strip() or "Не указано",
            operator=self.operator_combo.currentText(),
            notes=self.note_field.text().strip(),
        )
        self.package_field.clear()
        self.note_field.clear()
        return record

    def _confirm(self) -> None:
        record = self._build_record()
        if record:
            self.scan_registered.emit(record)

    def _flag_issue(self) -> None:
        record = self._build_record()
        if record:
            record.status = "Ошибка"
            self.error_registered.emit(record)


class TablePage(Card):
    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(18)

        title_lbl = QtWidgets.QLabel(title)
        title_lbl.setStyleSheet("font-size: 24px; font-weight: 600; color: #0F172A;")
        layout.addWidget(title_lbl)

        subtitle_lbl = QtWidgets.QLabel(subtitle)
        subtitle_lbl.setWordWrap(True)
        subtitle_lbl.setStyleSheet("color: #475569; font-size: 15px;")
        layout.addWidget(subtitle_lbl)

        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Время", "Отправление", "Статус", "Зона", "Оператор", "Комментарий"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            "QTableWidget { border: none; font-size: 14px; }"
            "QHeaderView::section { background: #F8FAFC; padding: 8px; }"
        )
        layout.addWidget(self.table)

    def add_record(self, record: ScanRecord) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, value in enumerate(record.to_row()):
            item = QtWidgets.QTableWidgetItem(value)
            item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
            self.table.setItem(row, column, item)


class CameraPage(Card):
    def __init__(self) -> None:
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(18)

        title = QtWidgets.QLabel("Камера и фотофиксация")
        title.setStyleSheet("font-size: 24px; font-weight: 600; color: #0F172A;")
        layout.addWidget(title)

        subtitle = QtWidgets.QLabel(
            "Подключите внешнюю камеру или используйте встроенную."
            " Снимок можно прикрепить к проблемному отправлению."
        )
        subtitle.setStyleSheet("color: #475569; font-size: 15px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        placeholder = QtWidgets.QLabel()
        placeholder.setMinimumHeight(320)
        placeholder.setAlignment(QtCore.Qt.AlignCenter)
        placeholder.setStyleSheet(
            "border: 2px dashed #CBD5F5; border-radius: 20px;"
            "color: #475569; font-size: 15px;"
        )
        placeholder.setText(
            "Здесь будет поток камеры Windows.\n"
            "В демо-версии отображается заглушка."
        )
        layout.addWidget(placeholder)

        attach_btn = AccentButton("Выбрать фото", accent="#7C3AED")
        attach_btn.clicked.connect(self._select_file)
        layout.addWidget(attach_btn)
        layout.addStretch()

    def _select_file(self) -> None:
        QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Выберите файл",  # title
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg)"
        )


class MainApp(QtWidgets.QWidget):
    def __init__(self, operator: str) -> None:
        super().__init__()
        self.operator = operator
        self.history: List[ScanRecord] = []
        self.errors: List[ScanRecord] = []
        self.stack = QtWidgets.QStackedWidget()

        self.scanner_page = ScannerPage()
        self.history_page = TablePage(
            "История операций",
            "Последние отправления фиксируются автоматически",
        )
        self.errors_page = TablePage(
            "Ошибки и претензии",
            "Отправления, помеченные операторами как проблемные",
        )
        self.camera_page = CameraPage()

        self.stack.addWidget(self.scanner_page)
        self.stack.addWidget(self.history_page)
        self.stack.addWidget(self.errors_page)
        self.stack.addWidget(self.camera_page)

        self.scanner_page.scan_registered.connect(self._handle_scan)
        self.scanner_page.error_registered.connect(self._handle_error)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)

        sidebar = self._build_sidebar()
        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)

    def _build_sidebar(self) -> QtWidgets.QWidget:
        container = Card()
        container.setFixedWidth(280)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setSpacing(18)

        avatar = QtWidgets.QLabel()
        avatar.setPixmap(self._build_avatar_pixmap())
        avatar.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(avatar)

        welcome = QtWidgets.QLabel(f"Добро пожаловать,\n{self.operator}")
        welcome.setAlignment(QtCore.Qt.AlignCenter)
        welcome.setStyleSheet(
            "font-size: 20px; font-weight: 600; color: #0F172A;"
        )
        layout.addWidget(welcome)

        layout.addWidget(self._nav_button("Сканер", 0))
        layout.addWidget(self._nav_button("История", 1))
        layout.addWidget(self._nav_button("Ошибки", 2))
        layout.addWidget(self._nav_button("Камера", 3))
        layout.addStretch()

        return container

    def _nav_button(self, label: str, index: int, icon: str | None = None) -> NavigationButton:
        btn = NavigationButton(label, icon)
        btn.setChecked(index == 0)
        btn.clicked.connect(lambda: self.stack.setCurrentIndex(index))
        return btn

    def _build_avatar_pixmap(self) -> QtGui.QPixmap:
        pixmap = QtGui.QPixmap(120, 120)
        pixmap.fill(QtCore.Qt.transparent)

        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        brush = QtGui.QBrush(QtGui.QColor("#2563EB"))
        painter.setBrush(brush)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(0, 0, 120, 120)

        painter.setPen(QtGui.QPen(QtGui.QColor("white"), 8))
        painter.drawArc(20, 20, 80, 80, 30 * 16, 300 * 16)
        painter.end()
        return pixmap

    def _handle_scan(self, record: ScanRecord) -> None:
        self.history.append(record)
        self.history_page.add_record(record)

    def _handle_error(self, record: ScanRecord) -> None:
        self.errors.append(record)
        self.errors_page.add_record(record)


class ReliseWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Relise Tracking Desktop")
        self.resize(1320, 860)
        self._setup_palette()

        self.login_panel = LoginPanel()
        self.login_panel.login_requested.connect(self._on_login)

        backdrop = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(backdrop)
        layout.setContentsMargins(60, 60, 60, 60)
        layout.setSpacing(40)

        hero = QtWidgets.QLabel()
        hero.setWordWrap(True)
        hero.setStyleSheet(
            "font-size: 34px; font-weight: 700; color: #FFFFFF;"
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            "stop:0 #1D4ED8, stop:1 #0EA5E9);"
            "border-radius: 32px; padding: 40px;"
        )
        hero.setText(
            "Оцифруйте операции склада.\n"
            "Работайте на ноутбуке, моноблоке или планшете"
        )
        layout.addWidget(hero, 1)
        layout.addWidget(self.login_panel, 1)

        self.setCentralWidget(backdrop)

    def _setup_palette(self) -> None:
        palette = self.palette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#EFF4FF"))
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor("#FFFFFF"))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#0F172A"))
        self.setPalette(palette)

    def _on_login(self, username: str) -> None:
        self.centralWidget().deleteLater()
        main_app = MainApp(operator=username)
        wrapper = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(wrapper)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.addWidget(main_app)
        self.setCentralWidget(wrapper)


def main() -> None:
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    app = QtWidgets.QApplication([])
    font = QtGui.QFont("Inter", 11)
    app.setFont(font)
    window = ReliseWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
