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
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "images" / "logo.png"

# Design constants for corporate-style UI
PRIMARY_BG = "#0f172a"
SECONDARY_BG = "#111c3a"
CARD_BG = "#ffffff"
ACCENT_COLOR = "#1d4ed8"
ACCENT_HOVER = "#1e40af"
TEXT_PRIMARY = "#0f172a"
TEXT_SECONDARY = "#475569"
NEUTRAL_BORDER = "#cbd5f5"
APP_BACKGROUND = "#edf2ff"
HERO_GRADIENT_START = "#0057ff"
HERO_GRADIENT_END = "#3ec1ff"
LINK_COLOR = "#2563eb"
CARD_SHADOW = "#dce6ff"
# Базовый "дизайн-размер" окна
BASE_WIDTH = 1920
BASE_HEIGHT = 1080

def compute_scale(screen_w: int, screen_h: int) -> float:
    """
    Возвращает коэффициент масштабирования интерфейса
    относительно базового размера.
    """
    scale_w = screen_w / BASE_WIDTH
    scale_h = screen_h / BASE_HEIGHT
    scale = min(scale_w, scale_h)

    # Ограничим, чтобы на очень маленьких/огромных экранах
    # шрифты не становились слишком мелкими или гигантскими
    if scale < 0.8:
        scale = 0.8
    if scale > 1.6:
        scale = 1.6
    return scale


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
        return dt
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
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
        font=("Segoe UI", 50, "bold"),
        bg=CARD_BG,
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
        font=("Segoe UI", 20, "bold"),
        bg=CARD_BG,
        fg=TEXT_PRIMARY,
        insertbackground=TEXT_PRIMARY,
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightcolor=ACCENT_COLOR,
        highlightbackground=NEUTRAL_BORDER,
        disabledforeground="#94a3b8",
        disabledbackground="#e2e8f0",
    )
    return entry


def draw_vertical_gradient(
    canvas: tk.Canvas,
    *,
    color_from: str,
    color_to: str,
) -> None:
    width = canvas.winfo_width()
    height = canvas.winfo_height()
    canvas.delete("gradient")
    if width <= 0 or height <= 0:
        return

    start_r, start_g, start_b = [value // 256 for value in canvas.winfo_rgb(color_from)]
    end_r, end_g, end_b = [value // 256 for value in canvas.winfo_rgb(color_to)]

    steps = max(height, 1)
    for i in range(steps):
        ratio = i / steps
        red = int(start_r + (end_r - start_r) * ratio)
        green = int(start_g + (end_g - start_g) * ratio)
        blue = int(start_b + (end_b - start_b) * ratio)
        canvas.create_line(
            0,
            i,
            width,
            i,
            tags="gradient",
            fill=f"#{red:02x}{green:02x}{blue:02x}",
        )




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

    def perform_logout(self) -> None:
        if not messagebox.askyesno("Підтвердження", "Вийти з акаунту?"):
            return
        self.app.state_data = AppState()
        self.app.state_data.save()
        self.app.show_login()
    def attach_tree_copy_menu(self, tree: ttk.Treeview) -> None:
        """Добавляет контекстное меню копирования для указанного Treeview."""
        menu = tk.Menu(tree, tearoff=0)
        state: dict[str, Optional[str]] = {"row": None, "col": None}

        def on_right_click(event: tk.Event) -> None:
            row_id = tree.identify_row(event.y)
            if not row_id:
                return  # кликнули мимо строки — меню не показываем

            # выделяем строку под курсором
            tree.selection_set(row_id)
            tree.focus(row_id)
            state["row"] = row_id
            state["col"] = tree.identify_column(event.x)

            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        def copy_cell() -> None:
            row_id = state["row"] or (tree.selection()[0] if tree.selection() else None)
            if not row_id:
                return

            values = tree.item(row_id, "values")
            if not values:
                return

            col_id = state["col"]
            index = 0
            if col_id:
                try:
                    index = int(col_id.lstrip("#")) - 1
                except ValueError:
                    index = 0

            value = values[index] if 0 <= index < len(values) else ""
            self.clipboard_clear()
            self.clipboard_append(value)

        def copy_row() -> None:
            row_id = state["row"] or (tree.selection()[0] if tree.selection() else None)
            if not row_id:
                return

            values = tree.item(row_id, "values") or ()
            text = "\t".join(str(v) for v in values)
            self.clipboard_clear()
            self.clipboard_append(text)

        menu.add_command(label="Копіювати значення", command=copy_cell)
        menu.add_command(label="Копіювати рядок", command=copy_row)

        # ПКМ по дереву — открыть меню
        tree.bind("<Button-3>", on_right_click)


class TrackingApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("TrackingApp Windows Edition")

        # размеры экрана
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        # коэффициент масштабирования для всего UI
        self.ui_scale = compute_scale(screen_w, screen_h)

        # масштабирование шрифтов Tk (DPI-aware)
        try:
            self.tk.call("tk", "scaling", self.ui_scale)
        except tk.TclError:
            pass

        # стартовый размер окна относительно базового
        width = int(BASE_WIDTH * self.ui_scale)
        height = int(BASE_HEIGHT * self.ui_scale)
        self.geometry(f"{width}x{height}")

        # минимальный размер, чтобы всё не "ломалось"
        self.minsize(int(BASE_WIDTH * 0.8), int(BASE_HEIGHT * 0.8))

        self.configure(bg=PRIMARY_BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # сразу разворачиваем на полный экран
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
            "Card.TLabel",
            font=("Segoe UI", 12),
            background=CARD_BG,
            foreground=TEXT_SECONDARY,
        )
        self.style.configure(
            "CardHeading.TLabel",
            font=("Segoe UI", 28, "bold"),
            background=CARD_BG,
            foreground=TEXT_PRIMARY,
        )
        self.style.configure(
            "CardSubheading.TLabel",
            font=("Segoe UI", 14),
            background=CARD_BG,
            foreground=TEXT_SECONDARY,
        )
        self.style.configure(
            "Primary.TButton",
            font=("Segoe UI", 14, "bold"),
            padding=(24, 12),
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
            padding=(18, 10),
            background="#1f2937",
            foreground="#f8fafc",
            borderwidth=0,
        )
        self.style.map(
            "Secondary.TButton",
            background=[("active", "#0f172a")],
            foreground=[("disabled", "#94a3b8")],
        )
        self.style.configure(
            "TEntry",
            font=("Segoe UI", 16),
            padding=10,
        )
        self.style.configure(
            "Treeview",
            font=("Segoe UI", 12),
            rowheight=36,
            fieldbackground="#f8fafc",
            background="#f8fafc",
            foreground=TEXT_PRIMARY,
            borderwidth=0,
        )
        self.style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 12, "bold"),
            padding=12,
            background=ACCENT_COLOR,
            foreground="white",
            relief="flat",
        )
        self.style.map(
            "Treeview.Heading",
            background=[("active", ACCENT_HOVER)],
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

        self.hero_canvas: Optional[tk.Canvas] = None
        self.logo_image: Optional[tk.PhotoImage] = None

        self._build_layout()

    def _build_layout(self) -> None:
        self._load_logo_image()
        self.configure(bg=APP_BACKGROUND)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        wrapper = tk.Frame(self, bg=APP_BACKGROUND, padx=40, pady=40)
        wrapper.grid(row=0, column=0, sticky="nsew")
        wrapper.columnconfigure(0, weight=1)
        wrapper.columnconfigure(1, weight=1)
        wrapper.rowconfigure(0, weight=1)

        hero_container = tk.Frame(wrapper, bg=APP_BACKGROUND)
        hero_container.grid(row=0, column=0, sticky="nsew", padx=(0, 32))
        hero_container.columnconfigure(0, weight=1)
        hero_container.rowconfigure(0, weight=1)

        hero_panel = tk.Frame(hero_container, bg=APP_BACKGROUND, bd=0)
        hero_panel.grid(row=0, column=0, sticky="nsew")
        hero_panel.columnconfigure(0, weight=1)
        hero_panel.rowconfigure(0, weight=1)

        self.hero_canvas = tk.Canvas(
            hero_panel,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.hero_canvas.grid(row=0, column=0, sticky="nsew")
        self.hero_canvas.bind("<Configure>", self._draw_hero_panel)

        card_container = tk.Frame(wrapper, bg=APP_BACKGROUND)
        card_container.grid(row=0, column=1, sticky="nsew")
        card_container.columnconfigure(0, weight=1)
        card_container.rowconfigure(0, weight=1)

        shadow = tk.Frame(card_container, bg=CARD_SHADOW, bd=0)
        shadow.grid(row=0, column=0, sticky="nsew")
        shadow.columnconfigure(0, weight=1)
        shadow.rowconfigure(0, weight=1)

        card = tk.Frame(shadow, bg=CARD_BG, padx=56, pady=48)
        card.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)

        tk.Label(
            card,
            text="1-2-3",
            font=("Segoe UI", 32, "bold"),
            fg=TEXT_PRIMARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")

        self.subtitle_var = tk.StringVar(value="Будь-ласка увійдіть у систему")
        tk.Label(
            card,
            textvariable=self.subtitle_var,
            font=("Segoe UI", 14),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
            wraplength=420,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(8, 24))

        self.forms_container = tk.Frame(card, bg=CARD_BG)
        self.forms_container.grid(row=2, column=0, sticky="nsew")
        self.forms_container.columnconfigure(0, weight=1)

        self.login_form = self._build_login_form(self.forms_container)
        self.register_form = self._build_registration_form(self.forms_container)

        links = tk.Frame(card, bg=CARD_BG)
        links.grid(row=3, column=0, sticky="ew", pady=(32, 0))
        links.columnconfigure(0, weight=1)

        self.mode_link_text = tk.StringVar(value="Відправити заявку на доступ")
        self.mode_link = tk.Button(
            links,
            textvariable=self.mode_link_text,
            command=lambda: self.set_mode("register"),
            bg=CARD_BG,
            fg=LINK_COLOR,
            activebackground=CARD_BG,
            activeforeground=ACCENT_COLOR,
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 12, "bold"),
            cursor="hand2",
        )
        self.mode_link.grid(row=0, column=0, sticky="w")

        self.admin_link = tk.Button(
            links,
            text="Панель адміністратора",
            command=self.open_admin_panel,
            bg=CARD_BG,
            fg=LINK_COLOR,
            activebackground=CARD_BG,
            activeforeground=ACCENT_COLOR,
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 12),
            cursor="hand2",
        )
        self.admin_link.grid(row=1, column=0, sticky="w", pady=(12, 0))

        self.set_mode(self.mode.get())

    def _load_logo_image(self) -> None:
        if LOGO_PATH.exists():
            try:
                self.logo_image = tk.PhotoImage(file=str(LOGO_PATH))
            except tk.TclError:
                self.logo_image = None
        else:
            self.logo_image = None

    def _draw_hero_panel(self, event: Optional[tk.Event] = None) -> None:
        if not self.hero_canvas:
            return
        draw_vertical_gradient(
            self.hero_canvas,
            color_from=HERO_GRADIENT_START,
            color_to=HERO_GRADIENT_END,
        )
        self.hero_canvas.delete("hero-text")
        self.hero_canvas.delete("hero-image")
        width = self.hero_canvas.winfo_width()
        height = self.hero_canvas.winfo_height()
        if width <= 0 or height <= 0:
            return

        padding = max(int(min(width, height) * 0.1), 48)
        center_x = width // 2
        available_width = max(width - padding * 2, 200)
        current_y = padding
        if self.logo_image:
            img_height = self.logo_image.height()
            self.hero_canvas.create_image(
                center_x,
                current_y,
                anchor="n",
                image=self.logo_image,
                tags="hero-image",
            )
            current_y += img_height + 48
        heading = "TrackingApp 2.0 "
        subheading = "Версія для Windows by DimonVR"

        heading_item = self.hero_canvas.create_text(
            center_x,
            current_y,
            anchor="n",
            width=available_width,
            text=heading,
            font=("Segoe UI", 34, "bold"),
            fill="#ffffff",
            justify="center",
            tags="hero-text",
        )
        heading_bbox = self.hero_canvas.bbox(heading_item)
        if heading_bbox:
            current_y = heading_bbox[3] + 24
        else:
            current_y += 96
        self.hero_canvas.create_text(
            center_x,
            current_y,
            anchor="n",
            width=available_width,
            text=subheading,
            font=("Segoe UI", 20),
            fill="#e2f3ff",
            justify="center",
            tags="hero-text",
        )

    def _build_login_form(self, parent: tk.Misc) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD_BG)
        frame.columnconfigure(0, weight=1)

        tk.Label(
            frame,
            text="Прізвище",
            font=("Segoe UI", 14, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")
        surname_entry = create_form_entry(
            frame, textvariable=self.login_surname_var, justify="left"
        )
        surname_entry.grid(row=1, column=0, sticky="ew", pady=(8, 16), ipady=6)
        surname_entry.bind("<Return>", lambda _: self.login())

        tk.Label(
            frame,
            text="Пароль",
            font=("Segoe UI", 14, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=2, column=0, sticky="w")
        password_entry = create_form_entry(
            frame, textvariable=self.login_password_var, show="*", justify="left"
        )
        password_entry.grid(row=3, column=0, sticky="ew", pady=(8, 8), ipady=6)
        password_entry.bind("<Return>", lambda _: self.login())

        self.login_error_label = tk.Label(
            frame,
            textvariable=self.login_error_var,
            font=("Segoe UI", 12),
            fg="#d32f2f",
            bg=CARD_BG,
        )
        self.login_error_label.grid(row=4, column=0, sticky="ew", pady=(4, 0))

        self.login_button = ttk.Button(
            frame,
            text="Увійти в систему",
            style="Primary.TButton",
            command=self.login,
        )
        self.login_button.grid(row=5, column=0, sticky="ew", pady=(24, 0))

        self.login_surname_entry = surname_entry
        return frame

    def _build_registration_form(self, parent: tk.Misc) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD_BG)
        frame.columnconfigure(0, weight=1)

        tk.Label(
            frame,
            text="Прізвище",
            font=("Segoe UI", 14, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")
        surname_entry = create_form_entry(
            frame, textvariable=self.register_surname_var, justify="left"
        )
        surname_entry.grid(row=1, column=0, sticky="ew", pady=(8, 16), ipady=6)
        surname_entry.bind("<Return>", lambda _: self.register())

        tk.Label(
            frame,
            text="Пароль",
            font=("Segoe UI", 14, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=2, column=0, sticky="w")
        password_entry = create_form_entry(
            frame, textvariable=self.register_password_var, show="*", justify="left"
        )
        password_entry.grid(row=3, column=0, sticky="ew", pady=(8, 16), ipady=6)
        password_entry.bind("<Return>", lambda _: self.register())

        tk.Label(
            frame,
            text="Підтвердження пароля",
            font=("Segoe UI", 14, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=4, column=0, sticky="w")
        confirm_entry = create_form_entry(
            frame, textvariable=self.register_confirm_var, show="*", justify="left"
        )
        confirm_entry.grid(row=5, column=0, sticky="ew", pady=(8, 8), ipady=6)
        confirm_entry.bind("<Return>", lambda _: self.register())

        self.register_feedback_label = tk.Label(
            frame,
            textvariable=self.register_message_var,
            font=("Segoe UI", 12),
            fg="#16a34a",
            bg=CARD_BG,
            wraplength=420,
            justify="left",
        )
        self.register_feedback_label.grid(row=6, column=0, sticky="ew", pady=(4, 0))

        self.register_button = ttk.Button(
            frame,
            text="Відправити заявку",
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
            self.subtitle_var.set("Будь-ласка увійдіть в систему")
            self.mode_link_text.set("Відправити заявку на доступ")
            self.mode_link.configure(command=lambda: self.set_mode("register"))
        else:
            self.login_form.grid_forget()
            self.register_form.grid(row=0, column=0, sticky="nsew")
            self.login_error_var.set("")
            self.after(100, self.register_surname_entry.focus_set)
            self.subtitle_var.set("Надішліть заявку, щоб отримати доступ")
            self.mode_link_text.set("Повернутися до входу")
            self.mode_link.configure(command=lambda: self.set_mode("login"))

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
        button = getattr(self, "login_button", None)
        if not button:
            return
        try:
            if loading:
                button.configure(text="Зачекайте...", state="disabled")
            else:
                button.configure(text="Увійти в систему", state="normal")
        except tk.TclError:
            # Віджет вже знищено (наприклад, після переходу з екрана входу)
            # і повторна зміна стану не потрібна.
            return

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
            self.register_button.configure(text="Відправити заявку", state="normal")

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

        header = tk.Frame(self, bg=SECONDARY_BG, padx=32, pady=20)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)

        tk.Label(
            header,
            text="Панель адміністратора",
            font=("Segoe UI", 28, "bold"),
            fg="white",
            bg=SECONDARY_BG,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Керуйте користувачами та запитами на реєстрацію",
            font=("Segoe UI", 12),
            fg="#cbd5f5",
            bg=SECONDARY_BG,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        ttk.Button(
            header,
            text="Оновити дані",
            style="Secondary.TButton",
            command=self.refresh_data,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        body = tk.Frame(self, bg=PRIMARY_BG, padx=24, pady=24)
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

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
        tk.Label(
            status_bar,
            textvariable=self.status_var,
            font=("Segoe UI", 12),
            fg="#e2e8f0",
            bg=SECONDARY_BG,
        ).grid(row=0, column=0, sticky="w")

        self.refresh_data()

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
        self.pending_tree.column("surname", width=280)
        self.pending_tree.column("created", width=200)
        self.pending_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.pending_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.pending_tree.configure(yscrollcommand=scrollbar.set)

        actions = tk.Frame(parent, bg=CARD_BG)
        actions.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 24))
        actions.columnconfigure((0, 1, 2, 3), weight=1)

        ttk.Button(
            actions,
            text="Підтвердити як адміністратор",
            style="Secondary.TButton",
            command=lambda: self.approve_selected(UserRole.ADMIN),
        ).grid(row=0, column=0, padx=6, sticky="ew")
        ttk.Button(
            actions,
            text="Підтвердити як оператор",
            style="Secondary.TButton",
            command=lambda: self.approve_selected(UserRole.OPERATOR),
        ).grid(row=0, column=1, padx=6, sticky="ew")
        ttk.Button(
            actions,
            text="Підтвердити як перегляд",
            style="Secondary.TButton",
            command=lambda: self.approve_selected(UserRole.VIEWER),
        ).grid(row=0, column=2, padx=6, sticky="ew")
        ttk.Button(
            actions,
            text="Відхилити",
            style="Secondary.TButton",
            command=self.reject_selected,
        ).grid(row=0, column=3, padx=6, sticky="ew")

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
            "surname": 220,
            "role": 140,
            "active": 140,
            "created": 160,
            "updated": 160,
        }
        for key in columns:
            self.users_tree.heading(key, text=headings[key])
            self.users_tree.column(key, width=widths[key])
        self.users_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.users_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.users_tree.configure(yscrollcommand=scrollbar.set)

        actions = tk.Frame(parent, bg=CARD_BG)
        actions.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 24))
        actions.columnconfigure((0, 1, 2, 3, 4), weight=1)

        ttk.Button(
            actions,
            text="Зробити адміністратором",
            style="Secondary.TButton",
            command=lambda: self.set_user_role(UserRole.ADMIN),
        ).grid(row=0, column=0, padx=6, sticky="ew")
        ttk.Button(
            actions,
            text="Зробити оператором",
            style="Secondary.TButton",
            command=lambda: self.set_user_role(UserRole.OPERATOR),
        ).grid(row=0, column=1, padx=6, sticky="ew")
        ttk.Button(
            actions,
            text="Зробити перегляд",
            style="Secondary.TButton",
            command=lambda: self.set_user_role(UserRole.VIEWER),
        ).grid(row=0, column=2, padx=6, sticky="ew")
        ttk.Button(
            actions,
            text="Активувати/Призупинити",
            style="Secondary.TButton",
            command=self.toggle_user_active,
        ).grid(row=0, column=3, padx=6, sticky="ew")
        ttk.Button(
            actions,
            text="Видалити",
            style="Secondary.TButton",
            command=self.delete_user,
        ).grid(row=0, column=4, padx=6, sticky="ew")

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
        self.passwords_tree.column("role", width=200)
        self.passwords_tree.column("password", width=320)
        self.passwords_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.passwords_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.passwords_tree.configure(yscrollcommand=scrollbar.set)

        actions = tk.Frame(parent, bg=CARD_BG)
        actions.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 24))
        actions.columnconfigure(0, weight=1)

        ttk.Button(
            actions,
            text="Змінити пароль",
            style="Secondary.TButton",
            command=self.update_role_password,
        ).grid(row=0, column=0, sticky="e", padx=6)

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

    def _apply_admin_data(
        self,
        pending: List[PendingUser],
        users: List[ManagedUser],
        passwords: Dict[UserRole, str],
    ) -> None:
        self.pending_users = pending
        self.managed_users = users
        self.role_passwords = {UserRole.ADMIN: passwords.get(UserRole.ADMIN, "")}
        self._populate_pending()
        self._populate_users()
        self._populate_passwords()
        self.status_var.set(
            f"Запити: {len(pending)} | Користувачі: {len(users)} | Ролі: {len(self.role_passwords)}"
        )

    @staticmethod
    def _format_datetime(value: Optional[datetime]) -> str:
        if not value:
            return "—"
        return value.strftime("%d.%m.%Y %H:%M")

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

        self.configure(bg=APP_BACKGROUND)
        wrapper = tk.Frame(self, bg=APP_BACKGROUND, padx=120, pady=120)
        wrapper.grid(row=0, column=0, sticky="nsew")
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(0, weight=1)

        shadow = tk.Frame(wrapper, bg=CARD_SHADOW, bd=0)
        shadow.grid(row=0, column=0, sticky="nsew")
        shadow.columnconfigure(0, weight=1)
        shadow.rowconfigure(0, weight=1)

        card = tk.Frame(
            shadow,
            bg=CARD_BG,
            padx=72,
            pady=64,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        card.columnconfigure(0, weight=1)

        badge = tk.Label(
            card,
            text="Налаштування профілю",
            font=("Segoe UI", 12, "bold"),
            fg=LINK_COLOR,
            bg=CARD_BG,
        )
        badge.grid(row=0, column=0, sticky="w")
        tk.Label(
            card,
            text="Вкажіть оператора, який працює із системою",
            font=("Segoe UI", 28, "bold"),
            fg=TEXT_PRIMARY,
            bg=CARD_BG,
        ).grid(row=1, column=0, sticky="w", pady=(12, 0))
        tk.Label(
            card,
            text="Ім’я відображатиметься у звітах, історії та логах синхронізації",
            font=("Segoe UI", 13),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=2, column=0, sticky="w", pady=(8, 32))

        input_block = tk.Frame(card, bg=CARD_BG)
        input_block.grid(row=3, column=0, sticky="ew")
        input_block.columnconfigure(0, weight=1)
        tk.Label(
            input_block,
            text="Ім’я користувача",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")
        entry = create_large_entry(
            input_block,
            textvariable=self.name_var,
        )
        entry.grid(row=1, column=0, sticky="ew", pady=(12, 0), ipady=36)
        entry.bind("<Return>", lambda _: self.save())

        ttk.Button(
            card,
            text="Продовжити",
            command=self.save,
            style="Primary.TButton",
        ).grid(row=4, column=0, sticky="ew", pady=(36, 0))

        entry.focus_set()

    def save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Увага", "Введіть ім’я користувача")
            return
        self.app.state_data.user_name = name
        self.app.state_data.save()
        self.app.show_scanner()


class ScannerFrame(BaseFrame):
    def __init__(self, app: TrackingApp) -> None:
        super().__init__(app)
        self.box_var = tk.StringVar()
        self.ttn_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Готово до введення BoxID")
        self.online_var = tk.StringVar(value="Перевірка зв’язку...")
        self.online_color = "#facc15"
        self.step_progress_var = tk.StringVar(value="Крок 1 з 2")
        self.step_title_var = tk.StringVar(value="Введіть BoxID")

        self.role_info = get_role_info(
            app.state_data.user_role, app.state_data.access_level
        )
        self.is_admin = self.role_info.get("can_clear_history") and self.role_info.get(
            "can_clear_errors"
        )
        self.is_view_only = self.role_info.get("role") == UserRole.VIEWER

        self.configure(bg=APP_BACKGROUND)
        shell = tk.Frame(self, bg=APP_BACKGROUND, padx=36, pady=36)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = tk.Frame(shell, bg=APP_BACKGROUND)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        header_card = tk.Frame(
            header,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            padx=36,
            pady=28,
        )
        header_card.grid(row=0, column=0, sticky="ew")
        header_card.columnconfigure(0, weight=1)
        header_card.columnconfigure(1, weight=1)
        header_card.columnconfigure(2, weight=1)

        brand = tk.Frame(header_card, bg=CARD_BG)
        brand.grid(row=0, column=0, sticky="w")
        tk.Label(
            brand,
            text="1-2-3",
            font=("Segoe UI", 28, "bold"),
            fg=TEXT_PRIMARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            brand,
            text="Система фіксації BoxID до ТТН ",
            font=("Segoe UI", 12),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        connection = tk.Frame(header_card, bg=CARD_BG)
        connection.grid(row=0, column=1, sticky="e")
        self.online_chip = tk.Label(
            connection,
            textvariable=self.online_var,
            font=("Segoe UI", 12, "bold"),
            bg=self.online_color,
            fg=TEXT_PRIMARY,
            padx=18,
            pady=10,
        )
        self.online_chip.grid(row=0, column=0, sticky="e")

        user_info = tk.Frame(header_card, bg=CARD_BG)
        user_info.grid(row=0, column=2, sticky="e")
        tk.Label(
            user_info,
            text=app.state_data.user_name,
            font=("Segoe UI", 18, "bold"),
            fg=TEXT_PRIMARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="e")
        tk.Label(
            user_info,
            text=self.role_info["label"],
            font=("Segoe UI", 12, "bold"),
            fg="white",
            bg=self.role_info["color"],
            padx=12,
            pady=4,
        ).grid(row=1, column=0, sticky="e", pady=(8, 0))

        nav = tk.Frame(header_card, bg=CARD_BG)
        nav.grid(row=1, column=0, columnspan=3, sticky="e", pady=(24, 0))
        column = 0
        if self.is_admin:
            ttk.Button(
                nav,
                text="Статистика",
                command=self.open_statistics,
                style="Secondary.TButton",
            ).grid(row=0, column=column, padx=6)
            column += 1
        ttk.Button(
            nav,
            text="Історія",
            command=self.open_history,
            style="Secondary.TButton",
        ).grid(row=0, column=column, padx=6)
        column += 1
        ttk.Button(
            nav,
            text="Помилки",
            command=self.open_errors,
            style="Secondary.TButton",
        ).grid(row=0, column=column, padx=6)
        column += 1
        ttk.Button(
            nav,
            text="Вийти",
            command=self.logout,
            style="Secondary.TButton",
        ).grid(row=0, column=column, padx=6)

        content = tk.Frame(shell, bg=APP_BACKGROUND, padx=12, pady=28)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        card = tk.Frame(
            content,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            padx=64,
            pady=52,
        )
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)

        header_section = tk.Frame(card, bg=CARD_BG)
        header_section.grid(row=0, column=0, sticky="ew")
        header_section.columnconfigure(0, weight=1)
        ttk.Label(
            header_section,
            textvariable=self.step_progress_var,
            style="CardSubheading.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header_section,
            textvariable=self.step_title_var,
            style="CardHeading.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 32))

        self.box_group, self.box_entry = self._create_input_group(
            card,
            title="BoxID",
            variable=self.box_var,
            row=1,
        )
        self.box_entry.bind("<Return>", lambda _: self.to_next())

        self.ttn_group, self.ttn_entry = self._create_input_group(
            card,
            title="ТТН",
            variable=self.ttn_var,
            row=2,
        )
        self.ttn_entry.configure(state="disabled")
        self.ttn_entry.bind("<Return>", lambda _: self.submit())

        actions = tk.Frame(card, bg=CARD_BG)
        actions.grid(row=3, column=0, sticky="ew", pady=(32, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
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
            style="Secondary.TButton",
            command=self.reset_fields,
        )
        self.reset_button.grid(row=0, column=1, sticky="ew")

        status_panel = tk.Frame(card, bg="#f8fafc", padx=20, pady=20)
        status_panel.grid(row=4, column=0, sticky="ew", pady=(40, 0))
        status_panel.columnconfigure(0, weight=1)
        tk.Label(
            status_panel,
            textvariable=self.status_var,
            font=("Segoe UI", 14),
            fg=TEXT_SECONDARY,
            bg="#f8fafc",
            wraplength=1200,
            justify="center",
        ).grid(row=0, column=0, sticky="ew")

        self.stage = "box"
        self._apply_role_permissions()
        if not self.is_view_only:
            self.box_entry.focus_set()
        self.check_connectivity()
        OfflineQueue.sync_pending(self.app.state_data.token or "")

    def _apply_role_permissions(self) -> None:
        if not self.is_view_only:
            return
        self.box_entry.configure(state="disabled")
        self.ttn_entry.configure(state="disabled")
        self.primary_button.configure(state="disabled")
        self.reset_button.configure(state="disabled")
        self.step_title_var.set("Режим перегляду")
        self.status_var.set(
            "Ваш обліковий запис має рівень \"Перегляд\". Введення BoxID та ТТН недоступне."
        )

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
        entry.grid(row=1, column=0, sticky="ew", pady=(8, 0), ipady=10)
        return frame, entry

    def set_online_state(self, online: bool) -> None:
        if online:
            self.online_color = "#16a34a"
            self.online_var.set("🟢 Підключення активне")
            fg = "white"
        else:
            self.online_color = "#dc2626"
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
        if self.is_view_only:
            return
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
        if self.is_view_only:
            return
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
        if self.is_view_only:
            return
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

        self.configure(bg=APP_BACKGROUND)
        shell = tk.Frame(self, bg=APP_BACKGROUND, padx=36, pady=36)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = tk.Frame(shell, bg=APP_BACKGROUND)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        header_card = tk.Frame(
            header,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            padx=36,
            pady=24,
        )
        header_card.grid(row=0, column=0, sticky="ew")
        header_card.columnconfigure(0, weight=1)
        header_card.columnconfigure(1, weight=1)

        branding = tk.Frame(header_card, bg=CARD_BG)
        branding.grid(row=0, column=0, sticky="w")
        tk.Label(
            branding,
            text="Історія операцій",
            font=("Segoe UI", 26, "bold"),
            fg=TEXT_PRIMARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            branding,
            text="Переглядайте та фільтруйте всі записані відправлення",
            font=("Segoe UI", 12),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        user_info = tk.Frame(header_card, bg=CARD_BG)
        user_info.grid(row=0, column=1, sticky="e")
        tk.Label(
            user_info,
            text=app.state_data.user_name,
            font=("Segoe UI", 18, "bold"),
            fg=TEXT_PRIMARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="e")
        tk.Label(
            user_info,
            text=self.role_info["label"],
            font=("Segoe UI", 12, "bold"),
            fg="white",
            bg=self.role_info["color"],
            padx=12,
            pady=4,
        ).grid(row=1, column=0, sticky="e", pady=(8, 0))

        nav = tk.Frame(header_card, bg=CARD_BG)
        nav.grid(row=1, column=0, columnspan=2, sticky="e", pady=(20, 0))
        column = 0
        ttk.Button(
            nav,
            text="⬅ Головна",
            command=self.app.show_scanner,
            style="Secondary.TButton",
        ).grid(row=0, column=column, padx=6)
        column += 1
        ttk.Button(
            nav,
            text="Журнал помилок",
            command=self.app.show_errors,
            style="Secondary.TButton",
        ).grid(row=0, column=column, padx=6)
        column += 1
        if self.is_admin:
            ttk.Button(
                nav,
                text="Статистика",
                command=self.app.show_statistics,
                style="Secondary.TButton",
            ).grid(row=0, column=column, padx=6)
            column += 1
        ttk.Button(nav, text="Вийти", command=self.logout, style="Secondary.TButton").grid(row=0, column=column, padx=6)

        content = tk.Frame(shell, bg=APP_BACKGROUND, padx=32, pady=32)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        card = tk.Frame(
            content,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            padx=36,
            pady=32,
        )
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1)

        ttk.Label(
            card,
            text="Зведення сканувань",
            style="CardHeading.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            card,
            text="Швидкий пошук за BoxID, ТТН, користувачем або датою",
            style="CardSubheading.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 16))

        filters = tk.Frame(card, bg=CARD_BG)
        filters.grid(row=2, column=0, sticky="ew")
        filters.columnconfigure(0, weight=1)

        inputs = tk.Frame(filters, bg=CARD_BG)
        inputs.grid(row=0, column=0, sticky="w")

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
        ttk.Button(buttons, text="Дата", command=self.pick_date, style="Secondary.TButton").grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text="Початок", command=lambda: self.pick_time(True), style="Secondary.TButton").grid(row=0, column=1, padx=4)
        ttk.Button(buttons, text="Кінець", command=lambda: self.pick_time(False), style="Secondary.TButton").grid(row=0, column=2, padx=4)
        ttk.Button(buttons, text="Скинути", command=self.clear_filters, style="Secondary.TButton").grid(row=0, column=3, padx=4)
        ttk.Button(buttons, text="Оновити", command=self.fetch_history, style="Secondary.TButton").grid(row=0, column=4, padx=4)
        if self.role_info["can_clear_history"]:
            ttk.Button(buttons, text="Очистити", command=self.clear_history, style="Secondary.TButton").grid(row=0, column=5, padx=4)

        status = tk.Frame(filters, bg=CARD_BG)
        status.grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 0))

        self.date_display = tk.StringVar(value="Дата: —")
        self.start_display = tk.StringVar(value="Початок: —")
        self.end_display = tk.StringVar(value="Кінець: —")

        ttk.Label(status, textvariable=self.date_display, style="Card.TLabel").grid(row=0, column=0, padx=(0, 24))
        ttk.Label(status, textvariable=self.start_display, style="Card.TLabel").grid(row=0, column=1, padx=(0, 24))
        ttk.Label(status, textvariable=self.end_display, style="Card.TLabel").grid(row=0, column=2)

        tree_container = tk.Frame(card, bg=CARD_BG)
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

        self.attach_tree_copy_menu(self.tree)

        if self.role_info["can_clear_history"]:
            self.tree.bind("<Delete>", self.delete_selected_record)


        self.records: List[Dict[str, Any]] = []
        self.filtered: List[Dict[str, Any]] = []
        self.tree_records: Dict[str, Dict[str, Any]] = {}

        self.fetch_history()

    def _add_filter_entry(self, parent: tk.Widget, label: str, variable: tk.StringVar, column: int) -> None:
        frame = tk.Frame(parent, bg=CARD_BG)
        frame.grid(row=0, column=column, padx=6)
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
        self.tree_records = {}
        for item in filtered:
            dt = parse_api_datetime(item.get("datetime"))
            dt_txt = dt.strftime("%d.%m.%Y %H:%M:%S") if dt else item.get("datetime", "")
            item_id = self.tree.insert(
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
            self.tree_records[item_id] = item

    def delete_selected_record(self, event: Optional[tk.Event] = None) -> None:
        if not self.role_info.get("can_clear_history"):
            return
        item_id = self.tree.focus()
        if not item_id:
            if event is None:
                messagebox.showinfo("Видалення", "Оберіть запис у таблиці")
            return
        record = self.tree_records.get(item_id)
        if not record:
            messagebox.showerror("Видалення", "Не вдалося визначити запис")
            return
        raw_id = record.get("id")
        try:
            record_id = int(float(raw_id))
        except (TypeError, ValueError):
            messagebox.showerror("Видалення", "Для цього запису відсутній ідентифікатор")
            return
        boxid = record.get("boxid") or "—"
        ttn = record.get("ttn") or "—"
        if not messagebox.askyesno(
            "Підтвердження",
            f"Видалити запис #{record_id}?\nBoxID: {boxid} | TTN: {ttn}",
        ):
            return
        token = self.app.state_data.token
        if not token:
            return

        def worker() -> None:
            try:
                response = requests.delete(
                    f"{API_BASE}/delete_tracking/{record_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                if response.status_code == 200:
                    def update() -> None:
                        updated: List[Dict[str, Any]] = []
                        for item in self.records:
                            try:
                                item_id_value = int(float(item.get("id")))
                            except (TypeError, ValueError):
                                updated.append(item)
                                continue
                            if item_id_value != record_id:
                                updated.append(item)
                        self.records = updated
                        self.apply_filters()

                    self.after(0, update)
                else:
                    raise requests.RequestException(f"status {response.status_code}")
            except requests.RequestException as exc:
                error_text = str(exc)
                self.after(
                    0,
                    lambda msg=error_text: messagebox.showerror(
                        "Помилка", f"Не вдалося видалити: {msg}"
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

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

        self.configure(bg=APP_BACKGROUND)
        shell = tk.Frame(self, bg=APP_BACKGROUND, padx=36, pady=36)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = tk.Frame(shell, bg=APP_BACKGROUND)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        header_card = tk.Frame(
            header,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            padx=36,
            pady=24,
        )
        header_card.grid(row=0, column=0, sticky="ew")
        header_card.columnconfigure(0, weight=1)
        header_card.columnconfigure(1, weight=1)

        branding = tk.Frame(header_card, bg=CARD_BG)
        branding.grid(row=0, column=0, sticky="w")
        tk.Label(
            branding,
            text="Аналітика сканувань",
            font=("Segoe UI", 26, "bold"),
            fg=TEXT_PRIMARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            branding,
            text="Переглядайте продуктивність команди та помилки за обраний період",
            font=("Segoe UI", 12),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        user_info = tk.Frame(header_card, bg=CARD_BG)
        user_info.grid(row=0, column=1, sticky="e")
        tk.Label(
            user_info,
            text=app.state_data.user_name,
            font=("Segoe UI", 18, "bold"),
            fg=TEXT_PRIMARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="e")
        tk.Label(
            user_info,
            text=self.role_info["label"],
            font=("Segoe UI", 12, "bold"),
            fg="white",
            bg=self.role_info["color"],
            padx=12,
            pady=4,
        ).grid(row=1, column=0, sticky="e", pady=(8, 0))

        nav = tk.Frame(header_card, bg=CARD_BG)
        nav.grid(row=1, column=0, columnspan=2, sticky="e", pady=(20, 0))
        ttk.Button(nav, text="⬅ Головна", command=self.app.show_scanner, style="Secondary.TButton").grid(row=0, column=0, padx=6)
        ttk.Button(nav, text="Історія", command=self.app.show_history, style="Secondary.TButton").grid(row=0, column=1, padx=6)
        ttk.Button(nav, text="Журнал помилок", command=self.app.show_errors, style="Secondary.TButton").grid(row=0, column=2, padx=6)
        ttk.Button(nav, text="Вийти", command=self.logout, style="Secondary.TButton").grid(row=0, column=3, padx=6)

        content = tk.Frame(shell, bg=APP_BACKGROUND, padx=32, pady=32)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        card = tk.Frame(
            content,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            padx=36,
            pady=32,
        )
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(6, weight=1)

        ttk.Label(card, text="Адміністративна статистика", style="CardHeading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            card,
            text="Виберіть період та аналізуйте навантаження операторів",
            style="CardSubheading.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 16))

        filters = tk.Frame(card, bg=CARD_BG)
        filters.grid(row=2, column=0, sticky="ew")
        filters.columnconfigure(0, weight=1)

        ttk.Label(filters, textvariable=self.period_var, style="CardSubheading.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        buttons = tk.Frame(filters, bg=CARD_BG)
        buttons.grid(row=0, column=1, sticky="e")
        ttk.Button(buttons, text="Дата початку", command=self.pick_start_date, style="Secondary.TButton").grid(
            row=0, column=0, padx=4
        )
        ttk.Button(buttons, text="Час початку", command=self.pick_start_time, style="Secondary.TButton").grid(
            row=0, column=1, padx=4
        )
        ttk.Button(buttons, text="Дата завершення", command=self.pick_end_date, style="Secondary.TButton").grid(
            row=0, column=2, padx=4
        )
        ttk.Button(buttons, text="Час завершення", command=self.pick_end_time, style="Secondary.TButton").grid(
            row=0, column=3, padx=4
        )
        ttk.Button(buttons, text="Скинути", command=self.reset_period, style="Secondary.TButton").grid(
            row=0, column=4, padx=4
        )
        ttk.Button(buttons, text="Оновити дані", command=self.fetch_data, style="Secondary.TButton").grid(
            row=0, column=5, padx=4
        )
        ttk.Button(buttons, text="Зберегти звіт", command=self.export_statistics, style="Primary.TButton").grid(
            row=0, column=6, padx=4
        )

        status = tk.Frame(card, bg=CARD_BG)
        status.grid(row=3, column=0, sticky="w", pady=(12, 0))
        ttk.Label(status, textvariable=self.status_var, style="CardSubheading.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        metrics = tk.Frame(card, bg=CARD_BG)
        metrics.grid(row=4, column=0, sticky="ew", pady=(24, 0))
        for col in range(4):
            metrics.columnconfigure(col, weight=1)

        self._create_metric(metrics, 0, "Сканувань", self.total_scans_var)
        self._create_metric(metrics, 1, "Операторів", self.unique_users_var)
        self._create_metric(metrics, 2, "Помилок", self.total_errors_var)
        self._create_metric(metrics, 3, "Користувачів з помилками", self.error_users_var)

        insights = tk.Frame(card, bg=CARD_BG)
        insights.grid(row=5, column=0, sticky="ew", pady=(28, 0))
        insights.columnconfigure(0, weight=1)
        insights.columnconfigure(1, weight=1)

        self._create_insight(
            insights,
            column=0,
            title="Найактивніший оператор",
            name_var=self.top_operator_var,
            count_var=self.top_operator_count_var,
            suffix="сканувань",
        )
        self._create_insight(
            insights,
            column=1,
            title="Найбільше помилок",
            name_var=self.top_error_operator_var,
            count_var=self.top_error_count_var,
            suffix="помилок",
        )

        tables = tk.Frame(card, bg=CARD_BG)
        tables.grid(row=6, column=0, sticky="nsew", pady=(32, 0))
        tables.columnconfigure(0, weight=1)
        tables.columnconfigure(1, weight=1)
        tables.columnconfigure(2, weight=1)
        tables.rowconfigure(0, weight=1)

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

        self._update_period_label()
        self.fetch_data()

    def _create_metric(self, parent: tk.Frame, column: int, title: str, variable: tk.StringVar) -> None:
        container = tk.Frame(
            parent,
            bg="#e2e8f0",
            padx=24,
            pady=18,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
        )
        container.grid(row=0, column=column, sticky="nsew", padx=8)
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

    def _create_insight(
        self,
        parent: tk.Frame,
        *,
        column: int,
        title: str,
        name_var: tk.StringVar,
        count_var: tk.StringVar,
        suffix: str,
    ) -> None:
        container = tk.Frame(
            parent,
            bg="#f1f5f9",
            padx=15,
            pady=5,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
        )
        container.grid(row=0, column=column, sticky="nsew", padx=(0, 16) if column == 0 else (16, 0))
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
            return dt_value.replace(tzinfo=None)
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

        self.configure(bg=APP_BACKGROUND)
        shell = tk.Frame(self, bg=APP_BACKGROUND, padx=36, pady=36)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = tk.Frame(shell, bg=APP_BACKGROUND)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        header_card = tk.Frame(
            header,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            padx=36,
            pady=24,
        )
        header_card.grid(row=0, column=0, sticky="ew")
        header_card.columnconfigure(0, weight=1)
        header_card.columnconfigure(1, weight=1)

        branding = tk.Frame(header_card, bg=CARD_BG)
        branding.grid(row=0, column=0, sticky="w")
        tk.Label(
            branding,
            text="Журнал помилок",
            font=("Segoe UI", 26, "bold"),
            fg=TEXT_PRIMARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            branding,
            text="Фіксація невідповідностей",
            font=("Segoe UI", 12),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        user_info = tk.Frame(header_card, bg=CARD_BG)
        user_info.grid(row=0, column=1, sticky="e")
        tk.Label(
            user_info,
            text=app.state_data.user_name,
            font=("Segoe UI", 18, "bold"),
            fg=TEXT_PRIMARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="e")
        tk.Label(
            user_info,
            text=self.role_info["label"],
            font=("Segoe UI", 12, "bold"),
            fg="white",
            bg=self.role_info["color"],
            padx=12,
            pady=4,
        ).grid(row=1, column=0, sticky="e", pady=(8, 0))

        nav = tk.Frame(header_card, bg=CARD_BG)
        nav.grid(row=1, column=0, columnspan=2, sticky="e", pady=(20, 0))
        column = 0
        ttk.Button(
            nav,
            text="⬅ Головна",
            command=self.app.show_scanner,
            style="Secondary.TButton",
        ).grid(row=0, column=column, padx=6)
        column += 1
        ttk.Button(
            nav,
            text="Історія сканувань",
            command=self.app.show_history,
            style="Secondary.TButton",
        ).grid(row=0, column=column, padx=6)
        column += 1
        if self.is_admin:
            ttk.Button(
                nav,
                text="Статистика",
                command=self.app.show_statistics,
                style="Secondary.TButton",
            ).grid(row=0, column=column, padx=6)
            column += 1
        ttk.Button(nav, text="Вийти", command=self.logout, style="Secondary.TButton").grid(row=0, column=column, padx=6)

        content = tk.Frame(shell, bg=APP_BACKGROUND, padx=32, pady=32)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        card = tk.Frame(
            content,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=1,
            padx=36,
            pady=32,
        )
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1)

        ttk.Label(card, text="Виявлені помилки", style="CardHeading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            card,
            text="Подвійний клік видаляє запис (для ролей з правами)",
            style="CardSubheading.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 20))

        toolbar = tk.Frame(card, bg=CARD_BG)
        toolbar.grid(row=2, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=1)
        button_bar = tk.Frame(toolbar, bg=CARD_BG)
        button_bar.grid(row=0, column=1, sticky="e")
        ttk.Button(button_bar, text="Оновити", command=self.fetch_errors, style="Secondary.TButton").grid(row=0, column=0, padx=4)
        if self.role_info["can_clear_errors"]:
            ttk.Button(button_bar, text="Очистити всі", command=self.clear_errors, style="Secondary.TButton").grid(row=0, column=1, padx=4)

        tree_container = tk.Frame(card, bg=CARD_BG)
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
        
        self.attach_tree_copy_menu(self.tree)


        if self.role_info["can_clear_errors"]:
            self.tree.bind("<Double-1>", self.delete_selected_error)

        self.records: List[Dict[str, Any]] = []

        self.fetch_errors()

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


def main() -> None:
    app = TrackingApp()
    app.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
