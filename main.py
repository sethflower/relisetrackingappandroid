#!/usr/bin/env python3
"""Windows desktop client for the Relise tracking backend.

This Tkinter application mirrors the Android Flutter client: it works with the
same REST API, persists the same user/session metadata, keeps an offline queue
for failed scans, and exposes history, errors, statistics, and administrator
management tools.
"""

from __future__ import annotations

import datetime as dt
import json
import queue
import sqlite3
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

APP_TITLE = "Relise Tracking Desktop"
API_BASE_URL = "https://tracking-api-b4jb.onrender.com"
CONFIG_PATH = Path("tracking_desktop_profile.json")
QUEUE_DB_PATH = Path("tracking_offline_queue.db")
REQUEST_TIMEOUT = 12

PALETTE = {
    "canvas": "#edf1f7",
    "surface": "#ffffff",
    "surface_alt": "#f3f6fb",
    "surface_subtle": "#f8fafc",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "accent_active": "#1e40af",
    "accent_soft": "#dbeafe",
    "nav_bg": "#111827",
    "nav_hover": "#1f2937",
    "nav_active": "#2563eb",
    "hero_bg": "#0f172a",
    "hero_text": "#e2e8f0",
    "text": "#0f172a",
    "muted": "#64748b",
    "muted_alt": "#94a3b8",
    "success": "#166534",
    "warning": "#b45309",
    "danger": "#b91c1c",
    "divider": "#d8e1f1",
    "chip_info_bg": "#e8edfb",
    "chip_info_fg": "#1e293b",
    "chip_success_bg": "#d1fae5",
    "chip_success_fg": "#166534",
    "chip_warning_bg": "#fef3c7",
    "chip_warning_fg": "#92400e",
    "chip_danger_bg": "#fee2e2",
    "chip_danger_fg": "#b91c1c",
    "chip_muted_bg": "#e2e8f0",
    "chip_muted_fg": "#475569",
}


@dataclass
class UserProfile:
    token: str
    surname: str
    role: str
    access_level: int

    def to_json(self) -> Dict[str, Any]:
        return {
            "token": self.token,
            "surname": self.surname,
            "role": self.role,
            "access_level": self.access_level,
        }

    @classmethod
    def from_json(cls, payload: Dict[str, Any]) -> "UserProfile":
        return cls(
            token=str(payload.get("token", "")),
            surname=str(payload.get("surname", "")),
            role=str(payload.get("role", "viewer")),
            access_level=int(payload.get("access_level", 2)),
        )


class AppState:
    """Stores the current session profile and persists it between runs."""

    def __init__(self) -> None:
        self._profile: Optional[UserProfile] = None
        self.load()

    def load(self) -> None:
        if CONFIG_PATH.exists():
            try:
                payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                self._profile = UserProfile.from_json(payload)
            except Exception:
                CONFIG_PATH.unlink(missing_ok=True)
                self._profile = None
        else:
            self._profile = None

    def save(self) -> None:
        if self._profile is None:
            CONFIG_PATH.unlink(missing_ok=True)
            return
        CONFIG_PATH.write_text(
            json.dumps(self._profile.to_json(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def profile(self) -> Optional[UserProfile]:
        return self._profile

    def set_profile(self, profile: Optional[UserProfile]) -> None:
        self._profile = profile
        self.save()

    @property
    def token(self) -> Optional[str]:
        return self._profile.token if self._profile else None

    @property
    def surname(self) -> Optional[str]:
        return self._profile.surname if self._profile else None

    @property
    def role(self) -> Optional[str]:
        return self._profile.role if self._profile else None

    @property
    def access_level(self) -> Optional[int]:
        return self._profile.access_level if self._profile else None


class ApiError(RuntimeError):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    """Thin wrapper around the REST API used by the Android client."""

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "ReliseTrackingDesktop/1.0",
            }
        )

    def _url(self, path: str) -> str:
        return f"{API_BASE_URL}{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: Optional[str] = None,
        timeout: int = REQUEST_TIMEOUT,
        **kwargs: Any,
    ) -> requests.Response:
        headers = kwargs.pop("headers", {}).copy()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = self._session.request(
                method,
                self._url(path),
                headers=headers,
                timeout=timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise ApiError(str(exc), -1) from exc

        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                raise ApiError(
                    f"Помилка сервера ({response.status_code})",
                    response.status_code,
                )
            message = payload.get("detail") or payload.get("message")
            if not message:
                message = f"Помилка сервера ({response.status_code})"
            raise ApiError(message, response.status_code)
        return response

    def login(self, surname: str, password: str) -> UserProfile:
        response = self._request(
            "POST",
            "/login",
            json={"surname": surname, "password": password},
        )
        payload = response.json()
        token = payload.get("token", "")
        role = payload.get("role", "viewer")
        access_level = int(payload.get("access_level", 2))
        resolved_name = payload.get("surname", surname)
        if not token:
            raise ApiError("Сервер не повернув токен", 500)
        return UserProfile(token=token, surname=resolved_name, role=role, access_level=access_level)

    def register(self, surname: str, password: str) -> None:
        self._request("POST", "/register", json={"surname": surname, "password": password})

    def admin_login(self, password: str) -> str:
        response = self._request("POST", "/admin_login", json={"password": password})
        token = response.json().get("token")
        if not token:
            raise ApiError("Сервер не повернув токен адміністратора", 500)
        return token

    def add_record(self, token: str, user_name: str, boxid: str, ttn: str) -> Dict[str, Any]:
        response = self._request(
            "POST",
            "/add_record",
            token=token,
            json={"user_name": user_name, "boxid": boxid, "ttn": ttn},
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def get_history(self, token: str) -> List[Dict[str, Any]]:
        response = self._request("GET", "/get_history", token=token)
        payload = response.json()
        return list(payload) if isinstance(payload, list) else []

    def get_errors(self, token: str) -> List[Dict[str, Any]]:
        response = self._request("GET", "/get_errors", token=token)
        payload = response.json()
        return list(payload) if isinstance(payload, list) else []

    def clear_errors(self, token: str) -> None:
        self._request("DELETE", "/clear_errors", token=token)

    def delete_error(self, token: str, error_id: int) -> None:
        self._request("DELETE", f"/delete_error/{error_id}", token=token)

    def fetch_pending_users(self, token: str) -> List[Dict[str, Any]]:
        response = self._request("GET", "/admin/registration_requests", token=token)
        payload = response.json()
        return list(payload) if isinstance(payload, list) else []

    def approve_user(self, token: str, request_id: int, role: str) -> None:
        self._request(
            "POST",
            f"/admin/registration_requests/{request_id}/approve",
            token=token,
            json={"role": role},
        )

    def reject_user(self, token: str, request_id: int) -> None:
        self._request(
            "POST",
            f"/admin/registration_requests/{request_id}/reject",
            token=token,
        )

    def fetch_users(self, token: str) -> List[Dict[str, Any]]:
        response = self._request("GET", "/admin/users", token=token)
        payload = response.json()
        return list(payload) if isinstance(payload, list) else []

    def update_user(
        self,
        token: str,
        user_id: int,
        *,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if role is not None:
            body["role"] = role
        if is_active is not None:
            body["is_active"] = is_active
        response = self._request(
            "PATCH",
            f"/admin/users/{user_id}",
            token=token,
            json=body,
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else body

    def delete_user(self, token: str, user_id: int) -> None:
        self._request("DELETE", f"/admin/users/{user_id}", token=token)

    def fetch_role_passwords(self, token: str) -> Dict[str, str]:
        response = self._request("GET", "/admin/role-passwords", token=token)
        payload = response.json()
        if isinstance(payload, dict):
            return {str(k): str(v or "") for k, v in payload.items()}
        return {}

    def update_role_password(self, token: str, role: str, password: str) -> None:
        self._request(
            "POST",
            f"/admin/role-passwords/{role}",
            token=token,
            json={"password": password},
        )


class OfflineQueue:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_name TEXT NOT NULL,
                    boxid TEXT NOT NULL,
                    ttn TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def add(self, user_name: str, boxid: str, ttn: str) -> None:
        timestamp = dt.datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO records (user_name, boxid, ttn, created_at) VALUES (?, ?, ?, ?)",
                (user_name, boxid, ttn, timestamp),
            )
            conn.commit()

    def pending(self) -> List[Dict[str, Any]]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "SELECT id, user_name, boxid, ttn, created_at FROM records ORDER BY id"
            )
            return [
                {
                    "id": row[0],
                    "user_name": row[1],
                    "boxid": row[2],
                    "ttn": row[3],
                    "created_at": row[4],
                }
                for row in cursor.fetchall()
            ]

    def delete(self, record_id: int) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
            conn.commit()

    def clear(self) -> None:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM records")
            conn.commit()


class AsyncRunner:
    """Utility to run blocking operations without freezing the UI."""

    def __init__(self, tk_root: tk.Tk) -> None:
        self._root = tk_root
        self._result_queue: "queue.Queue[Tuple[Callable[[Any], None], Any]]" = queue.Queue()
        self._root.after(100, self._poll_results)

    def run(self, func: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        def worker() -> None:
            try:
                result = func()
            except Exception as exc:  # propagate exceptions as result objects
                result = exc
            self._result_queue.put((callback, result))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_results(self) -> None:
        try:
            while True:
                callback, result = self._result_queue.get_nowait()
                callback(result)
        except queue.Empty:
            pass
        finally:
            self._root.after(100, self._poll_results)


class Screen(ttk.Frame):
    def __init__(self, master: tk.Widget, app: "TrackingDesktopApp") -> None:
        super().__init__(master, style="Screen.TFrame")
        self.app = app

        # ensure consistent internal spacing for each dashboard screen
        if isinstance(self, LoginScreen):  # pragma: no cover - handled explicitly
            return
        self.configure(padding=(32, 24))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

    def on_show(self) -> None:  # pragma: no cover - hook for subclasses
        pass


class AccentButton(ttk.Button):
    def __init__(self, master: tk.Widget, **kwargs: Any) -> None:
        super().__init__(master, style="Accent.TButton", **kwargs)


class NavButton(ttk.Button):
    def __init__(self, master: tk.Widget, **kwargs: Any) -> None:
        super().__init__(master, style="Nav.TButton", **kwargs)


class LoginScreen(Screen):
    def __init__(self, master: tk.Widget, app: "TrackingDesktopApp") -> None:
        super().__init__(master, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        wrapper = ttk.Frame(self, padding=64, style="Screen.TFrame")
        wrapper.grid(row=0, column=0, sticky="nsew")
        wrapper.columnconfigure(0, weight=1)
        wrapper.columnconfigure(1, weight=1)
        wrapper.rowconfigure(0, weight=1)

        hero = ttk.Frame(wrapper, padding=(36, 64), style="Hero.TFrame")
        hero.grid(row=0, column=0, sticky="nsew", padx=(0, 48))
        hero.columnconfigure(0, weight=1)
        hero.rowconfigure(4, weight=1)
        ttk.Label(hero, text="RELlSE", style="HeroBrand.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            hero,
            text="Корпоративна панель моніторингу відправлень",
            style="HeroSubtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(12, 32))

        for idx, text in enumerate(
            (
                "Єдина база сканувань у реальному часі",
                "Офлайн резерв з автоматичною синхронізацією",
                "Контроль команд, помилок і статистики",
            )
        ):
            ttk.Label(hero, text=f"• {text}", style="HeroBullet.TLabel").grid(
                row=2 + idx, column=0, sticky="w", pady=6
            )

        ttk.Label(
            hero,
            text="Windows-додаток для складу та офісу",
            style="HeroBadge.TLabel",
        ).grid(row=5, column=0, sticky="sw", pady=(48, 0))

        card = ttk.Frame(wrapper, padding=40, style="Card.TFrame")
        card.grid(row=0, column=1, sticky="nsew")
        card.columnconfigure(0, weight=1)

        ttk.Label(card, text="Вхід до системи", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            card,
            text="Використовуйте корпоративний обліковий запис",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 24))

        self._tabs = ttk.Notebook(card, style="Relise.TNotebook")
        self._tabs.grid(row=2, column=0, sticky="nsew")
        card.rowconfigure(2, weight=1)

        self._login_tab = ttk.Frame(self._tabs, padding=16, style="Surface.TFrame")
        self._register_tab = ttk.Frame(self._tabs, padding=16, style="Surface.TFrame")
        self._tabs.add(self._login_tab, text="Вхід")
        self._tabs.add(self._register_tab, text="Реєстрація")

        self._build_login_tab()
        self._build_register_tab()

        AccentButton(card, text="Панель адміністратора", command=self._open_admin_panel).grid(
            row=3, column=0, sticky="ew", pady=(24, 0)
        )
        ttk.Label(
            card,
            text="Дані синхронізовані з мобільним застосунком",
            style="MutedSmall.TLabel",
        ).grid(row=4, column=0, sticky="w", pady=(16, 0))

    def _build_login_tab(self) -> None:
        frame = self._login_tab
        frame.columnconfigure(0, weight=1)
        self._login_surname = tk.StringVar()
        self._login_password = tk.StringVar()
        self._login_status = ttk.Label(frame, foreground=PALETTE["danger"], style="MutedSmall.TLabel")

        ttk.Label(frame, text="Прізвище", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        surname_entry = ttk.Entry(frame, textvariable=self._login_surname)
        surname_entry.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        surname_entry.focus_set()

        ttk.Label(frame, text="Пароль", font=("Segoe UI", 11, "bold")).grid(
            row=2, column=0, sticky="w"
        )
        password_entry = ttk.Entry(frame, show="*", textvariable=self._login_password)
        password_entry.grid(row=3, column=0, sticky="ew", pady=(4, 12))
        password_entry.bind("<Return>", lambda _: self._handle_login())

        self._login_status.grid(row=4, column=0, sticky="w")

        AccentButton(frame, text="Увійти", command=self._handle_login).grid(
            row=5, column=0, sticky="ew", pady=(18, 0)
        )

    def _handle_login(self) -> None:
        surname = self._login_surname.get().strip()
        password = self._login_password.get().strip()
        if not surname or not password:
            self._login_status.configure(text="Введіть прізвище та пароль")
            return
        self._login_status.configure(text="Виконуємо вхід...")

        def task() -> Any:
            try:
                return self.app.api.login(surname, password)
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                self._login_status.configure(text=str(result))
                return
            assert isinstance(result, UserProfile)
            self._login_status.configure(
                text="Успішно! Завантаження даних...",
                foreground=PALETTE["success"],
            )
            self.app.on_login_success(result)

        self.app.run_async(task, done)

    def _build_register_tab(self) -> None:
        frame = self._register_tab
        frame.columnconfigure(0, weight=1)
        self._reg_surname = tk.StringVar()
        self._reg_password = tk.StringVar()
        self._reg_confirm = tk.StringVar()
        self._reg_status = ttk.Label(frame, foreground=PALETTE["danger"], style="MutedSmall.TLabel")

        ttk.Label(frame, text="Прізвище", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Entry(frame, textvariable=self._reg_surname).grid(
            row=1, column=0, sticky="ew", pady=(4, 12)
        )

        ttk.Label(frame, text="Пароль", font=("Segoe UI", 11, "bold")).grid(
            row=2, column=0, sticky="w"
        )
        ttk.Entry(frame, show="*", textvariable=self._reg_password).grid(
            row=3, column=0, sticky="ew", pady=(4, 12)
        )

        ttk.Label(frame, text="Підтвердження пароля", font=("Segoe UI", 11, "bold")).grid(
            row=4, column=0, sticky="w"
        )
        confirm_entry = ttk.Entry(frame, show="*", textvariable=self._reg_confirm)
        confirm_entry.grid(row=5, column=0, sticky="ew", pady=(4, 12))
        confirm_entry.bind("<Return>", lambda _: self._handle_registration())

        self._reg_status.grid(row=6, column=0, sticky="w")

        AccentButton(frame, text="Відправити заявку", command=self._handle_registration).grid(
            row=7, column=0, sticky="ew", pady=(18, 0)
        )

    def _handle_registration(self) -> None:
        surname = self._reg_surname.get().strip()
        password = self._reg_password.get().strip()
        confirm = self._reg_confirm.get().strip()
        if not surname or not password or not confirm:
            self._reg_status.configure(text="Заповніть усі поля")
            return
        if password != confirm:
            self._reg_status.configure(text="Паролі не збігаються")
            return
        if len(password) < 6:
            self._reg_status.configure(text="Пароль має містити щонайменше 6 символів")
            return

        self._reg_status.configure(text="Надсилаємо заявку...")

        def task() -> Any:
            try:
                self.app.api.register(surname, password)
                return True
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                self._reg_status.configure(text=str(result))
                return
            self._reg_status.configure(
                text="✅ Заявку відправлено. Дочекайтесь підтвердження адміністратора",
                foreground="#2a7d2a",
            )
            self._reg_surname.set("")
            self._reg_password.set("")
            self._reg_confirm.set("")

        self.app.run_async(task, done)

    def _open_admin_panel(self) -> None:
        password = simpledialog.askstring(
            "Панель адміністратора",
            "Введіть пароль адміністратора",
            show="*",
            parent=self,
        )
        if not password:
            return

        def task() -> Any:
            try:
                return self.app.api.admin_login(password.strip())
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                messagebox.showerror("Помилка", str(result), parent=self)
                return
            AdminPanel(self.app, result)

        self.app.run_async(task, done)


class ScannerScreen(Screen):
    def __init__(self, master: tk.Widget, app: "TrackingDesktopApp") -> None:
        super().__init__(master, app)
        self._box = tk.StringVar()
        self._ttn = tk.StringVar()
        self._status = tk.StringVar(value="Готово до сканування")
        self._queue_status = tk.StringVar(value="Офлайн записів: 0")
        self._busy = False

        card = ttk.Frame(self, style="Card.TFrame", padding=(48, 40))
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)

        header = ttk.Frame(card, style="Card.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 28))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Сканування", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Великі поля для BoxID та TTN — зручно бачити результат навіть здалеку",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        fields = ttk.Frame(card, style="CardSection.TFrame", padding=(28, 28))
        fields.grid(row=1, column=0, sticky="nsew")
        fields.columnconfigure(0, weight=1)

        ttk.Label(fields, text="BoxID", style="InputLabel.TLabel").grid(row=0, column=0, sticky="w")
        self._box_entry = ttk.Entry(
            fields,
            textvariable=self._box,
            font=("Segoe UI", 26, "bold"),
            justify="center",
        )
        self._box_entry.grid(row=1, column=0, sticky="ew", pady=(8, 24))
        self._box_entry.focus_set()
        self._box_entry.bind("<Return>", lambda _: self._focus_ttn())

        ttk.Label(fields, text="TTN", style="InputLabel.TLabel").grid(row=2, column=0, sticky="w")
        self._ttn_entry = ttk.Entry(
            fields,
            textvariable=self._ttn,
            font=("Segoe UI", 26, "bold"),
            justify="center",
        )
        self._ttn_entry.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self._ttn_entry.bind("<Return>", lambda _: self._submit())

        ttk.Label(
            fields,
            text="Скануйте послідовно: спочатку BoxID, потім TTN. Автоматичний перехід здійснюється після Enter.",
            style="MutedSmall.TLabel",
        ).grid(row=4, column=0, sticky="w", pady=(18, 0))

        controls = ttk.Frame(card, style="Card.TFrame")
        controls.grid(row=2, column=0, sticky="ew", pady=(24, 0))
        controls.columnconfigure(2, weight=1)
        AccentButton(controls, text="Зберегти", command=self._submit).grid(row=0, column=0, sticky="ew")
        ttk.Button(controls, text="Очистити", command=self._clear).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(12, 12),
        )
        ttk.Button(controls, text="Синхронізувати офлайн", command=self._sync_queue).grid(
            row=0,
            column=2,
            sticky="e",
        )

        status_row = ttk.Frame(card, style="Card.TFrame")
        status_row.grid(row=3, column=0, sticky="ew", pady=(28, 0))
        status_row.columnconfigure(0, weight=1)
        self._status_label = ttk.Label(status_row, textvariable=self._status, style="StatusInfo.TLabel")
        self._status_label.grid(row=0, column=0, sticky="w")
        self._queue_badge = ttk.Label(status_row, textvariable=self._queue_status, style="StatusBadge.TLabel")
        self._queue_badge.grid(row=0, column=1, sticky="e")

        self._update_status("Готово до сканування", tone="info")
        self.update_queue_status()

    def on_show(self) -> None:
        self.update_queue_status()

    def _focus_ttn(self) -> None:
        self._ttn_entry.focus_set()
        self._ttn_entry.select_range(0, tk.END)

    def _clear(self) -> None:
        self._box.set("")
        self._ttn.set("")
        self._update_status("Готово до сканування", tone="info")
        self._box_entry.focus_set()

    def _submit(self) -> None:
        if self._busy:
            return
        profile = self.app.state.profile
        if not profile:
            messagebox.showerror("Помилка", "Спочатку виконайте вхід", parent=self)
            return
        boxid = self._box.get().strip()
        ttn = self._ttn.get().strip()
        if not boxid or not ttn:
            self._update_status("Вкажіть обидва значення", tone="warning")
            return

        self._busy = True
        self._update_status("Надсилаємо...", tone="info")

        def task() -> Any:
            try:
                return self.app.api.add_record(profile.token, profile.surname, boxid, ttn)
            except ApiError as exc:
                return exc
            except Exception as exc:
                return ApiError(str(exc), -1)

        def done(result: Any) -> None:
            self._busy = False
            if isinstance(result, ApiError) and result.status_code == -1:
                self.app.offline_queue.add(profile.surname, boxid, ttn)
                self.update_queue_status()
                self._update_status("📦 Офлайн: запис збережено локально", tone="warning")
            elif isinstance(result, ApiError):
                self._update_status(f"Помилка: {result}", tone="danger")
            else:
                note = result.get("note") if isinstance(result, dict) else None
                if note:
                    self._update_status(f"⚠️ Дублікат: {note}", tone="warning")
                else:
                    self._update_status("✅ Успішно збережено", tone="success")
            self._box.set("")
            self._ttn.set("")
            self._focus_ttn()
            self.app.schedule_queue_sync()
            self.update_queue_status()

        self.app.run_async(task, done)

    def _sync_queue(self) -> None:
        self.app.schedule_queue_sync(manual=True)

    def _update_status(self, message: str, tone: str = "info") -> None:
        styles = {
            "info": "StatusInfo.TLabel",
            "success": "StatusSuccess.TLabel",
            "warning": "StatusWarning.TLabel",
            "danger": "StatusDanger.TLabel",
        }
        self._status.set(message)
        self._status_label.configure(style=styles.get(tone, "StatusInfo.TLabel"))

    def update_queue_status(self) -> None:
        count = len(self.app.offline_queue.pending())
        self._queue_status.set(f"Офлайн записів: {count}")
        if count:
            self._queue_badge.configure(style="StatusBadgeWarn.TLabel")
        else:
            self._queue_badge.configure(style="StatusBadgeOk.TLabel")


class HistoryScreen(Screen):
    def __init__(self, master: tk.Widget, app: "TrackingDesktopApp") -> None:
        super().__init__(master, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._records: List[Dict[str, Any]] = []
        self._filtered: List[Dict[str, Any]] = []

        card = ttk.Frame(self, style="Card.TFrame", padding=(40, 32))
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, weight=1)

        header = ttk.Frame(card, style="Card.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Історія сканувань", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        AccentButton(header, text="Оновити", command=self.refresh).grid(row=0, column=1)

        filters = ttk.Frame(card, style="CardSection.TFrame", padding=(20, 20))
        filters.grid(row=1, column=0, sticky="ew", pady=(20, 0))
        filters.columnconfigure((0, 1, 2, 3), weight=1)

        self._box_filter = tk.StringVar()
        self._ttn_filter = tk.StringVar()
        self._user_filter = tk.StringVar()
        self._date_filter = tk.StringVar()

        self._add_filter(filters, 0, "BoxID", self._box_filter)
        self._add_filter(filters, 1, "TTN", self._ttn_filter)
        self._add_filter(filters, 2, "Користувач", self._user_filter)

        ttk.Label(filters, text="Дата (YYYY-MM-DD)", style="MutedSmall.TLabel").grid(row=0, column=3, sticky="w")
        ttk.Entry(filters, textvariable=self._date_filter).grid(row=1, column=3, sticky="ew")

        control_row = ttk.Frame(filters, style="CardSection.TFrame")
        control_row.grid(row=2, column=0, columnspan=4, sticky="w", pady=(16, 0))
        AccentButton(control_row, text="Застосувати", command=self.apply_filters).pack(side=tk.LEFT)
        ttk.Button(control_row, text="Скинути", command=self._reset_filters).pack(side=tk.LEFT, padx=12)

        columns = ("datetime", "user", "box", "ttn")
        table_frame = ttk.Frame(card, style="Surface.TFrame")
        table_frame.grid(row=3, column=0, sticky="nsew", pady=(24, 16))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        self._table = ttk.Treeview(table_frame, columns=columns, show="headings")
        self._table.heading("datetime", text="Дата та час")
        self._table.heading("user", text="Користувач")
        self._table.heading("box", text="BoxID")
        self._table.heading("ttn", text="TTN")
        self._table.column("datetime", width=200)
        self._table.column("user", width=160)
        self._table.column("box", width=160)
        self._table.column("ttn", width=160)
        self._table.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self._table.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._table.configure(yscrollcommand=scrollbar.set)

        self._status = ttk.Label(card, text="", style="StatusInfo.TLabel")
        self._status.grid(row=4, column=0, sticky="w", pady=(8, 0))

    def _add_filter(self, frame: ttk.Frame, column: int, title: str, var: tk.StringVar) -> None:
        ttk.Label(frame, text=title, style="MutedSmall.TLabel").grid(row=0, column=column, sticky="w")
        entry = ttk.Entry(frame, textvariable=var)
        entry.grid(row=1, column=column, sticky="ew", padx=(0 if column == 0 else 12, 0))
        entry.bind("<Return>", lambda _: self.apply_filters())

    def on_show(self) -> None:
        if not self._records:
            self.refresh()

    def refresh(self) -> None:
        profile = self.app.state.profile
        if not profile:
            return
        self._status.configure(text="Завантаження...", style="StatusInfo.TLabel")

        def task() -> Any:
            try:
                return self.app.api.get_history(profile.token)
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                self._status.configure(text=str(result), style="StatusDanger.TLabel")
                return
            assert isinstance(result, list)
            self._records = sorted(result, key=lambda item: _parse_iso(item.get("datetime")), reverse=True)
            self.apply_filters()

        self.app.run_async(task, done)

    def apply_filters(self) -> None:
        filtered = list(self._records)
        box_text = self._box_filter.get().strip().lower()
        ttn_text = self._ttn_filter.get().strip().lower()
        user_text = self._user_filter.get().strip().lower()
        date_text = self._date_filter.get().strip()

        if box_text:
            filtered = [item for item in filtered if box_text in str(item.get("boxid", "")).lower()]
        if ttn_text:
            filtered = [item for item in filtered if ttn_text in str(item.get("ttn", "")).lower()]
        if user_text:
            filtered = [item for item in filtered if user_text in str(item.get("user_name", "")).lower()]
        if date_text:
            try:
                selected = dt.datetime.strptime(date_text, "%Y-%m-%d").date()
                filtered = [item for item in filtered if _parse_iso(item.get("datetime")).date() == selected]
            except ValueError:
                self._status.configure(
                    text="Невірний формат дати. Використовуйте YYYY-MM-DD",
                    style="StatusWarning.TLabel",
                )

        self._filtered = filtered
        self._render_table()

    def _reset_filters(self) -> None:
        self._box_filter.set("")
        self._ttn_filter.set("")
        self._user_filter.set("")
        self._date_filter.set("")
        self.apply_filters()

    def _render_table(self) -> None:
        self._table.delete(*self._table.get_children())
        for row in self._filtered:
            parsed = _parse_iso(row.get("datetime"))
            self._table.insert(
                "",
                "end",
                values=(
                    parsed.strftime("%d.%m.%Y %H:%M:%S"),
                    row.get("user_name") or row.get("operator") or "—",
                    row.get("boxid", ""),
                    row.get("ttn", ""),
                ),
            )
        self._status.configure(text=f"Показано записів: {len(self._filtered)}", style="StatusInfo.TLabel")


class ErrorsScreen(Screen):
    def __init__(self, master: tk.Widget, app: "TrackingDesktopApp") -> None:
        super().__init__(master, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._errors: List[Dict[str, Any]] = []

        card = ttk.Frame(self, style="Card.TFrame", padding=(40, 32))
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)

        header = ttk.Frame(card, style="Card.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Журнал помилок", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        AccentButton(header, text="Оновити", command=self.refresh).grid(row=0, column=1)

        columns = ("datetime", "user", "box", "ttn", "note")
        table_frame = ttk.Frame(card, style="Surface.TFrame")
        table_frame.grid(row=1, column=0, sticky="nsew", pady=(18, 12))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        self._table = ttk.Treeview(table_frame, columns=columns, show="headings")
        self._table.heading("datetime", text="Дата")
        self._table.heading("user", text="Користувач")
        self._table.heading("box", text="BoxID")
        self._table.heading("ttn", text="TTN")
        self._table.heading("note", text="Опис")
        self._table.column("datetime", width=200)
        self._table.column("note", width=240)
        self._table.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self._table.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._table.configure(yscrollcommand=scrollbar.set)

        controls = ttk.Frame(card, style="Card.TFrame")
        controls.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        controls.columnconfigure(2, weight=1)
        AccentButton(controls, text="Очистити всі", command=self._clear_all).grid(row=0, column=0, sticky="w")
        AccentButton(controls, text="Видалити вибраний", command=self._delete_selected).grid(
            row=0,
            column=1,
            sticky="w",
            padx=(12, 0),
        )

        self._status = ttk.Label(card, text="", style="StatusInfo.TLabel")
        self._status.grid(row=3, column=0, sticky="w", pady=(24, 0))

    def on_show(self) -> None:
        if not self._errors:
            self.refresh()

    def refresh(self) -> None:
        profile = self.app.state.profile
        if not profile:
            return
        self._status.configure(text="Завантаження...", style="StatusInfo.TLabel")

        def task() -> Any:
            try:
                return self.app.api.get_errors(profile.token)
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                self._status.configure(text=str(result), style="StatusDanger.TLabel")
                return
            assert isinstance(result, list)
            self._errors = sorted(result, key=lambda item: _parse_iso(item.get("datetime")), reverse=True)
            self._render_table()

        self.app.run_async(task, done)

    def _render_table(self) -> None:
        self._table.delete(*self._table.get_children())
        for record in self._errors:
            parsed = _parse_iso(record.get("datetime"))
            self._table.insert(
                "",
                "end",
                iid=str(record.get("id")),
                values=(
                    parsed.strftime("%d.%m.%Y %H:%M:%S"),
                    record.get("user_name") or record.get("operator") or "—",
                    record.get("boxid", ""),
                    record.get("ttn", ""),
                    record.get("note", ""),
                ),
            )
        self._status.configure(text=f"Помилок: {len(self._errors)}", style="StatusInfo.TLabel")

    def _clear_all(self) -> None:
        profile = self.app.state.profile
        if not profile:
            return
        if not messagebox.askyesno(
            "Очистити журнал",
            "Видалити усі записи про помилки?",
            parent=self,
        ):
            return

        def task() -> Any:
            try:
                self.app.api.clear_errors(profile.token)
                return True
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                messagebox.showerror("Помилка", str(result), parent=self)
                return
            self._errors = []
            self._render_table()

        self.app.run_async(task, done)

    def _delete_selected(self) -> None:
        profile = self.app.state.profile
        if not profile:
            return
        selection = self._table.selection()
        if not selection:
            messagebox.showinfo("Видалення", "Оберіть запис", parent=self)
            return
        record_id = int(selection[0])
        if not messagebox.askyesno("Видалити", "Видалити вибраний запис?", parent=self):
            return

        def task() -> Any:
            try:
                self.app.api.delete_error(profile.token, record_id)
                return True
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                messagebox.showerror("Помилка", str(result), parent=self)
                return
            self._errors = [err for err in self._errors if int(err.get("id", -1)) != record_id]
            self._render_table()

        self.app.run_async(task, done)


class StatisticsScreen(Screen):
    def __init__(self, master: tk.Widget, app: "TrackingDesktopApp") -> None:
        super().__init__(master, app)
        self.columnconfigure(0, weight=1)
        self._history: List[Dict[str, Any]] = []
        self._errors: List[Dict[str, Any]] = []
        now = dt.datetime.now()
        self._start = dt.datetime(now.year, now.month, 1)
        self._end = now

        card = ttk.Frame(self, style="Card.TFrame", padding=(40, 32))
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)

        header = ttk.Frame(card, style="Card.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Статистика", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        AccentButton(header, text="Оновити", command=self.refresh).grid(row=0, column=1)

        filters = ttk.LabelFrame(card, text="Період", padding=18, style="Relise.TLabelframe")
        filters.grid(row=1, column=0, sticky="ew", pady=(18, 12))
        filters.columnconfigure(1, weight=1)

        self._start_var = tk.StringVar(value=self._start.strftime("%Y-%m-%d %H:%M"))
        self._end_var = tk.StringVar(value=self._end.strftime("%Y-%m-%d %H:%M"))

        ttk.Label(filters, text="Початок (YYYY-MM-DD HH:MM)", style="MutedSmall.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(filters, textvariable=self._start_var).grid(row=0, column=1, sticky="ew")
        ttk.Label(filters, text="Кінець (YYYY-MM-DD HH:MM)", style="MutedSmall.TLabel").grid(
            row=1, column=0, sticky="w", pady=(12, 0)
        )
        ttk.Entry(filters, textvariable=self._end_var).grid(row=1, column=1, sticky="ew", pady=(12, 0))

        filter_buttons = ttk.Frame(filters, style="CardSection.TFrame")
        filter_buttons.grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))
        AccentButton(filter_buttons, text="Застосувати", command=self._apply_filters).pack(side=tk.LEFT)
        ttk.Button(filter_buttons, text="Поточний місяць", command=self._reset_period).pack(side=tk.LEFT, padx=12)

        self._summary = ttk.LabelFrame(card, text="Ключові показники", padding=18, style="Relise.TLabelframe")
        self._summary.grid(row=2, column=0, sticky="ew", pady=(12, 12))
        self._summary.columnconfigure((0, 1, 2, 3), weight=1)

        self._leaders = ttk.LabelFrame(card, text="Лідери", padding=18, style="Relise.TLabelframe")
        self._leaders.grid(row=3, column=0, sticky="ew", pady=(12, 12))
        self._leaders.columnconfigure((0, 1), weight=1)

        self._daily = ttk.LabelFrame(card, text="Добова активність", padding=18, style="Relise.TLabelframe")
        self._daily.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self._daily.columnconfigure(0, weight=1)

        self._status = ttk.Label(card, text="", style="StatusInfo.TLabel")
        self._status.grid(row=5, column=0, sticky="w", pady=(24, 0))

    def on_show(self) -> None:
        profile = self.app.state.profile
        if profile and profile.role == "admin" and not self._history:
            self.refresh()
        elif profile and profile.role != "admin":
            self._status.configure(text="Статистика доступна лише адміністраторам", style="StatusWarning.TLabel")

    def refresh(self) -> None:
        profile = self.app.state.profile
        if not profile or profile.role != "admin":
            messagebox.showinfo("Доступ обмежено", "Цей розділ лише для адміністраторів", parent=self)
            return
        self._status.configure(text="Завантаження...", style="StatusInfo.TLabel")

        def task() -> Any:
            try:
                return self.app.api.get_history(profile.token), self.app.api.get_errors(profile.token)
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                self._status.configure(text=str(result), style="StatusDanger.TLabel")
                return
            self._history, self._errors = result
            self._apply_filters()

        self.app.run_async(task, done)

    def _reset_period(self) -> None:
        now = dt.datetime.now()
        self._start = dt.datetime(now.year, now.month, 1)
        self._end = now
        self._start_var.set(self._start.strftime("%Y-%m-%d %H:%M"))
        self._end_var.set(self._end.strftime("%Y-%m-%d %H:%M"))
        self._apply_filters()

    def _apply_filters(self) -> None:
        try:
            self._start = dt.datetime.strptime(self._start_var.get(), "%Y-%m-%d %H:%M")
            self._end = dt.datetime.strptime(self._end_var.get(), "%Y-%m-%d %H:%M")
        except ValueError:
            self._status.configure(text="Невірний формат періоду", style="StatusDanger.TLabel")
            return
        if self._end < self._start:
            self._start, self._end = self._end, self._start
            self._start_var.set(self._start.strftime("%Y-%m-%d %H:%M"))
            self._end_var.set(self._end.strftime("%Y-%m-%d %H:%M"))

        scans = [item for item in self._history if self._start <= _parse_iso(item.get("datetime")) <= self._end]
        errors = [item for item in self._errors if self._start <= _parse_iso(item.get("datetime")) <= self._end]

        scan_counts = Counter(_extract_user(item) for item in scans)
        error_counts = Counter(_extract_user(item) for item in errors)

        total_scans = sum(scan_counts.values())
        unique_users = len(scan_counts)
        total_errors = sum(error_counts.values())
        error_users = len(error_counts)

        self._render_summary(total_scans, unique_users, total_errors, error_users)
        self._render_leaders(scan_counts, error_counts)
        self._render_daily(scans, errors)

        self._status.configure(
            text=f"Період: {self._start.strftime('%d.%m.%Y %H:%M')} – {self._end.strftime('%d.%m.%Y %H:%M')}",
            style="StatusInfo.TLabel",
        )

    def _render_summary(self, total_scans: int, unique_users: int, total_errors: int, error_users: int) -> None:
        for child in self._summary.winfo_children():
            child.destroy()
        metrics = [
            ("Сканувань", total_scans),
            ("Операторів", unique_users),
            ("Помилок", total_errors),
            ("Користувачів з помилками", error_users),
        ]
        for idx, (title, value) in enumerate(metrics):
            frame = ttk.Frame(self._summary, padding=20, style="Metric.TFrame")
            frame.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 16, 0))
            frame.columnconfigure(0, weight=1)
            ttk.Label(frame, text=title, style="MetricLabel.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Label(frame, text=str(value), style="MetricValue.TLabel").grid(
                row=1, column=0, sticky="w", pady=(10, 0)
            )

    def _render_leaders(self, scan_counts: Counter, error_counts: Counter) -> None:
        for child in self._leaders.winfo_children():
            child.destroy()
        top_scan = scan_counts.most_common(1)
        top_error = error_counts.most_common(1)
        cards = [
            ("Найактивніший оператор", top_scan[0] if top_scan else None, "MetricValueSuccess.TLabel"),
            ("Найбільше помилок", top_error[0] if top_error else None, "MetricValueDanger.TLabel"),
        ]
        for idx, (title, data, style_name) in enumerate(cards):
            frame = ttk.Frame(self._leaders, padding=20, style="Metric.TFrame")
            frame.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 16, 0))
            frame.columnconfigure(0, weight=1)
            ttk.Label(frame, text=title, style="MetricLabel.TLabel").grid(row=0, column=0, sticky="w")
            display = "—" if data is None else f"{data[0]} ({data[1]})"
            ttk.Label(frame, text=display, style=style_name).grid(row=1, column=0, sticky="w", pady=(10, 0))

    def _render_daily(self, scans: List[Dict[str, Any]], errors: List[Dict[str, Any]]) -> None:
        for child in self._daily.winfo_children():
            child.destroy()
        grouped: Dict[dt.date, Dict[str, Counter]] = defaultdict(lambda: {"scan": Counter(), "error": Counter()})
        for item in scans:
            parsed = _parse_iso(item.get("datetime"))
            grouped[parsed.date()]["scan"][_extract_user(item)] += 1
        for item in errors:
            parsed = _parse_iso(item.get("datetime"))
            grouped[parsed.date()]["error"][_extract_user(item)] += 1

        rows = sorted(grouped.items(), key=lambda entry: entry[0], reverse=True)
        if not rows:
            ttk.Label(self._daily, text="Немає даних для вибраного періоду").pack(anchor="w")
            return
        for day, values in rows:
            frame = ttk.Frame(self._daily, style="CardSection.TFrame", padding=(18, 16))
            frame.pack(fill="x", pady=6)
            frame.columnconfigure(0, weight=1)
            ttk.Label(frame, text=day.strftime("%d.%m.%Y"), style="InputLabel.TLabel").grid(row=0, column=0, sticky="w")
            scans_total = sum(values["scan"].values())
            errors_total = sum(values["error"].values())
            top_scan = values["scan"].most_common(1)
            top_error = values["error"].most_common(1)

            chips = ttk.Frame(frame, style="CardSection.TFrame")
            chips.grid(row=1, column=0, sticky="w", pady=(10, 0))
            ttk.Label(chips, text=f"Сканів: {scans_total}", style="StatusBadgeOk.TLabel").pack(side=tk.LEFT)
            error_style = "StatusBadgeWarn.TLabel" if errors_total else "StatusBadge.TLabel"
            ttk.Label(chips, text=f"Помилок: {errors_total}", style=error_style).pack(side=tk.LEFT, padx=(10, 0))

            details: List[str] = []
            if top_scan:
                details.append(f"Лідер сканувань: {top_scan[0][0]} ({top_scan[0][1]})")
            if top_error:
                details.append(f"Помилки: {top_error[0][0]} ({top_error[0][1]})")
            if details:
                ttk.Label(
                    frame,
                    text=" • ".join(details),
                    style="MutedOnSection.TLabel",
                ).grid(row=2, column=0, sticky="w", pady=(10, 0))


class AdminPanel(tk.Toplevel):
    def __init__(self, app: "TrackingDesktopApp", admin_token: str) -> None:
        super().__init__(app)
        self.app = app
        self.token = admin_token
        self.title("Керування користувачами")
        self.geometry("1000x680")
        self.configure(bg=PALETTE["canvas"])

        self._pending: List[Dict[str, Any]] = []
        self._users: List[Dict[str, Any]] = []
        self._passwords: Dict[str, str] = {}

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=24, style="Header.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Панель адміністратора", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        AccentButton(header, text="Оновити", command=self._refresh).grid(row=0, column=1)

        content = ttk.Frame(self, style="Screen.TFrame")
        content.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 18))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        self._pending_frame = ttk.LabelFrame(content, text="Заявки", padding=18, style="Relise.TLabelframe")
        self._pending_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._pending_frame.columnconfigure(0, weight=1)

        self._users_frame = ttk.LabelFrame(content, text="Користувачі", padding=18, style="Relise.TLabelframe")
        self._users_frame.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        self._users_frame.columnconfigure(0, weight=1)

        self._passwords_frame = ttk.LabelFrame(self, text="Паролі ролей", padding=18, style="Relise.TLabelframe")
        self._passwords_frame.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 24))
        self._passwords_frame.columnconfigure(0, weight=1)

        self._status = ttk.Label(self, text="", style="Status.TLabel")
        self._status.grid(row=3, column=0, sticky="w", padx=24, pady=(0, 24))

        self._refresh()

    def _refresh(self) -> None:
        self._status.configure(text="Завантаження...")

        def task() -> Any:
            try:
                pending = self.app.api.fetch_pending_users(self.token)
                users = self.app.api.fetch_users(self.token)
                passwords = self.app.api.fetch_role_passwords(self.token)
                return pending, users, passwords
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                self._status.configure(text=str(result))
                return
            self._pending, self._users, self._passwords = result
            self._render_pending()
            self._render_users()
            self._render_passwords()
            self._status.configure(text=f"Заявок: {len(self._pending)} | Користувачів: {len(self._users)}")

        self.app.run_async(task, done)

    def _render_pending(self) -> None:
        for child in self._pending_frame.winfo_children():
            child.destroy()
        if not self._pending:
            ttk.Label(self._pending_frame, text="Немає заявок").pack(anchor="w")
            return
        for request in self._pending:
            card = ttk.Frame(self._pending_frame, padding=12, style="Card.TFrame")
            card.pack(fill="x", pady=6)
            ttk.Label(
                card,
                text=f"{request.get('surname')} (#{request.get('id')})",
                font=("Segoe UI", 11, "bold"),
            ).grid(row=0, column=0, sticky="w")
            ttk.Label(card, text=str(request.get("created_at", ""))).grid(row=1, column=0, sticky="w")
            buttons = ttk.Frame(card)
            buttons.grid(row=0, column=1, rowspan=2, sticky="e")
            AccentButton(buttons, text="Адмін", command=lambda r=request: self._approve(r, "admin")).pack(side=tk.LEFT, padx=4)
            AccentButton(buttons, text="Оператор", command=lambda r=request: self._approve(r, "operator")).pack(side=tk.LEFT, padx=4)
            ttk.Button(buttons, text="Відхилити", command=lambda r=request: self._reject(r)).pack(side=tk.LEFT, padx=4)

    def _render_users(self) -> None:
        for child in self._users_frame.winfo_children():
            child.destroy()
        if not self._users:
            ttk.Label(self._users_frame, text="Немає користувачів").pack(anchor="w")
            return
        tree = ttk.Treeview(
            self._users_frame,
            columns=("id", "surname", "role", "active", "created", "updated"),
            show="headings",
            height=12,
        )
        tree.heading("id", text="ID")
        tree.heading("surname", text="Прізвище")
        tree.heading("role", text="Роль")
        tree.heading("active", text="Активний")
        tree.heading("created", text="Створено")
        tree.heading("updated", text="Оновлено")
        tree.column("surname", width=160)
        tree.column("role", width=120)
        tree.column("active", width=90)
        tree.pack(fill="both", expand=True)

        for user in self._users:
            tree.insert(
                "",
                "end",
                iid=str(user.get("id")),
                values=(
                    user.get("id"),
                    user.get("surname"),
                    user.get("role"),
                    "Так" if user.get("is_active") else "Ні",
                    user.get("created_at"),
                    user.get("updated_at"),
                ),
            )

        controls = ttk.Frame(self._users_frame, padding=(0, 12, 0, 0))
        controls.pack(fill="x")
        AccentButton(controls, text="Змінити роль", command=lambda: self._change_role(tree)).pack(side=tk.LEFT)
        AccentButton(controls, text="Активувати/деактивувати", command=lambda: self._toggle_user(tree)).pack(side=tk.LEFT, padx=12)
        ttk.Button(controls, text="Видалити", command=lambda: self._delete_user(tree)).pack(side=tk.LEFT)

    def _render_passwords(self) -> None:
        for child in self._passwords_frame.winfo_children():
            child.destroy()
        if not self._passwords:
            ttk.Label(self._passwords_frame, text="Дані відсутні").pack(anchor="w")
            return
        for role, password in self._passwords.items():
            row = ttk.Frame(self._passwords_frame)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=role.upper(), font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
            ttk.Label(row, text=password or "—", foreground="#6b7688").pack(side=tk.LEFT, padx=(12, 12))
            ttk.Button(row, text="Редагувати", command=lambda r=role: self._edit_password(r)).pack(side=tk.LEFT)

    def _approve(self, request: Dict[str, Any], role: str) -> None:
        def task() -> Any:
            try:
                self.app.api.approve_user(self.token, int(request.get("id")), role)
                return True
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                messagebox.showerror("Помилка", str(result), parent=self)
                return
            self._refresh()

        self.app.run_async(task, done)

    def _reject(self, request: Dict[str, Any]) -> None:
        def task() -> Any:
            try:
                self.app.api.reject_user(self.token, int(request.get("id")))
                return True
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                messagebox.showerror("Помилка", str(result), parent=self)
                return
            self._refresh()

        self.app.run_async(task, done)

    def _change_role(self, tree: ttk.Treeview) -> None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("Роль", "Оберіть користувача", parent=self)
            return
        user_id = int(selection[0])
        role = simpledialog.askstring("Нова роль", "Введіть роль (admin/operator/viewer)", parent=self)
        if not role:
            return

        def task() -> Any:
            try:
                self.app.api.update_user(self.token, user_id, role=role.strip())
                return True
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                messagebox.showerror("Помилка", str(result), parent=self)
                return
            self._refresh()

        self.app.run_async(task, done)

    def _toggle_user(self, tree: ttk.Treeview) -> None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("Статус", "Оберіть користувача", parent=self)
            return
        user_id = int(selection[0])
        current = tree.set(selection[0], "active") == "Так"

        def task() -> Any:
            try:
                self.app.api.update_user(self.token, user_id, is_active=not current)
                return True
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                messagebox.showerror("Помилка", str(result), parent=self)
                return
            self._refresh()

        self.app.run_async(task, done)

    def _delete_user(self, tree: ttk.Treeview) -> None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("Видалення", "Оберіть користувача", parent=self)
            return
        user_id = int(selection[0])
        if not messagebox.askyesno("Видалити", "Видалити користувача?", parent=self):
            return

        def task() -> Any:
            try:
                self.app.api.delete_user(self.token, user_id)
                return True
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                messagebox.showerror("Помилка", str(result), parent=self)
                return
            self._refresh()

        self.app.run_async(task, done)

    def _edit_password(self, role: str) -> None:
        new_password = simpledialog.askstring(
            "Пароль роли",
            f"Новий пароль для {role}",
            parent=self,
        )
        if new_password is None:
            return

        def task() -> Any:
            try:
                self.app.api.update_role_password(self.token, role, new_password.strip())
                return True
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                messagebox.showerror("Помилка", str(result), parent=self)
                return
            self._refresh()

        self.app.run_async(task, done)


def _parse_iso(value: Optional[str]) -> dt.datetime:
    if not value:
        return dt.datetime.fromtimestamp(0)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except ValueError:
        try:
            return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return dt.datetime.fromtimestamp(0)


def _extract_user(record: Dict[str, Any]) -> str:
    value = record.get("user_name") or record.get("operator") or "Невідомий користувач"
    value = str(value).strip()
    return value or "Невідомий користувач"


class TrackingDesktopApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1300x820")
        self.minsize(1100, 700)

        self.style = ttk.Style(self)
        self._build_styles()

        self.state = AppState()
        self.api = ApiClient()
        self.offline_queue = OfflineQueue(QUEUE_DB_PATH)
        self._runner = AsyncRunner(self)

        self._login_screen: Optional[LoginScreen] = None
        self._app_frame: Optional[ttk.Frame] = None
        self._screen_container: Optional[ttk.Frame] = None
        self._screens: Dict[str, Screen] = {}
        self._current_screen: Optional[str] = None
        self._sync_in_progress = False

        self.user_label = tk.StringVar(value="Не авторизовано")
        self.role_label = tk.StringVar(value="")
        self._status_var = tk.StringVar(value="")

        if self.state.profile:
            self._build_app_layout()
            self.show_screen("scanner")
            self.schedule_queue_sync()
        else:
            self._show_login()

    # ---- styling --------------------------------------------------------
    def _build_styles(self) -> None:
        base_font = ("Segoe UI", 11)
        self.option_add("*Font", base_font)
        self.option_add("*TEntry.Font", ("Segoe UI", 12))
        self.option_add("*Treeview.Font", ("Segoe UI", 11))
        self.option_add("*Treeview.Heading.Font", ("Segoe UI", 11, "bold"))
        self.style.theme_use("clam")
        self.configure(bg=PALETTE["canvas"])

        # base surfaces
        self.style.configure("TFrame", background=PALETTE["surface"])
        self.style.configure("Screen.TFrame", background=PALETTE["canvas"])
        self.style.configure("Surface.TFrame", background=PALETTE["surface"])
        self.style.configure("Card.TFrame", background=PALETTE["surface"], borderwidth=0, relief="flat")
        self.style.configure("CardSection.TFrame", background=PALETTE["surface_alt"], borderwidth=0, relief="flat")
        self.style.configure("Navigation.TFrame", background=PALETTE["nav_bg"])
        self.style.configure("Header.TFrame", background=PALETTE["surface"], borderwidth=0)
        self.style.configure("Footer.TFrame", background=PALETTE["surface"], borderwidth=0)
        self.style.configure("Hero.TFrame", background=PALETTE["hero_bg"])

        # typography
        self.style.configure("TLabel", background=PALETTE["surface"], foreground=PALETTE["text"])
        self.style.configure("Muted.TLabel", background=PALETTE["surface"], foreground=PALETTE["muted"])
        self.style.configure(
            "MutedSmall.TLabel",
            background=PALETTE["surface"],
            foreground=PALETTE["muted"],
            font=("Segoe UI", 10),
        )
        self.style.configure(
            "MutedOnSection.TLabel",
            background=PALETTE["surface_alt"],
            foreground=PALETTE["muted"],
            font=("Segoe UI", 10),
        )
        self.style.configure(
            "CardTitle.TLabel",
            background=PALETTE["surface"],
            foreground=PALETTE["text"],
            font=("Segoe UI", 20, "bold"),
        )
        self.style.configure(
            "SectionTitle.TLabel",
            background=PALETTE["surface"],
            foreground=PALETTE["muted"],
            font=("Segoe UI", 12, "bold"),
        )
        self.style.configure(
            "InputLabel.TLabel",
            background=PALETTE["surface_alt"],
            foreground=PALETTE["muted"],
            font=("Segoe UI", 12, "bold"),
        )
        self.style.configure(
            "Status.TLabel",
            background=PALETTE["surface"],
            foreground=PALETTE["muted"],
        )
        self.style.configure(
            "StatusInfo.TLabel",
            background=PALETTE["chip_info_bg"],
            foreground=PALETTE["chip_info_fg"],
            font=("Segoe UI", 12),
            padding=(16, 10),
        )
        self.style.configure(
            "StatusSuccess.TLabel",
            background=PALETTE["chip_success_bg"],
            foreground=PALETTE["chip_success_fg"],
            font=("Segoe UI", 12),
            padding=(16, 10),
        )
        self.style.configure(
            "StatusWarning.TLabel",
            background=PALETTE["chip_warning_bg"],
            foreground=PALETTE["chip_warning_fg"],
            font=("Segoe UI", 12),
            padding=(16, 10),
        )
        self.style.configure(
            "StatusDanger.TLabel",
            background=PALETTE["chip_danger_bg"],
            foreground=PALETTE["chip_danger_fg"],
            font=("Segoe UI", 12),
            padding=(16, 10),
        )
        self.style.configure(
            "StatusBadge.TLabel",
            background=PALETTE["chip_muted_bg"],
            foreground=PALETTE["chip_muted_fg"],
            font=("Segoe UI", 10, "bold"),
            padding=(12, 6),
        )
        self.style.configure(
            "StatusBadgeWarn.TLabel",
            background=PALETTE["chip_warning_bg"],
            foreground=PALETTE["chip_warning_fg"],
            font=("Segoe UI", 10, "bold"),
            padding=(12, 6),
        )
        self.style.configure(
            "StatusBadgeOk.TLabel",
            background=PALETTE["chip_success_bg"],
            foreground=PALETTE["chip_success_fg"],
            font=("Segoe UI", 10, "bold"),
            padding=(12, 6),
        )
        self.style.configure(
            "HeroBrand.TLabel",
            background=PALETTE["hero_bg"],
            foreground=PALETTE["hero_text"],
            font=("Segoe UI", 30, "bold"),
        )
        self.style.configure(
            "HeroSubtitle.TLabel",
            background=PALETTE["hero_bg"],
            foreground=PALETTE["hero_text"],
            font=("Segoe UI", 14),
        )
        self.style.configure(
            "HeroBullet.TLabel",
            background=PALETTE["hero_bg"],
            foreground=PALETTE["hero_text"],
            font=("Segoe UI", 12),
        )
        self.style.configure(
            "HeroBadge.TLabel",
            background=PALETTE["hero_bg"],
            foreground=PALETTE["hero_text"],
            font=("Segoe UI", 10, "bold"),
            padding=(10, 6),
        )
        self.style.configure(
            "NavBrand.TLabel",
            background=PALETTE["nav_bg"],
            foreground="#ffffff",
            font=("Segoe UI", 16, "bold"),
        )
        self.style.configure(
            "NavSection.TLabel",
            background=PALETTE["nav_bg"],
            foreground=PALETTE["muted_alt"],
            font=("Segoe UI", 9, "bold"),
        )
        self.style.configure(
            "NavFooter.TLabel",
            background=PALETTE["nav_bg"],
            foreground=PALETTE["muted_alt"],
            font=("Segoe UI", 9),
        )
        self.style.configure(
            "HeaderUser.TLabel",
            background=PALETTE["surface"],
            foreground=PALETTE["text"],
            font=("Segoe UI", 16, "bold"),
        )
        self.style.configure(
            "HeaderRole.TLabel",
            background=PALETTE["surface"],
            foreground=PALETTE["muted"],
        )
        self.style.configure(
            "Metric.TFrame",
            background=PALETTE["surface_alt"],
            borderwidth=0,
            relief="flat",
        )
        self.style.configure(
            "MetricLabel.TLabel",
            background=PALETTE["surface_alt"],
            foreground=PALETTE["muted"],
            font=("Segoe UI", 12, "bold"),
        )
        self.style.configure(
            "MetricValue.TLabel",
            background=PALETTE["surface_alt"],
            foreground=PALETTE["accent_active"],
            font=("Segoe UI", 26, "bold"),
        )
        self.style.configure(
            "MetricValueSuccess.TLabel",
            background=PALETTE["surface_alt"],
            foreground=PALETTE["success"],
            font=("Segoe UI", 26, "bold"),
        )
        self.style.configure(
            "MetricValueDanger.TLabel",
            background=PALETTE["surface_alt"],
            foreground=PALETTE["danger"],
            font=("Segoe UI", 26, "bold"),
        )

        # buttons
        self.style.configure(
            "TButton",
            font=("Segoe UI", 11, "bold"),
            padding=(16, 12),
            borderwidth=0,
            background=PALETTE["surface_alt"],
            foreground=PALETTE["text"],
        )
        self.style.map(
            "TButton",
            background=[("active", PALETTE["surface_subtle"]), ("pressed", PALETTE["surface_alt"])],
            foreground=[("disabled", PALETTE["muted_alt"])],
        )
        self.style.configure(
            "Accent.TButton",
            background=PALETTE["accent"],
            foreground="#ffffff",
            borderwidth=0,
            focuscolor=PALETTE["accent"],
        )
        self.style.map(
            "Accent.TButton",
            background=[("active", PALETTE["accent_hover"]), ("pressed", PALETTE["accent_active"])],
            foreground=[("disabled", "#d0d8eb")],
        )
        self.style.configure(
            "Nav.TButton",
            background=PALETTE["nav_bg"],
            foreground=PALETTE["muted_alt"],
            anchor="w",
            padding=(20, 14),
            borderwidth=0,
            focuscolor=PALETTE["nav_bg"],
        )
        self.style.map(
            "Nav.TButton",
            background=[("active", PALETTE["nav_hover"])],
            foreground=[("active", "#ffffff")],
        )
        self.style.configure(
            "NavActive.TButton",
            background=PALETTE["nav_active"],
            foreground="#ffffff",
            anchor="w",
            padding=(20, 14),
            borderwidth=0,
        )

        # inputs
        self.style.configure(
            "TEntry",
            padding=14,
            fieldbackground=PALETTE["surface"],
            insertcolor=PALETTE["accent"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["divider"],
            lightcolor=PALETTE["divider"],
            darkcolor=PALETTE["divider"],
            borderwidth=1,
        )
        self.style.map(
            "TEntry",
            fieldbackground=[("disabled", PALETTE["surface_alt"])],
            bordercolor=[("focus", PALETTE["accent"])],
            foreground=[("disabled", PALETTE["muted_alt"])],
        )

        # tables
        self.style.configure(
            "Treeview",
            background=PALETTE["surface"],
            fieldbackground=PALETTE["surface"],
            foreground=PALETTE["text"],
            rowheight=36,
            borderwidth=0,
        )
        self.style.map(
            "Treeview",
            background=[("selected", PALETTE["accent"])],
            foreground=[("selected", "#ffffff")],
        )
        self.style.configure(
            "Treeview.Heading",
            background=PALETTE["surface_alt"],
            foreground=PALETTE["muted"],
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            padding=12,
        )
        self.style.map(
            "Treeview.Heading",
            background=[("active", PALETTE["surface_subtle"])],
        )

        # notebook
        self.style.configure(
            "Relise.TNotebook",
            background=PALETTE["surface"],
            borderwidth=0,
            tabposition="n",
        )
        self.style.configure(
            "Relise.TNotebook.Tab",
            background=PALETTE["surface_alt"],
            padding=(20, 12),
            font=("Segoe UI", 11, "bold"),
        )
        self.style.map(
            "Relise.TNotebook.Tab",
            background=[("selected", PALETTE["surface"]), ("active", PALETTE["surface"])],
            foreground=[("selected", PALETTE["accent"]), ("!selected", PALETTE["muted"])],
        )

        # labelframes
        self.style.configure(
            "Relise.TLabelframe",
            background=PALETTE["surface"],
            foreground=PALETTE["muted"],
            borderwidth=0,
            relief="flat",
            padding=16,
        )
        self.style.configure(
            "Relise.TLabelframe.Label",
            background=PALETTE["surface"],
            foreground=PALETTE["muted"],
            font=("Segoe UI", 12, "bold"),
        )
        self.style.configure("TLabelframe", background=PALETTE["surface"])
        self.style.configure("TLabelframe.Label", background=PALETTE["surface"], foreground=PALETTE["muted"])

    # ---- layout ---------------------------------------------------------
    def _show_login(self) -> None:
        self._destroy_app_layout()
        if self._login_screen:
            self._login_screen.destroy()
        self._login_screen = LoginScreen(self, self)
        self._login_screen.pack(fill="both", expand=True)

    def _destroy_app_layout(self) -> None:
        if self._app_frame is not None:
            self._app_frame.destroy()
            self._app_frame = None
            self._screen_container = None
            self._screens.clear()
            self._current_screen = None

    def _build_app_layout(self) -> None:
        if self._login_screen:
            self._login_screen.destroy()
            self._login_screen = None

        self._app_frame = ttk.Frame(self, style="Screen.TFrame")
        self._app_frame.pack(fill="both", expand=True)
        self._app_frame.columnconfigure(1, weight=1)
        self._app_frame.rowconfigure(1, weight=1)

        nav = ttk.Frame(self._app_frame, padding=28, style="Navigation.TFrame")
        nav.grid(row=0, column=0, rowspan=3, sticky="ns")
        nav.columnconfigure(0, weight=1)

        ttk.Label(nav, text="RELlSE", style="NavBrand.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(nav, text="Логістика", style="NavFooter.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 20))

        ttk.Label(nav, text="Операції", style="NavSection.TLabel").grid(row=2, column=0, sticky="w", pady=(12, 6))

        self._nav_buttons: Dict[str, NavButton] = {}
        self._add_nav_button(nav, "Сканер", "scanner", row=3)
        self._add_nav_button(nav, "Історія", "history", row=4)
        self._add_nav_button(nav, "Помилки", "errors", row=5)
        self._statistics_button = self._add_nav_button(nav, "Статистика", "statistics", row=6)

        ttk.Label(nav, text="Адміністрування", style="NavSection.TLabel").grid(
            row=7, column=0, sticky="w", pady=(24, 6)
        )
        self._admin_button = NavButton(nav, text="Адмін панель", command=self._open_admin_panel_from_app)
        self._admin_button.grid(row=8, column=0, sticky="ew", pady=(0, 4))

        nav.rowconfigure(9, weight=1)
        ttk.Label(
            nav,
            text="Синхронізовано з мобільним застосунком",
            style="NavFooter.TLabel",
        ).grid(row=10, column=0, sticky="sw", pady=(40, 0))

        header = ttk.Frame(self._app_frame, padding=(32, 24), style="Header.TFrame")
        header.grid(row=0, column=1, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, textvariable=self.user_label, style="HeaderUser.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.role_label, style="HeaderRole.TLabel").grid(row=1, column=0, sticky="w")
        AccentButton(header, text="Вийти", command=self.logout).grid(row=0, column=1, rowspan=2, sticky="e")

        self._screen_container = ttk.Frame(self._app_frame, style="Screen.TFrame")
        self._screen_container.grid(row=1, column=1, sticky="nsew")
        self._screen_container.columnconfigure(0, weight=1)
        self._screen_container.rowconfigure(0, weight=1)

        footer = ttk.Frame(self._app_frame, padding=(32, 16), style="Footer.TFrame")
        footer.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Label(footer, textvariable=self._status_var, style="Status.TLabel").grid(row=0, column=0, sticky="w")

        self._screens = {
            "scanner": ScannerScreen(self._screen_container, self),
            "history": HistoryScreen(self._screen_container, self),
            "errors": ErrorsScreen(self._screen_container, self),
            "statistics": StatisticsScreen(self._screen_container, self),
        }
        for frame in self._screens.values():
            frame.grid(row=0, column=0, sticky="nsew")

        self._update_user_labels()
        self._update_access_controls()

    def _add_nav_button(
        self, parent: ttk.Frame, label: str, screen: str, *, row: int
    ) -> NavButton:
        btn = NavButton(parent, text=label, command=lambda s=screen: self.show_screen(s))
        btn.grid(row=row, column=0, sticky="ew", pady=2)
        self._nav_buttons[screen] = btn
        return btn

    def _open_admin_panel_from_app(self) -> None:
        password = simpledialog.askstring(
            "Панель адміністратора",
            "Введіть пароль адміністратора",
            show="*",
            parent=self,
        )
        if not password:
            return

        def task() -> Any:
            try:
                return self.api.admin_login(password.strip())
            except Exception as exc:
                return exc

        def done(result: Any) -> None:
            if isinstance(result, Exception):
                messagebox.showerror("Помилка", str(result), parent=self)
                return
            AdminPanel(self, result)

        self.run_async(task, done)

    # ---- navigation -----------------------------------------------------
    def show_screen(self, name: str) -> None:
        if not self._screen_container:
            return
        if name not in self._screens:
            return
        for key, frame in self._screens.items():
            if key == name:
                frame.tkraise()
            else:
                frame.lower()
        self._current_screen = name
        self._set_active_nav(name)
        self._screens[name].on_show()

    def _set_active_nav(self, name: str) -> None:
        for key, button in self._nav_buttons.items():
            style = "NavActive.TButton" if key == name else "Nav.TButton"
            button.configure(style=style)

    # ---- session management ---------------------------------------------
    def on_login_success(self, profile: UserProfile) -> None:
        self.state.set_profile(profile)
        self._build_app_layout()
        self.show_screen("scanner")
        self.schedule_queue_sync()

    def logout(self) -> None:
        if messagebox.askyesno("Вихід", "Вийти з облікового запису?", parent=self):
            self.state.set_profile(None)
            self._status_var.set("")
            self._show_login()

    def _update_user_labels(self) -> None:
        profile = self.state.profile
        if profile:
            self.user_label.set(profile.surname)
            role_map = {"admin": "Адмін", "operator": "Оператор", "viewer": "Перегляд"}
            label = role_map.get(profile.role, profile.role)
            self.role_label.set(f"Роль: {label}")
        else:
            self.user_label.set("Не авторизовано")
            self.role_label.set("")

    def _update_access_controls(self) -> None:
        profile = self.state.profile
        is_admin = profile is not None and profile.role == "admin"
        if self._statistics_button:
            self._statistics_button.configure(state="normal" if is_admin else "disabled")
        if self._admin_button:
            self._admin_button.configure(state="normal" if is_admin else "disabled")

    # ---- offline queue --------------------------------------------------
    def schedule_queue_sync(self, *, manual: bool = False) -> None:
        if self._sync_in_progress:
            return
        profile = self.state.profile
        if not profile:
            return
        pending = self.offline_queue.pending()
        if not pending:
            if manual:
                self._status_var.set("Офлайн записів немає")
            scanner = self._screens.get("scanner") if self._screens else None
            if scanner:
                scanner.update_queue_status()
            return

        self._sync_in_progress = True
        self._status_var.set("Синхронізація офлайн записів...")

        def task() -> Any:
            synced = 0
            for record in pending:
                try:
                    self.api.add_record(
                        profile.token,
                        record["user_name"],
                        record["boxid"],
                        record["ttn"],
                    )
                    self.offline_queue.delete(record["id"])
                    synced += 1
                except ApiError as exc:
                    if exc.status_code == -1:
                        return synced, False
                    return synced, False
                except Exception:
                    return synced, False
            return synced, True

        def done(result: Any) -> None:
            self._sync_in_progress = False
            scanner = self._screens.get("scanner") if self._screens else None
            if isinstance(result, Exception):
                self._status_var.set(f"Синхронізація не вдалася: {result}")
            else:
                synced, success = result
                if synced:
                    self._status_var.set(f"Синхронізовано записів: {synced}")
                elif not success:
                    self._status_var.set("Не вдалося синхронізувати офлайн записи")
                else:
                    self._status_var.set("Офлайн записів немає")
            if scanner:
                scanner.update_queue_status()

        self.run_async(task, done)

    # ---- async wrapper --------------------------------------------------
    def run_async(self, func: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        self._runner.run(func, callback)


def main() -> None:
    app = TrackingDesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()
