"""Windows desktop adaptation of the Tracking mobile application."""
from __future__ import annotations

import asyncio
import inspect
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import flet as ft
import requests


API_HOST = "https://tracking-api-b4jb.onrender.com"


class ApiError(RuntimeError):
    """Raised when backend returns non-success response."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class LoginResponse:
    token: str
    access_level: int
    role: str
    surname: str


@dataclass(frozen=True)
class AdminCredentials:
    token: str


def _raise_for_status(response: requests.Response) -> None:
    if response.ok:
        return
    try:
        data = response.json()
        message = str(data.get("detail") or data.get("message") or response.text)
    except ValueError:
        message = response.text
    raise ApiError(message or "Сервер повернув помилку", response.status_code)


class ApiClient:
    """Thin wrapper above HTTP endpoints used by the Flutter app."""

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self._session = session or requests.Session()

    def login(self, surname: str, password: str) -> LoginResponse:
        response = self._session.post(
            f"{API_HOST}/login",
            json={"surname": surname.strip(), "password": password.strip()},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        _raise_for_status(response)
        data = response.json()
        return LoginResponse(
            token=str(data.get("token", "")),
            access_level=int(data.get("access_level", 2)),
            role=str(data.get("role", "viewer")),
            surname=str(data.get("surname", surname)),
        )

    def register(self, surname: str, password: str) -> None:
        response = self._session.post(
            f"{API_HOST}/register",
            json={"surname": surname.strip(), "password": password.strip()},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        _raise_for_status(response)

    def admin_login(self, password: str) -> AdminCredentials:
        response = self._session.post(
            f"{API_HOST}/admin_login",
            json={"password": password.strip()},
            headers={"Accept": "application/json"},
            timeout=10,
        )
        _raise_for_status(response)
        data = response.json()
        token = str(data.get("token", ""))
        if not token:
            raise ApiError("Сервер не повернув токен доступу", response.status_code)
        return AdminCredentials(token=token)

    def add_record(self, token: str, user_name: str, boxid: str, ttn: str) -> Dict:
        response = self._session.post(
            f"{API_HOST}/add_record",
            json={"user_name": user_name, "boxid": boxid, "ttn": ttn},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        _raise_for_status(response)
        return response.json()

    def get_history(self, token: str) -> List[Dict]:
        response = self._session.get(
            f"{API_HOST}/get_history",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        _raise_for_status(response)
        return list(response.json())

    def clear_history(self, token: str) -> None:
        response = self._session.delete(
            f"{API_HOST}/clear_history",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        _raise_for_status(response)

    def get_errors(self, token: str) -> List[Dict]:
        response = self._session.get(
            f"{API_HOST}/get_errors",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        _raise_for_status(response)
        return list(response.json())

    def clear_errors(self, token: str) -> None:
        response = self._session.delete(
            f"{API_HOST}/clear_errors",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        _raise_for_status(response)

    def delete_error(self, token: str, error_id: int) -> None:
        response = self._session.delete(
            f"{API_HOST}/delete_error/{error_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        _raise_for_status(response)

    def get_pending_users(self, token: str) -> List[Dict]:
        response = self._session.get(
            f"{API_HOST}/admin/registration_requests",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        _raise_for_status(response)
        return list(response.json())

    def approve_pending(self, token: str, request_id: int, role: str) -> None:
        response = self._session.post(
            f"{API_HOST}/admin/registration_requests/{request_id}/approve",
            json={"role": role},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        _raise_for_status(response)

    def reject_pending(self, token: str, request_id: int) -> None:
        response = self._session.post(
            f"{API_HOST}/admin/registration_requests/{request_id}/reject",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        _raise_for_status(response)

    def get_users(self, token: str) -> List[Dict]:
        response = self._session.get(
            f"{API_HOST}/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        _raise_for_status(response)
        return list(response.json())

    def update_user(
        self,
        token: str,
        user_id: int,
        *,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Dict:
        payload: Dict[str, object] = {}
        if role is not None:
            payload["role"] = role
        if is_active is not None:
            payload["is_active"] = is_active
        if not payload:
            raise ApiError("Немає даних для оновлення", 400)
        response = self._session.patch(
            f"{API_HOST}/admin/users/{user_id}",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        _raise_for_status(response)
        return response.json()


ROLE_LABELS = {
    "admin": "🔑 Адмін",
    "operator": "🧰 Оператор",
    "viewer": "👁 Перегляд",
}
ROLE_LEVEL = {"admin": 1, "operator": 0, "viewer": 2}
ROLE_CAN_CLEAR_HISTORY = {"admin": True, "operator": False, "viewer": False}
ROLE_CAN_CLEAR_ERRORS = {"admin": True, "operator": True, "viewer": False}


class ConnectionState(Enum):
    ONLINE = "online"
    OFFLINE = "offline"


@dataclass
class SessionState:
    token: Optional[str] = None
    user_name: str = "operator"
    role: str = "viewer"
    access_level: int = 2
    connection: ConnectionState = ConnectionState.ONLINE
    admin_token: Optional[str] = None
    client_storage_loaded: bool = False
    last_note: str = ""

    def reset(self) -> None:
        self.token = None
        self.user_name = "operator"
        self.role = "viewer"
        self.access_level = 2
        self.connection = ConnectionState.ONLINE
        self.admin_token = None
        self.last_note = ""

    @property
    def is_authenticated(self) -> bool:
        return bool(self.token)

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, ROLE_LABELS["viewer"])

    @property
    def can_clear_history(self) -> bool:
        return ROLE_CAN_CLEAR_HISTORY.get(self.role, False)

    @property
    def can_clear_errors(self) -> bool:
        return ROLE_CAN_CLEAR_ERRORS.get(self.role, False)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def to_dict(self) -> Dict[str, str]:
        return {
            "token": self.token or "",
            "user_name": self.user_name,
            "role": self.role,
            "access_level": str(self.access_level),
        }

    def apply_persisted(self, data: Dict[str, str]) -> None:
        token = data.get("token") or None
        role = data.get("role") or "viewer"
        self.token = token
        self.role = role
        self.access_level = int(data.get("access_level") or ROLE_LEVEL.get(role, 2))
        self.user_name = data.get("user_name") or "operator"


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def format_human_datetime(value: Optional[str]) -> str:
    dt = parse_iso(value)
    if not dt:
        return value or "—"
    return dt.strftime("%d.%m.%Y %H:%M:%S")


def ensure_sorted(records: List[dict], *, key: str, reverse: bool = True) -> List[dict]:
    def sort_key(item: dict) -> datetime:
        return parse_iso(item.get(key)) or datetime.fromtimestamp(0)

    return sorted(records, key=sort_key, reverse=reverse)


def unique(sequence: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for item in sequence:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


@dataclass
class QueuedRecord:
    boxid: str
    ttn: str
    user_name: str
    payload: dict
    row_id: Optional[int] = None


class OfflineQueue:
    """Simple SQLite backed FIFO queue."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    boxid TEXT NOT NULL,
                    ttn TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def enqueue(self, *, boxid: str, ttn: str, user_name: str, payload: dict) -> None:
        serialized = json.dumps(payload, ensure_ascii=False)
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO queue(boxid, ttn, user_name, payload) VALUES (?, ?, ?, ?)",
                (boxid, ttn, user_name, serialized),
            )
            conn.commit()

    def pending(self) -> List[QueuedRecord]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT id, boxid, ttn, user_name, payload FROM queue ORDER BY id ASC"
            )
            records = []
            for row in cursor.fetchall():
                records.append(
                    QueuedRecord(
                        boxid=row["boxid"],
                        ttn=row["ttn"],
                        user_name=row["user_name"],
                        payload=json.loads(row["payload"]),
                        row_id=row["id"],
                    )
                )
            return records

    def delete_many(self, ids: Iterable[int]) -> None:
        ids = list(ids)
        if not ids:
            return
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM queue WHERE id IN (%s)" % ",".join("?" for _ in ids), ids
            )
            conn.commit()


@dataclass
class HistoryFilters:
    boxid: str = ""
    ttn: str = ""
    user: str = ""
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class TrackingDesktopApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.api = ApiClient()
        self.state = SessionState()
        self.queue = OfflineQueue(Path(page.app_storage_dir) / "offline_queue.db")
        self.history_records: List[Dict[str, Any]] = []
        self.errors: List[Dict[str, Any]] = []
        self.history_filters = HistoryFilters()
        self.login_mode = "login"
        self._connectivity_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    async def init(self) -> None:
        self.page.title = "Tracking Desktop"
        self.page.padding = 24
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.window_width = 1200
        self.page.window_height = 800
        self.page.on_route_change = self._route_change
        self.page.on_view_pop = self._view_pop
        await self._load_session()
        self.page.go("/scanner" if self.state.is_authenticated else "/")
        if self._connectivity_task is None:
            self._connectivity_task = asyncio.create_task(self._watch_connectivity())

    async def _load_session(self) -> None:
        stored = await self.page.client_storage.get_async("session")
        if isinstance(stored, dict):
            self.state.apply_persisted({k: str(v) for k, v in stored.items()})
        self.state.client_storage_loaded = True

    async def _persist_session(self) -> None:
        await self.page.client_storage.set_async("session", self.state.to_dict())

    async def _watch_connectivity(self) -> None:
        while True:
            if self.state.token:
                await self.sync_offline_records(show_messages=False)
            await asyncio.sleep(15)

    # ------------------------------------------------------------------
    def _route_change(self, event: ft.RouteChangeEvent) -> None:
        self.page.views.clear()
        if event.route == "/":
            self.page.views.append(self._build_login_view())
        elif event.route == "/scanner":
            self.page.views.append(self._build_scanner_view())
        elif event.route == "/history":
            self.page.views.append(self._build_history_view())
        elif event.route == "/errors":
            self.page.views.append(self._build_errors_view())
        elif event.route == "/statistics":
            self.page.views.append(self._build_statistics_view())
        elif event.route == "/admin":
            self.page.views.append(self._build_admin_view())
        else:
            self.page.views.append(
                ft.View(
                    route=event.route,
                    controls=[
                        ft.Container(
                            alignment=ft.alignment.center,
                            expand=True,
                            content=ft.Text("Сторінку не знайдено", size=24),
                        )
                    ],
                )
            )
        self.page.update()

    def _view_pop(self, event: ft.ViewPopEvent) -> None:
        self.page.views.pop()
        top = self.page.views[-1]
        self.page.go(top.route)

    # ------------------------------------------------------------------
    def _build_login_view(self) -> ft.View:
        surname_input = ft.TextField(label="Прізвище", autofocus=True)
        password_input = ft.TextField(label="Пароль", password=True)
        login_status = ft.Text(value="", color=ft.colors.RED)

        register_surname = ft.TextField(label="Прізвище")
        register_password = ft.TextField(label="Пароль", password=True)
        register_confirm = ft.TextField(label="Підтвердження пароля", password=True)
        register_status = ft.Text(value="", color=ft.colors.GREEN)

        def switch_mode(e: ft.ControlEvent) -> None:
            self.login_mode = "register" if self.login_mode == "login" else "login"
            login_status.value = ""
            register_status.value = ""
            toggle.text = (
                "Перейти до реєстрації" if self.login_mode == "login" else "Повернутися до входу"
            )
            self.page.update()

        async def handle_login() -> None:
            surname = surname_input.value.strip()
            password = password_input.value.strip()
            if not surname or not password:
                login_status.value = "Введіть прізвище та пароль"
                self.page.update()
                return

            def task() -> Any:
                return self.api.login(surname, password)

            def on_complete(result: ft.ThreadRunResult) -> None:
                if result.error:
                    if isinstance(result.error, ApiError):
                        login_status.value = result.error.message
                    else:
                        login_status.value = "Не вдалося з'єднатися з сервером"
                    self.page.update()
                    return
                resp = result.result
                self.state.token = resp.token
                self.state.access_level = resp.access_level
                self.state.role = resp.role
                self.state.user_name = resp.surname
                login_status.value = ""
                self.page.update()
                asyncio.create_task(self._persist_session())
                self.page.go("/scanner")

            self.page.run_thread(task, on_complete=on_complete)

        async def handle_register() -> None:
            surname = register_surname.value.strip()
            password = register_password.value.strip()
            confirm = register_confirm.value.strip()
            if not surname or not password or not confirm:
                register_status.value = "Заповніть усі поля"
                register_status.color = ft.colors.RED
                self.page.update()
                return
            if len(password) < 6:
                register_status.value = "Пароль має містити щонайменше 6 символів"
                register_status.color = ft.colors.RED
                self.page.update()
                return
            if password != confirm:
                register_status.value = "Паролі не співпадають"
                register_status.color = ft.colors.RED
                self.page.update()
                return

            def task() -> Any:
                self.api.register(surname, password)
                return None

            def on_complete(result: ft.ThreadRunResult) -> None:
                if result.error:
                    if isinstance(result.error, ApiError):
                        register_status.value = result.error.message
                    else:
                        register_status.value = "Не вдалося відправити заявку"
                    register_status.color = ft.colors.RED
                else:
                    register_status.value = (
                        "Заявку відправлено. Дочекайтесь підтвердження адміністратора."
                    )
                    register_status.color = ft.colors.GREEN
                    register_surname.value = ""
                    register_password.value = ""
                    register_confirm.value = ""
                self.page.update()

            self.page.run_thread(task, on_complete=on_complete)

        def open_admin_dialog(e: ft.ControlEvent) -> None:
            password_field = ft.TextField(label="Пароль адміністратора", password=True)

            def proceed(dialog_event: ft.ControlEvent) -> None:
                password = password_field.value.strip()
                if not password:
                    return

                def task() -> Any:
                    return self.api.admin_login(password)

                def on_complete(result: ft.ThreadRunResult) -> None:
                    if result.error:
                        message = (
                            result.error.message
                            if isinstance(result.error, ApiError)
                            else "Не вдалося увійти"
                        )
                        self.page.snack_bar = ft.SnackBar(ft.Text(message))
                        self.page.snack_bar.open = True
                        self.page.update()
                        return
                    self.state.admin_token = result.result.token
                    self.page.update()
                    asyncio.create_task(self._persist_session())
                    self.page.go("/admin")

                self.page.run_thread(task, on_complete=on_complete)
                dialog.open = False
                self.page.update()

            dialog = ft.AlertDialog(
                title=ft.Text("Вхід до панелі адміністратора"),
                content=password_field,
                actions=[
                    ft.TextButton("Скасувати", on_click=lambda _: self.page.close(dialog)),
                    ft.ElevatedButton("Увійти", on_click=proceed),
                ],
            )
            self.page.dialog = dialog
            dialog.open = True
            self.page.update()

        login_button = ft.ElevatedButton(
            "Увійти",
            icon=ft.icons.LOGIN,
            on_click=lambda _: asyncio.create_task(handle_login()),
            bgcolor=ft.colors.BLUE,
            color=ft.colors.WHITE,
        )
        register_button = ft.ElevatedButton(
            "Відправити заявку",
            icon=ft.icons.SEND,
            on_click=lambda _: asyncio.create_task(handle_register()),
        )

        toggle = ft.TextButton(
            "Перейти до реєстрації" if self.login_mode == "login" else "Повернутися до входу",
            on_click=switch_mode,
        )

        card_content: List[ft.Control] = [
            ft.Text("Tracking Desktop", size=32, weight=ft.FontWeight.BOLD),
            ft.Text("Однаковий інтерфейс із мобільною версією", color=ft.colors.GREY),
            ft.Container(height=20),
        ]

        if self.login_mode == "login":
            card_content.extend(
                [
                    surname_input,
                    password_input,
                    ft.Container(height=10),
                    login_status,
                    ft.Row([login_button], alignment=ft.MainAxisAlignment.END),
                    ft.TextButton("Вхід для адміністратора", on_click=open_admin_dialog),
                ]
            )
        else:
            card_content.extend(
                [
                    register_surname,
                    register_password,
                    register_confirm,
                    ft.Container(height=10),
                    register_status,
                    ft.Row([register_button], alignment=ft.MainAxisAlignment.END),
                ]
            )

        card_content.append(toggle)

        login_card = ft.Container(
            bgcolor=ft.colors.WHITE,
            padding=40,
            border_radius=16,
            expand=0,
            width=500,
            shadow=ft.BoxShadow(blur_radius=25, color=ft.colors.BLACK12, spread_radius=1),
            content=ft.Column(card_content, tight=True, spacing=12),
        )

        return ft.View(
            route="/",
            vertical_alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    alignment=ft.alignment.center,
                    expand=True,
                    content=ft.ResponsiveRow(
                        [
                            ft.Column(
                                [login_card],
                                alignment=ft.MainAxisAlignment.CENTER,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                col={'xs': 12, 'sm': 8, 'md': 6, 'lg': 5},
                            )
                        ]
                    ),
                )
            ],
        )

    # ------------------------------------------------------------------
    def _build_top_app_bar(self, show_history: bool = True) -> ft.Container:
        role_chip = ft.Chip(
            label=ft.Text(self.state.role_label),
            bgcolor=ft.colors.with_opacity(0.1, ft.colors.BLUE if self.state.is_admin else ft.colors.GREY),
        )
        return ft.Container(
            bgcolor=ft.colors.WHITE,
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
            content=ft.ResponsiveRow(
                [
                    ft.Column(
                        [
                            ft.Text(
                                f"Оператор: {self.state.user_name}",
                                size=18,
                                weight=ft.FontWeight.W_500,
                            ),
                            ft.Row(
                                [
                                    role_chip,
                                    ft.Text(
                                        "🟢 Онлайн" if self.state.connection == ConnectionState.ONLINE else "🔴 Офлайн",
                                        color=ft.colors.GREEN if self.state.connection == ConnectionState.ONLINE else ft.colors.RED,
                                    ),
                                ],
                                spacing=12,
                            ),
                        ],
                        col={'xs': 12, 'sm': 6, 'md': 6, 'lg': 6},
                    ),
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.IconButton(ft.icons.HISTORY, tooltip="Історія", on_click=lambda _: self.page.go("/history"))
                                    if show_history
                                    else None,
                                    ft.IconButton(
                                        ft.icons.ERROR_OUTLINE,
                                        tooltip="Помилки",
                                        on_click=lambda _: self.page.go("/errors"),
                                    ),
                                    ft.IconButton(
                                        ft.icons.INSIGHTS,
                                        tooltip="Статистика",
                                        visible=self.state.is_admin,
                                        on_click=lambda _: self.page.go("/statistics"),
                                    ),
                                    ft.IconButton(
                                        ft.icons.ADMIN_PANEL_SETTINGS,
                                        tooltip="Адмін панель",
                                        visible=self.state.admin_token is not None,
                                        on_click=lambda _: self.page.go("/admin"),
                                    ),
                                    ft.IconButton(
                                        ft.icons.LOGOUT,
                                        tooltip="Вийти",
                                        on_click=lambda _: asyncio.create_task(self._logout()),
                                        bgcolor=ft.colors.with_opacity(0.1, ft.colors.RED),
                                    ),
                                ],
                                spacing=6,
                                alignment=ft.MainAxisAlignment.END,
                            )
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                        col={'xs': 12, 'sm': 6, 'md': 6, 'lg': 6},
                    ),
                ]
            ),
        )

    async def _logout(self) -> None:
        self.state.reset()
        await self._persist_session()
        self.page.go("/")

    # ------------------------------------------------------------------
    def _build_scanner_view(self) -> ft.View:
        box_field = ft.TextField(label="BoxID", autofocus=True, text_align=ft.TextAlign.CENTER, width=300)
        ttn_field = ft.TextField(label="ТТН", text_align=ft.TextAlign.CENTER, width=300)
        status_text = ft.Text(self.state.last_note, size=16)

        def submit_record(e: ft.ControlEvent | None = None) -> None:
            boxid = box_field.value.strip()
            ttn = ttn_field.value.strip()
            if not boxid or not ttn:
                return

            record = {"user_name": self.state.user_name, "boxid": boxid, "ttn": ttn}

            def task() -> Any:
                if not self.state.token:
                    raise ApiError("Необхідна авторизація", 401)
                return self.api.add_record(self.state.token, self.state.user_name, boxid, ttn)

            def on_complete(result: ft.ThreadRunResult) -> None:
                if result.error:
                    self.state.connection = ConnectionState.OFFLINE
                    self.queue.enqueue(boxid=boxid, ttn=ttn, user_name=self.state.user_name, payload=record)
                    status_text.value = "📦 Збережено локально (офлайн)"
                else:
                    response: Dict[str, Any] = result.result
                    note = response.get("note")
                    if note:
                        status_text.value = f"⚠️ Дублікат: {note}"
                    else:
                        status_text.value = "✅ Успішно додано"
                        self.state.connection = ConnectionState.ONLINE
                box_field.value = ""
                ttn_field.value = ""
                self.state.last_note = status_text.value
                self.page.update()
                asyncio.create_task(self._persist_session())
                asyncio.create_task(self.sync_offline_records(show_messages=False))

            self.page.run_thread(task, on_complete=on_complete)

        sync_button = ft.ElevatedButton(
            "Синхронізувати офлайн записи",
            icon=ft.icons.CLOUD_SYNC,
            on_click=lambda _: asyncio.create_task(self.sync_offline_records()),
        )

        scanner_layout = ft.Column(
            [
                ft.Text(
                    "Сканування", size=28, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER
                ),
                ft.Text(
                    "Послідовно введіть BoxID та ТТН (підтримується сканер-емулятор клавіатури).",
                    text_align=ft.TextAlign.CENTER,
                    color=ft.colors.GREY,
                ),
                ft.Container(height=20),
                ft.Row([box_field, ttn_field], alignment=ft.MainAxisAlignment.CENTER, spacing=16, wrap=True),
                ft.Row(
                    [
                        ft.ElevatedButton("Надіслати", icon=ft.icons.SEND, on_click=submit_record),
                        sync_button,
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=12,
                ),
                ft.Container(height=20),
                status_text,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        )

        return ft.View(
            route="/scanner",
            padding=0,
            controls=[
                ft.Column(
                    [
                        self._build_top_app_bar(),
                        ft.Container(
                            expand=True,
                            alignment=ft.alignment.center,
                            padding=40,
                            content=scanner_layout,
                        ),
                    ],
                    expand=True,
                )
            ],
        )

    # ------------------------------------------------------------------
    async def sync_offline_records(self, show_messages: bool = True) -> None:
        pending = self.queue.pending()
        if not pending or not self.state.token:
            if show_messages and not pending:
                self.page.snack_bar = ft.SnackBar(ft.Text("Локальних записів немає"))
                self.page.snack_bar.open = True
                self.page.update()
            return

        sent_ids: List[int] = []

        def task(record: Dict[str, Any]) -> None:
            self.api.add_record(
                self.state.token or "",
                record["user_name"],
                record["boxid"],
                record["ttn"],
            )

        loop = asyncio.get_running_loop()
        for item in pending:
            try:
                await loop.run_in_executor(None, task, item.payload)
                sent_ids.append(item.row_id or 0)
            except Exception:
                self.state.connection = ConnectionState.OFFLINE
                break
        if sent_ids:
            self.queue.delete_many(sent_ids)
            self.state.connection = ConnectionState.ONLINE
            if show_messages:
                self.page.snack_bar = ft.SnackBar(ft.Text(f"Синхронізовано {len(sent_ids)} записів"))
                self.page.snack_bar.open = True
                self.page.update()
        else:
            if show_messages and self.state.connection == ConnectionState.OFFLINE:
                self.page.snack_bar = ft.SnackBar(ft.Text("Сервер недоступний"))
                self.page.snack_bar.open = True
                self.page.update()
        self.page.update()

    # ------------------------------------------------------------------
    def _build_history_view(self) -> ft.View:
        table = ft.DataTable(columns=[], rows=[])

        async def load_history() -> None:
            if not self.state.token:
                return

            def task() -> List[Dict[str, Any]]:
                return self.api.get_history(self.state.token or "")

            def on_complete(result: ft.ThreadRunResult) -> None:
                if result.error:
                    self.page.snack_bar = ft.SnackBar(ft.Text("Не вдалося завантажити історію"))
                    self.page.snack_bar.open = True
                    self.page.update()
                    return
                self.history_records = ensure_sorted(result.result, key="datetime")
                self._apply_history_filters(table)

            self.page.run_thread(task, on_complete=on_complete)

        asyncio.create_task(load_history())

        content = ft.Column(
            [
                self._build_filters(table),
                ft.Container(height=12),
                ft.Container(
                    bgcolor=ft.colors.WHITE,
                    padding=12,
                    border_radius=8,
                    expand=True,
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        "Історія сканувань",
                                        size=22,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.IconButton(
                                        ft.icons.REFRESH,
                                        tooltip="Оновити",
                                        on_click=lambda _: asyncio.create_task(load_history()),
                                    ),
                                    ft.IconButton(
                                        ft.icons.DELETE_SWEEP,
                                        tooltip="Очистити історію",
                                        visible=self.state.can_clear_history,
                                        on_click=lambda _: asyncio.create_task(self._clear_history(table)),
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ft.Divider(),
                            ft.Container(expand=True, content=ft.SingleChildScrollView(content=table)),
                        ]
                    ),
                ),
            ],
            expand=True,
        )

        return ft.View(
            route="/history",
            padding=0,
            controls=[ft.Column([self._build_top_app_bar(show_history=False), ft.Expanded(content)])],
        )

    def _build_filters(self, table: ft.DataTable) -> ft.Container:
        box_filter = ft.TextField(label="BoxID", on_change=lambda _: apply_filters(), col={"xs": 12, "sm": 6, "md": 2, "lg": 2})
        ttn_filter = ft.TextField(label="ТТН", on_change=lambda _: apply_filters(), col={"xs": 12, "sm": 6, "md": 2, "lg": 2})
        user_filter = ft.TextField(label="Користувач", on_change=lambda _: apply_filters(), col={"xs": 12, "sm": 6, "md": 2, "lg": 2})
        date_picker = ft.DatePicker()
        start_time_picker = ft.TimePicker()
        end_time_picker = ft.TimePicker()

        for picker in (date_picker, start_time_picker, end_time_picker):
            if picker not in self.page.overlay:
                self.page.overlay.append(picker)

        def apply_filters(_: Any = None) -> None:
            self.history_filters.boxid = box_filter.value.strip()
            self.history_filters.ttn = ttn_filter.value.strip()
            self.history_filters.user = user_filter.value.strip()
            self._apply_history_filters(table)

        def pick_date(_: ft.ControlEvent) -> None:
            def on_date_change(e: ft.DatePickerChangeEvent) -> None:
                selected = getattr(e.control, "value", None) or getattr(e, "data", None)
                self.history_filters.date = selected
                self._apply_history_filters(table)

            date_picker.on_change = on_date_change
            date_picker.pick_date()

        def pick_time(_: ft.ControlEvent, *, start: bool) -> None:
            def on_time_change(e: ft.TimePickerChangeEvent) -> None:
                value = getattr(e.control, "value", None) or getattr(e, "data", None)
                if start:
                    self.history_filters.start_time = value
                else:
                    self.history_filters.end_time = value
                self._apply_history_filters(table)

            picker = start_time_picker if start else end_time_picker
            picker.on_change = on_time_change
            picker.pick_time()

        return ft.Container(
            bgcolor=ft.colors.WHITE,
            padding=12,
            border_radius=8,
            content=ft.ResponsiveRow(
                [
                    ft.Text("Фільтри", size=20, weight=ft.FontWeight.BOLD, col={"xs": 12, "sm": 12, "md": 2, "lg": 2}),
                    box_filter,
                    ttn_filter,
                    user_filter,
                    ft.IconButton(
                        ft.icons.CALENDAR_MONTH,
                        tooltip="Обрати дату",
                        on_click=pick_date,
                        col={"xs": 6, "sm": 3, "md": 1, "lg": 1},
                    ),
                    ft.IconButton(
                        ft.icons.ACCESS_TIME,
                        tooltip="Початковий час",
                        on_click=lambda e: pick_time(e, start=True),
                        col={"xs": 6, "sm": 3, "md": 1, "lg": 1},
                    ),
                    ft.IconButton(
                        ft.icons.ACCESS_TIME_FILLED,
                        tooltip="Кінцевий час",
                        on_click=lambda e: pick_time(e, start=False),
                        col={"xs": 6, "sm": 3, "md": 1, "lg": 1},
                    ),
                    ft.TextButton(
                        "Скинути",
                        on_click=lambda _: self._reset_history_filters(table, box_filter, ttn_filter, user_filter),
                        col={"xs": 6, "sm": 3, "md": 1, "lg": 1},
                    ),
                ]
            ),
        )

    def _reset_history_filters(
        self,
        table: ft.DataTable,
        box_filter: ft.TextField,
        ttn_filter: ft.TextField,
        user_filter: ft.TextField,
    ) -> None:
        self.history_filters = HistoryFilters()
        box_filter.value = ""
        ttn_filter.value = ""
        user_filter.value = ""
        self._apply_history_filters(table)
        self.page.update()

    def _apply_history_filters(self, table: ft.DataTable) -> None:
        filtered = list(self.history_records)
        if self.history_filters.boxid:
            filtered = [r for r in filtered if self.history_filters.boxid in str(r.get("boxid", ""))]
        if self.history_filters.ttn:
            filtered = [r for r in filtered if self.history_filters.ttn in str(r.get("ttn", ""))]
        if self.history_filters.user:
            filtered = [
                r
                for r in filtered
                if self.history_filters.user.lower() in str(r.get("user_name", "")).lower()
            ]
        if self.history_filters.date:
            filtered = [
                r
                for r in filtered
                if (dt := parse_iso(r.get("datetime"))) and dt.strftime("%Y-%m-%d") == self.history_filters.date
            ]
        if self.history_filters.start_time or self.history_filters.end_time:
            start = self.history_filters.start_time
            end = self.history_filters.end_time
            filtered = [
                r
                for r in filtered
                if (dt := parse_iso(r.get("datetime")))
                and (start is None or dt.strftime("%H:%M") >= start)
                and (end is None or dt.strftime("%H:%M") <= end)
            ]

        table.columns = [
            ft.DataColumn(ft.Text("Дата")),
            ft.DataColumn(ft.Text("BoxID")),
            ft.DataColumn(ft.Text("ТТН")),
            ft.DataColumn(ft.Text("Користувач")),
        ]
        table.rows = [
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(format_human_datetime(item.get("datetime")))),
                    ft.DataCell(ft.Text(str(item.get("boxid", "")))),
                    ft.DataCell(ft.Text(str(item.get("ttn", "")))),
                    ft.DataCell(ft.Text(str(item.get("user_name", "")))),
                ]
            )
            for item in filtered
        ]
        self.page.update()

    async def _clear_history(self, table: ft.DataTable) -> None:
        if not self.state.can_clear_history or not self.state.token:
            return

        confirmed = await self._confirm("Очистити історію сканувань?")
        if not confirmed:
            return

        def task() -> None:
            self.api.clear_history(self.state.token or "")

        def on_complete(result: ft.ThreadRunResult) -> None:
            if result.error:
                self.page.snack_bar = ft.SnackBar(ft.Text("Не вдалося очистити історію"))
                self.page.snack_bar.open = True
            else:
                self.history_records = []
                self._apply_history_filters(table)
                self.page.snack_bar = ft.SnackBar(ft.Text("Історію очищено"))
                self.page.snack_bar.open = True
            self.page.update()

        self.page.run_thread(task, on_complete=on_complete)

    async def _confirm(self, message: str) -> bool:
        future: asyncio.Future[bool] = asyncio.get_event_loop().create_future()

        def close(value: bool) -> None:
            dialog.open = False
            self.page.update()
            future.set_result(value)

        dialog = ft.AlertDialog(
            title=ft.Text(message),
            actions=[
                ft.TextButton("Скасувати", on_click=lambda _: close(False)),
                ft.ElevatedButton("Підтвердити", on_click=lambda _: close(True)),
            ],
        )
        self.page.dialog = dialog
        dialog.open = True
        self.page.update()
        return await future

    # ------------------------------------------------------------------
    def _build_errors_view(self) -> ft.View:
        list_view = ft.ListView(expand=True, spacing=12)

        async def load_errors() -> None:
            if not self.state.token:
                return

            def task() -> List[Dict[str, Any]]:
                return self.api.get_errors(self.state.token or "")

            def on_complete(result: ft.ThreadRunResult) -> None:
                if result.error:
                    self.page.snack_bar = ft.SnackBar(ft.Text("Не вдалося завантажити помилки"))
                    self.page.snack_bar.open = True
                    self.page.update()
                    return
                self.errors = ensure_sorted(result.result, key="datetime")
                self._populate_errors(list_view)

            self.page.run_thread(task, on_complete=on_complete)

        asyncio.create_task(load_errors())

        content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Журнал помилок", size=24, weight=ft.FontWeight.BOLD),
                        ft.IconButton(ft.icons.REFRESH, on_click=lambda _: asyncio.create_task(load_errors())),
                        ft.IconButton(
                            ft.icons.DELETE_SWEEP,
                            visible=self.state.can_clear_errors,
                            on_click=lambda _: asyncio.create_task(self._clear_errors(list_view)),
                        ),
                    ]
                ),
                ft.Divider(),
                ft.Container(expand=True, content=list_view),
            ],
            expand=True,
            padding=20,
        )

        return ft.View(
            route="/errors",
            padding=0,
            controls=[ft.Column([self._build_top_app_bar(show_history=False), ft.Expanded(content)])],
        )

    def _populate_errors(self, list_view: ft.ListView) -> None:
        list_view.controls = [
            ft.Container(
                bgcolor=ft.colors.WHITE,
                padding=16,
                border_radius=12,
                content=ft.Column(
                    [
                        ft.Text(format_human_datetime(item.get("datetime")), weight=ft.FontWeight.BOLD),
                        ft.Text(f"BoxID: {item.get('boxid', '—')}"),
                        ft.Text(f"ТТН: {item.get('ttn', '—')}"),
                        ft.Text(f"Повідомлення: {item.get('note', '—')}"),
                        ft.Text(
                            f"Оператор: {item.get('user_name', '—')}",
                            color=ft.colors.GREY,
                        ),
                        ft.Row(
                            [
                                ft.FilledButton(
                                    "Видалити",
                                    icon=ft.icons.DELETE,
                                    on_click=lambda _, error_id=item.get("id"): asyncio.create_task(
                                        self._delete_error(error_id, list_view)
                                    ),
                                    visible=self.state.can_clear_errors,
                                ),
                            ]
                        ),
                    ],
                    spacing=6,
                ),
            )
            for item in self.errors
        ]
        self.page.update()

    async def _clear_errors(self, list_view: ft.ListView) -> None:
        if not self.state.can_clear_errors or not self.state.token:
            return
        confirmed = await self._confirm("Очистити всі помилки?")
        if not confirmed:
            return

        def task() -> None:
            self.api.clear_errors(self.state.token or "")

        def on_complete(result: ft.ThreadRunResult) -> None:
            if result.error:
                self.page.snack_bar = ft.SnackBar(ft.Text("Не вдалося очистити помилки"))
                self.page.snack_bar.open = True
            else:
                self.errors = []
                self._populate_errors(list_view)
                self.page.snack_bar = ft.SnackBar(ft.Text("Помилки очищено"))
                self.page.snack_bar.open = True
            self.page.update()

        self.page.run_thread(task, on_complete=on_complete)

    async def _delete_error(self, error_id: int, list_view: ft.ListView) -> None:
        if not self.state.can_clear_errors or not self.state.token:
            return
        confirmed = await self._confirm(f"Видалити помилку #{error_id}?")
        if not confirmed:
            return

        def task() -> None:
            self.api.delete_error(self.state.token or "", error_id)

        def on_complete(result: ft.ThreadRunResult) -> None:
            if result.error:
                self.page.snack_bar = ft.SnackBar(ft.Text("Не вдалося видалити помилку"))
                self.page.snack_bar.open = True
            else:
                self.errors = [e for e in self.errors if e.get("id") != error_id]
                self._populate_errors(list_view)
            self.page.update()

        self.page.run_thread(task, on_complete=on_complete)

    # ------------------------------------------------------------------
    def _build_statistics_view(self) -> ft.View:
        stats_column = ft.Column(spacing=16)

        async def load_stats() -> None:
            if not self.state.is_admin or not self.state.token:
                return

            def task() -> Dict[str, List[Dict[str, Any]]]:
                history = self.api.get_history(self.state.token or "")
                errors = self.api.get_errors(self.state.token or "")
                return {"history": history, "errors": errors}

            def on_complete(result: ft.ThreadRunResult) -> None:
                if result.error:
                    self.page.snack_bar = ft.SnackBar(ft.Text("Не вдалося оновити статистику"))
                    self.page.snack_bar.open = True
                    self.page.update()
                    return
                data = result.result
                history = ensure_sorted(data["history"], key="datetime")
                errors = ensure_sorted(data["errors"], key="datetime")
                stats_column.controls = self._compose_stats_cards(history, errors)
                self.page.update()

            self.page.run_thread(task, on_complete=on_complete)

        asyncio.create_task(load_stats())

        content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Статистика", size=28, weight=ft.FontWeight.BOLD),
                        ft.IconButton(ft.icons.REFRESH, on_click=lambda _: asyncio.create_task(load_stats())),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                stats_column,
            ],
            expand=True,
            padding=24,
        )

        return ft.View(
            route="/statistics",
            padding=0,
            controls=[ft.Column([self._build_top_app_bar(show_history=False), ft.Expanded(content)])],
        )

    def _compose_stats_cards(self, history: List[Dict[str, Any]], errors: List[Dict[str, Any]]) -> List[ft.Control]:
        total_scans = len(history)
        unique_users = len(unique(item.get("user_name", "") for item in history))
        total_errors = len(errors)
        error_users = len(unique(item.get("user_name", "") for item in errors))

        operator_counts = Counter(item.get("user_name", "") for item in history)
        top_operator, top_operator_count = ("—", 0)
        if operator_counts:
            top_operator, top_operator_count = operator_counts.most_common(1)[0]

        error_counts = Counter(item.get("user_name", "") for item in errors)
        top_error_operator, top_error_count = ("—", 0)
        if error_counts:
            top_error_operator, top_error_count = error_counts.most_common(1)[0]

        def info_card(title: str, value: str, icon: str, color: str) -> ft.Container:
            return ft.Container(
                bgcolor=ft.colors.with_opacity(0.08, color),
                padding=24,
                border_radius=16,
                col={'xs': 12, 'sm': 6, 'md': 3},
                content=ft.Column(
                    [
                        ft.Icon(icon, size=36, color=color),
                        ft.Text(title, weight=ft.FontWeight.W_600, color=color),
                        ft.Text(value, size=26, weight=ft.FontWeight.BOLD),
                    ]
                ),
            )

        cards: List[ft.Control] = [
            ft.ResponsiveRow(
                [
                    info_card("Загалом сканувань", str(total_scans), ft.icons.QR_CODE_SCANNER, ft.colors.BLUE),
                    info_card("Унікальних операторів", str(unique_users), ft.icons.GROUP, ft.colors.GREEN),
                    info_card("Помилок", str(total_errors), ft.icons.ERROR, ft.colors.RED),
                    info_card("Операторів з помилками", str(error_users), ft.icons.REPORT, ft.colors.ORANGE),
                ]
            ),
            ft.Container(height=12),
            ft.ResponsiveRow(
                [
                    info_card(
                        "Топ оператор",
                        f"{top_operator} ({top_operator_count})",
                        ft.icons.EMOJI_EVENTS,
                        ft.colors.INDIGO,
                    ),
                    info_card(
                        "Найбільше помилок",
                        f"{top_error_operator} ({top_error_count})",
                        ft.icons.WARNING,
                        ft.colors.DEEP_ORANGE,
                    ),
                ]
            ),
        ]
        return cards

    # ------------------------------------------------------------------
    def _build_admin_view(self) -> ft.View:
        if not self.state.admin_token:
            return ft.View(
                route="/admin",
                controls=[ft.Text("Авторизуйтеся як адміністратор", size=20)],
            )

        pending_column = ft.Column(spacing=12)
        users_column = ft.Column(spacing=12)
        passwords_column = ft.Column(spacing=12)

        async def load_admin_data() -> None:
            token = self.state.admin_token or ""

            def task() -> Dict[str, Any]:
                pending = self.api.get_pending_users(token)
                users = self.api.get_users(token)
                passwords = self.api.get_role_passwords(token)
                return {"pending": pending, "users": users, "passwords": passwords}

            def on_complete(result: ft.ThreadRunResult) -> None:
                if result.error:
                    self.page.snack_bar = ft.SnackBar(ft.Text("Не вдалося завантажити адмін панель"))
                    self.page.snack_bar.open = True
                    self.page.update()
                    return
                data = result.result
                pending_column.controls = [self._pending_user_card(item) for item in data["pending"]]
                users_column.controls = [self._managed_user_card(item) for item in data["users"]]
                passwords_column.controls = [self._password_card(role, value) for role, value in data["passwords"].items()]
                self.page.update()

            self.page.run_thread(task, on_complete=on_complete)

        self._pending_card_click = lambda request_id, role: asyncio.create_task(
            self._approve_user(request_id, role, load_admin_data)
        )
        self._reject_click = lambda request_id: asyncio.create_task(
            self._reject_user(request_id, load_admin_data)
        )
        self._change_role_click = lambda user_id, role: asyncio.create_task(
            self._update_user(user_id, role=role, refresh=load_admin_data)
        )
        self._toggle_user_click = lambda user_id, is_active: asyncio.create_task(
            self._update_user(user_id, is_active=is_active, refresh=load_admin_data)
        )
        self._update_password_click = lambda role: asyncio.create_task(
            self._update_role_password(role, load_admin_data)
        )

        asyncio.create_task(load_admin_data())

        content = ft.Column(
            [
                ft.Text("Адміністративна панель", size=28, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Text("Заявки на реєстрацію", size=20, weight=ft.FontWeight.W_600),
                pending_column,
                ft.Divider(),
                ft.Text("Користувачі", size=20, weight=ft.FontWeight.W_600),
                users_column,
                ft.Divider(),
                ft.Text("API паролі для ролей", size=20, weight=ft.FontWeight.W_600),
                passwords_column,
            ],
            expand=True,
            padding=24,
        )

        return ft.View(
            route="/admin",
            padding=0,
            controls=[ft.Column([self._build_top_app_bar(show_history=False), ft.Expanded(content)])],
        )

    def _pending_user_card(self, item: Dict[str, Any]) -> ft.Control:
        request_id = int(item.get("id", 0))
        surname = item.get("surname", "—")
        created = format_human_datetime(item.get("created_at"))
        return ft.Container(
            bgcolor=ft.colors.WHITE,
            padding=16,
            border_radius=12,
            content=ft.Column(
                [
                    ft.Text(surname, size=20, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Створено: {created}", color=ft.colors.GREY),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "Адмін",
                                icon=ft.icons.VERIFIED_USER,
                                on_click=lambda _, rid=request_id: self._pending_card_click(rid, "admin"),
                            ),
                            ft.ElevatedButton(
                                "Оператор",
                                icon=ft.icons.WORK,
                                on_click=lambda _, rid=request_id: self._pending_card_click(rid, "operator"),
                            ),
                            ft.ElevatedButton(
                                "Перегляд",
                                icon=ft.icons.REMOVE_RED_EYE,
                                on_click=lambda _, rid=request_id: self._pending_card_click(rid, "viewer"),
                            ),
                            ft.TextButton(
                                "Відхилити",
                                on_click=lambda _, rid=request_id: self._reject_click(rid),
                                style=ft.ButtonStyle(color={ft.MaterialState.DEFAULT: ft.colors.RED}),
                            ),
                        ],
                        wrap=True,
                    ),
                ]
            ),
        )

    def _managed_user_card(self, item: Dict[str, Any]) -> ft.Control:
        user_id = int(item.get("id", 0))
        surname = item.get("surname", "—")
        role = item.get("role", "viewer")
        is_active = item.get("is_active", True)
        created = format_human_datetime(item.get("created_at"))
        return ft.Container(
            bgcolor=ft.colors.WHITE,
            padding=16,
            border_radius=12,
            content=ft.Column(
                [
                    ft.Text(surname, size=20, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Роль: {role}"),
                    ft.Text(f"Створено: {created}", color=ft.colors.GREY),
                    ft.Row(
                        [
                            ft.Dropdown(
                                width=180,
                                value=role,
                                options=[
                                    ft.dropdown.Option("admin"),
                                    ft.dropdown.Option("operator"),
                                    ft.dropdown.Option("viewer"),
                                ],
                                on_change=lambda e, uid=user_id: self._change_role_click(uid, e.control.value),
                            ),
                            ft.Switch(
                                label="Активний",
                                value=is_active,
                                on_change=lambda e, uid=user_id: self._toggle_user_click(uid, e.control.value),
                            ),
                        ],
                        wrap=True,
                    ),
                ]
            ),
        )

    def _password_card(self, role: str, value: str) -> ft.Control:
        return ft.Container(
            bgcolor=ft.colors.WHITE,
            padding=16,
            border_radius=12,
            content=ft.Row(
                [
                    ft.Text(f"Роль: {role}", weight=ft.FontWeight.BOLD),
                    ft.Text("*" * len(value) if value else "—"),
                    ft.TextButton("Змінити", on_click=lambda _, r=role: self._update_password_click(r)),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )

    async def _approve_user(self, request_id: int, role: str, refresh) -> None:
        token = self.state.admin_token or ""

        def task() -> None:
            self.api.approve_pending(token, request_id, role)

        def on_complete(result: ft.ThreadRunResult) -> None:
            if result.error:
                self.page.snack_bar = ft.SnackBar(ft.Text("Не вдалося підтвердити користувача"))
                self.page.snack_bar.open = True
            else:
                self.page.snack_bar = ft.SnackBar(ft.Text("Користувача підтверджено"))
                self.page.snack_bar.open = True
                asyncio.create_task(refresh())
            self.page.update()

        self.page.run_thread(task, on_complete=on_complete)

    async def _reject_user(self, request_id: int, refresh) -> None:
        token = self.state.admin_token or ""

        def task() -> None:
            self.api.reject_pending(token, request_id)

        def on_complete(result: ft.ThreadRunResult) -> None:
            if result.error:
                self.page.snack_bar = ft.SnackBar(ft.Text("Не вдалося відхилити користувача"))
                self.page.snack_bar.open = True
            else:
                asyncio.create_task(refresh())
            self.page.update()

        self.page.run_thread(task, on_complete=on_complete)

    async def _update_user(
        self,
        user_id: int,
        *,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        refresh=None,
    ) -> None:
        token = self.state.admin_token or ""

        def task() -> Dict[str, Any]:
            return self.api.update_user(token, user_id, role=role, is_active=is_active)

        def on_complete(result: ft.ThreadRunResult) -> None:
            message = "Дані користувача оновлено" if not result.error else "Не вдалося оновити користувача"
            self.page.snack_bar = ft.SnackBar(ft.Text(message))
            self.page.snack_bar.open = True
            if not result.error and refresh is not None:
                asyncio.create_task(refresh())
            self.page.update()

        self.page.run_thread(task, on_complete=on_complete)

    async def _update_role_password(self, role: str, refresh) -> None:
        token = self.state.admin_token or ""
        field = ft.TextField(label=f"Новий пароль для {role}", password=True)

        def on_save(_: ft.ControlEvent) -> None:
            value = field.value.strip()
            if not value:
                return

            def task() -> None:
                self.api.update_role_password(token, role, value)

            def on_complete(result: ft.ThreadRunResult) -> None:
                message = "Пароль оновлено" if not result.error else "Не вдалося оновити пароль"
                self.page.snack_bar = ft.SnackBar(ft.Text(message))
                self.page.snack_bar.open = True
                if not result.error:
                    asyncio.create_task(refresh())
                self.page.update()

            self.page.run_thread(task, on_complete=on_complete)
            dialog.open = False
            self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text("Оновити пароль"),
            content=field,
            actions=[
                ft.TextButton("Скасувати", on_click=lambda _: self.page.close(dialog)),
                ft.ElevatedButton("Зберегти", on_click=on_save),
            ],
        )
        self.page.dialog = dialog
        dialog.open = True
        self.page.update()

async def main(page: ft.Page) -> None:
    app = TrackingDesktopApp(page)
    await app.init()


if __name__ == "__main__":
    app_kwargs: Dict[str, Any] = {"target": main}
    try:
        signature = inspect.signature(ft.app)
    except (TypeError, ValueError):  # pragma: no cover - signature resolution edge cases
        signature = None
    if signature and "use_asyncio" in signature.parameters:
        app_kwargs["use_asyncio"] = True
    ft.app(**app_kwargs)
