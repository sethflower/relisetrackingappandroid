import json
import hashlib
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, List

import tkinter as tk
from tkinter import messagebox, ttk

APP_TITLE = "Relise Tracking Desktop"
DATA_FILE = Path("tracking_desktop_data.json")


# ------------------------------
# Data management utilities
# ------------------------------
def _default_data() -> Dict[str, Any]:
    return {
        "users": {
            "admin": {
                "password": _hash_password("admin123"),
                "role": "administrator",
                "access_level": 3,
                "display_name": "Адміністратор",
            },
            "operator": {
                "password": _hash_password("operator"),
                "role": "operator",
                "access_level": 1,
                "display_name": "Оператор",
            },
        },
        "pending_users": [],
        "records": [],
        "errors": [],
        "offline_queue": [],
        "sync_log": [],
    }


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def load_data() -> Dict[str, Any]:
    if not DATA_FILE.exists():
        data = _default_data()
        save_data(data)
        return data

    with DATA_FILE.open("r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            messagebox.showwarning(
                "Пошкоджені дані",
                "Файл даних було пошкоджено. Буде створено новий профіль.",
            )
            data = _default_data()
            save_data(data)
        return data


def save_data(data: Dict[str, Any]) -> None:
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------
# Tkinter helpers
# ------------------------------
class AccentButton(ttk.Button):
    """Button with accent style."""

    def __init__(self, master=None, **kwargs):
        super().__init__(master, style="Accent.TButton", **kwargs)


class Header(ttk.Frame):
    def __init__(self, master, app: "TrackingApp", title: str):
        super().__init__(master, padding=(16, 16))
        self.app = app
        self.columnconfigure(0, weight=1)

        title_label = ttk.Label(self, text=title, font=("Segoe UI", 20, "bold"))
        title_label.grid(row=0, column=0, sticky="w")

        profile_frame = ttk.Frame(self)
        profile_frame.grid(row=0, column=1, sticky="e")

        ttk.Label(
            profile_frame,
            textvariable=app.current_user_display,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left", padx=(0, 12))

        ttk.Label(
            profile_frame,
            textvariable=app.connection_status,
            foreground="#1a73e8",
        ).pack(side="left", padx=(0, 12))

        ttk.Button(profile_frame, text="Вийти", command=app.logout).pack(side="left")


class Navigation(ttk.Frame):
    def __init__(self, master, app: "TrackingApp"):
        super().__init__(master, padding=12)
        self.app = app
        self.configure(style="Navigation.TFrame")

        ttk.Label(
            self,
            text="Навігація",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 12))

        self._add_button("Сканер", "scanner")
        self._add_button("Історія", "history")
        self._add_button("Помилки", "errors")
        self._add_button("Статистика", "statistics")

        self.admin_button = self._add_button("Адмін панель", "admin", require_admin=True)

    def _add_button(self, title: str, screen: str, require_admin: bool = False):
        btn = AccentButton(
            self,
            text=title,
            command=lambda: self.app.show_screen(screen),
        )
        btn.pack(fill="x", pady=4)

        if require_admin:
            def update_visibility(*_):
                btn.configure(state="normal" if self.app.is_admin else "disabled")

            self.app.is_admin_trace.append(update_visibility)
            update_visibility()
        return btn


class Screen(ttk.Frame):
    def __init__(self, master, app: "TrackingApp"):
        super().__init__(master)
        self.app = app

    def on_show(self):
        """Called each time screen becomes visible."""


class LoginScreen(Screen):
    def __init__(self, master, app: "TrackingApp"):
        super().__init__(master, app)
        self.configure(padding=48)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        card = ttk.Frame(self, padding=32, style="Card.TFrame")
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(card)
        notebook.grid(row=0, column=0, sticky="nsew")

        login_frame = ttk.Frame(notebook, padding=20)
        register_frame = ttk.Frame(notebook, padding=20)
        notebook.add(login_frame, text="Вхід")
        notebook.add(register_frame, text="Реєстрація")

        # Login tab
        login_frame.columnconfigure(1, weight=1)
        ttk.Label(login_frame, text="Прізвище", font=("Segoe UI", 11)).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self.login_user = tk.StringVar()
        ttk.Entry(login_frame, textvariable=self.login_user).grid(
            row=0, column=1, sticky="ew", padx=(8, 0)
        )

        ttk.Label(login_frame, text="Пароль", font=("Segoe UI", 11)).grid(
            row=1, column=0, sticky="w", pady=(12, 6)
        )
        self.login_password = tk.StringVar()
        ttk.Entry(login_frame, textvariable=self.login_password, show="*").grid(
            row=1, column=1, sticky="ew", padx=(8, 0)
        )

        AccentButton(login_frame, text="Увійти", command=self.handle_login).grid(
            row=2, column=0, columnspan=2, pady=(24, 0)
        )
        self.login_message = ttk.Label(login_frame, foreground="#d93025")
        self.login_message.grid(row=3, column=0, columnspan=2, pady=(12, 0))

        # Register tab
        register_frame.columnconfigure(1, weight=1)
        ttk.Label(register_frame, text="Прізвище", font=("Segoe UI", 11)).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self.register_user = tk.StringVar()
        ttk.Entry(register_frame, textvariable=self.register_user).grid(
            row=0, column=1, sticky="ew", padx=(8, 0)
        )

        ttk.Label(register_frame, text="Пароль", font=("Segoe UI", 11)).grid(
            row=1, column=0, sticky="w", pady=(12, 6)
        )
        self.register_password = tk.StringVar()
        ttk.Entry(register_frame, textvariable=self.register_password, show="*").grid(
            row=1, column=1, sticky="ew", padx=(8, 0)
        )

        ttk.Label(register_frame, text="Повторіть пароль", font=("Segoe UI", 11)).grid(
            row=2, column=0, sticky="w", pady=(12, 6)
        )
        self.register_confirm = tk.StringVar()
        ttk.Entry(register_frame, textvariable=self.register_confirm, show="*").grid(
            row=2, column=1, sticky="ew", padx=(8, 0)
        )

        AccentButton(register_frame, text="Надіслати заявку", command=self.handle_register).grid(
            row=3, column=0, columnspan=2, pady=(24, 0)
        )
        self.register_message = ttk.Label(register_frame)
        self.register_message.grid(row=4, column=0, columnspan=2, pady=(12, 0))

    def handle_login(self):
        user = self.login_user.get().strip().lower()
        password = self.login_password.get().strip()

        if not user or not password:
            self.login_message.config(text="Заповніть усі поля")
            return

        record = self.app.data["users"].get(user)
        if not record or record["password"] != _hash_password(password):
            self.login_message.config(text="Невірні дані для входу")
            return

        self.login_message.config(text="")
        self.login_user.set("")
        self.login_password.set("")
        self.app.login(user)

    def handle_register(self):
        user = self.register_user.get().strip().lower()
        password = self.register_password.get().strip()
        confirm = self.register_confirm.get().strip()

        if not user or not password or not confirm:
            self.register_message.config(text="Заповніть усі поля", foreground="#d93025")
            return

        if len(password) < 6:
            self.register_message.config(
                text="Пароль має містити щонайменше 6 символів", foreground="#d93025"
            )
            return

        if password != confirm:
            self.register_message.config(text="Паролі не співпадають", foreground="#d93025")
            return

        if user in self.app.data["users"]:
            self.register_message.config(text="Користувач вже існує", foreground="#d93025")
            return

        if any(p["surname"] == user for p in self.app.data["pending_users"]):
            self.register_message.config(text="Заявку вже відправлено", foreground="#d93025")
            return

        self.app.data["pending_users"].append(
            {
                "surname": user,
                "password": _hash_password(password),
                "requested_at": datetime.now().isoformat(),
            }
        )
        save_data(self.app.data)
        self.register_user.set("")
        self.register_password.set("")
        self.register_confirm.set("")
        self.register_message.config(
            text="Заявка відправлена. Очікуйте підтвердження адміністратора.",
            foreground="#188038",
        )


class DashboardScreen(Screen):
    def __init__(self, master, app: "TrackingApp"):
        super().__init__(master, app)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.navigation = Navigation(self, app)
        self.navigation.grid(row=0, column=0, sticky="ns")

        self.content = ttk.Frame(self, padding=(0, 0, 24, 24))
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(1, weight=1)

    def build(self):
        raise NotImplementedError

    def on_show(self):
        for child in list(self.content.children.values()):
            child.destroy()
        self.build()


class ScannerScreen(DashboardScreen):
    def build(self):
        Header(self.content, self.app, "Сканування накладних").grid(
            row=0, column=0, sticky="ew"
        )

        body = ttk.Frame(self.content, padding=24)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)

        card = ttk.Frame(body, padding=24, style="Card.TFrame")
        card.grid(row=0, column=0, columnspan=2, sticky="nsew")
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="Box ID", font=("Segoe UI", 12)).grid(row=0, column=0, sticky="w")
        self.box_id = tk.StringVar()
        ttk.Entry(card, textvariable=self.box_id, font=("Consolas", 14)).grid(
            row=0, column=1, sticky="ew", padx=(12, 0), pady=(0, 12)
        )

        ttk.Label(card, text="ТТН", font=("Segoe UI", 12)).grid(row=1, column=0, sticky="w")
        self.ttn = tk.StringVar()
        ttk.Entry(card, textvariable=self.ttn, font=("Consolas", 14)).grid(
            row=1, column=1, sticky="ew", padx=(12, 0)
        )

        controls = ttk.Frame(card)
        controls.grid(row=2, column=0, columnspan=2, pady=(16, 0))
        AccentButton(controls, text="Зберегти", command=self.handle_submit).pack(
            side="left"
        )
        ttk.Button(
            controls,
            text="Очистити",
            command=lambda: (self.box_id.set(""), self.ttn.set("")),
        ).pack(side="left", padx=(12, 0))

        status_card = ttk.Frame(body, padding=24, style="Card.TFrame")
        status_card.grid(row=0, column=2, sticky="nsew", padx=(24, 0))
        status_card.columnconfigure(0, weight=1)

        ttk.Label(status_card, text="Статус", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.status_var = tk.StringVar(value="Готово до сканування")
        ttk.Label(status_card, textvariable=self.status_var, wraplength=280).grid(
            row=1, column=0, sticky="w", pady=(8, 16)
        )

        AccentButton(
            status_card,
            text="Синхронізувати офлайн записи",
            command=self.sync_offline,
        ).grid(row=2, column=0, sticky="ew")

        ttk.Checkbutton(
            status_card,
            text="Працювати офлайн",
            variable=self.app.force_offline,
            command=self.toggle_connection_mode,
        ).grid(row=3, column=0, sticky="w", pady=(16, 0))

        recent_frame = ttk.Frame(body)
        recent_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(24, 0))
        recent_frame.columnconfigure(0, weight=1)

        ttk.Label(recent_frame, text="Останні операції", font=("Segoe UI", 12, "bold"))\
            .grid(row=0, column=0, sticky="w")

        columns = ("time", "box", "ttn", "status")
        tree = ttk.Treeview(recent_frame, columns=columns, show="headings", height=8)
        tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        for col, text, width in (
            ("time", "Час", 160),
            ("box", "Box ID", 120),
            ("ttn", "ТТН", 120),
            ("status", "Статус", 180),
        ):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="center")

        for record in reversed(self.app.data["records"][-15:]):
            tree.insert(
                "",
                "end",
                values=(
                    record["timestamp"],
                    record["boxid"],
                    record["ttn"],
                    record.get("note", "Успіх"),
                ),
            )

    def toggle_connection_mode(self):
        if self.app.force_offline.get():
            self.app.set_connection_status(False, note="Офлайн режим")
        else:
            self.app.set_connection_status(True, note="Підключено")

    def handle_submit(self):
        boxid = self.box_id.get().strip()
        ttn = self.ttn.get().strip()

        if not boxid or not ttn:
            self.status_var.set("Введіть Box ID та ТТН")
            return

        duplicate = next(
            (r for r in self.app.data["records"] if r["boxid"] == boxid and r["ttn"] == ttn),
            None,
        )
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
        record = {
            "boxid": boxid,
            "ttn": ttn,
            "timestamp": timestamp,
            "user": self.app.current_user,
        }

        if duplicate:
            note = "Дублікат"
            record["note"] = note
            self.app.data["errors"].append(
                {
                    "timestamp": timestamp,
                    "boxid": boxid,
                    "ttn": ttn,
                    "user": self.app.current_user,
                    "type": "duplicate",
                }
            )
            self.status_var.set(f"⚠️ {note}")
        elif not self.app.is_online:
            record["note"] = "Очікує синхронізації"
            self.app.data["offline_queue"].append(record)
            self.status_var.set("📦 Запис додано в офлайн чергу")
        else:
            record["note"] = "Успіх"
            self.app.data["records"].append(record)
            self.status_var.set("✅ Запис збережено")

        save_data(self.app.data)
        self.box_id.set("")
        self.ttn.set("")
        self.app.refresh_all()

    def sync_offline(self):
        if not self.app.is_online:
            self.status_var.set("Немає підключення до мережі")
            return

        queue = self.app.data["offline_queue"]
        if not queue:
            self.status_var.set("Офлайн черга порожня")
            return

        synced = 0
        for item in list(queue):
            record = dict(item)
            record["note"] = "Синхронізовано"
            self.app.data["records"].append(record)
            queue.remove(item)
            synced += 1

        self.app.data["sync_log"].append(
            {
                "timestamp": datetime.now().isoformat(),
                "user": self.app.current_user,
                "count": synced,
            }
        )
        save_data(self.app.data)
        self.status_var.set(f"Синхронізовано записів: {synced}")
        self.app.refresh_all()


class HistoryScreen(DashboardScreen):
    def build(self):
        Header(self.content, self.app, "Історія сканувань").grid(
            row=0, column=0, sticky="ew"
        )

        frame = ttk.Frame(self.content, padding=24)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        filters = ttk.Frame(frame)
        filters.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        ttk.Label(filters, text="Фільтр за користувачем:").pack(side="left")
        users = sorted(self.app.data["users"].keys())
        options = ["Усі"] + [self.app.data["users"][u].get("display_name", u) for u in users]
        self.selected_user = tk.StringVar(value="Усі")
        ttk.Combobox(filters, textvariable=self.selected_user, values=options, state="readonly")\
            .pack(side="left", padx=(8, 0))

        AccentButton(filters, text="Застосувати", command=self.app.refresh_all).pack(side="left", padx=(12, 0))

        columns = ("time", "user", "box", "ttn", "note")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings")
        self.tree.grid(row=1, column=0, sticky="nsew")
        for col, text, width in (
            ("time", "Час", 150),
            ("user", "Користувач", 140),
            ("box", "Box ID", 110),
            ("ttn", "ТТН", 110),
            ("note", "Примітка", 160),
        ):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width)

        self.populate()

    def populate(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        selection = getattr(self, "selected_user", tk.StringVar(value="Усі")).get()
        for record in sorted(self.app.data["records"], key=lambda r: r["timestamp"], reverse=True):
            display_name = self.app.data["users"].get(record["user"], {}).get("display_name", record["user"])
            if selection != "Усі" and display_name != selection:
                continue
            self.tree.insert(
                "",
                "end",
                values=(record["timestamp"], display_name, record["boxid"], record["ttn"], record.get("note", "")),
            )

    def on_show(self):
        super().on_show()
        self.populate()


class ErrorsScreen(DashboardScreen):
    def build(self):
        Header(self.content, self.app, "Помилки та офлайн записи").grid(
            row=0, column=0, sticky="ew"
        )

        body = ttk.Frame(self.content, padding=24)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        errors_frame = ttk.Frame(body)
        errors_frame.grid(row=0, column=0, sticky="nsew")
        errors_frame.columnconfigure(0, weight=1)
        ttk.Label(errors_frame, text="Останні помилки", font=("Segoe UI", 12, "bold"))\
            .grid(row=0, column=0, sticky="w")
        columns = ("time", "type", "box", "ttn", "user")
        error_tree = ttk.Treeview(errors_frame, columns=columns, show="headings", height=10)
        error_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        for col, text, width in (
            ("time", "Час", 140),
            ("type", "Тип", 120),
            ("box", "Box ID", 110),
            ("ttn", "ТТН", 110),
            ("user", "Користувач", 120),
        ):
            error_tree.heading(col, text=text)
            error_tree.column(col, width=width)

        for record in reversed(self.app.data["errors"][-20:]):
            error_tree.insert(
                "",
                "end",
                values=(
                    record["timestamp"],
                    "Дублікат" if record["type"] == "duplicate" else record["type"],
                    record["boxid"],
                    record["ttn"],
                    record["user"],
                ),
            )

        queue_frame = ttk.Frame(body)
        queue_frame.grid(row=0, column=1, sticky="nsew", padx=(24, 0))
        queue_frame.columnconfigure(0, weight=1)
        ttk.Label(queue_frame, text="Офлайн черга", font=("Segoe UI", 12, "bold"))\
            .grid(row=0, column=0, sticky="w")

        queue_columns = ("time", "box", "ttn", "user")
        queue_tree = ttk.Treeview(queue_frame, columns=queue_columns, show="headings", height=10)
        queue_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        for col, text, width in (
            ("time", "Час", 140),
            ("box", "Box ID", 110),
            ("ttn", "ТТН", 110),
            ("user", "Користувач", 120),
        ):
            queue_tree.heading(col, text=text)
            queue_tree.column(col, width=width)

        for record in self.app.data["offline_queue"]:
            queue_tree.insert(
                "",
                "end",
                values=(record.get("timestamp", "-"), record["boxid"], record["ttn"], record.get("user", "-")),
            )


class StatisticsScreen(DashboardScreen):
    def build(self):
        Header(self.content, self.app, "Статистика продуктивності").grid(
            row=0, column=0, sticky="ew"
        )

        body = ttk.Frame(self.content, padding=24)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        totals_frame = ttk.Frame(body, padding=24, style="Card.TFrame")
        totals_frame.grid(row=0, column=0, sticky="nsew")
        totals_frame.columnconfigure(0, weight=1)
        ttk.Label(totals_frame, text="Загальна кількість записів", font=("Segoe UI", 12, "bold"))\
            .grid(row=0, column=0, sticky="w")
        ttk.Label(
            totals_frame,
            text=str(len(self.app.data["records"])),
            font=("Segoe UI", 32, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(12, 0))

        per_user_frame = ttk.Frame(body, padding=24, style="Card.TFrame")
        per_user_frame.grid(row=0, column=1, sticky="nsew", padx=(24, 0))
        per_user_frame.columnconfigure(0, weight=1)
        ttk.Label(per_user_frame, text="Записів за користувачами", font=("Segoe UI", 12, "bold"))\
            .grid(row=0, column=0, sticky="w")

        per_user_tree = ttk.Treeview(per_user_frame, columns=("user", "count"), show="headings", height=6)
        per_user_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        per_user_tree.heading("user", text="Користувач")
        per_user_tree.heading("count", text="Кількість")
        per_user_tree.column("user", width=160)
        per_user_tree.column("count", width=80, anchor="center")

        stats = {}
        for record in self.app.data["records"]:
            stats.setdefault(record["user"], 0)
            stats[record["user"]] += 1

        for user, count in sorted(stats.items(), key=lambda item: item[1], reverse=True):
            name = self.app.data["users"].get(user, {}).get("display_name", user)
            per_user_tree.insert("", "end", values=(name, count))

        timeline_frame = ttk.Frame(body, padding=24, style="Card.TFrame")
        timeline_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(24, 0))
        timeline_frame.columnconfigure(0, weight=1)
        ttk.Label(
            timeline_frame,
            text="Динаміка за датами",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w")

        timeline_tree = ttk.Treeview(timeline_frame, columns=("date", "count"), show="headings", height=6)
        timeline_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        timeline_tree.heading("date", text="Дата")
        timeline_tree.heading("count", text="Записів")
        timeline_tree.column("date", width=160)
        timeline_tree.column("count", width=80, anchor="center")

        per_day = {}
        for record in self.app.data["records"]:
            if "timestamp" in record:
                day = record["timestamp"].split(" ")[0]
            else:
                day = date.today().strftime("%d.%m.%Y")
            per_day.setdefault(day, 0)
            per_day[day] += 1

        for day, count in sorted(per_day.items(), reverse=True):
            timeline_tree.insert("", "end", values=(day, count))


class AdminPanelScreen(DashboardScreen):
    def build(self):
        Header(self.content, self.app, "Панель адміністратора").grid(
            row=0, column=0, sticky="ew"
        )

        body = ttk.Frame(self.content, padding=24)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        pending_frame = ttk.Frame(body, padding=24, style="Card.TFrame")
        pending_frame.grid(row=0, column=0, sticky="nsew")
        pending_frame.columnconfigure(0, weight=1)
        ttk.Label(pending_frame, text="Запити на реєстрацію", font=("Segoe UI", 12, "bold"))\
            .grid(row=0, column=0, sticky="w")

        self.pending_tree = ttk.Treeview(
            pending_frame,
            columns=("user", "time"),
            show="headings",
            height=8,
        )
        self.pending_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.pending_tree.heading("user", text="Прізвище")
        self.pending_tree.heading("time", text="Подано")
        self.pending_tree.column("user", width=140)
        self.pending_tree.column("time", width=180)

        actions = ttk.Frame(pending_frame)
        actions.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        AccentButton(actions, text="Підтвердити", command=self.approve).pack(side="left")
        ttk.Button(actions, text="Видалити", command=self.reject).pack(side="left", padx=(12, 0))

        users_frame = ttk.Frame(body, padding=24, style="Card.TFrame")
        users_frame.grid(row=0, column=1, sticky="nsew", padx=(24, 0))
        users_frame.columnconfigure(0, weight=1)
        ttk.Label(users_frame, text="Користувачі", font=("Segoe UI", 12, "bold"))\
            .grid(row=0, column=0, sticky="w")

        self.users_tree = ttk.Treeview(users_frame, columns=("user", "role"), show="headings", height=8)
        self.users_tree.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.users_tree.heading("user", text="Прізвище")
        self.users_tree.heading("role", text="Роль")
        self.users_tree.column("user", width=140)
        self.users_tree.column("role", width=180)

        AccentButton(users_frame, text="Скинути пароль", command=self.reset_password).grid(
            row=2, column=0, sticky="w"
        )

        self.populate()

    def populate(self):
        for tree in (self.pending_tree, self.users_tree):
            for item in tree.get_children():
                tree.delete(item)

        for pending in self.app.data["pending_users"]:
            self.pending_tree.insert(
                "",
                "end",
                values=(pending["surname"], pending["requested_at"].replace("T", " ")),
            )

        for username, info in sorted(self.app.data["users"].items()):
            role = info.get("role", "operator")
            display = info.get("display_name", username)
            self.users_tree.insert("", "end", values=(display, role))

    def approve(self):
        selection = self.pending_tree.selection()
        if not selection:
            return

        item = self.pending_tree.item(selection[0])
        surname = item["values"][0]
        request = next((p for p in self.app.data["pending_users"] if p["surname"] == surname), None)
        if not request:
            return

        self.app.data["pending_users"].remove(request)
        self.app.data["users"][surname] = {
            "password": request["password"],
            "role": "operator",
            "access_level": 1,
            "display_name": surname.title(),
        }
        save_data(self.app.data)
        self.populate()
        self.app.refresh_all()

    def reject(self):
        selection = self.pending_tree.selection()
        if not selection:
            return
        surname = self.pending_tree.item(selection[0])["values"][0]
        self.app.data["pending_users"] = [
            p for p in self.app.data["pending_users"] if p["surname"] != surname
        ]
        save_data(self.app.data)
        self.populate()

    def reset_password(self):
        selection = self.users_tree.selection()
        if not selection:
            return
        surname = self.users_tree.item(selection[0])["values"][0]
        for username, info in self.app.data["users"].items():
            display = info.get("display_name", username)
            if display == surname:
                self.app.data["users"][username]["password"] = _hash_password("password123")
                save_data(self.app.data)
                messagebox.showinfo(
                    "Пароль скинуто",
                    f"Новий пароль для {display}: password123",
                )
                return


class TrackingApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x780")
        self.minsize(1080, 680)
        self.configure(bg="#f1f3f4")

        self.style = ttk.Style(self)
        self._configure_style()

        self.data = load_data()
        self.current_user = None
        self.current_user_display = tk.StringVar(value="Гість")
        self.connection_status = tk.StringVar(value="Підключено")
        self.force_offline = tk.BooleanVar(value=False)

        self.is_admin_trace: List[Any] = []

        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

        self.screens: Dict[str, Screen] = {}
        self.show_screen("login")

    # --------------- state properties ---------------
    @property
    def is_online(self) -> bool:
        return not self.force_offline.get()

    @property
    def is_admin(self) -> bool:
        if not self.current_user:
            return False
        info = self.data["users"].get(self.current_user, {})
        return info.get("role") == "administrator" or info.get("access_level", 0) >= 3

    # --------------- UI actions ---------------
    def _configure_style(self):
        self.style.theme_use("clam")
        self.style.configure("TFrame", background="#f5f7fb")
        self.style.configure("Card.TFrame", background="white", relief="flat")
        self.style.configure("Navigation.TFrame", background="#e8f0fe")
        self.style.configure("TLabel", background="#f5f7fb", font=("Segoe UI", 10))
        self.style.configure("Card.TLabel", background="white")
        self.style.configure("Accent.TButton", font=("Segoe UI", 11, "bold"))
        self.style.map("Accent.TButton", background=[("active", "#0b57d0")])

    def show_screen(self, name: str):
        if name != "login" and not self.current_user:
            messagebox.showwarning("Необхідна авторизація", "Увійдіть до системи")
            name = "login"

        if name == "admin" and not self.is_admin:
            messagebox.showwarning("Доступ обмежено", "Потрібні права адміністратора")
            name = "scanner"

        if name not in self.screens:
            screen = self._create_screen(name)
            self.screens[name] = screen
            screen.grid(row=0, column=0, sticky="nsew")
        screen = self.screens[name]
        screen.tkraise()
        screen.on_show()

    def _create_screen(self, name: str) -> Screen:
        if name == "login":
            return LoginScreen(self.container, self)
        mapping = {
            "scanner": ScannerScreen,
            "history": HistoryScreen,
            "errors": ErrorsScreen,
            "statistics": StatisticsScreen,
            "admin": AdminPanelScreen,
        }
        cls = mapping.get(name)
        if not cls:
            raise ValueError(f"Unknown screen: {name}")
        return cls(self.container, self)

    def login(self, username: str):
        self.current_user = username
        info = self.data["users"].get(username, {})
        display = info.get("display_name", username)
        self.current_user_display.set(display)
        self.set_connection_status(True, note="Підключено")
        self.refresh_all()
        self.show_screen("scanner")

    def logout(self):
        self.current_user = None
        self.current_user_display.set("Гість")
        self.show_screen("login")

    def refresh_all(self):
        save_data(self.data)
        for name, screen in self.screens.items():
            if name != "login":
                screen.on_show()
        for callback in self.is_admin_trace:
            callback()

    def set_connection_status(self, online: bool, note: str = ""):
        status = "Онлайн" if online else "Офлайн"
        if note:
            status = f"{status} — {note}"
        self.connection_status.set(status)

    # --------------- events ---------------
    def on_close(self):
        save_data(self.data)
        self.destroy()


if __name__ == "__main__":
    app = TrackingApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
