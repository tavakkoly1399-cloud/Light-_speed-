# -*- coding: utf-8 -*-
"""
Light Speed ⚡🔥
اپلیکیشن اندرویدی مدیریت کانفیگ - نمایش تاریخ انقضا و حجم باقی‌مانده
"""

import json
import os
import threading
from datetime import datetime, timezone

import requests
from kivy.app import App
from kivy.clock import mainthread
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

DATA_FILE_NAME = "lightspeed_subs.json"


def human_size(num_bytes):
    if num_bytes is None:
        return "نامشخص"
    try:
        num_bytes = float(num_bytes)
    except (TypeError, ValueError):
        return "نامشخص"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"


def human_date(ts):
    if ts is None:
        return "نامشخص"
    try:
        ts = int(ts)
        if ts <= 0:
            return "نامحدود"
        if ts > 10_000_000_000:
            ts //= 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError, OverflowError):
        return "نامشخص"


def days_left(ts):
    if ts is None:
        return None
    try:
        ts = int(ts)
        if ts <= 0:
            return None
        if ts > 10_000_000_000:
            ts //= 1000
        delta = datetime.fromtimestamp(ts, tz=timezone.utc) - datetime.now(timezone.utc)
        return delta.days
    except (ValueError, OSError, OverflowError):
        return None


def parse_userinfo_header(header_value):
    info = {}
    if not header_value:
        return info
    for part in header_value.split(";"):
        part = part.strip()
        if "=" in part:
            key, val = part.split("=", 1)
            key = key.strip().lower()
            try:
                info[key] = int(val.strip())
            except ValueError:
                info[key] = val.strip()
    return info


def fetch_subscription(url):
    headers = {"User-Agent": "v2rayNG/1.8.29"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "⏱️ زمان اتصال تمام شد."}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "🔌 خطای اتصال (اینترنت/فیلترینگ را بررسی کنید)."}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"❌ خطای درخواست: {e}"}

    if resp.status_code != 200:
        return {"ok": False, "error": f"❌ سرور کد {resp.status_code} برگرداند."}

    userinfo_raw = resp.headers.get("subscription-userinfo") or resp.headers.get(
        "Subscription-Userinfo"
    )
    userinfo = parse_userinfo_header(userinfo_raw)
    return {
        "ok": True,
        "data": {
            "upload": userinfo.get("upload"),
            "download": userinfo.get("download"),
            "total": userinfo.get("total"),
            "expire": userinfo.get("expire"),
        },
    }


def format_result(name, result):
    lines = [f"📡 {name}"]
    if not result["ok"]:
        lines.append(f"   {result['error']}")
        return "\n".join(lines)

    d = result["data"]
    upload = d.get("upload") or 0
    download = d.get("download") or 0
    total = d.get("total")
    used = upload + download
    remaining = (total - used) if total is not None else None

    if total is None:
        lines.append("   ⚠️ این سرور اطلاعات حجم/تاریخ ارسال نمی‌کند.")
    else:
        lines.append(f"   حجم کل: {human_size(total)}")
        lines.append(f"   مصرف‌شده: {human_size(used)}")
        lines.append(f"   باقی‌مانده: {human_size(remaining)}")

    expire = d.get("expire")
    dl = days_left(expire)
    line = f"   انقضا: {human_date(expire)}"
    if dl is not None:
        if dl < 0:
            line += "  ⚠️ منقضی شده!"
        elif dl <= 3:
            line += f"  ⚠️ {dl} روز مانده!"
        else:
            line += f"  ({dl} روز مانده)"
    lines.append(line)
    return "\n".join(lines)


class LightSpeedApp(App):
    title = "Light Speed"

    def build(self):
        self.data_path = os.path.join(self.user_data_dir, DATA_FILE_NAME)
        self.subs = self.load_subs()

        root = BoxLayout(orientation="vertical", padding=10, spacing=10)

        self.input = TextInput(
            hint_text="لینک ساب‌اسکریپشن را اینجا وارد کنید",
            multiline=False,
            size_hint_y=None,
            height=50,
        )
        root.add_widget(self.input)

        btn_row = BoxLayout(size_hint_y=None, height=50, spacing=10)
        add_btn = Button(text="افزودن +")
        add_btn.bind(on_release=self.add_sub)
        refresh_btn = Button(text="بروزرسانی همه")
        refresh_btn.bind(on_release=self.refresh_all)
        btn_row.add_widget(add_btn)
        btn_row.add_widget(refresh_btn)
        root.add_widget(btn_row)

        self.result_label = Label(
            text="Light Speed\nهنوز چیزی اضافه نشده.",
            size_hint_y=None,
            halign="right",
            valign="top",
        )
        self.result_label.bind(
            texture_size=lambda inst, val: setattr(inst, "height", val[1])
        )
        self.result_label.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None))
        )

        scroll = ScrollView()
        scroll.add_widget(self.result_label)
        root.add_widget(scroll)

        self.refresh_all(None)
        return root

    def load_subs(self):
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def save_subs(self):
        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.subs, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def add_sub(self, instance):
        url = self.input.text.strip()
        if not url.startswith(("http://", "https://")):
            self.show_popup("خطا", "لینک معتبر نیست.")
            return
        self.subs.append(url)
        self.save_subs()
        self.input.text = ""
        self.refresh_all(None)

    def refresh_all(self, instance):
        if not self.subs:
            self.result_label.text = "هیچ ساب‌اسکریپشنی ثبت نشده."
            return
        self.result_label.text = "در حال بررسی..."
        threading.Thread(target=self._refresh_thread, daemon=True).start()

    def _refresh_thread(self):
        blocks = []
        for i, url in enumerate(self.subs, 1):
            result = fetch_subscription(url)
            blocks.append(format_result(f"ساب {i}", result))
        self._set_result("\n\n".join(blocks))

    @mainthread
    def _set_result(self, text):
        self.result_label.text = text

    def show_popup(self, title, message):
        popup = Popup(title=title, content=Label(text=message), size_hint=(0.8, 0.3))
        popup.open()


if __name__ == "__main__":
    LightSpeedApp().run()
