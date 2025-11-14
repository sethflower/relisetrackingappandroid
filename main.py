"""Windows desktop adaptation of the Flutter TrackingApp for Windows."""
from __future__ import annotations

import calendar
import csv
import json
import threading
from collections import defaultdict
from dataclasses import dataclass, asdict, fields
from datetime import datetime, date, time as dtime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from enum import Enum

try:
    import requests
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit(
        "The 'requests' package is required. Install it with 'pip install requests'."
    ) from exc

API_BASE = "https://tracking-api-b4jb.onrender.com"
STATE_PATH = Path(__file__).with_name("tracking_app_state.json")
QUEUE_PATH = Path(__file__).with_name("offline_queue.json")

# Design constants for a refreshed, modern UI system
PRIMARY_BG = "#020817"
SECONDARY_BG = "#0b1220"
CARD_BG = "#f8fafc"
SURFACE_BG = "#e2e8f0"
ACCENT_COLOR = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
TEXT_PRIMARY = "#0f172a"
TEXT_SECONDARY = "#475467"
NEUTRAL_BORDER = "#d0d5dd"
SHADOW_COLOR = "#0f172a"
HERO_PANEL_BG = "#111c3a"
PILL_BG = "#dbeafe"
PILL_TEXT = "#1d4ed8"
ERROR_COLOR = "#d92d20"
SUCCESS_COLOR = "#039855"
WARNING_COLOR = "#f79009"


def _grid_reset(widget: tk.Misc) -> None:
    """Remove all children from the grid manager."""

    for child in widget.grid_slaves():
        child.grid_forget()

def maximize_window(window: tk.Misc) -> None:
    """Expand a Tk window to occupy the entire screen."""

    try:
        window.state("zoomed")
    except tk.TclError:
        try:
            window.attributes("-zoomed", True)
        except tk.TclError:
            window.attributes("-fullscreen", True)



MONTH_NAMES = [
    "",
    "Січень",
    "Лютий",
    "Березень",
    "Квітень",
    "Травень",
    "Червень",
    "Липень",
    "Серпень",
    "Вересень",
    "Жовтень",
    "Листопад",
    "Грудень",
]

WEEKDAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]


class ApiException(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class UserRole(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"

    @property
    def label(self) -> str:
        return {
            UserRole.ADMIN: "🔑 Адмін",
            UserRole.OPERATOR: "🧰 Оператор",
            UserRole.VIEWER: "👁 Перегляд",
        }[self]

    @property
    def description(self) -> str:
        return {
            UserRole.ADMIN: "Повний доступ до функцій та керування користувачами",
            UserRole.OPERATOR: "Додавання записів та базовий функціонал",
            UserRole.VIEWER: "Перегляд інформації без змін",
        }[self]

    @property
    def level(self) -> int:
        return {
            UserRole.ADMIN: 1,
            UserRole.OPERATOR: 0,
            UserRole.VIEWER: 2,
        }[self]

    @staticmethod
    def from_value(value: Optional[str], access_level: Optional[int] = None) -> "UserRole":
        if value:
            normalized = value.lower()
            if normalized == "admin":
                return UserRole.ADMIN
            if normalized == "operator":
                return UserRole.OPERATOR
            if normalized == "viewer":
                return UserRole.VIEWER
        if access_level == 1:
            return UserRole.ADMIN
        if access_level == 0:
            return UserRole.OPERATOR
        return UserRole.VIEWER


@dataclass
class PendingUser:
    id: int
    surname: str
    created_at: Optional[datetime]


@dataclass
class ManagedUser:
    id: int
    surname: str
    role: UserRole
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class UserApi:
    @staticmethod
    def _url(path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{API_BASE}{path}"

    @staticmethod
    def _headers(token: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _extract_message(payload: Any, status: int) -> str:
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("message")
            if isinstance(detail, str) and detail:
                return detail
        return f"Помилка сервера ({status})"

    @staticmethod
    def _request(
        method: str,
        path: str,
        *,
        token: Optional[str] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        response = requests.request(
            method,
            UserApi._url(path),
            headers=UserApi._headers(token),
            json=json_data,
            timeout=15,
        )
        if 200 <= response.status_code < 300:
            if response.content:
                try:
                    return response.json()
                except ValueError:
                    return None
            return None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        raise ApiException(
            UserApi._extract_message(payload, response.status_code),
            response.status_code,
        )

    @staticmethod
    def register_user(surname: str, password: str) -> None:
        UserApi._request(
            "POST",
            "/register",
            json_data={"surname": surname, "password": password},
        )

    @staticmethod
    def admin_login(password: str) -> str:
        data = UserApi._request(
            "POST",
            "/admin_login",
            json_data={"password": password},
        )
        if not isinstance(data, dict):
            raise ApiException("Некоректна відповідь сервера", 500)
        token = str(data.get("token", ""))
        if not token:
            raise ApiException("Сервер не повернув токен доступу", 500)
        return token

    @staticmethod
    def fetch_pending_users(token: str) -> List[PendingUser]:
        data = UserApi._request("GET", "/admin/registration_requests", token=token)
        results: List[PendingUser] = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    created = parse_api_datetime(item.get("created_at"))
                    results.append(
                        PendingUser(
                            id=int(float(item.get("id", 0) or 0)),
                            surname=str(item.get("surname", "Невідомий користувач")),
                            created_at=created,
                        )
                    )
        return results

    @staticmethod
    def approve_pending_user(token: str, request_id: int, role: UserRole) -> None:
        UserApi._request(
            "POST",
            f"/admin/registration_requests/{request_id}/approve",
            token=token,
            json_data={"role": role.value},
        )

    @staticmethod
    def reject_pending_user(token: str, request_id: int) -> None:
        UserApi._request(
            "POST",
            f"/admin/registration_requests/{request_id}/reject",
            token=token,
        )

    @staticmethod
    def fetch_users(token: str) -> List[ManagedUser]:
        data = UserApi._request("GET", "/admin/users", token=token)
        results: List[ManagedUser] = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    role = UserRole.from_value(item.get("role"))
                    created = parse_api_datetime(item.get("created_at"))
                    updated = parse_api_datetime(item.get("updated_at"))
                    results.append(
                        ManagedUser(
                            id=int(float(item.get("id", 0) or 0)),
                            surname=str(item.get("surname", "Невідомий користувач")),
                            role=role,
                            is_active=bool(item.get("is_active", False)),
                            created_at=created,
                            updated_at=updated,
                        )
                    )
        return results

    @staticmethod
    def update_user(
        token: str,
        user_id: int,
        *,
        role: Optional[UserRole] = None,
        is_active: Optional[bool] = None,
    ) -> ManagedUser:
        payload: Dict[str, Any] = {}
        if role is not None:
            payload["role"] = role.value
        if is_active is not None:
            payload["is_active"] = is_active
        if not payload:
            raise ApiException("Немає даних для оновлення", 400)
        data = UserApi._request(
            "PATCH",
            f"/admin/users/{user_id}",
            token=token,
            json_data=payload,
        )
        if not isinstance(data, dict):
            raise ApiException("Некоректна відповідь сервера", 500)
        role_value = UserRole.from_value(data.get("role"))
        return ManagedUser(
            id=int(float(data.get("id", user_id) or user_id)),
            surname=str(data.get("surname", "Невідомий користувач")),
            role=role_value,
            is_active=bool(data.get("is_active", False)),
            created_at=parse_api_datetime(data.get("created_at")),
            updated_at=parse_api_datetime(data.get("updated_at")),
        )

    @staticmethod
    def delete_user(token: str, user_id: int) -> None:
        UserApi._request("DELETE", f"/admin/users/{user_id}", token=token)

    @staticmethod
    def fetch_role_passwords(token: str) -> Dict[UserRole, str]:
        data = UserApi._request("GET", "/admin/role-passwords", token=token)
        results: Dict[UserRole, str] = {}
        if isinstance(data, dict):
            for key, value in data.items():
                role = UserRole.from_value(str(key))
                results[role] = "" if value is None else str(value)
        return results

    @staticmethod
    def update_role_password(token: str, role: UserRole, password: str) -> None:
        UserApi._request(
            "POST",
            f"/admin/role-passwords/{role.value}",
            token=token,
            json_data={"password": password},
        )


def normalize_role(role_name: Optional[str], access_level: Optional[int]) -> UserRole:
    return UserRole.from_value(role_name, access_level)


def get_role_info(role_name: Optional[str], access_level: Optional[int]) -> Dict[str, Any]:
    role = normalize_role(role_name, access_level)
    color = {
        UserRole.ADMIN: "#e53935",
        UserRole.OPERATOR: "#1e88e5",
        UserRole.VIEWER: "#757575",
    }[role]
    can_clear_history = role == UserRole.ADMIN
    can_clear_errors = role in (UserRole.ADMIN, UserRole.OPERATOR)
    return {
        "label": role.label,
        "color": color,
        "can_clear_history": can_clear_history,
        "can_clear_errors": can_clear_errors,
        "is_admin": role == UserRole.ADMIN,
        "level": access_level if access_level is not None else role.level,
        "role": role,
    }


@dataclass
class AppState:
    token: Optional[str] = None
    access_level: Optional[int] = None
    user_name: str = ""
    user_role: str = "viewer"

    @classmethod
    def load(cls) -> "AppState":
        if STATE_PATH.exists():
            try:
                data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                allowed = {field.name for field in fields(cls)}
                filtered = {
                    key: value
                    for key, value in data.items()
                    if key in allowed
                }
                return cls(**filtered)
            except Exception:
                STATE_PATH.unlink(missing_ok=True)
        return cls()

    def save(self) -> None:
        STATE_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


class OfflineQueue:
    _lock = threading.Lock()

    @staticmethod
    def _load() -> List[Dict[str, Any]]:
        if QUEUE_PATH.exists():
            try:
                return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
            except Exception:
                QUEUE_PATH.unlink(missing_ok=True)
        return []

    @classmethod
    def add_record(cls, record: Dict[str, Any]) -> None:
        with cls._lock:
            pending = cls._load()
            pending.append(record)
            QUEUE_PATH.write_text(json.dumps(pending, indent=2), encoding="utf-8")

    @classmethod
    def sync_pending(
        cls, token: str, callback: Optional[Callable[[int], None]] = None
    ) -> None:
        def worker() -> None:
            with cls._lock:
                pending = cls._load()
            if not pending or not token:
                return
            synced: List[Dict[str, Any]] = []
            for record in pending:
                try:
                    response = requests.post(
                        f"{API_BASE}/add_record",
                        json=record,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                        timeout=10,
                    )
                    if response.status_code == 200:
                        synced.append(record)
                except requests.RequestException:
                    break
            if synced:
                with cls._lock:
                    remaining = [r for r in cls._load() if r not in synced]
                    QUEUE_PATH.write_text(
                        json.dumps(remaining, indent=2), encoding="utf-8"
                    )
            if callback:
                callback(len(synced))

        threading.Thread(target=worker, daemon=True).start()


def parse_api_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    cleaned = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone()
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def create_large_entry(
    parent: tk.Misc,
    *,
    textvariable: tk.StringVar,
    show: Optional[str] = None,
    justify: str = "center",
) -> tk.Entry:
    """Factory for oversized entry widgets with consistent styling."""

    entry = tk.Entry(
        parent,
        textvariable=textvariable,
        show=show,
        justify=justify,
        font=("Segoe UI", 32, "bold"),
        bg=SURFACE_BG,
        fg=TEXT_PRIMARY,
        insertbackground=TEXT_PRIMARY,
        relief="flat",
        bd=0,
        highlightthickness=2,
        highlightcolor=ACCENT_COLOR,
        highlightbackground=NEUTRAL_BORDER,
        disabledforeground="#94a3b8",
        disabledbackground="#e2e8f0",
    )
    return entry
    
    
def create_form_entry(
    parent: tk.Misc,
    *,
    textvariable: tk.StringVar,
    show: Optional[str] = None,
    justify: str = "left",
) -> tk.Entry:
    entry = tk.Entry(
        parent,
        textvariable=textvariable,
        show=show,
        justify=justify,
        font=("Segoe UI", 18, "bold"),
        bg=SURFACE_BG,
        fg=TEXT_PRIMARY,
        insertbackground=TEXT_PRIMARY,
        relief="flat",
        bd=0,
        highlightthickness=2,
        highlightcolor=ACCENT_COLOR,
        highlightbackground=NEUTRAL_BORDER,
        disabledforeground="#94a3b8",
        disabledbackground="#e2e8f0",
    )
    return entry




class DatePickerDialog(tk.Toplevel):
    """Calendar-style picker that returns a :class:`date` selection."""

    def __init__(self, parent: tk.Misc, initial: Optional[date] = None) -> None:
        super().__init__(parent)
        self.configure(bg=CARD_BG)
        self.resizable(False, False)
        self.title("Оберіть дату")
        self.transient(parent)
        self.grab_set()

       
        

        today = date.today()
        self._initial = initial
        self.result: Optional[date] = initial
        self._cancelled = True
        base = initial or today
        self._current_year = base.year
        self._current_month = base.month
        
        container = tk.Frame(self, bg=CARD_BG, padx=24, pady=24)
        container.grid(row=0, column=0)
        header = tk.Frame(container, bg=CARD_BG)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Button(
            header,
            text="◀",
            width=3,
            command=self._go_previous,
            style="Secondary.TButton",
        ).grid(row=0, column=0, padx=(0, 12))

        self._title_var = tk.StringVar()
        ttk.Label(header, textvariable=self._title_var, style="CardHeading.TLabel").grid(
            row=0, column=1, sticky="ew"
        )

        ttk.Button(
            header,
            text="▶",
            width=3,
            command=self._go_next,
            style="Secondary.TButton",
        ).grid(row=0, column=2, padx=(12, 0))

        self._days_frame = tk.Frame(container, bg=CARD_BG)
        self._days_frame.grid(row=1, column=0, pady=(16, 0))

        footer = tk.Frame(container, bg=CARD_BG)
        footer.grid(row=2, column=0, pady=(20, 0), sticky="ew")
        footer.columnconfigure(0, weight=1)
        footer.columnconfigure(1, weight=1)
        footer.columnconfigure(2, weight=1)

        ttk.Button(
            footer,
            text="Сьогодні",
            command=self._select_today,
            style="Secondary.TButton",
        ).grid(row=0, column=0, padx=6)

        ttk.Button(
            footer,
            text="Очистити",
            command=self._clear,
            style="Secondary.TButton",
        ).grid(row=0, column=1, padx=6)

        ttk.Button(
            footer,
            text="Закрити",
            command=self._close,
            style="Secondary.TButton",
        ).grid(row=0, column=2, padx=6)

        self._render_days()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._center_over_parent(parent)

    def _center_over_parent(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        width = self.winfo_width()
        height = self.winfo_height()
        x = parent_x + (parent_width - width) // 2
        y = parent_y + (parent_height - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        

    def _render_days(self) -> None:
        for child in self._days_frame.winfo_children():
            child.destroy()

        title = f"{MONTH_NAMES[self._current_month]} {self._current_year}"
        self._title_var.set(title)

        for idx, name in enumerate(WEEKDAY_NAMES):
            tk.Label(
                self._days_frame,
                text=name,
                font=("Segoe UI", 12, "bold"),
                bg=CARD_BG,
                fg=TEXT_SECONDARY,
                width=4,
            ).grid(row=0, column=idx, padx=4, pady=4)

        month_calendar = calendar.Calendar(firstweekday=0)
        for row, week in enumerate(month_calendar.monthdayscalendar(self._current_year, self._current_month), start=1):
            for col, day in enumerate(week):
                if day == 0:
                    spacer = tk.Frame(self._days_frame, width=60, height=40, bg=CARD_BG)
                    spacer.grid(row=row, column=col, padx=4, pady=4)
                    continue
                btn = ttk.Button(
                    self._days_frame,
                    text=str(day),
                    width=4,
                    command=lambda d=day: self._select_day(d),
                    style="Secondary.TButton",
                )
                btn.grid(row=row, column=col, padx=4, pady=4)

    def _go_previous(self) -> None:
        month = self._current_month - 1
        year = self._current_year
        if month == 0:
            month = 12
            year -= 1
        self._current_month = month
        self._current_year = year
        self._render_days()

    def _go_next(self) -> None:
        month = self._current_month + 1
        year = self._current_year
        if month == 13:
            month = 1
            year += 1
        self._current_month = month
        self._current_year = year
        self._render_days()

    def _select_day(self, day: int) -> None:
        self.result = date(self._current_year, self._current_month, day)
        self._cancelled = False
        self.destroy()

    def _select_today(self) -> None:
        today = date.today()
        self._current_year = today.year
        self._current_month = today.month
        self._render_days()
        self.result = today
        self._cancelled = False
        self.destroy()

    def _clear(self) -> None:
        self.result = None
        self._cancelled = False
        self.destroy()

    def _close(self) -> None:
        self._cancelled = True
        self.destroy()

    def show(self) -> Optional[date]:
        self.wait_window()
        if self._cancelled:
            return self._initial
        return self.result


class TimePickerDialog(tk.Toplevel):
    """Simple hour/minute picker returning :class:`datetime.time`."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        initial: Optional[dtime] = None,
    ) -> None:
        super().__init__(parent)
        self.configure(bg=CARD_BG)
        self.resizable(False, False)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        

        self._initial = initial
        self.result: Optional[dtime] = initial
        self._cancelled = True

        container = tk.Frame(self, bg=CARD_BG, padx=24, pady=24)
        container.grid(row=0, column=0)

        ttk.Label(
            container,
            text="Оберіть час",
            style="CardHeading.TLabel",
        ).grid(row=0, column=0, columnspan=3, pady=(0, 16))
        
        self._hour_var = tk.StringVar(
            value=f"{initial.hour:02d}" if initial else "00"
        )
        self._minute_var = tk.StringVar(
            value=f"{initial.minute:02d}" if initial else "00"
        )

        hour_spin = tk.Spinbox(
            container,
            from_=0,
            to=23,
            wrap=True,
            textvariable=self._hour_var,
            font=("Segoe UI", 18, "bold"),
            width=4,
            justify="center",
            state="readonly",
        )
        hour_spin.grid(row=1, column=0, padx=6)

        tk.Label(
            container,
            text=":",
            font=("Segoe UI", 18, "bold"),
            bg=CARD_BG,
            fg=TEXT_PRIMARY,
        ).grid(row=1, column=1)

        minute_spin = tk.Spinbox(
            container,
            from_=0,
            to=59,
            wrap=True,
            textvariable=self._minute_var,
            font=("Segoe UI", 18, "bold"),
            width=4,
            justify="center",
            state="readonly",
        )
        minute_spin.grid(row=1, column=2, padx=6)

        controls = tk.Frame(container, bg=CARD_BG)
        controls.grid(row=2, column=0, columnspan=3, pady=(20, 0))

        ttk.Button(
            controls,
            text="Очистити",
            command=self._clear,
            style="Secondary.TButton",
        ).grid(row=0, column=0, padx=6)

        ttk.Button(
            controls,
            text="Застосувати",
            command=self._apply,
            style="Secondary.TButton",
        ).grid(row=0, column=1, padx=6)

        ttk.Button(
            controls,
            text="Закрити",
            command=self._close,
            style="Secondary.TButton",
        ).grid(row=0, column=2, padx=6)

        self.protocol("WM_DELETE_WINDOW", self._close)
        
        self._center_over_parent(parent)

    def _center_over_parent(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        width = self.winfo_width()
        height = self.winfo_height()
        x = parent_x + (parent_width - width) // 2
        y = parent_y + (parent_height - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")    

    def _clear(self) -> None:
        self.result = None
        self._cancelled = False
        self.destroy()

    def _apply(self) -> None:
        try:
            hours = int(self._hour_var.get())
            minutes = int(self._minute_var.get())
        except ValueError:
            messagebox.showerror("Помилка", "Невірний час")
            return
        hours %= 24
        minutes %= 60
        self.result = dtime(hour=hours, minute=minutes)
        self._cancelled = False
        self.destroy()

    def _close(self) -> None:
        self._cancelled = True
        self.destroy()

    def show(self) -> Optional[dtime]:
        self.wait_window()
        if self._cancelled:
            return self._initial
        return self.result


class BaseFrame(tk.Frame):
    """Base frame that keeps every view consistent with the app brand."""

    def __init__(self, app: "TrackingApp", *, background: str = PRIMARY_BG) -> None:
        super().__init__(app, bg=background, highlightthickness=0)
        self.app = app
        self.pack_propagate(False)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._responsive_handlers: list[Callable[[int, int], None]] = []
        self.bind("<Configure>", self._on_resize, add="+")

    def register_responsive(self, handler: Callable[[int, int], None]) -> None:
        """Register a callback that adapts layout to width/height changes."""

        self._responsive_handlers.append(handler)

    def _on_resize(self, event: tk.Event) -> None:
        width = getattr(event, "width", self.winfo_width())
        height = getattr(event, "height", self.winfo_height())
        for handler in self._responsive_handlers:
            handler(width, height)

    def perform_logout(self) -> None:
        if not messagebox.askyesno("Підтвердження", "Вийти з акаунту?"):
            return
        self.app.state_data = AppState()
        self.app.state_data.save()
        self.app.show_login()

    def build_surface(
        self,
        *,
        title: str,
        subtitle: str,
        nav_actions: List[Tuple[str, Callable[[], None]]],
    ) -> tuple[tk.Frame, tk.Frame]:
        shell = tk.Frame(self, bg=PRIMARY_BG, padx=48, pady=48)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        app_bar = tk.Frame(shell, bg=PRIMARY_BG)
        app_bar.grid(row=0, column=0, sticky="ew")
        app_bar.columnconfigure(0, weight=1)
        app_bar.columnconfigure(1, weight=1)

        brand = tk.Frame(app_bar, bg=PRIMARY_BG)
        brand.grid(row=0, column=0, sticky="w")
        tk.Label(
            brand,
            text=title,
            font=("Segoe UI", 28, "bold"),
            fg="#f8fafc",
            bg=PRIMARY_BG,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            brand,
            text=subtitle,
            font=("Segoe UI", 13),
            fg="#94a3b8",
            bg=PRIMARY_BG,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        user_area = tk.Frame(app_bar, bg=PRIMARY_BG)
        user_area.grid(row=0, column=1, sticky="e")
        tk.Label(
            user_area,
            text=self.app.state_data.user_name or "Оператор",
            font=("Segoe UI", 14, "bold"),
            fg="#e2e8f0",
            bg=PRIMARY_BG,
        ).grid(row=0, column=0, sticky="e")
        role_label = self.app.state_data.user_role or "viewer"
        role_info = get_role_info(role_label, self.app.state_data.access_level)
        tk.Label(
            user_area,
            text=role_info["label"],
            font=("Segoe UI", 11, "bold"),
            fg=PILL_TEXT,
            bg=PILL_BG,
            padx=14,
            pady=6,
        ).grid(row=0, column=1, sticky="e", padx=(12, 0))

        nav = tk.Frame(app_bar, bg=PRIMARY_BG)
        nav.grid(row=1, column=0, columnspan=2, sticky="e", pady=(28, 0))
        nav_buttons: list[ttk.Button] = []
        for column, (label, command) in enumerate(nav_actions):
            button = ttk.Button(
                nav,
                text=label,
                command=command,
                style="Secondary.TButton",
            )
            button.grid(row=0, column=column, padx=6, sticky="ew")
            nav_buttons.append(button)

        card = tk.Frame(
            shell,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            bd=0,
        )
        card.grid(row=1, column=0, sticky="nsew", pady=(36, 0))
        card.columnconfigure(0, weight=1)
        self._register_surface_responsive(shell, app_bar, user_area, nav, nav_buttons)
        return shell, card

    def _register_surface_responsive(
        self,
        shell: tk.Frame,
        app_bar: tk.Frame,
        user_area: tk.Frame,
        nav: tk.Frame,
        nav_buttons: List[ttk.Button],
    ) -> None:
        state = {"mode": None}

        def handler(width: int, height: int) -> None:
            breakpoint = "compact" if width < 1360 else "default"
            if state["mode"] == breakpoint:
                return
            state["mode"] = breakpoint
            if breakpoint == "compact":
                shell.configure(padx=24, pady=32)
                app_bar.grid_columnconfigure(0, weight=1)
                app_bar.grid_columnconfigure(1, weight=0)
                user_area.grid_configure(row=1, column=0, columnspan=2, sticky="w", pady=(16, 0))
                nav.grid_configure(row=2, column=0, columnspan=2, sticky="ew", pady=(24, 0))
                _grid_reset(nav)
                nav.columnconfigure(0, weight=1)
                for index, button in enumerate(nav_buttons):
                    button.grid(row=index, column=0, sticky="ew", pady=4)
            else:
                shell.configure(padx=48, pady=48)
                app_bar.grid_columnconfigure(0, weight=1)
                app_bar.grid_columnconfigure(1, weight=1)
                user_area.grid_configure(row=0, column=1, columnspan=1, sticky="e", pady=0)
                nav.grid_configure(row=1, column=0, columnspan=2, sticky="e", pady=(28, 0))
                _grid_reset(nav)
                for index, button in enumerate(nav_buttons):
                    nav.grid_columnconfigure(index, weight=0)
                    button.grid(row=0, column=index, padx=6, sticky="ew")

        self.register_responsive(handler)


class TrackingApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("TrackingApp Windows Edition")
        self.geometry("1280x800")
        self.minsize(1200, 720)
        self.configure(bg=PRIMARY_BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        maximize_window(self)

        self.state_data = AppState.load()
        self._current_frame: Optional[tk.Frame] = None

        self.style = ttk.Style(self)
        self._setup_styles()

        if self.state_data.token and self.state_data.user_name:
            self.show_scanner()
        elif self.state_data.token:
            self.show_username()
        else:
            self.show_login()

    def _setup_styles(self) -> None:
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.style.configure(
            "TLabel",
            font=("Segoe UI", 12),
            background=PRIMARY_BG,
            foreground="#e2e8f0",
        )
        self.style.configure(
            "Muted.TLabel",
            font=("Segoe UI", 11),
            background=PRIMARY_BG,
            foreground="#94a3b8",
        )
        self.style.configure(
            "Card.TLabel",
            font=("Segoe UI", 12),
            background=CARD_BG,
            foreground=TEXT_SECONDARY,
        )
        self.style.configure(
            "CardHeading.TLabel",
            font=("Segoe UI", 26, "bold"),
            background=CARD_BG,
            foreground=TEXT_PRIMARY,
        )
        self.style.configure(
            "CardSubheading.TLabel",
            font=("Segoe UI", 13),
            background=CARD_BG,
            foreground=TEXT_SECONDARY,
        )
        self.style.configure(
            "CardPill.TLabel",
            font=("Segoe UI", 11, "bold"),
            background=PILL_BG,
            foreground=PILL_TEXT,
            padding=(12, 6),
        )
        self.style.configure(
            "Primary.TButton",
            font=("Segoe UI", 13, "bold"),
            padding=(20, 12),
            background=ACCENT_COLOR,
            foreground="white",
            borderwidth=0,
        )
        self.style.map(
            "Primary.TButton",
            background=[("active", ACCENT_HOVER), ("disabled", "#94a3b8")],
            foreground=[("disabled", "#e2e8f0")],
        )
        self.style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 12, "bold"),
            padding=(16, 10),
            background=SECONDARY_BG,
            foreground="#e2e8f0",
            borderwidth=0,
        )
        self.style.map(
            "Secondary.TButton",
            background=[("active", "#1d2939")],
            foreground=[("disabled", "#94a3b8")],
        )
        self.style.configure(
            "Outline.TButton",
            font=("Segoe UI", 12, "bold"),
            padding=(16, 10),
            background=CARD_BG,
            foreground=TEXT_PRIMARY,
            borderwidth=1,
            relief="solid",
        )
        self.style.map(
            "Outline.TButton",
            background=[("active", SURFACE_BG)],
            foreground=[("disabled", "#94a3b8")],
        )
        self.style.configure(
            "Segmented.TButton",
            font=("Segoe UI", 12, "bold"),
            padding=(16, 8),
            background=SURFACE_BG,
            foreground=TEXT_SECONDARY,
            borderwidth=0,
        )
        self.style.map(
            "Segmented.TButton",
            background=[("active", "#cbd5f5")],
        )
        self.style.configure(
            "SegmentedActive.TButton",
            font=("Segoe UI", 12, "bold"),
            padding=(16, 8),
            background=ACCENT_COLOR,
            foreground="white",
            borderwidth=0,
        )
        self.style.map(
            "SegmentedActive.TButton",
            background=[("active", ACCENT_HOVER)],
        )
        self.style.configure(
            "TEntry",
            font=("Segoe UI", 14),
            padding=10,
        )
        self.style.configure(
            "Treeview",
            font=("Segoe UI", 12),
            rowheight=40,
            fieldbackground=CARD_BG,
            background=CARD_BG,
            foreground=TEXT_PRIMARY,
            borderwidth=0,
        )
        self.style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 12, "bold"),
            padding=12,
            background=SECONDARY_BG,
            foreground="#e2e8f0",
            relief="flat",
        )
        self.style.map(
            "Treeview.Heading",
            background=[("active", ACCENT_COLOR)],
        )

    def switch_to(self, frame_cls: type[tk.Frame]) -> None:
        if self._current_frame is not None:
            self._current_frame.destroy()
        frame = frame_cls(self)
        frame.grid(row=0, column=0, sticky="nsew")
        self._current_frame = frame

    def show_login(self) -> None:
        self.switch_to(LoginFrame)

    def show_username(self) -> None:
        self.switch_to(UserNameFrame)

    def show_scanner(self) -> None:
        self.switch_to(ScannerFrame)

    def show_history(self) -> None:
        self.switch_to(HistoryFrame)

    def show_errors(self) -> None:
        self.switch_to(ErrorsFrame)

    def show_statistics(self) -> None:
        role = get_role_info(self.state_data.user_role, self.state_data.access_level)
        if not (role.get("can_clear_history") and role.get("can_clear_errors")):
            messagebox.showerror(
                "Обмежено",
                "Доступ до статистики має лише адміністратор.",
            )
            return
        self.switch_to(StatisticsFrame)


class LoginFrame(BaseFrame):
    def __init__(self, app: TrackingApp) -> None:
        super().__init__(app)
        self.mode = tk.StringVar(value="login")

        # Login state
        self.login_surname_var = tk.StringVar()
        self.login_password_var = tk.StringVar()
        self.login_error_var = tk.StringVar()
        self.login_loading = False

        # Registration state
        self.register_surname_var = tk.StringVar()
        self.register_password_var = tk.StringVar()
        self.register_confirm_var = tk.StringVar()
        self.register_message_var = tk.StringVar()
        self.register_success = False
        self.register_loading = False

        self._build_layout()
        self._layout_mode: Optional[str] = None

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        wrapper = tk.Frame(self, bg=PRIMARY_BG, padx=72, pady=56)
        wrapper.grid(row=0, column=0, sticky="nsew")
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(0, weight=1)
        self.wrapper = wrapper

        card = tk.Frame(
            wrapper,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            bd=0,
        )
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=6)
        card.columnconfigure(1, weight=7)
        card.rowconfigure(0, weight=1)
        self.card = card

        hero = tk.Frame(card, bg=HERO_PANEL_BG, padx=48, pady=48)
        hero.grid(row=0, column=0, sticky="nsew")
        hero.columnconfigure(0, weight=1)
        self.hero = hero
        tk.Label(
            hero,
            text="TrackingApp",
            font=("Segoe UI", 38, "bold"),
            fg="white",
            bg=HERO_PANEL_BG,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            hero,
            text="Професійний контроль логістики",
            font=("Segoe UI", 16),
            fg="#c7d2fe",
            bg=HERO_PANEL_BG,
        ).grid(row=1, column=0, sticky="w", pady=(8, 28))

        features = [
            ("🔐", "Захищена авторизація користувачів"),
            ("⚡", "Миттєва реєстрація BoxID та ТТН"),
            ("📊", "Аналітика для керування командами"),
        ]
        for idx, (icon, text) in enumerate(features, start=2):
            tk.Label(
                hero,
                text=f"{icon}  {text}",
                font=("Segoe UI", 14, "bold"),
                fg="#e0e7ff",
                bg=HERO_PANEL_BG,
            ).grid(row=idx, column=0, sticky="w", pady=(0, 12))

        tk.Label(
            hero,
            text="Від Windows до мобільних застосунків — одна екосистема управління",
            font=("Segoe UI", 11),
            fg="#b4c6ff",
            bg=HERO_PANEL_BG,
            wraplength=360,
            justify="left",
        ).grid(row=len(features) + 2, column=0, sticky="w", pady=(28, 0))

        form_section = tk.Frame(card, bg=CARD_BG, padx=48, pady=48)
        form_section.grid(row=0, column=1, sticky="nsew")
        form_section.columnconfigure(0, weight=1)
        self.form_section = form_section

        ttk.Label(
            form_section,
            text="Windows-версія",
            style="CardPill.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            form_section,
            text="Увійдіть у робочу зону",
            style="CardHeading.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(16, 4))
        ttk.Label(
            form_section,
            text="Обирайте режим роботи: авторизація або заявка на доступ",
            style="CardSubheading.TLabel",
            wraplength=420,
        ).grid(row=2, column=0, sticky="w")

        switcher = tk.Frame(form_section, bg=CARD_BG)
        switcher.grid(row=3, column=0, sticky="ew", pady=(28, 24))
        switcher.columnconfigure(0, weight=1)
        switcher.columnconfigure(1, weight=1)
        self.switcher = switcher

        self.login_tab = ttk.Button(
            switcher,
            text="Вхід",
            style="SegmentedActive.TButton",
            command=lambda: self.set_mode("login"),
        )
        self.login_tab.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.register_tab = ttk.Button(
            switcher,
            text="Реєстрація",
            style="Segmented.TButton",
            command=lambda: self.set_mode("register"),
        )
        self.register_tab.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        self.forms_container = tk.Frame(form_section, bg=CARD_BG)
        self.forms_container.grid(row=4, column=0, sticky="nsew")
        self.forms_container.columnconfigure(0, weight=1)

        self.login_form = self._build_login_form(self.forms_container)
        self.register_form = self._build_registration_form(self.forms_container)

        footer = tk.Frame(form_section, bg=CARD_BG)
        footer.grid(row=5, column=0, sticky="ew", pady=(32, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Button(
            footer,
            text="Панель адміністратора",
            style="Outline.TButton",
            command=self.open_admin_panel,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            footer,
            text="TrackingApp • Від DimonVR",
            style="CardSubheading.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(16, 0))

        self.set_mode(self.mode.get())
        self.register_responsive(self._update_responsive_layout)

    def _build_login_form(self, parent: tk.Misc) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD_BG)
        frame.columnconfigure(0, weight=1)

        tk.Label(
            frame,
            text="Прізвище",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")
        surname_entry = create_form_entry(
            frame, textvariable=self.login_surname_var, justify="left"
        )
        surname_entry.grid(row=1, column=0, sticky="ew", pady=(8, 16), ipady=12)
        surname_entry.bind("<Return>", lambda _: self.login())

        tk.Label(
            frame,
            text="Пароль",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=2, column=0, sticky="w")
        password_entry = create_form_entry(
            frame, textvariable=self.login_password_var, show="*", justify="left"
        )
        password_entry.grid(row=3, column=0, sticky="ew", pady=(8, 8), ipady=12)
        password_entry.bind("<Return>", lambda _: self.login())

        self.login_error_label = tk.Label(
            frame,
            textvariable=self.login_error_var,
            font=("Segoe UI", 12),
            fg=ERROR_COLOR,
            bg=CARD_BG,
        )
        self.login_error_label.grid(row=4, column=0, sticky="ew", pady=(4, 0))

        self.login_button = ttk.Button(
            frame,
            text="Увійти",
            style="Primary.TButton",
            command=self.login,
        )
        self.login_button.grid(row=5, column=0, sticky="ew", pady=(24, 0))

        self.login_surname_entry = surname_entry
        return frame

    def _update_responsive_layout(self, width: int, height: int) -> None:
        mode = "stacked" if width < 1180 else "wide"
        if self._layout_mode == mode:
            return
        self._layout_mode = mode
        if mode == "stacked":
            self.wrapper.configure(padx=28, pady=28)
            self.card.grid_columnconfigure(0, weight=1)
            self.card.grid_columnconfigure(1, weight=0)
            self.card.grid_rowconfigure(0, weight=0)
            self.card.grid_rowconfigure(1, weight=1)
            _grid_reset(self.card)
            self.hero.configure(padx=32, pady=32)
            self.hero.grid(row=0, column=0, sticky="nsew")
            self.form_section.configure(padx=32, pady=32)
            self.form_section.grid(row=1, column=0, sticky="nsew")
        else:
            self.wrapper.configure(padx=72, pady=56)
            self.card.grid_rowconfigure(0, weight=1)
            self.card.grid_columnconfigure(0, weight=6)
            self.card.grid_columnconfigure(1, weight=7)
            _grid_reset(self.card)
            self.hero.configure(padx=48, pady=48)
            self.hero.grid(row=0, column=0, sticky="nsew")
            self.form_section.configure(padx=48, pady=48)
            self.form_section.grid(row=0, column=1, sticky="nsew")

    def _build_registration_form(self, parent: tk.Misc) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD_BG)
        frame.columnconfigure(0, weight=1)

        tk.Label(
            frame,
            text="Прізвище",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")
        surname_entry = create_form_entry(
            frame, textvariable=self.register_surname_var, justify="left"
        )
        surname_entry.grid(row=1, column=0, sticky="ew", pady=(8, 16), ipady=12)
        surname_entry.bind("<Return>", lambda _: self.register())

        tk.Label(
            frame,
            text="Пароль",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=2, column=0, sticky="w")
        password_entry = create_form_entry(
            frame, textvariable=self.register_password_var, show="*", justify="left"
        )
        password_entry.grid(row=3, column=0, sticky="ew", pady=(8, 16), ipady=12)
        password_entry.bind("<Return>", lambda _: self.register())

        tk.Label(
            frame,
            text="Підтвердження пароля",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=4, column=0, sticky="w")
        confirm_entry = create_form_entry(
            frame, textvariable=self.register_confirm_var, show="*", justify="left"
        )
        confirm_entry.grid(row=5, column=0, sticky="ew", pady=(8, 8), ipady=12)
        confirm_entry.bind("<Return>", lambda _: self.register())

        self.register_feedback_label = tk.Label(
            frame,
            textvariable=self.register_message_var,
            font=("Segoe UI", 12),
            fg=SUCCESS_COLOR,
            bg=CARD_BG,
            wraplength=540,
            justify="left",
        )
        self.register_feedback_label.grid(row=6, column=0, sticky="ew", pady=(4, 0))

        self.register_button = ttk.Button(
            frame,
            text="Надіслати заявку",
            style="Primary.TButton",
            command=self.register,
        )
        self.register_button.grid(row=7, column=0, sticky="ew", pady=(24, 0))

        self.register_surname_entry = surname_entry
        return frame

    def set_mode(self, mode: str) -> None:
        if mode not in {"login", "register"}:
            return
        self.mode.set(mode)
        self._update_mode()

    def _update_mode(self) -> None:
        is_login = self.mode.get() == "login"
        if is_login:
            self.register_form.grid_forget()
            self.login_form.grid(row=0, column=0, sticky="nsew")
            self.register_message_var.set("")
            self.after(100, self.login_surname_entry.focus_set)
        else:
            self.login_form.grid_forget()
            self.register_form.grid(row=0, column=0, sticky="nsew")
            self.login_error_var.set("")
            self.after(100, self.register_surname_entry.focus_set)
        self.login_tab.state(["!disabled"])
        self.register_tab.state(["!disabled"])
        self.login_tab.configure(
            style="SegmentedActive.TButton" if is_login else "Segmented.TButton"
        )
        self.register_tab.configure(
            style="SegmentedActive.TButton" if not is_login else "Segmented.TButton"
        )

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    def _set_login_loading(self, loading: bool) -> None:
        self.login_loading = loading
        if loading:
            self.login_button.configure(text="Зачекайте...", state="disabled")
        else:
            self.login_button.configure(text="Увійти", state="normal")

    def login(self) -> None:
        if self.login_loading:
            return
        surname = self.login_surname_var.get().strip()
        password = self.login_password_var.get().strip()
        if not surname or not password:
            self.login_error_var.set("Введіть прізвище та пароль")
            return

        def worker() -> None:
            try:
                response = requests.post(
                    f"{API_BASE}/login",
                    json={"surname": surname, "password": password},
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    timeout=15,
                )
                if response.status_code == 200:
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ApiException("Некоректна відповідь сервера", 500)
                    token = str(data.get("token", ""))
                    if not token:
                        raise ApiException("Сервер не повернув коректний токен", 500)
                    access_level = self._to_int(data.get("access_level"))
                    role_name = data.get("role")
                    resolved_name = str(data.get("surname", surname))

                    def finalize() -> None:
                        self.login_error_var.set("")
                        self.app.state_data.token = token
                        self.app.state_data.access_level = access_level
                        self.app.state_data.user_name = resolved_name
                        self.app.state_data.user_role = str(role_name or "viewer").lower()
                        self.app.state_data.save()
                        OfflineQueue.sync_pending(token)
                        if resolved_name:
                            self.app.show_scanner()
                        else:
                            self.app.show_username()

                    self.after(0, finalize)
                    return

                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                message = UserApi._extract_message(payload, response.status_code)
                self.after(0, lambda: self.login_error_var.set(message))
            except ApiException as exc:
                self.after(0, lambda: self.login_error_var.set(exc.message))
            except requests.RequestException:
                self.after(0, lambda: self.login_error_var.set("Помилка підключення до сервера"))
            finally:
                self.after(0, lambda: self._set_login_loading(False))

        self.login_error_var.set("")
        self._set_login_loading(True)
        threading.Thread(target=worker, daemon=True).start()

    def _set_register_loading(self, loading: bool) -> None:
        self.register_loading = loading
        if loading:
            self.register_button.configure(text="Надсилання...", state="disabled")
        else:
            self.register_button.configure(text="Надіслати заявку", state="normal")

    def _set_register_feedback(self, message: str, success: bool) -> None:
        self.register_message_var.set(message)
        self.register_success = success
        self.register_feedback_label.configure(
            fg="#16a34a" if success else "#d32f2f"
        )

    def register(self) -> None:
        if self.register_loading:
            return
        surname = self.register_surname_var.get().strip()
        password = self.register_password_var.get().strip()
        confirm = self.register_confirm_var.get().strip()

        if not surname or not password or not confirm:
            self._set_register_feedback("Заповніть усі поля", False)
            return
        if len(password) < 6:
            self._set_register_feedback("Пароль має містити щонайменше 6 символів", False)
            return
        if password != confirm:
            self._set_register_feedback("Паролі не співпадають", False)
            return

        def worker() -> None:
            try:
                UserApi.register_user(surname, password)
                self.after(
                    0,
                    lambda: self._on_registration_success(
                        "Заявку на реєстрацію надіслано. Дочекайтесь підтвердження адміністратора."
                    ),
                )
            except ApiException as exc:
                self.after(0, lambda: self._set_register_feedback(exc.message, False))
            except requests.RequestException:
                 self.after(
                    0,
                    lambda: self._set_register_feedback(
                        "Не вдалося з’єднатися з сервером. Спробуйте пізніше.",
                        False,
                    ),
                )
            finally:
                self.after(0, lambda: self._set_register_loading(False))

        self._set_register_feedback("", False)
        self._set_register_loading(True)
        threading.Thread(target=worker, daemon=True).start()

    def _on_registration_success(self, message: str) -> None:
        self._set_register_feedback(message, True)
        self.register_surname_var.set("")
        self.register_password_var.set("")
        self.register_confirm_var.set("")

    def open_admin_panel(self) -> None:
        password = simpledialog.askstring(
            "Адмін-панель",
            "Введіть пароль адміністратора",
            show="*",
            parent=self,
        )
        if not password:
            return

        def worker() -> None:
            try:
                token = UserApi.admin_login(password.strip())

                def launch() -> None:
                    AdminPanelWindow(self.app, token)

                self.after(0, launch)
            except ApiException as exc:
                self.after(0, lambda: messagebox.showerror("Помилка", exc.message))
            except requests.RequestException:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Помилка", "Не вдалося з’єднатися з сервером"
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()


class AdminPanelWindow(tk.Toplevel):
    def __init__(self, app: TrackingApp, token: str) -> None:
        super().__init__(app)
        self.app = app
        self.admin_token = token
        self.title("Панель адміністратора")
        self.configure(bg=PRIMARY_BG)
        self.geometry("1280x760")
        self.minsize(1100, 680)
        maximize_window(self)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.status_var = tk.StringVar(value="Завантаження даних...")
        self.loading = False
        self.pending_users: List[PendingUser] = []
        self.managed_users: List[ManagedUser] = []
        self.role_passwords: Dict[UserRole, str] = {}

        self._layout_mode: Optional[str] = None
        self._action_groups: list[tuple[tk.Frame, list[ttk.Button]]] = []

        header = tk.Frame(self, bg=SECONDARY_BG, padx=32, pady=20)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)
        self.header = header

        self.header_title = tk.Label(
            header,
            text="Панель адміністратора",
            font=("Segoe UI", 28, "bold"),
            fg="white",
            bg=SECONDARY_BG,
        )
        self.header_title.grid(row=0, column=0, sticky="w")
        self.header_subtitle = tk.Label(
            header,
            text="Керуйте користувачами та запитами на реєстрацію",
            font=("Segoe UI", 12),
            fg="#cbd5f5",
            bg=SECONDARY_BG,
        )
        self.header_subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.refresh_button = ttk.Button(
            header,
            text="Оновити дані",
            style="Secondary.TButton",
            command=self.refresh_data,
        )
        self.refresh_button.grid(row=0, column=1, rowspan=2, sticky="e")

        body = tk.Frame(self, bg=PRIMARY_BG, padx=24, pady=24)
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.body = body

        notebook = ttk.Notebook(body)
        notebook.grid(row=0, column=0, sticky="nsew")

        self.pending_tab = tk.Frame(notebook, bg=CARD_BG)
        notebook.add(self.pending_tab, text="Запити на реєстрацію")
        self._build_pending_tab(self.pending_tab)

        self.users_tab = tk.Frame(notebook, bg=CARD_BG)
        notebook.add(self.users_tab, text="Користувачі")
        self._build_users_tab(self.users_tab)

        self.passwords_tab = tk.Frame(notebook, bg=CARD_BG)
        notebook.add(self.passwords_tab, text="Паролі ролей")
        self._build_passwords_tab(self.passwords_tab)

        status_bar = tk.Frame(self, bg=SECONDARY_BG, padx=32, pady=12)
        status_bar.grid(row=2, column=0, sticky="ew")
        self.status_bar = status_bar
        tk.Label(
            status_bar,
            textvariable=self.status_var,
            font=("Segoe UI", 12),
            fg="#e2e8f0",
            bg=SECONDARY_BG,
        ).grid(row=0, column=0, sticky="w")

        self.refresh_data()
        self.bind("<Configure>", self._handle_resize, add="+")
        self.update_idletasks()
        self._apply_responsive_layout(self.winfo_width())

    def _build_pending_tab(self, parent: tk.Misc) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        ttk.Label(
            parent,
            text="Очікуючі запити",
            style="CardHeading.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(24, 12))

        container = tk.Frame(parent, bg=CARD_BG)
        container.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 12))
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        columns = ("surname", "created")
        self.pending_tree = ttk.Treeview(
            container,
            columns=columns,
            show="headings",
            height=8,
        )
        self.pending_tree.heading("surname", text="Прізвище")
        self.pending_tree.heading("created", text="Створено")
        self.pending_tree.column("surname", width=280, anchor="w", stretch=True)
        self.pending_tree.column("created", width=200, anchor="center", stretch=True)
        self.pending_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.pending_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.pending_tree.configure(yscrollcommand=scrollbar.set)

        actions = tk.Frame(parent, bg=CARD_BG)
        actions.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 24))
        actions.columnconfigure((0, 1, 2, 3), weight=1)

        pending_buttons = [
            ttk.Button(
                actions,
                text="Підтвердити як адміністратор",
                style="Secondary.TButton",
                command=lambda: self.approve_selected(UserRole.ADMIN),
            ),
            ttk.Button(
                actions,
                text="Підтвердити як оператор",
                style="Secondary.TButton",
                command=lambda: self.approve_selected(UserRole.OPERATOR),
            ),
            ttk.Button(
                actions,
                text="Підтвердити як перегляд",
                style="Secondary.TButton",
                command=lambda: self.approve_selected(UserRole.VIEWER),
            ),
            ttk.Button(
                actions,
                text="Відхилити",
                style="Secondary.TButton",
                command=self.reject_selected,
            ),
        ]
        for idx, button in enumerate(pending_buttons):
            button.grid(row=0, column=idx, padx=6, sticky="ew")
        self._action_groups.append((actions, pending_buttons))

    def _build_users_tab(self, parent: tk.Misc) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        ttk.Label(
            parent,
            text="Зареєстровані користувачі",
            style="CardHeading.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(24, 12))

        container = tk.Frame(parent, bg=CARD_BG)
        container.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 12))
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        columns = ("surname", "role", "active", "created", "updated")
        self.users_tree = ttk.Treeview(
            container,
            columns=columns,
            show="headings",
            height=12,
        )
        headings = {
            "surname": "Прізвище",
            "role": "Роль",
            "active": "Статус",
            "created": "Створено",
            "updated": "Оновлено",
        }
        widths = {
            "surname": (220, "w"),
            "role": (140, "center"),
            "active": (140, "center"),
            "created": (160, "center"),
            "updated": (160, "center"),
        }
        for key in columns:
            self.users_tree.heading(key, text=headings[key])
            width, anchor = widths[key]
            self.users_tree.column(key, width=width, anchor=anchor, stretch=True)
        self.users_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.users_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.users_tree.configure(yscrollcommand=scrollbar.set)

        actions = tk.Frame(parent, bg=CARD_BG)
        actions.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 24))
        actions.columnconfigure((0, 1, 2, 3, 4), weight=1)

        user_buttons = [
            ttk.Button(
                actions,
                text="Зробити адміністратором",
                style="Secondary.TButton",
                command=lambda: self.set_user_role(UserRole.ADMIN),
            ),
            ttk.Button(
                actions,
                text="Зробити оператором",
                style="Secondary.TButton",
                command=lambda: self.set_user_role(UserRole.OPERATOR),
            ),
            ttk.Button(
                actions,
                text="Зробити перегляд",
                style="Secondary.TButton",
                command=lambda: self.set_user_role(UserRole.VIEWER),
            ),
            ttk.Button(
                actions,
                text="Активувати/Призупинити",
                style="Secondary.TButton",
                command=self.toggle_user_active,
            ),
            ttk.Button(
                actions,
                text="Видалити",
                style="Secondary.TButton",
                command=self.delete_user,
            ),
        ]
        for idx, button in enumerate(user_buttons):
            button.grid(row=0, column=idx, padx=6, sticky="ew")
        self._action_groups.append((actions, user_buttons))

    def _build_passwords_tab(self, parent: tk.Misc) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        ttk.Label(
            parent,
            text="API паролі для ролей",
            style="CardHeading.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(24, 12))

        container = tk.Frame(parent, bg=CARD_BG)
        container.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 12))
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        columns = ("role", "password")
        self.passwords_tree = ttk.Treeview(
            container,
            columns=columns,
            show="headings",
            height=6,
        )
        self.passwords_tree.heading("role", text="Роль")
        self.passwords_tree.heading("password", text="Поточний пароль")
        self.passwords_tree.column("role", width=200, anchor="w", stretch=True)
        self.passwords_tree.column("password", width=320, anchor="w", stretch=True)
        self.passwords_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.passwords_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.passwords_tree.configure(yscrollcommand=scrollbar.set)

        actions = tk.Frame(parent, bg=CARD_BG)
        actions.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 24))
        actions.columnconfigure(0, weight=1)

        password_button = ttk.Button(
            actions,
            text="Змінити пароль",
            style="Secondary.TButton",
            command=self.update_role_password,
        )
        password_button.grid(row=0, column=0, sticky="e", padx=6)
        self._action_groups.append((actions, [password_button]))

    def refresh_data(self) -> None:
        if self.loading:
            return
        self.loading = True
        self.status_var.set("Оновлення даних...")

        def worker() -> None:
            try:
                pending = UserApi.fetch_pending_users(self.admin_token)
                users = UserApi.fetch_users(self.admin_token)
                passwords = UserApi.fetch_role_passwords(self.admin_token)
                self.after(0, lambda: self._apply_admin_data(pending, users, passwords))
            except ApiException as exc:
                self.after(0, lambda: self.status_var.set(f"Помилка: {exc.message}"))
            except requests.RequestException:
                self.after(0, lambda: self.status_var.set("Помилка зв’язку з сервером"))
            finally:
                self.after(0, lambda: setattr(self, "loading", False))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_resize(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        width = getattr(event, "width", self.winfo_width())
        self._apply_responsive_layout(width)

    def _apply_responsive_layout(self, width: int) -> None:
        mode = "compact" if width < 1220 else "wide"
        if mode == self._layout_mode:
            return
        self._layout_mode = mode

        padding = (24, 18) if mode == "compact" else (32, 20)
        self.header.configure(padx=padding[0], pady=padding[1])
        _grid_reset(self.header)
        if mode == "compact":
            self.header.columnconfigure(0, weight=1)
            self.header_title.configure(font=("Segoe UI", 24, "bold"))
            self.header_title.grid(row=0, column=0, sticky="w")
            self.header_subtitle.grid(row=1, column=0, sticky="w", pady=(6, 0))
            self.refresh_button.grid(row=2, column=0, sticky="ew", pady=(18, 0))
            self.body.configure(padx=18, pady=18)
            self.status_bar.configure(padx=24, pady=12)
        else:
            self.header.columnconfigure(0, weight=1)
            self.header.columnconfigure(1, weight=0)
            self.header_title.configure(font=("Segoe UI", 28, "bold"))
            self.header_title.grid(row=0, column=0, sticky="w")
            self.header_subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))
            self.refresh_button.grid(row=0, column=1, rowspan=2, sticky="e")
            self.body.configure(padx=24, pady=24)
            self.status_bar.configure(padx=32, pady=12)

        for frame, buttons in self._action_groups:
            _grid_reset(frame)
            if mode == "compact":
                frame.configure(padx=24, pady=(0, 24))
                for column in range(len(buttons)):
                    frame.columnconfigure(column, weight=0)
                frame.columnconfigure(0, weight=1)
                for idx, button in enumerate(buttons):
                    pady = (0, 12) if idx < len(buttons) - 1 else (0, 0)
                    button.grid(row=idx, column=0, sticky="ew", pady=pady)
            else:
                frame.configure(padx=24, pady=(0, 24))
                if len(buttons) == 1:
                    frame.columnconfigure(0, weight=1)
                    buttons[0].grid(row=0, column=0, sticky="e", padx=6)
                else:
                    for column in range(len(buttons)):
                        frame.columnconfigure(column, weight=1)
                    for idx, button in enumerate(buttons):
                        button.grid(row=0, column=idx, sticky="ew", padx=6)

    def _apply_admin_data(
        self,
        pending: List[PendingUser],
        users: List[ManagedUser],
        passwords: Dict[UserRole, str],
    ) -> None:
        self.pending_users = pending
        self.managed_users = users
        self.role_passwords = {role: passwords.get(role, "") for role in UserRole}
        self._populate_pending()
        self._populate_users()
        self._populate_passwords()
        self.status_var.set(
            f"Запити: {len(pending)} | Користувачі: {len(users)} | Ролі: {len(passwords)}"
        )

    @staticmethod
    def _format_datetime(value: Optional[datetime]) -> str:
        if not value:
            return "—"
        return value.astimezone().strftime("%d.%m.%Y %H:%M")

    def _populate_pending(self) -> None:
        for row in self.pending_tree.get_children():
            self.pending_tree.delete(row)
        if not self.pending_users:
            self.pending_tree.insert("", "end", values=("Немає запитів", "—"))
            return
        for user in self.pending_users:
            self.pending_tree.insert(
                "",
                "end",
                iid=str(user.id),
                values=(user.surname, self._format_datetime(user.created_at)),
            )

    def _populate_users(self) -> None:
        for row in self.users_tree.get_children():
            self.users_tree.delete(row)
        if not self.managed_users:
            self.users_tree.insert(
                "",
                "end",
                values=("Немає користувачів", "—", "—", "—", "—"),
            )
            return
        for user in self.managed_users:
            status = "Активний" if user.is_active else "Призупинено"
            self.users_tree.insert(
                "",
                "end",
                iid=str(user.id),
                values=(
                    user.surname,
                    user.role.label,
                    status,
                    self._format_datetime(user.created_at),
                    self._format_datetime(user.updated_at),
                ),
            )

    def _populate_passwords(self) -> None:
        for row in self.passwords_tree.get_children():
            self.passwords_tree.delete(row)
        if not self.role_passwords:
            self.passwords_tree.insert("", "end", values=("—", "Немає даних"))
            return
        for role, password in self.role_passwords.items():
            masked = "*" * len(password) if password else "—"
            self.passwords_tree.insert(
                "",
                "end",
                iid=role.value,
                values=(role.label, masked),
            )

    def _get_selected_pending(self) -> Optional[PendingUser]:
        item_id = self.pending_tree.focus()
        if not item_id:
            messagebox.showinfo("Запити", "Оберіть запит у списку")
            return None
        try:
            ident = int(float(item_id))
        except ValueError:
            return None
        for user in self.pending_users:
            if user.id == ident:
                return user
        return None

    def approve_selected(self, role: UserRole) -> None:
        if self.loading:
            return
        user = self._get_selected_pending()
        if not user:
            return

        if not messagebox.askyesno(
            "Підтвердження",
            f"Надати доступ користувачу {user.surname} як {role.label}?",
        ):
            return

        self.status_var.set("Підтвердження запиту...")

        def worker() -> None:
            try:
                UserApi.approve_pending_user(self.admin_token, user.id, role)
                self.after(0, lambda: self.status_var.set("Запит підтверджено"))
                self.after(0, self.refresh_data)
            except ApiException as exc:
                self.after(0, lambda: messagebox.showerror("Помилка", exc.message))
            except requests.RequestException:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Помилка", "Не вдалося з’єднатися з сервером"
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def reject_selected(self) -> None:
        if self.loading:
            return
        user = self._get_selected_pending()
        if not user:
            return
        if not messagebox.askyesno(
            "Відхилити запит",
            f"Відхилити заявку користувача {user.surname}?",
        ):
            return

        self.status_var.set("Відхилення запиту...")

        def worker() -> None:
            try:
                UserApi.reject_pending_user(self.admin_token, user.id)
                self.after(0, lambda: self.status_var.set("Запит відхилено"))
                self.after(0, self.refresh_data)
            except ApiException as exc:
                self.after(0, lambda: messagebox.showerror("Помилка", exc.message))
            except requests.RequestException:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Помилка", "Не вдалося з’єднатися з сервером"
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _get_selected_user(self) -> Optional[ManagedUser]:
        item_id = self.users_tree.focus()
        if not item_id:
            messagebox.showinfo("Користувачі", "Оберіть користувача зі списку")
            return None
        try:
            ident = int(float(item_id))
        except ValueError:
            return None
        for user in self.managed_users:
            if user.id == ident:
                return user
        return None

    def set_user_role(self, role: UserRole) -> None:
        if self.loading:
            return
        user = self._get_selected_user()
        if not user:
            return
        if not messagebox.askyesno(
            "Зміна ролі",
            f"Надати роль {role.label} користувачу {user.surname}?",
        ):
            return

        def worker() -> None:
            try:
                UserApi.update_user(self.admin_token, user.id, role=role)
                self.after(0, lambda: self.status_var.set("Роль оновлено"))
                self.after(0, self.refresh_data)
            except ApiException as exc:
                self.after(0, lambda: messagebox.showerror("Помилка", exc.message))
            except requests.RequestException:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Помилка", "Не вдалося з’єднатися з сервером"
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def toggle_user_active(self) -> None:
        if self.loading:
            return
        user = self._get_selected_user()
        if not user:
            return
        new_state = not user.is_active
        action = "активувати" if new_state else "призупинити"
        if not messagebox.askyesno(
            "Зміна статусу",
            f"Бажаєте {action} користувача {user.surname}?",
        ):
            return

        def worker() -> None:
            try:
                UserApi.update_user(
                    self.admin_token,
                    user.id,
                    is_active=new_state,
                )
                state_text = "активовано" if new_state else "призупинено"
                self.after(0, lambda: self.status_var.set(f"Користувача {state_text}"))
                self.after(0, self.refresh_data)
            except ApiException as exc:
                self.after(0, lambda: messagebox.showerror("Помилка", exc.message))
            except requests.RequestException:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Помилка", "Не вдалося з’єднатися з сервером"
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def delete_user(self) -> None:
        if self.loading:
            return
        user = self._get_selected_user()
        if not user:
            return
        if not messagebox.askyesno(
            "Видалення",
            f"Видалити користувача {user.surname}? Це дію неможливо скасувати.",
        ):
            return

        def worker() -> None:
            try:
                UserApi.delete_user(self.admin_token, user.id)
                self.after(0, lambda: self.status_var.set("Користувача видалено"))
                self.after(0, self.refresh_data)
            except ApiException as exc:
                self.after(0, lambda: messagebox.showerror("Помилка", exc.message))
            except requests.RequestException:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Помилка", "Не вдалося з’єднатися з сервером"
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def update_role_password(self) -> None:
        if self.loading:
            return
        item_id = self.passwords_tree.focus()
        if not item_id:
            messagebox.showinfo("Паролі", "Оберіть роль зі списку")
            return
        role = normalize_role(item_id, None)
        current = self.role_passwords.get(role, "")
        new_password = simpledialog.askstring(
            "Оновити пароль",
            f"Введіть новий пароль для ролі {role.label}",
            show="*",
            initialvalue=current,
            parent=self,
        )
        if new_password is None:
            return

        def worker() -> None:
            try:
                UserApi.update_role_password(
                    self.admin_token,
                    role,
                    new_password.strip(),
                )
                self.after(0, lambda: self.status_var.set("Пароль оновлено"))
                self.after(0, self.refresh_data)
            except ApiException as exc:
                self.after(0, lambda: messagebox.showerror("Помилка", exc.message))
            except requests.RequestException:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Помилка", "Не вдалося з’єднатися з сервером"
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()


class UserNameFrame(BaseFrame):
    def __init__(self, app: TrackingApp) -> None:
        super().__init__(app)
        self.name_var = tk.StringVar(value=app.state_data.user_name)
        self._layout_mode: Optional[str] = None

        wrapper = tk.Frame(self, bg=PRIMARY_BG, padx=96, pady=96)
        wrapper.grid(row=0, column=0, sticky="nsew")
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(0, weight=1)
        self.wrapper = wrapper

        card = tk.Frame(
            wrapper,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            bd=0,
        )
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)
        self.card = card

        header = tk.Frame(card, bg=CARD_BG, padx=48, pady=40)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.header = header
        ttk.Label(header, text="Профіль оператора", style="CardHeading.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text="Вкажіть ім’я, що буде збережено у історії операцій",
            style="CardSubheading.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        content = tk.Frame(card, bg=CARD_BG, padx=48, pady=32)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        self.content_area = content

        badge_row = tk.Frame(content, bg=CARD_BG)
        badge_row.grid(row=0, column=0, sticky="w", pady=(0, 12))
        ttk.Label(badge_row, text="Крок 2 з 2", style="CardPill.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        tk.Label(
            content,
            text="Ім’я користувача",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=1, column=0, sticky="w")
        entry = create_large_entry(content, textvariable=self.name_var)
        entry.grid(row=2, column=0, sticky="ew", pady=(12, 0), ipady=18)
        entry.bind("<Return>", lambda _: self.save())

        helper = tk.Frame(content, bg=CARD_BG)
        helper.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        helper.columnconfigure(0, weight=1)
        self.helper_label = ttk.Label(
            helper,
            text="Порада: використовуйте прізвище та ініціали для прозорої звітності",
            style="CardSubheading.TLabel",
            wraplength=520,
        )
        self.helper_label.grid(row=0, column=0, sticky="w")

        ttk.Button(
            content,
            text="Зберегти та перейти",
            command=self.save,
            style="Primary.TButton",
        ).grid(row=4, column=0, sticky="ew", pady=(32, 0))

        entry.focus_set()
        self.register_responsive(self._update_responsive_layout)

    def save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Увага", "Введіть ім’я користувача")
            return
        self.app.state_data.user_name = name
        self.app.state_data.save()
        self.app.show_scanner()

    def _update_responsive_layout(self, width: int, height: int) -> None:
        mode = "compact" if width < 960 else "default"
        if self._layout_mode == mode:
            return
        self._layout_mode = mode
        if mode == "compact":
            self.wrapper.configure(padx=32, pady=32)
            self.header.configure(padx=24, pady=24)
            self.content_area.configure(padx=24, pady=24)
            self.helper_label.configure(wraplength=360)
        else:
            self.wrapper.configure(padx=96, pady=96)
            self.header.configure(padx=48, pady=40)
            self.content_area.configure(padx=48, pady=32)
            self.helper_label.configure(wraplength=520)


class ScannerFrame(BaseFrame):
    def __init__(self, app: TrackingApp) -> None:
        super().__init__(app)
        self.box_var = tk.StringVar()
        self.ttn_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Готово до введення BoxID")
        self.online_var = tk.StringVar(value="Перевірка зв’язку...")
        self.online_color = WARNING_COLOR
        self.step_progress_var = tk.StringVar(value="Крок 1 з 2")
        self.step_title_var = tk.StringVar(value="Введіть BoxID")
        self._layout_mode: Optional[Tuple[str, str]] = None

        self.role_info = get_role_info(
            app.state_data.user_role, app.state_data.access_level
        )
        self.is_admin = self.role_info.get("can_clear_history") and self.role_info.get(
            "can_clear_errors"
        )

        shell = tk.Frame(self, bg=PRIMARY_BG, padx=48, pady=48)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)
        self.shell = shell

        app_bar = tk.Frame(shell, bg=PRIMARY_BG)
        app_bar.grid(row=0, column=0, sticky="ew")
        app_bar.columnconfigure(0, weight=1)
        app_bar.columnconfigure(1, weight=1)
        self.app_bar = app_bar

        brand = tk.Frame(app_bar, bg=PRIMARY_BG)
        brand.grid(row=0, column=0, sticky="w")
        tk.Label(
            brand,
            text="TrackingApp",
            font=("Segoe UI", 30, "bold"),
            fg="#f8fafc",
            bg=PRIMARY_BG,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            brand,
            text="Сканування відправлень",
            font=("Segoe UI", 13),
            fg="#94a3b8",
            bg=PRIMARY_BG,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        user_area = tk.Frame(app_bar, bg=PRIMARY_BG)
        user_area.grid(row=0, column=1, sticky="e")
        self.user_area = user_area
        tk.Label(
            user_area,
            text=app.state_data.user_name or "Оператор",
            font=("Segoe UI", 14, "bold"),
            fg="#e2e8f0",
            bg=PRIMARY_BG,
        ).grid(row=0, column=0, sticky="e")
        tk.Label(
            user_area,
            text=self.role_info["label"],
            font=("Segoe UI", 11, "bold"),
            fg=PILL_TEXT,
            bg=PILL_BG,
            padx=14,
            pady=6,
        ).grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.online_chip = tk.Label(
            user_area,
            textvariable=self.online_var,
            font=("Segoe UI", 11, "bold"),
            bg=self.online_color,
            fg="white",
            padx=14,
            pady=6,
        )
        self.online_chip.grid(row=1, column=0, columnspan=2, sticky="e", pady=(12, 0))

        nav = tk.Frame(app_bar, bg=PRIMARY_BG)
        nav.grid(row=1, column=0, columnspan=2, sticky="e", pady=(28, 0))
        self.nav = nav
        self.nav_buttons: List[ttk.Button] = []

        def add_nav_button(label: str, command: Callable[[], None], style: str = "Secondary.TButton") -> None:
            button = ttk.Button(nav, text=label, command=command, style=style)
            column = len(self.nav_buttons)
            button.grid(row=0, column=column, padx=6, sticky="ew")
            self.nav_buttons.append(button)

        add_nav_button("Журнал відправлень", self.open_history)
        add_nav_button("Журнал помилок", self.open_errors)
        if self.is_admin:
            add_nav_button("Статистика", self.open_statistics)
        add_nav_button("Вийти", self.logout)

        card = tk.Frame(
            shell,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            bd=0,
        )
        card.grid(row=1, column=0, sticky="nsew", pady=(36, 0))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)
        self.card = card

        header_section = tk.Frame(card, bg=CARD_BG, padx=48, pady=40)
        header_section.grid(row=0, column=0, sticky="ew")
        header_section.columnconfigure(0, weight=1)
        self.header_section = header_section
        ttk.Label(
            header_section,
            textvariable=self.step_progress_var,
            style="CardPill.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header_section,
            textvariable=self.step_title_var,
            style="CardHeading.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(12, 8))
        ttk.Label(
            header_section,
            text="Скануйте BoxID та підтверджуйте ТТН для синхронізації з сервером",
            style="CardSubheading.TLabel",
            wraplength=520,
        ).grid(row=2, column=0, sticky="w")

        inputs = tk.Frame(card, bg=CARD_BG, padx=48, pady=0)
        inputs.grid(row=1, column=0, sticky="nsew")
        inputs.columnconfigure(0, weight=1)
        self.inputs = inputs

        self.box_group, self.box_entry = self._create_input_group(
            inputs,
            title="BoxID",
            variable=self.box_var,
            row=0,
        )
        self.box_entry.bind("<Return>", lambda _: self.to_next())

        self.ttn_group, self.ttn_entry = self._create_input_group(
            inputs,
            title="Товарно-транспортна накладна",
            variable=self.ttn_var,
            row=1,
        )
        self.ttn_entry.configure(state="disabled")
        self.ttn_entry.bind("<Return>", lambda _: self.submit())

        actions = tk.Frame(inputs, bg=CARD_BG)
        actions.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        self.actions = actions
        self.primary_button = ttk.Button(
            actions,
            text="Перейти до ТТН",
            style="Primary.TButton",
            command=self.to_next,
        )
        self.primary_button.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.reset_button = ttk.Button(
            actions,
            text="Скинути поля",
            style="Outline.TButton",
            command=self.reset_fields,
        )
        self.reset_button.grid(row=0, column=1, sticky="ew")

        status_panel = tk.Frame(
            card,
            bg=SURFACE_BG,
            padx=36,
            pady=28,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
        )
        status_panel.grid(row=2, column=0, sticky="ew", padx=48, pady=(32, 48))
        status_panel.columnconfigure(0, weight=1)
        self.status_panel = status_panel
        self.status_label = tk.Label(
            status_panel,
            textvariable=self.status_var,
            font=("Segoe UI", 13),
            fg=TEXT_SECONDARY,
            bg=SURFACE_BG,
            wraplength=960,
            justify="center",
        )
        self.status_label.grid(row=0, column=0, sticky="ew")

        self.stage = "box"
        self.box_entry.focus_set()
        self.check_connectivity()
        OfflineQueue.sync_pending(self.app.state_data.token or "")
        self.register_responsive(self._update_responsive_layout)

    def _create_input_group(
        self,
        parent: tk.Frame,
        *,
        title: str,
        variable: tk.StringVar,
        row: int,
    ) -> tuple[tk.Frame, tk.Entry]:
        frame = tk.Frame(parent, bg=CARD_BG)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 24))
        frame.columnconfigure(0, weight=1)
        tk.Label(
            frame,
            text=title,
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")
        entry = create_large_entry(frame, textvariable=variable)
        entry.grid(row=1, column=0, sticky="ew", pady=(8, 0), ipady=14)
        return frame, entry

    def _update_responsive_layout(self, width: int, height: int) -> None:
        nav_mode = "compact" if width < 1340 else "wide"
        actions_mode = "stack" if width < 980 else "inline"
        desired = (nav_mode, actions_mode)
        if self._layout_mode == desired:
            return
        self._layout_mode = desired

        if nav_mode == "compact":
            self.shell.configure(padx=28, pady=32)
            self.app_bar.grid_columnconfigure(0, weight=1)
            self.app_bar.grid_columnconfigure(1, weight=0)
            self.user_area.grid_configure(row=1, column=0, columnspan=2, sticky="w", pady=(16, 0))
            self.nav.grid_configure(row=2, column=0, columnspan=2, sticky="ew", pady=(24, 0))
            _grid_reset(self.nav)
            self.nav.columnconfigure(0, weight=1)
            for index, button in enumerate(self.nav_buttons):
                button.grid(row=index, column=0, sticky="ew", pady=4)
            self.header_section.configure(padx=32, pady=28)
            self.inputs.configure(padx=32)
            self.card.grid_configure(pady=(28, 0))
            self.status_panel.grid_configure(padx=32, pady=(24, 32))
        else:
            self.shell.configure(padx=48, pady=48)
            self.app_bar.grid_columnconfigure(0, weight=1)
            self.app_bar.grid_columnconfigure(1, weight=1)
            self.user_area.grid_configure(row=0, column=1, columnspan=1, sticky="e", pady=0)
            self.nav.grid_configure(row=1, column=0, columnspan=2, sticky="e", pady=(28, 0))
            _grid_reset(self.nav)
            for index, button in enumerate(self.nav_buttons):
                self.nav.grid_columnconfigure(index, weight=0)
                button.grid(row=0, column=index, padx=6, sticky="ew")
            self.header_section.configure(padx=48, pady=40)
            self.inputs.configure(padx=48)
            self.card.grid_configure(pady=(36, 0))
            self.status_panel.grid_configure(padx=48, pady=(32, 48))

        wrap_width = max(min(width - 200, 960), 420)
        self.status_label.configure(wraplength=wrap_width)

        _grid_reset(self.actions)
        if actions_mode == "stack":
            self.actions.columnconfigure(0, weight=1)
            self.primary_button.grid(row=0, column=0, sticky="ew")
            self.reset_button.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        else:
            self.actions.columnconfigure(0, weight=1)
            self.actions.columnconfigure(1, weight=1)
            self.primary_button.grid(row=0, column=0, sticky="ew", padx=(0, 12))
            self.reset_button.grid(row=0, column=1, sticky="ew")

    def set_online_state(self, online: bool) -> None:
        if online:
            self.online_color = SUCCESS_COLOR
            self.online_var.set("🟢 Підключення активне")
            fg = "white"
        else:
            self.online_color = ERROR_COLOR
            self.online_var.set("🔴 Немає зв’язку з сервером")
            fg = "white"
        self.online_chip.configure(bg=self.online_color, fg=fg)

    def check_connectivity(self) -> None:
        def worker() -> None:
            try:
                response = requests.head(API_BASE, timeout=5)
                online = response.status_code < 500
            except requests.RequestException:
                online = False
            self.after(0, lambda: self.set_online_state(online))
            self.after(15000, self.check_connectivity)

        threading.Thread(target=worker, daemon=True).start()

    def to_next(self) -> None:
        if self.stage != "box":
            return
        value = self.box_var.get().strip()
        if not value:
            messagebox.showwarning("Увага", "Введіть BoxID")
            return
        self.stage = "ttn"
        self.step_progress_var.set("Крок 2 з 2")
        self.step_title_var.set("Введіть номер ТТН")
        self.status_var.set("Заповніть поле ТТН та підтвердіть запис")
        self.ttn_entry.configure(state="normal")
        self.primary_button.configure(text="Зберегти запис", command=self.submit)
        self.ttn_entry.focus_set()

    def reset_fields(self) -> None:
        self.box_var.set("")
        self.ttn_var.set("")
        self.stage = "box"
        self.step_progress_var.set("Крок 1 з 2")
        self.step_title_var.set("Введіть BoxID")
        self.status_var.set("Готово до введення BoxID")
        self.ttn_entry.configure(state="disabled")
        self.primary_button.configure(text="Перейти до ТТН", command=self.to_next, state="normal")
        self.box_entry.focus_set()

    def submit(self) -> None:
        if self.stage != "ttn":
            return
        boxid = self.box_var.get().strip()
        ttn = self.ttn_var.get().strip()
        if not boxid or not ttn:
            messagebox.showwarning("Увага", "Введіть BoxID та ТТН")
            return
        record = {
            "user_name": self.app.state_data.user_name,
            "boxid": boxid,
            "ttn": ttn,
        }
        self.status_var.set("Відправлення даних...")
        self.primary_button.configure(text="Відправлення...", state="disabled")

        def worker() -> None:
            token = self.app.state_data.token or ""
            if not token:
                OfflineQueue.add_record(record)
                self.after(
                    0,
                    lambda: self.status_var.set(
                        "📦 Збережено локально. Увійдіть знову, щоб синхронізувати."
                    ),
                )
                self.after(0, self.reset_fields)
                return
            try:
                response = requests.post(
                    f"{API_BASE}/add_record",
                    json=record,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    timeout=10,
                )
                if response.status_code == 200:
                    note = response.json().get("note", "")
                    if note:
                        message = f"⚠️ Дублікат: {note}"
                    else:
                        message = "✅ Успішно додано"
                    self.after(0, lambda: self.status_var.set(message))
                    self.after(0, lambda: self.set_online_state(True))
                else:
                    raise requests.RequestException(f"status {response.status_code}")
            except requests.RequestException:
                OfflineQueue.add_record(record)
                self.after(0, lambda: self.status_var.set("📦 Збережено локально (офлайн)"))
                self.after(0, lambda: self.set_online_state(False))
            finally:
                self.after(0, self.reset_fields)
                self.after(0, lambda: self.primary_button.configure(state="normal"))
                OfflineQueue.sync_pending(token)

        threading.Thread(target=worker, daemon=True).start()

    def logout(self) -> None:
        self.perform_logout()

    def open_history(self) -> None:
        self.app.show_history()

    def open_errors(self) -> None:
        self.app.show_errors()

    def open_statistics(self) -> None:
        self.app.show_statistics()


class HistoryFrame(BaseFrame):
    def __init__(self, app: TrackingApp) -> None:
        super().__init__(app)
        self.role_info = get_role_info(app.state_data.user_role, app.state_data.access_level)
        self.is_admin = self.role_info.get("can_clear_history") and self.role_info.get(
            "can_clear_errors"
        )
        self._layout_mode: Optional[str] = None

        nav_actions: List[Tuple[str, Callable[[], None]]] = [
            ("⬅ Сканування", self.app.show_scanner),
            ("Журнал помилок", self.app.show_errors),
        ]
        if self.is_admin:
            nav_actions.append(("Статистика", self.app.show_statistics))
        nav_actions.append(("Вийти", self.logout))

        _, card = self.build_surface(
            title="Історія операцій",
            subtitle="Перегляд та фільтрація усіх сканувань",
            nav_actions=nav_actions,
        )
        card.rowconfigure(0, weight=1)

        content = tk.Frame(card, bg=CARD_BG, padx=36, pady=32)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)
        self.content_area = content

        ttk.Label(
            content,
            text="Зведення сканувань",
            style="CardHeading.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            content,
            text="Швидкий пошук за BoxID, ТТН, користувачем або датою",
            style="CardSubheading.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 16))

        filters = tk.Frame(content, bg=CARD_BG)
        filters.grid(row=2, column=0, sticky="ew")
        filters.columnconfigure(0, weight=1)
        self.filters = filters

        inputs = tk.Frame(filters, bg=CARD_BG)
        inputs.grid(row=0, column=0, sticky="w")
        self.filter_inputs = inputs
        self.filter_entry_frames: List[tk.Frame] = []

        self.box_filter = tk.StringVar()
        self.ttn_filter = tk.StringVar()
        self.user_filter = tk.StringVar()
        self.date_filter: Optional[date] = None
        self.start_time: Optional[dtime] = None
        self.end_time: Optional[dtime] = None

        self._add_filter_entry(inputs, "BoxID", self.box_filter, 0)
        self._add_filter_entry(inputs, "TTN", self.ttn_filter, 1)
        self._add_filter_entry(inputs, "Користувач", self.user_filter, 2)

        buttons = tk.Frame(filters, bg=CARD_BG)
        buttons.grid(row=0, column=1, sticky="e", padx=(24, 0))
        self.filter_button_bar = buttons
        self.filter_buttons: List[ttk.Button] = []

        def add_filter_button(text: str, command: Callable[[], None], style: str) -> None:
            button = ttk.Button(buttons, text=text, command=command, style=style)
            column = len(self.filter_buttons)
            button.grid(row=0, column=column, padx=4, sticky="ew")
            self.filter_buttons.append(button)

        add_filter_button("Дата", self.pick_date, "Secondary.TButton")
        add_filter_button("Початок", lambda: self.pick_time(True), "Secondary.TButton")
        add_filter_button("Кінець", lambda: self.pick_time(False), "Secondary.TButton")
        add_filter_button("Скинути", self.clear_filters, "Outline.TButton")
        add_filter_button("Оновити", self.fetch_history, "Primary.TButton")
        if self.role_info["can_clear_history"]:
            add_filter_button("Очистити", self.clear_history, "Outline.TButton")

        status = tk.Frame(filters, bg=CARD_BG)
        status.grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self.status_frame = status

        self.date_display = tk.StringVar(value="Дата: —")
        self.start_display = tk.StringVar(value="Початок: —")
        self.end_display = tk.StringVar(value="Кінець: —")

        ttk.Label(status, textvariable=self.date_display, style="Card.TLabel").grid(row=0, column=0, padx=(0, 24))
        ttk.Label(status, textvariable=self.start_display, style="Card.TLabel").grid(row=0, column=1, padx=(0, 24))
        ttk.Label(status, textvariable=self.end_display, style="Card.TLabel").grid(row=0, column=2)

        tree_container = tk.Frame(content, bg=CARD_BG)
        tree_container.grid(row=3, column=0, sticky="nsew", pady=(24, 0))
        tree_container.columnconfigure(0, weight=1)
        tree_container.rowconfigure(0, weight=1)

        columns = ("datetime", "boxid", "ttn", "user", "note")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings")
        headings = {
            "datetime": "Дата",
            "boxid": "BoxID",
            "ttn": "TTN",
            "user": "Користувач",
            "note": "Примітка",
        }
        for col, text in headings.items():
            self.tree.heading(col, text=text)
            self.tree.column(col, width=200 if col == "datetime" else 160, anchor="center")

        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.records: List[Dict[str, Any]] = []
        self.filtered: List[Dict[str, Any]] = []

        self.fetch_history()
        self.register_responsive(self._update_responsive_layout)

    def _add_filter_entry(self, parent: tk.Widget, label: str, variable: tk.StringVar, column: int) -> None:
        frame = tk.Frame(parent, bg=CARD_BG)
        frame.grid(row=0, column=column, padx=6)
        self.filter_entry_frames.append(frame)
        tk.Label(
            frame,
            text=label,
            font=("Segoe UI", 11, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(frame, textvariable=variable, width=18)
        entry.grid(row=1, column=0, pady=(6, 0))
        entry.bind("<KeyRelease>", lambda _: self.apply_filters())

    def pick_date(self) -> None:
        picker = DatePickerDialog(self, initial=self.date_filter)
        selected = picker.show()
        self.date_filter = selected
        if selected:
            self.date_display.set(f"Дата: {selected.strftime('%d.%m.%Y')}")
        else:
            self.date_display.set("Дата: —")
        self.apply_filters()

    def pick_time(self, is_start: bool) -> None:
        initial = self.start_time if is_start else self.end_time
        dialog = TimePickerDialog(
            self,
            title="Оберіть час початку" if is_start else "Оберіть час завершення",
            initial=initial,
        )
        selected = dialog.show()
        if is_start:
            self.start_time = selected
            if selected:
                self.start_display.set(f"Початок: {selected.strftime('%H:%M')}")
            else:
                self.start_display.set("Початок: —")
        else:
            self.end_time = selected
            if selected:
                self.end_display.set(f"Кінець: {selected.strftime('%H:%M')}")
            else:
                self.end_display.set("Кінець: —")
        self.apply_filters()

    def clear_filters(self) -> None:
        self.box_filter.set("")
        self.ttn_filter.set("")
        self.user_filter.set("")
        self.date_filter = None
        self.start_time = None
        self.end_time = None
        self.date_display.set("Дата: —")
        self.start_display.set("Початок: —")
        self.end_display.set("Кінець: —")
        self.apply_filters()

    def fetch_history(self) -> None:
        token = self.app.state_data.token
        if not token:
            messagebox.showerror("Помилка", "Необхідна авторизація")
            return

        def worker() -> None:
            try:
                response = requests.get(
                    f"{API_BASE}/get_history",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    fallback = datetime.min.replace(tzinfo=timezone.utc)
                    data.sort(
                        key=lambda r: parse_api_datetime(r.get("datetime")) or fallback,
                        reverse=True,
                    )
                    self.records = data
                    self.after(0, self.apply_filters)
                else:
                    raise requests.RequestException(f"status {response.status_code}")
            except requests.RequestException as exc:
                self.after(0, lambda: messagebox.showerror("Помилка", f"Не вдалося завантажити історію: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def apply_filters(self) -> None:
        filtered = list(self.records)
        if self.box_filter.get():
            needle = self.box_filter.get().strip().lower()
            filtered = [r for r in filtered if needle in str(r.get("boxid", "")).lower()]
        if self.ttn_filter.get():
            needle = self.ttn_filter.get().strip().lower()
            filtered = [r for r in filtered if needle in str(r.get("ttn", "")).lower()]
        if self.user_filter.get():
            needle = self.user_filter.get().strip().lower()
            filtered = [r for r in filtered if needle in str(r.get("user_name", "")).lower()]

        if self.date_filter or self.start_time or self.end_time:
            timed: list[Dict[str, Any]] = []
            for record in filtered:
                dt = parse_api_datetime(record.get("datetime"))
                if not dt:
                    continue
                if self.date_filter and dt.date() != self.date_filter:
                    continue
                tm = dt.time()
                if self.start_time and tm < self.start_time:
                    continue
                if self.end_time and tm > self.end_time:
                    continue
                timed.append(record)
            filtered = timed

        self.filtered = filtered
        for row in self.tree.get_children():
            self.tree.delete(row)
        for item in filtered:
            dt = parse_api_datetime(item.get("datetime"))
            dt_txt = dt.strftime("%d.%m.%Y %H:%M:%S") if dt else item.get("datetime", "")
            self.tree.insert(
                "",
                "end",
                values=(
                    dt_txt,
                    item.get("boxid", ""),
                    item.get("ttn", ""),
                    item.get("user_name", ""),
                    item.get("note", ""),
                ),
            )

    def clear_history(self) -> None:
        if not messagebox.askyesno("Підтвердження", "Очистити історію? Це незворотньо."):
            return
        token = self.app.state_data.token
        if not token:
            return

        def worker() -> None:
            try:
                response = requests.delete(
                    f"{API_BASE}/clear_tracking",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                if response.status_code == 200:
                    def update() -> None:
                        self.records.clear()
                        self.apply_filters()

                    self.after(0, update)
                else:
                    raise requests.RequestException(f"status {response.status_code}")
            except requests.RequestException as exc:
                self.after(0, lambda: messagebox.showerror("Помилка", f"Не вдалося очистити: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def logout(self) -> None:
        self.perform_logout()

    def _update_responsive_layout(self, width: int, height: int) -> None:
        mode = "compact" if width < 1400 else "default"
        if self._layout_mode == mode:
            return
        self._layout_mode = mode

        if mode == "compact":
            self.content_area.configure(padx=24, pady=24)
            self.filters.grid_configure(pady=(16, 0))
            _grid_reset(self.filter_inputs)
            for index, frame in enumerate(self.filter_entry_frames):
                frame.grid(row=index, column=0, sticky="ew", pady=(0, 12))
                frame.columnconfigure(0, weight=1)
            _grid_reset(self.filter_button_bar)
            self.filter_button_bar.columnconfigure(0, weight=1)
            for index, button in enumerate(self.filter_buttons):
                button.grid(row=index, column=0, sticky="ew", pady=4)
            self.filter_inputs.grid(row=0, column=0, sticky="ew")
            self.filter_button_bar.grid(row=1, column=0, sticky="ew", pady=(16, 0))
            self.status_frame.grid_configure(row=2, column=0, columnspan=1, sticky="ew", pady=(16, 0))
        else:
            self.content_area.configure(padx=36, pady=32)
            self.filters.grid_configure(pady=(0, 0))
            _grid_reset(self.filter_inputs)
            for index, frame in enumerate(self.filter_entry_frames):
                frame.grid(row=0, column=index, padx=6, sticky="w")
            _grid_reset(self.filter_button_bar)
            for index, button in enumerate(self.filter_buttons):
                button.grid(row=0, column=index, padx=4, sticky="ew")
            self.filter_button_bar.grid(row=0, column=1, sticky="e", padx=(24, 0), pady=0)
            self.status_frame.grid_configure(row=1, column=0, columnspan=2, sticky="w", pady=(12, 0))


class StatisticsFrame(BaseFrame):
    def __init__(self, app: TrackingApp) -> None:
        super().__init__(app)
        self.role_info = get_role_info(app.state_data.user_role, app.state_data.access_level)
        self.is_admin = self.role_info.get("can_clear_history") and self.role_info.get(
            "can_clear_errors"
        )
        if not self.is_admin:
            messagebox.showerror("Обмежено", "Статистика доступна лише адміністратору.")
            self.after(0, self.app.show_scanner)
            return
        self._layout_mode: Optional[Tuple[str, str, str]] = None

        self.history_records: List[Dict[str, Any]] = []
        self.error_records: List[Dict[str, Any]] = []
        today = date.today()
        self.start_date: Optional[date] = today.replace(day=1)
        self.start_time: Optional[dtime] = dtime.min
        self.end_date: Optional[date] = today
        self.end_time: Optional[dtime] = dtime(hour=23, minute=59, second=59)
        self.last_updated: Optional[str] = None

        self.period_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Завантаження даних...")
        self.total_scans_var = tk.StringVar(value="0")
        self.unique_users_var = tk.StringVar(value="0")
        self.total_errors_var = tk.StringVar(value="0")
        self.error_users_var = tk.StringVar(value="0")
        self.top_operator_var = tk.StringVar(value="—")
        self.top_operator_count_var = tk.StringVar(value="0")
        self.top_error_operator_var = tk.StringVar(value="—")
        self.top_error_count_var = tk.StringVar(value="0")

        self.scan_counts: Dict[str, int] = {}
        self.error_counts: Dict[str, int] = {}
        self.daily_rows: List[Tuple[str, int, int, str, str]] = []

        nav_actions: List[Tuple[str, Callable[[], None]]] = [
            ("⬅ Сканування", self.app.show_scanner),
            ("Історія", self.app.show_history),
            ("Журнал помилок", self.app.show_errors),
            ("Вийти", self.logout),
        ]

        _, card = self.build_surface(
            title="Аналітика сканувань",
            subtitle="Переглядайте продуктивність команди та помилки за обраний період",
            nav_actions=nav_actions,
        )
        card.rowconfigure(0, weight=1)

        content = tk.Frame(card, bg=CARD_BG, padx=36, pady=32)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(6, weight=1)
        self.content_area = content

        ttk.Label(content, text="Адміністративна статистика", style="CardHeading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            content,
            text="Виберіть період та аналізуйте навантаження операторів",
            style="CardSubheading.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 16))

        filters = tk.Frame(content, bg=CARD_BG)
        filters.grid(row=2, column=0, sticky="ew")
        filters.columnconfigure(0, weight=1)
        self.filters = filters

        ttk.Label(filters, textvariable=self.period_var, style="CardSubheading.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        buttons = tk.Frame(filters, bg=CARD_BG)
        buttons.grid(row=0, column=1, sticky="e")
        self.filter_button_bar = buttons
        self.filter_buttons: List[ttk.Button] = []

        def add_stat_button(text: str, command: Callable[[], None], style: str) -> None:
            button = ttk.Button(buttons, text=text, command=command, style=style)
            column = len(self.filter_buttons)
            button.grid(row=0, column=column, padx=4)
            self.filter_buttons.append(button)

        add_stat_button("Дата початку", self.pick_start_date, "Secondary.TButton")
        add_stat_button("Час початку", self.pick_start_time, "Secondary.TButton")
        add_stat_button("Дата завершення", self.pick_end_date, "Secondary.TButton")
        add_stat_button("Час завершення", self.pick_end_time, "Secondary.TButton")
        add_stat_button("Скинути", self.reset_period, "Outline.TButton")
        add_stat_button("Оновити дані", self.fetch_data, "Secondary.TButton")
        add_stat_button("Зберегти звіт", self.export_statistics, "Primary.TButton")

        status = tk.Frame(content, bg=CARD_BG)
        status.grid(row=3, column=0, sticky="w", pady=(12, 0))
        self.status_frame = status
        ttk.Label(status, textvariable=self.status_var, style="CardSubheading.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        metrics = tk.Frame(content, bg=CARD_BG)
        metrics.grid(row=4, column=0, sticky="ew", pady=(24, 0))
        self.metrics_frame = metrics
        self.metric_cards: List[tk.Frame] = []
        self.metric_cards.append(self._create_metric(metrics, 0, "Сканувань", self.total_scans_var))
        self.metric_cards.append(self._create_metric(metrics, 1, "Операторів", self.unique_users_var))
        self.metric_cards.append(self._create_metric(metrics, 2, "Помилок", self.total_errors_var))
        self.metric_cards.append(
            self._create_metric(metrics, 3, "Користувачів з помилками", self.error_users_var)
        )

        insights = tk.Frame(content, bg=CARD_BG)
        insights.grid(row=5, column=0, sticky="ew", pady=(28, 0))
        insights.columnconfigure(0, weight=1)
        insights.columnconfigure(1, weight=1)
        self.insights_frame = insights
        self.insight_cards: List[tk.Frame] = []
        self.insight_cards.append(
            self._create_insight(
                insights,
                column=0,
                title="Найактивніший оператор",
                name_var=self.top_operator_var,
                count_var=self.top_operator_count_var,
                suffix="сканувань",
            )
        )
        self.insight_cards.append(
            self._create_insight(
                insights,
                column=1,
                title="Найбільше помилок",
                name_var=self.top_error_operator_var,
                count_var=self.top_error_count_var,
                suffix="помилок",
            )
        )

        tables = tk.Frame(content, bg=CARD_BG)
        tables.grid(row=6, column=0, sticky="nsew", pady=(32, 0))
        tables.columnconfigure(0, weight=1)
        tables.columnconfigure(1, weight=1)
        tables.columnconfigure(2, weight=1)
        tables.rowconfigure(0, weight=1)
        self.tables_frame = tables

        scans_section = tk.Frame(
            tables,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            padx=24,
            pady=20,
        )
        scans_section.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        scans_section.columnconfigure(0, weight=1)
        scans_section.rowconfigure(1, weight=1)

        ttk.Label(scans_section, text="Сканування за користувачами", style="CardSubheading.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        scan_columns = ("user", "count")
        self.scan_tree = ttk.Treeview(scans_section, columns=scan_columns, show="headings", height=5)
        self.scan_tree.heading("user", text="Користувач")
        self.scan_tree.heading("count", text="Кількість")
        self.scan_tree.column("user", width=240, anchor="w")
        self.scan_tree.column("count", width=120, anchor="center")
        self.scan_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        scan_scroll = ttk.Scrollbar(scans_section, orient="vertical", command=self.scan_tree.yview)
        scan_scroll.grid(row=1, column=1, sticky="ns", pady=(12, 0))
        self.scan_tree.configure(yscrollcommand=scan_scroll.set)

        errors_section = tk.Frame(
            tables,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            padx=24,
            pady=20,
        )
        errors_section.grid(row=0, column=1, sticky="nsew")
        errors_section.columnconfigure(0, weight=1)
        errors_section.rowconfigure(1, weight=1)

        ttk.Label(errors_section, text="Помилки за користувачами", style="CardSubheading.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        error_columns = ("user", "count")
        self.error_tree = ttk.Treeview(errors_section, columns=error_columns, show="headings", height=10)
        self.error_tree.heading("user", text="Користувач")
        self.error_tree.heading("count", text="Кількість")
        self.error_tree.column("user", width=240, anchor="w")
        self.error_tree.column("count", width=120, anchor="center")
        self.error_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        error_scroll = ttk.Scrollbar(errors_section, orient="vertical", command=self.error_tree.yview)
        error_scroll.grid(row=1, column=1, sticky="ns", pady=(12, 0))
        self.error_tree.configure(yscrollcommand=error_scroll.set)

        timeline_section = tk.Frame(
            tables,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            padx=24,
            pady=20,
        )
        timeline_section.grid(row=0, column=2, sticky="nsew")
        timeline_section.columnconfigure(0, weight=1)
        timeline_section.rowconfigure(1, weight=1)

        ttk.Label(
            timeline_section,
            text="Щоденна активність",
            style="CardSubheading.TLabel",
        ).grid(row=0, column=0, sticky="w")
        timeline_columns = ("date", "scan_count", "error_count", "top_scan", "top_error")
        self.timeline_tree = ttk.Treeview(
            timeline_section,
            columns=timeline_columns,
            show="headings",
            height=10,
        )
        self.timeline_tree.heading("date", text="Дата")
        self.timeline_tree.heading("scan_count", text="Сканування")
        self.timeline_tree.heading("error_count", text="Помилки")
        self.timeline_tree.heading("top_scan", text="Лідер")
        self.timeline_tree.heading("top_error", text="Найбільше помилок")
        self.timeline_tree.column("date", width=140, anchor="center")
        self.timeline_tree.column("scan_count", width=120, anchor="center")
        self.timeline_tree.column("error_count", width=120, anchor="center")
        self.timeline_tree.column("top_scan", width=220, anchor="w")
        self.timeline_tree.column("top_error", width=220, anchor="w")
        self.timeline_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        timeline_scroll = ttk.Scrollbar(timeline_section, orient="vertical", command=self.timeline_tree.yview)
        timeline_scroll.grid(row=1, column=1, sticky="ns", pady=(12, 0))
        self.timeline_tree.configure(yscrollcommand=timeline_scroll.set)
        self.table_sections = [scans_section, errors_section, timeline_section]

        self._update_period_label()
        self.fetch_data()
        self.register_responsive(self._update_responsive_layout)

    def _update_responsive_layout(self, width: int, height: int) -> None:
        metrics_mode = "single" if width < 1100 else ("double" if width < 1500 else "grid")
        insights_mode = "single" if width < 1400 else "double"
        tables_mode = "stack" if width < 1500 else "row"
        key = (metrics_mode, insights_mode, tables_mode)
        if self._layout_mode == key:
            return
        self._layout_mode = key

        if width < 1100:
            self.content_area.configure(padx=24, pady=24)
        elif width < 1500:
            self.content_area.configure(padx=30, pady=28)
        else:
            self.content_area.configure(padx=36, pady=32)

        if width < 1400:
            self.filters.grid_configure(pady=(16, 0))
            _grid_reset(self.filter_button_bar)
            self.filter_button_bar.columnconfigure(0, weight=1)
            for index, button in enumerate(self.filter_buttons):
                button.grid(row=index, column=0, sticky="ew", pady=4)
            self.filter_button_bar.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        else:
            self.filters.grid_configure(pady=(0, 0))
            _grid_reset(self.filter_button_bar)
            for index, button in enumerate(self.filter_buttons):
                button.grid(row=0, column=index, padx=4)
            self.filter_button_bar.grid(row=0, column=1, sticky="e", pady=0)

        for col in range(4):
            self.metrics_frame.grid_columnconfigure(col, weight=0)
        _grid_reset(self.metrics_frame)
        if metrics_mode == "grid":
            for index, card in enumerate(self.metric_cards):
                self.metrics_frame.grid_columnconfigure(index, weight=1)
                card.grid(row=0, column=index, sticky="nsew", padx=8)
        elif metrics_mode == "double":
            for col in range(2):
                self.metrics_frame.grid_columnconfigure(col, weight=1)
            for index, card in enumerate(self.metric_cards):
                row = index // 2
                column = index % 2
                pady = (12, 0) if row > 0 else (0, 0)
                card.grid(row=row, column=column, sticky="nsew", padx=8, pady=pady)
        else:
            self.metrics_frame.grid_columnconfigure(0, weight=1)
            for index, card in enumerate(self.metric_cards):
                card.grid(row=index, column=0, sticky="ew", padx=0, pady=(0, 12))

        for col in range(2):
            self.insights_frame.grid_columnconfigure(col, weight=0)
        _grid_reset(self.insights_frame)
        if insights_mode == "double":
            for index, card in enumerate(self.insight_cards):
                self.insights_frame.grid_columnconfigure(index, weight=1)
                pad = (0, 16) if index == 0 else (16, 0)
                card.grid(row=0, column=index, sticky="nsew", padx=pad)
        else:
            self.insights_frame.grid_columnconfigure(0, weight=1)
            for index, card in enumerate(self.insight_cards):
                pady = (0, 16) if index == 0 else (0, 0)
                card.grid(row=index, column=0, sticky="ew", padx=0, pady=pady)

        for col in range(3):
            self.tables_frame.grid_columnconfigure(col, weight=0)
        _grid_reset(self.tables_frame)
        if tables_mode == "row":
            for index, section in enumerate(self.table_sections):
                self.tables_frame.grid_columnconfigure(index, weight=1)
                if index == 0:
                    pad = (0, 12)
                elif index == len(self.table_sections) - 1:
                    pad = (12, 0)
                else:
                    pad = (12, 12)
                section.grid(row=0, column=index, sticky="nsew", padx=pad)
        else:
            self.tables_frame.grid_columnconfigure(0, weight=1)
            for index, section in enumerate(self.table_sections):
                pady = (0, 16) if index < len(self.table_sections) - 1 else (0, 0)
                section.grid(row=index, column=0, sticky="nsew", pady=pady)
    def _create_metric(
        self, parent: tk.Frame, column: int, title: str, variable: tk.StringVar
    ) -> tk.Frame:
        container = tk.Frame(
            parent,
            bg="#e2e8f0",
            padx=24,
            pady=18,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
        )
        container.columnconfigure(0, weight=1)
        tk.Label(
            container,
            text=title,
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_PRIMARY,
            bg="#e2e8f0",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            container,
            textvariable=variable,
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_PRIMARY,
            bg="#e2e8f0",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        return container

    def _create_insight(
        self,
        parent: tk.Frame,
        *,
        column: int,
        title: str,
        name_var: tk.StringVar,
        count_var: tk.StringVar,
        suffix: str,
    ) -> tk.Frame:
        container = tk.Frame(
            parent,
            bg="#f1f5f9",
            padx=15,
            pady=5,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
        )
        container.columnconfigure(0, weight=1)

        tk.Label(
            container,
            text=title,
            font=("Segoe UI", 13, "bold"),
            fg=TEXT_PRIMARY,
            bg="#f1f5f9",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            container,
            textvariable=name_var,
            font=("Segoe UI", 12, "bold"),
            fg=ACCENT_COLOR,
            bg="#f1f5f9",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        tk.Label(
            container,
            textvariable=count_var,
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_SECONDARY,
            bg="#f1f5f9",
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        tk.Label(
            container,
            text=suffix,
            font=("Segoe UI", 11),
            fg=TEXT_SECONDARY,
            bg="#f1f5f9",
        ).grid(row=3, column=0, sticky="w")
        return container
        

    def pick_start_date(self) -> None:
        dialog = DatePickerDialog(self, self.start_date)
        result = dialog.show()
        self.start_date = result
        self._ensure_period_order()
        self._update_period_label()
        self.refresh_statistics()

    def pick_end_date(self) -> None:
        dialog = DatePickerDialog(self, self.end_date)
        result = dialog.show()
        self.end_date = result
        self._ensure_period_order()
        self._update_period_label()
        self.refresh_statistics()

    def pick_start_time(self) -> None:
        dialog = TimePickerDialog(self, title="Час початку", initial=self.start_time)
        result = dialog.show()
        self.start_time = result
        self._ensure_period_order()
        self._update_period_label()
        self.refresh_statistics()

    def pick_end_time(self) -> None:
        dialog = TimePickerDialog(self, title="Час завершення", initial=self.end_time)
        result = dialog.show()
        self.end_time = result
        self._ensure_period_order()
        self._update_period_label()
        self.refresh_statistics()

    def reset_period(self) -> None:
        today = date.today()
        self.start_date = today.replace(day=1)
        self.start_time = dtime.min
        self.end_date = today
        self.end_time = dtime(hour=23, minute=59, second=59)
        self._update_period_label()
        self.refresh_statistics()

    def _combine_datetime(
        self, d_value: Optional[date], t_value: Optional[dtime], *, is_start: bool
    ) -> Optional[datetime]:
        if not d_value:
            return None
        if t_value is None:
            t_value = dtime.min if is_start else dtime(hour=23, minute=59, second=59)
        return datetime.combine(d_value, t_value)

    def _start_datetime(self) -> Optional[datetime]:
        return self._combine_datetime(self.start_date, self.start_time, is_start=True)

    def _end_datetime(self) -> Optional[datetime]:
        return self._combine_datetime(self.end_date, self.end_time, is_start=False)

    def _ensure_period_order(self) -> None:
        start = self._start_datetime()
        end = self._end_datetime()
        if start and end and start > end:
            self.start_date, self.end_date = self.end_date, self.start_date
            self.start_time, self.end_time = self.end_time, self.start_time

    def _update_period_label(self) -> None:
        start = self._start_datetime()
        end = self._end_datetime()
        if start and end:
            text = f"Період: {start.strftime('%d.%m.%Y %H:%M')} – {end.strftime('%d.%m.%Y %H:%M')}"
        elif start:
            text = f"Період від: {start.strftime('%d.%m.%Y %H:%M')}"
        elif end:
            text = f"Період до: {end.strftime('%d.%m.%Y %H:%M')}"
        else:
            text = "Період: Усі дані"
        self.period_var.set(text)

    def fetch_data(self) -> None:
        token = self.app.state_data.token
        if not token:
            messagebox.showerror("Помилка", "Необхідна авторизація для перегляду статистики")
            return
        self.status_var.set("Завантаження даних...")

        def worker() -> None:
            try:
                headers = {"Authorization": f"Bearer {token}"}
                history_resp = requests.get(
                    f"{API_BASE}/get_history",
                    headers=headers,
                    timeout=10,
                )
                errors_resp = requests.get(
                    f"{API_BASE}/get_errors",
                    headers=headers,
                    timeout=10,
                )
                if history_resp.status_code == 200 and errors_resp.status_code == 200:
                    history_data = history_resp.json()
                    errors_data = errors_resp.json()
                    fallback = datetime.min.replace(tzinfo=timezone.utc)
                    history_data.sort(
                        key=lambda r: parse_api_datetime(r.get("datetime")) or fallback,
                        reverse=True,
                    )
                    errors_data.sort(
                        key=lambda r: parse_api_datetime(r.get("datetime")) or fallback,
                        reverse=True,
                    )
                    self.after(0, lambda: self._on_data_loaded(history_data, errors_data))
                else:
                    raise requests.RequestException(
                        f"history {history_resp.status_code}, errors {errors_resp.status_code}"
                    )
            except requests.RequestException as exc:
                self.after(
                    0,
                    lambda: self.status_var.set(
                        f"Помилка завантаження: {exc}"
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_data_loaded(self, history: List[Dict[str, Any]], errors: List[Dict[str, Any]]) -> None:
        self.history_records = history
        self.error_records = errors
        self.last_updated = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.refresh_statistics()

    @staticmethod
    def _normalize(dt_value: Optional[datetime]) -> Optional[datetime]:
        if dt_value and dt_value.tzinfo:
            return dt_value.astimezone().replace(tzinfo=None)
        return dt_value

    def _filter_records(
        self, records: List[Dict[str, Any]], start: Optional[datetime], end: Optional[datetime]
    ) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []
        for record in records:
            dt_value = self._normalize(parse_api_datetime(record.get("datetime")))
            if not dt_value:
                continue
            if start and dt_value < start:
                continue
            if end and dt_value > end:
                continue
            filtered.append(record)
        return filtered

    def refresh_statistics(self) -> None:
        start = self._start_datetime()
        end = self._end_datetime()
        scans = self._filter_records(self.history_records, start, end)
        errors = self._filter_records(self.error_records, start, end)

        scan_counts: Dict[str, int] = defaultdict(int)
        for record in scans:
            name = (record.get("user_name") or "Невідомий користувач").strip() or "Невідомий користувач"
            scan_counts[name] += 1

        error_counts: Dict[str, int] = defaultdict(int)
        for record in errors:
            name = (record.get("user_name") or "Невідомий користувач").strip() or "Невідомий користувач"
            error_counts[name] += 1

        self.scan_counts = dict(scan_counts)
        self.error_counts = dict(error_counts)

        self.total_scans_var.set(str(sum(self.scan_counts.values())))
        self.unique_users_var.set(str(len(self.scan_counts)))
        self.total_errors_var.set(str(sum(self.error_counts.values())))
        self.error_users_var.set(str(len(self.error_counts)))

        top_scan_name, top_scan_count = self._get_top_entry(self.scan_counts)
        top_error_name, top_error_count = self._get_top_entry(self.error_counts)
        self.top_operator_var.set(top_scan_name)
        self.top_operator_count_var.set(str(top_scan_count))
        self.top_error_operator_var.set(top_error_name)
        self.top_error_count_var.set(str(top_error_count))

        daily_map: Dict[date, Dict[str, Any]] = {}

        def ensure_day(day: date) -> Dict[str, Any]:
            if day not in daily_map:
                daily_map[day] = {
                    "scans": 0,
                    "errors": 0,
                    "scan_users": defaultdict(int),
                    "error_users": defaultdict(int),
                }
            return daily_map[day]

        for record in scans:
            dt_value = self._normalize(parse_api_datetime(record.get("datetime")))
            if not dt_value:
                continue
            info = ensure_day(dt_value.date())
            name = (record.get("user_name") or "Невідомий користувач").strip() or "Невідомий користувач"
            info["scans"] += 1
            info["scan_users"][name] += 1

        for record in errors:
            dt_value = self._normalize(parse_api_datetime(record.get("datetime")))
            if not dt_value:
                continue
            info = ensure_day(dt_value.date())
            name = (record.get("user_name") or "Невідомий користувач").strip() or "Невідомий користувач"
            info["errors"] += 1
            info["error_users"][name] += 1

        daily_rows: List[Tuple[str, int, int, str, str]] = []
        for day, info in sorted(daily_map.items(), key=lambda item: item[0], reverse=True):
            top_day_scan, top_day_scan_count = self._get_top_entry(info["scan_users"])
            top_day_error, top_day_error_count = self._get_top_entry(info["error_users"])
            daily_rows.append(
                (
                    day.strftime("%d.%m.%Y"),
                    info["scans"],
                    info["errors"],
                    self._format_top_display(top_day_scan, top_day_scan_count),
                    self._format_top_display(top_day_error, top_day_error_count),
                )
            )

        self.daily_rows = daily_rows

        self._populate_tree(self.scan_tree, self.scan_counts)
        self._populate_tree(self.error_tree, self.error_counts)
        self._populate_daily_tree(self.timeline_tree, daily_rows)

        if self.last_updated:
            suffix = f" (оновлено {self.last_updated})"
        else:
            suffix = ""
        leader_suffix = (
            f" | Лідер: {top_scan_name} ({top_scan_count})" if top_scan_count else ""
        )
        self.status_var.set(
            f"Відображено {self.total_scans_var.get()} сканувань та {self.total_errors_var.get()} помилок{suffix}{leader_suffix}"
        )

    def _populate_tree(self, tree: ttk.Treeview, data: Dict[str, int]) -> None:
        for row in tree.get_children():
            tree.delete(row)
        if not data:
            tree.insert("", "end", values=("Немає даних", "—"))
            return
        for name, count in sorted(data.items(), key=lambda item: item[1], reverse=True):
            tree.insert("", "end", values=(name, count))

    def export_statistics(self) -> None:
        if not (self.scan_counts or self.error_counts or self.daily_rows):
            messagebox.showinfo(
                "Звіт", "Немає даних для експорту. Оновіть період або синхронізуйте дані."
            )
            return

        file_path = filedialog.asksaveasfilename(
            title="Зберегти звіт",
            defaultextension=".csv",
            filetypes=[("CSV файли", "*.csv"), ("Усі файли", "*.*")],
        )
        if not file_path:
            return

        period_text = self.period_var.get() or "Період: Усі дані"
        updated_text = self.last_updated or "—"

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(["Аналітичний звіт TrackingApp"])
                writer.writerow([period_text])
                writer.writerow([f"Оновлено: {updated_text}"])
                writer.writerow([])
                writer.writerow(["Підсумки"])
                writer.writerow(["Усього сканувань", self.total_scans_var.get()])
                writer.writerow(["Унікальних операторів", self.unique_users_var.get()])
                writer.writerow(["Усього помилок", self.total_errors_var.get()])
                writer.writerow(["Користувачів з помилками", self.error_users_var.get()])
                writer.writerow(["Найактивніший оператор", self.top_operator_var.get(), self.top_operator_count_var.get()])
                writer.writerow(["Найбільше помилок", self.top_error_operator_var.get(), self.top_error_count_var.get()])

                writer.writerow([])
                writer.writerow(["Сканування за користувачами"])
                writer.writerow(["Користувач", "Кількість"])
                if self.scan_counts:
                    for name, count in sorted(self.scan_counts.items(), key=lambda item: item[1], reverse=True):
                        writer.writerow([name, count])
                else:
                    writer.writerow(["Немає даних", "—"])

                writer.writerow([])
                writer.writerow(["Помилки за користувачами"])
                writer.writerow(["Користувач", "Кількість"])
                if self.error_counts:
                    for name, count in sorted(self.error_counts.items(), key=lambda item: item[1], reverse=True):
                        writer.writerow([name, count])
                else:
                    writer.writerow(["Немає даних", "—"])

                writer.writerow([])
                writer.writerow(["Щоденна активність"])
                writer.writerow(["Дата", "Сканування", "Помилки", "Лідер", "Найбільше помилок"])
                if self.daily_rows:
                    for row in self.daily_rows:
                        writer.writerow(row)
                else:
                    writer.writerow(["Немає даних", "—", "—", "—", "—"])

            messagebox.showinfo("Звіт", "Звіт успішно збережено.")
        except OSError as exc:
            messagebox.showerror("Помилка", f"Не вдалося зберегти файл: {exc}")

    def _populate_daily_tree(
        self, tree: ttk.Treeview, rows: List[Tuple[str, int, int, str, str]]
    ) -> None:
        for row in tree.get_children():
            tree.delete(row)
        if not rows:
            tree.insert("", "end", values=("Немає даних", "—", "—", "—", "—"))
            return
        for values in rows:
            tree.insert("", "end", values=values)

    @staticmethod
    def _get_top_entry(counts: Dict[str, int]) -> Tuple[str, int]:
        if not counts:
            return "—", 0
        name, count = max(counts.items(), key=lambda item: item[1])
        return name, count

    @staticmethod
    def _format_top_display(name: str, count: int) -> str:
        if not count or name == "—":
            return "—"
        return f"{name} ({count})"

    def logout(self) -> None:
        self.perform_logout()


class ErrorsFrame(BaseFrame):
    def __init__(self, app: TrackingApp) -> None:
        super().__init__(app)
        self.role_info = get_role_info(app.state_data.user_role, app.state_data.access_level)
        self.is_admin = self.role_info.get("can_clear_history") and self.role_info.get(
            "can_clear_errors"
        )
        self._layout_mode: Optional[str] = None

        nav_actions: List[Tuple[str, Callable[[], None]]] = [
            ("⬅ Сканування", self.app.show_scanner),
            ("Історія", self.app.show_history),
        ]
        if self.is_admin:
            nav_actions.append(("Статистика", self.app.show_statistics))
        nav_actions.append(("Вийти", self.logout))

        _, card = self.build_surface(
            title="Журнал помилок",
            subtitle="Аналізуйте проблеми синхронізації та очищайте журнал",
            nav_actions=nav_actions,
        )
        card.rowconfigure(0, weight=1)

        content = tk.Frame(card, bg=CARD_BG, padx=36, pady=32)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)
        self.content_area = content

        ttk.Label(content, text="Виявлені помилки", style="CardHeading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            content,
            text="Подвійний клік видаляє запис (для ролей з правами)",
            style="CardSubheading.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 20))

        toolbar = tk.Frame(content, bg=CARD_BG)
        toolbar.grid(row=2, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=1)
        self.toolbar = toolbar
        button_bar = tk.Frame(toolbar, bg=CARD_BG)
        button_bar.grid(row=0, column=1, sticky="e")
        self.button_bar = button_bar
        self.button_widgets: List[ttk.Button] = []

        def add_toolbar_button(text: str, command: Callable[[], None], style: str) -> None:
            button = ttk.Button(button_bar, text=text, command=command, style=style)
            column = len(self.button_widgets)
            button.grid(row=0, column=column, padx=4)
            self.button_widgets.append(button)

        add_toolbar_button("Оновити", self.fetch_errors, "Primary.TButton")
        if self.role_info["can_clear_errors"]:
            add_toolbar_button("Очистити всі", self.clear_errors, "Outline.TButton")

        tree_container = tk.Frame(content, bg=CARD_BG)
        tree_container.grid(row=3, column=0, sticky="nsew", pady=(24, 0))
        tree_container.columnconfigure(0, weight=1)
        tree_container.rowconfigure(0, weight=1)

        columns = ("datetime", "boxid", "ttn", "user", "reason")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings")
        headings = {
            "datetime": "Дата",
            "boxid": "BoxID",
            "ttn": "TTN",
            "user": "Користувач",
            "reason": "Причина",
        }
        for col, text in headings.items():
            self.tree.heading(col, text=text)
            self.tree.column(col, width=200 if col == "reason" else 160, anchor="center")

        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        if self.role_info["can_clear_errors"]:
            self.tree.bind("<Double-1>", self.delete_selected_error)

        self.records: List[Dict[str, Any]] = []

        self.fetch_errors()
        self.register_responsive(self._update_responsive_layout)

    def fetch_errors(self) -> None:
        token = self.app.state_data.token
        if not token:
            messagebox.showerror("Помилка", "Необхідна авторизація")
            return

        def worker() -> None:
            try:
                response = requests.get(
                    f"{API_BASE}/get_errors",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    fallback = datetime.min.replace(tzinfo=timezone.utc)
                    data.sort(
                        key=lambda r: parse_api_datetime(r.get("datetime")) or fallback,
                        reverse=True,
                    )
                    self.records = data
                    self.after(0, self.render_records)
                else:
                    raise requests.RequestException(f"status {response.status_code}")
            except requests.RequestException as exc:
                self.after(0, lambda: messagebox.showerror("Помилка", f"Не вдалося завантажити: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def render_records(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)
        for item in self.records:
            dt = parse_api_datetime(item.get("datetime"))
            dt_txt = dt.strftime("%d.%m.%Y %H:%M:%S") if dt else item.get("datetime", "")
            reason = (
                item.get("error_message")
                or item.get("reason")
                or item.get("note")
                or item.get("message")
                or item.get("error")
                or "Причина не вказана"
            )
            self.tree.insert(
                "",
                "end",
                iid=str(item.get("id", "")),
                values=(
                    dt_txt,
                    item.get("boxid", ""),
                    item.get("ttn", ""),
                    item.get("user_name", ""),
                    reason,
                ),
            )

    def clear_errors(self) -> None:
        if not messagebox.askyesno("Підтвердження", "Очистити журнал помилок?"):
            return
        token = self.app.state_data.token
        if not token:
            return

        def worker() -> None:
            try:
                response = requests.delete(
                    f"{API_BASE}/clear_errors",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                if response.status_code == 200:
                    def update() -> None:
                        self.records.clear()
                        self.render_records()

                    self.after(0, update)
                else:
                    raise requests.RequestException(f"status {response.status_code}")
            except requests.RequestException as exc:
                self.after(0, lambda: messagebox.showerror("Помилка", f"Не вдалося очистити: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def delete_selected_error(self, event: tk.Event) -> None:
        item_id = self.tree.focus()
        if not item_id:
            return
        try:
            record_id = int(float(item_id))
        except ValueError:
            return
        if not messagebox.askyesno("Підтвердження", f"Видалити помилку #{record_id}?"):
            return
        token = self.app.state_data.token
        if not token:
            return

        def worker() -> None:
            try:
                response = requests.delete(
                    f"{API_BASE}/delete_error/{record_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                if response.status_code == 200:
                    def update() -> None:
                        self.records = [r for r in self.records if r.get("id") != record_id]
                        self.render_records()

                    self.after(0, update)
                else:
                    raise requests.RequestException(f"status {response.status_code}")
            except requests.RequestException as exc:
                self.after(0, lambda: messagebox.showerror("Помилка", f"Не вдалося видалити: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def logout(self) -> None:
        self.perform_logout()

    def _update_responsive_layout(self, width: int, height: int) -> None:
        mode = "compact" if width < 1280 else "default"
        if self._layout_mode == mode:
            return
        self._layout_mode = mode

        if mode == "compact":
            self.content_area.configure(padx=24, pady=24)
            self.toolbar.grid_configure(pady=(0, 0))
            _grid_reset(self.button_bar)
            self.button_bar.columnconfigure(0, weight=1)
            for index, button in enumerate(self.button_widgets):
                button.grid(row=index, column=0, sticky="ew", pady=4)
            self.button_bar.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        else:
            self.content_area.configure(padx=36, pady=32)
            _grid_reset(self.button_bar)
            for index, button in enumerate(self.button_widgets):
                button.grid(row=0, column=index, padx=4)
            self.button_bar.grid(row=0, column=1, sticky="e", pady=0)


def main() -> None:
    app = TrackingApp()
    app.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
