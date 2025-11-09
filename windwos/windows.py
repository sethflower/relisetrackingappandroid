"""Windows desktop adaptation of the Flutter TrackingApp for Windows."""
from __future__ import annotations

import calendar
import csv
import json
import threading
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, date, time as dtime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import requests
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit(
        "The 'requests' package is required. Install it with 'pip install requests'."
    ) from exc

API_BASE = "https://tracking-api-b4jb.onrender.com"
STATE_PATH = Path(__file__).with_name("tracking_app_state.json")
QUEUE_PATH = Path(__file__).with_name("offline_queue.json")

# Design constants for corporate-style UI
PRIMARY_BG = "#0f172a"
SECONDARY_BG = "#111c3a"
CARD_BG = "#ffffff"
ACCENT_COLOR = "#1d4ed8"
ACCENT_HOVER = "#1e40af"
TEXT_PRIMARY = "#0f172a"
TEXT_SECONDARY = "#475569"
NEUTRAL_BORDER = "#cbd5f5"

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


@dataclass
class AppState:
    token: Optional[str] = None
    access_level: int = 2
    last_password: str = ""
    user_name: str = "operator"

    @classmethod
    def load(cls) -> "AppState":
        if STATE_PATH.exists():
            try:
                data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                return cls(**data)
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


def get_role_info(access_level: int, password: str) -> Dict[str, Any]:
    if access_level == 1 or password == "301993":
        return {"label": "🔑 Адмін", "color": "#e53935", "can_clear_history": True, "can_clear_errors": True}
    if password == "123123123":
        return {"label": "🧰 Очищення помилок", "color": "#fb8c00", "can_clear_history": False, "can_clear_errors": True}
    if access_level == 0:
        return {"label": "🧰 Оператор", "color": "#1e88e5", "can_clear_history": False, "can_clear_errors": False}
    return {"label": "👁 Перегляд", "color": "#757575", "can_clear_history": False, "can_clear_errors": False}


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
        font=("Segoe UI", 120, "bold"),
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
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

    def perform_logout(self) -> None:
        if not messagebox.askyesno("Підтвердження", "Вийти з акаунту?"):
            return
        self.app.state_data = AppState()
        self.app.state_data.save()
        self.app.show_login()


class TrackingApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("TrackingApp Windows Edition")
        self.geometry("1280x800")
        self.minsize(1200, 720)
        self.configure(bg=PRIMARY_BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._maximize()

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

    def _maximize(self) -> None:
        """Occupy full screen while remaining resizable."""

        try:
            self.state("zoomed")
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)
            except tk.TclError:
                self.attributes("-fullscreen", True)

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
        role = get_role_info(self.state_data.access_level, self.state_data.last_password)
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
        self.password_var = tk.StringVar()
        self.error_var = tk.StringVar()
        self.loading = False

        wrapper = tk.Frame(self, bg=PRIMARY_BG, padx=120, pady=120)
        wrapper.grid(row=0, column=0, sticky="nsew")
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(0, weight=1)

        card = tk.Frame(
            wrapper,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=2,
            bd=0,
        )
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)

        header = tk.Frame(card, bg=ACCENT_COLOR, pady=20, padx=40)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="TrackingApp",
            font=("Segoe UI", 36, "bold"),
            fg="white",
            bg=ACCENT_COLOR,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Корпоративна панель управління",
            font=("Segoe UI", 14),
            fg="#dbeafe",
            bg=ACCENT_COLOR,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        content = tk.Frame(card, bg=CARD_BG, padx=80, pady=60)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)

        ttk.Label(
            content,
            text="Ласкаво просимо!",
            style="CardHeading.TLabel",
            anchor="center",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            content,
            text="Увійдіть, щоб продовжити роботу з системою",
            style="CardSubheading.TLabel",
            anchor="center",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 30))

        input_block = tk.Frame(content, bg=CARD_BG)
        input_block.grid(row=2, column=0, sticky="ew")
        input_block.columnconfigure(0, weight=1)
        tk.Label(
            input_block,
            text="Пароль доступу",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).grid(row=0, column=0, sticky="w")
        entry = create_large_entry(
            input_block,
            textvariable=self.password_var,
            show="*",
        )
        entry.grid(row=1, column=0, sticky="ew", pady=(8, 0), ipady=40)
        entry.bind("<Return>", lambda _: self.login())

        self.error_label = tk.Label(
            content,
            textvariable=self.error_var,
            font=("Segoe UI", 12),
            fg="#d32f2f",
            bg=CARD_BG,
        )
        self.error_label.grid(row=3, column=0, sticky="ew", pady=(16, 0))

        self.button = ttk.Button(
            content,
            text="Увійти в систему",
            command=self.login,
            style="Primary.TButton",
        )
        self.button.grid(row=4, column=0, sticky="ew", pady=(32, 12))

        footer = tk.Frame(card, bg=CARD_BG, pady=20)
        footer.grid(row=2, column=0, sticky="ew")
        tk.Label(
            footer,
            text="TrackingApp by DimonVR",
            font=("Segoe UI", 12),
            fg=TEXT_SECONDARY,
            bg=CARD_BG,
        ).pack()

        entry.focus_set()

    def set_loading(self, value: bool) -> None:
        self.loading = value
        if value:
            self.button.configure(text="Зачекайте...", state="disabled")
        else:
            self.button.configure(text="Увійти в систему", state="normal")

    def login(self) -> None:
        if self.loading:
            return
        password = self.password_var.get().strip()
        if not password:
            self.error_var.set("Введіть пароль")
            return

        def worker() -> None:
            try:
                response = requests.post(
                    f"{API_BASE}/login",
                    params={"password": password},
                    headers={"Accept": "application/json"},
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    self.app.state_data.token = data.get("token")
                    self.app.state_data.access_level = data.get("access_level", 2)
                    self.app.state_data.last_password = password
                    self.app.state_data.save()
                    self.after(0, self.app.show_username)
                else:
                    try:
                        message = response.json().get("message", "Невірний пароль")
                    except Exception:
                        message = "Невірний пароль"
                    self.after(0, lambda: self.error_var.set(message))
            except requests.RequestException:
                self.after(0, lambda: self.error_var.set("Помилка підключення до сервера"))
            finally:
                self.after(0, lambda: self.set_loading(False))

        self.error_var.set("")
        self.set_loading(True)
        threading.Thread(target=worker, daemon=True).start()


class UserNameFrame(BaseFrame):
    def __init__(self, app: TrackingApp) -> None:
        super().__init__(app)
        self.name_var = tk.StringVar(value=app.state_data.user_name)

        wrapper = tk.Frame(self, bg=PRIMARY_BG, padx=120, pady=120)
        wrapper.grid(row=0, column=0, sticky="nsew")
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(0, weight=1)

        card = tk.Frame(
            wrapper,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=2,
            bd=0,
        )
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)

        header = tk.Frame(card, bg=ACCENT_COLOR, pady=18, padx=40)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="Профіль оператора",
            font=("Segoe UI", 28, "bold"),
            fg="white",
            bg=ACCENT_COLOR,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Вкажіть, хто працює із системою",
            font=("Segoe UI", 13),
            fg="#dbeafe",
            bg=ACCENT_COLOR,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        content = tk.Frame(card, bg=CARD_BG, padx=80, pady=60)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)

        ttk.Label(
            content,
            text="Введіть ім’я оператора",
            style="CardHeading.TLabel",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            content,
            text="Це ім’я буде відображатися у звітах та історії",
            style="CardSubheading.TLabel",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 24))

        input_block = tk.Frame(content, bg=CARD_BG)
        input_block.grid(row=2, column=0, sticky="ew")
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
        entry.grid(row=1, column=0, sticky="ew", pady=(8, 0), ipady=40)
        entry.bind("<Return>", lambda _: self.save())

        ttk.Button(
            content,
            text="Продовжити",
            command=self.save,
            style="Primary.TButton",
        ).grid(row=3, column=0, sticky="ew", pady=(32, 0))

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
            app.state_data.access_level, app.state_data.last_password
        )
        self.is_admin = self.role_info.get("can_clear_history") and self.role_info.get(
            "can_clear_errors"
        )

        shell = tk.Frame(self, bg=PRIMARY_BG, padx=24, pady=24)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)

        header = tk.Frame(shell, bg=SECONDARY_BG, padx=36, pady=24)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=1)
        header.columnconfigure(2, weight=1)

        tk.Label(
            header,
            text="TrackingApp",
            font=("Segoe UI", 30, "bold"),
            fg="white",
            bg=SECONDARY_BG,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Корпоративна система відстеження",
            font=("Segoe UI", 12),
            fg="#cbd5f5",
            bg=SECONDARY_BG,
        ).grid(row=1, column=0, sticky="w")

        connection = tk.Frame(header, bg=SECONDARY_BG)
        connection.grid(row=0, column=1, rowspan=2, sticky="nsew")
        connection.columnconfigure(0, weight=1)
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

        user_info = tk.Frame(header, bg=SECONDARY_BG)
        user_info.grid(row=0, column=2, rowspan=2, sticky="e")
        tk.Label(
            user_info,
            text=app.state_data.user_name,
            font=("Segoe UI", 18, "bold"),
            fg="white",
            bg=SECONDARY_BG,
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

        toolbar = tk.Frame(shell, bg=PRIMARY_BG)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(24, 0))
        toolbar.columnconfigure(0, weight=1)
        nav = tk.Frame(toolbar, bg=PRIMARY_BG)
        nav.grid(row=0, column=0, sticky="e")
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

        content = tk.Frame(shell, bg=PRIMARY_BG, padx=12, pady=12)
        content.grid(row=2, column=0, sticky="nsew", pady=(24, 0))
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        card = tk.Frame(
            content,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=2,
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
            title="Товарно-транспортна накладна",
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
        ttk.Button(
            actions,
            text="Скинути поля",
            style="Secondary.TButton",
            command=self.reset_fields,
        ).grid(row=0, column=1, sticky="ew")

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
        self.box_entry.focus_set()
        self.check_connectivity()
        OfflineQueue.sync_pending(self.app.state_data.token or "")

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
        entry.grid(row=1, column=0, sticky="ew", pady=(8, 0), ipady=40)
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
        self.role_info = get_role_info(app.state_data.access_level, app.state_data.last_password)
        self.is_admin = self.role_info.get("can_clear_history") and self.role_info.get(
            "can_clear_errors"
        )

        shell = tk.Frame(self, bg=PRIMARY_BG, padx=24, pady=24)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = tk.Frame(shell, bg=SECONDARY_BG, padx=36, pady=24)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=1)
        header.columnconfigure(2, weight=1)

        branding = tk.Frame(header, bg=SECONDARY_BG)
        branding.grid(row=0, column=0, rowspan=2, sticky="w")
        tk.Label(
            branding,
            text="Історія операцій",
            font=("Segoe UI", 26, "bold"),
            fg="white",
            bg=SECONDARY_BG,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            branding,
            text="Переглядайте та фільтруйте всі записані відправлення",
            font=("Segoe UI", 12),
            fg="#cbd5f5",
            bg=SECONDARY_BG,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        user_info = tk.Frame(header, bg=SECONDARY_BG)
        user_info.grid(row=0, column=1, rowspan=2, sticky="e")
        tk.Label(
            user_info,
            text=app.state_data.user_name,
            font=("Segoe UI", 18, "bold"),
            fg="white",
            bg=SECONDARY_BG,
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

        nav = tk.Frame(header, bg=SECONDARY_BG)
        nav.grid(row=0, column=2, rowspan=2, sticky="e")
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

        content = tk.Frame(shell, bg=PRIMARY_BG, padx=32, pady=24)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        card = tk.Frame(
            content,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=2,
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

        self.records: List[Dict[str, Any]] = []
        self.filtered: List[Dict[str, Any]] = []

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


class StatisticsFrame(BaseFrame):
    def __init__(self, app: TrackingApp) -> None:
        super().__init__(app)
        self.role_info = get_role_info(app.state_data.access_level, app.state_data.last_password)
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

        shell = tk.Frame(self, bg=PRIMARY_BG, padx=24, pady=24)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = tk.Frame(shell, bg=SECONDARY_BG, padx=36, pady=24)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=1)
        header.columnconfigure(2, weight=1)

        branding = tk.Frame(header, bg=SECONDARY_BG)
        branding.grid(row=0, column=0, rowspan=2, sticky="w")
        tk.Label(
            branding,
            text="Аналітика сканувань",
            font=("Segoe UI", 26, "bold"),
            fg="white",
            bg=SECONDARY_BG,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            branding,
            text="Переглядайте продуктивність команди та помилки за обраний період",
            font=("Segoe UI", 12),
            fg="#cbd5f5",
            bg=SECONDARY_BG,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        user_info = tk.Frame(header, bg=SECONDARY_BG)
        user_info.grid(row=0, column=1, rowspan=2, sticky="e")
        tk.Label(
            user_info,
            text=app.state_data.user_name,
            font=("Segoe UI", 18, "bold"),
            fg="white",
            bg=SECONDARY_BG,
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

        nav = tk.Frame(header, bg=SECONDARY_BG)
        nav.grid(row=0, column=2, rowspan=2, sticky="e")
        ttk.Button(nav, text="⬅ Головна", command=self.app.show_scanner, style="Secondary.TButton").grid(row=0, column=0, padx=6)
        ttk.Button(nav, text="Історія", command=self.app.show_history, style="Secondary.TButton").grid(row=0, column=1, padx=6)
        ttk.Button(nav, text="Журнал помилок", command=self.app.show_errors, style="Secondary.TButton").grid(row=0, column=2, padx=6)
        ttk.Button(nav, text="Вийти", command=self.logout, style="Secondary.TButton").grid(row=0, column=3, padx=6)

        content = tk.Frame(shell, bg=PRIMARY_BG, padx=32, pady=24)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        card = tk.Frame(
            content,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=2,
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
        self.scan_tree = ttk.Treeview(scans_section, columns=scan_columns, show="headings", height=10)
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
            font=("Segoe UI", 36, "bold"),
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
            padx=24,
            pady=16,
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
            font=("Segoe UI", 20, "bold"),
            fg=ACCENT_COLOR,
            bg="#f1f5f9",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        tk.Label(
            container,
            textvariable=count_var,
            font=("Segoe UI", 14, "bold"),
            fg=TEXT_SECONDARY,
            bg="#f1f5f9",
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        tk.Label(
            container,
            text=suffix,
            font=("Segoe UI", 12),
            fg=TEXT_SECONDARY,
            bg="#f1f5f9",
        ).grid(row=3, column=0, sticky="w")

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
        self.role_info = get_role_info(app.state_data.access_level, app.state_data.last_password)
        self.is_admin = self.role_info.get("can_clear_history") and self.role_info.get(
            "can_clear_errors"
        )

        shell = tk.Frame(self, bg=PRIMARY_BG, padx=24, pady=24)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = tk.Frame(shell, bg=SECONDARY_BG, padx=36, pady=24)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=1)
        header.columnconfigure(2, weight=1)

        branding = tk.Frame(header, bg=SECONDARY_BG)
        branding.grid(row=0, column=0, rowspan=2, sticky="w")
        tk.Label(
            branding,
            text="Журнал помилок",
            font=("Segoe UI", 26, "bold"),
            fg="white",
            bg=SECONDARY_BG,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            branding,
            text="Аналізуйте проблеми синхронізації та очищайте журнал",
            font=("Segoe UI", 12),
            fg="#cbd5f5",
            bg=SECONDARY_BG,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        user_info = tk.Frame(header, bg=SECONDARY_BG)
        user_info.grid(row=0, column=1, rowspan=2, sticky="e")
        tk.Label(
            user_info,
            text=app.state_data.user_name,
            font=("Segoe UI", 18, "bold"),
            fg="white",
            bg=SECONDARY_BG,
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

        nav = tk.Frame(header, bg=SECONDARY_BG)
        nav.grid(row=0, column=2, rowspan=2, sticky="e")
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

        content = tk.Frame(shell, bg=PRIMARY_BG, padx=32, pady=24)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        card = tk.Frame(
            content,
            bg=CARD_BG,
            highlightbackground=NEUTRAL_BORDER,
            highlightthickness=2,
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
