#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Light Speed ⚡🔥
ابزار مدیریت کانفیگ‌های V2Ray / Shadowsocks / Trojan
نمایش تاریخ انقضا و حجم باقی‌مانده

سازگار با: ویندوز، لینوکس، مک، اندروید (Termux یا Pydroid3)

نصب پیش‌نیاز:
    pip install requests

اجرا:
    python config_manager.py
"""

import json
import os
import re
import sys
import base64
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote

try:
    import requests
except ImportError:
    print("❌ کتابخانه requests نصب نیست.")
    print("   دستور نصب: pip install requests")
    sys.exit(1)

DATA_FILE = os.path.join(os.path.expanduser("~"), ".config_manager_data.json")
TIMEOUT = 10  # ثانیه، برای جلوگیری از هنگ کردن برنامه در صورت قطعی اینترنت


# ==================== ابزارهای کمکی ====================

def human_size(num_bytes):
    """تبدیل بایت به واحد خوانا (KB/MB/GB/...)"""
    if num_bytes is None:
        return "نامشخص"
    try:
        num_bytes = float(num_bytes)
    except (TypeError, ValueError):
        return "نامشخص"
    if num_bytes < 0:
        return "نامشخص"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"


def human_date(ts):
    """تبدیل timestamp یونیکس (ثانیه یا میلی‌ثانیه) به تاریخ خوانا"""
    if ts is None:
        return "نامشخص"
    try:
        ts = int(ts)
        if ts <= 0:
            return "نامحدود"
        # بعضی پنل‌ها timestamp رو به میلی‌ثانیه می‌فرستن
        if ts > 10_000_000_000:
            ts = ts // 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError, OverflowError):
        return "نامشخص"


def days_left(ts):
    """چند روز تا انقضا مونده؛ None یعنی نامشخص یا نامحدود"""
    if ts is None:
        return None
    try:
        ts = int(ts)
        if ts <= 0:
            return None
        if ts > 10_000_000_000:
            ts = ts // 1000
        delta = datetime.fromtimestamp(ts, tz=timezone.utc) - datetime.now(timezone.utc)
        return delta.days
    except (ValueError, OSError, OverflowError):
        return None


def safe_b64decode(data):
    """دیکد base64 با رفع خودکار مشکل padding (خیلی از پنل‌ها padding رو حذف می‌کنن)"""
    if not data:
        return None
    data = data.strip().replace("\n", "").replace("\r", "")
    data += "=" * (-len(data) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            return decoder(data).decode("utf-8", errors="ignore")
        except Exception:
            continue
    return None


# ==================== ذخیره‌سازی محلی ====================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"subscriptions": [], "single_configs": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("subscriptions", [])
            data.setdefault("single_configs", [])
            return data
    except (json.JSONDecodeError, OSError):
        print("⚠️ فایل داده قابل خواندن نبود، یک فایل جدید ساخته می‌شود.")
        return {"subscriptions": [], "single_configs": []}


def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"❌ خطا در ذخیره‌سازی روی دیسک: {e}")


# ==================== پردازش ساب‌اسکریپشن ====================

def parse_userinfo_header(header_value):
    """
    نمونه‌ی هدر subscription-userinfo:
    upload=123; download=456; total=789000000; expire=1735689600
    """
    info = {}
    if not header_value:
        return info
    for part in header_value.split(";"):
        part = part.strip()
        if "=" in part:
            key, val = part.split("=", 1)
            key = key.strip().lower()
            val = val.strip()
            try:
                info[key] = int(val)
            except ValueError:
                info[key] = val
    return info


def fetch_subscription(url):
    """
    دریافت اطلاعات یک لینک ساب‌اسکریپشن.
    خروجی: dict شامل ok و data/error
    """
    headers = {
        # بعضی پنل‌ها بدون User-Agent مناسب پاسخ نمی‌دن یا لیست کوچیک‌تری برمی‌گردونن
        "User-Agent": "v2rayNG/1.8.29"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "⏱️ زمان اتصال تمام شد (Timeout)."}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "🔌 خطای اتصال (اینترنت یا فیلترینگ را بررسی کنید)."}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"❌ خطای درخواست: {e}"}

    if resp.status_code != 200:
        return {"ok": False, "error": f"❌ سرور کد وضعیت {resp.status_code} برگرداند."}

    userinfo_raw = (
        resp.headers.get("subscription-userinfo")
        or resp.headers.get("Subscription-Userinfo")
    )
    userinfo = parse_userinfo_header(userinfo_raw)

    # تعداد کانفیگ‌های داخل ساب، فقط برای اطلاع کاربر (اختیاری)
    body = resp.text.strip()
    config_count = None
    decoded = safe_b64decode(body)
    if decoded and "://" in decoded:
        config_count = len([l for l in decoded.splitlines() if l.strip()])
    elif "://" in body:
        config_count = len([l for l in body.splitlines() if l.strip() and "://" in l])

    return {
        "ok": True,
        "data": {
            "upload": userinfo.get("upload"),
            "download": userinfo.get("download"),
            "total": userinfo.get("total"),
            "expire": userinfo.get("expire"),
            "config_count": config_count,
        },
    }


def print_subscription_status(name, result):
    print("─" * 50)
    print(f"📡 {name}")
    if not result["ok"]:
        print(f"   وضعیت: {result['error']}")
        return

    d = result["data"]
    upload = d.get("upload") or 0
    download = d.get("download") or 0
    total = d.get("total")
    used = upload + download
    remaining = (total - used) if total is not None else None

    if total is None:
        print("   ⚠️ سرور این ساب هدر حجم/تاریخ (subscription-userinfo) را نمی‌فرستد.")
    else:
        print(f"   حجم کل:        {human_size(total)}")
        print(f"   مصرف‌شده:       {human_size(used)}")
        print(f"   حجم باقی‌مانده:  {human_size(remaining)}")

    expire = d.get("expire")
    dl = days_left(expire)
    line = f"   تاریخ انقضا:    {human_date(expire)}"
    if dl is not None:
        if dl < 0:
            line += "  ⚠️ منقضی شده!"
        elif dl <= 3:
            line += f"  ⚠️ فقط {dl} روز مانده!"
        else:
            line += f"  ({dl} روز مانده)"
    print(line)

    if d.get("config_count"):
        print(f"   تعداد کانفیگ‌های داخل ساب: {d['config_count']}")


# ==================== پردازش کانفیگ تکی ====================

def parse_single_config(link):
    """
    استخراج نام/سرور از یک لینک کانفیگ تکی.
    توجه: کانفیگ تکی معمولاً حجم/تاریخ انقضای واقعی را در خود ندارد؛
    آن اطلاعات فقط از پاسخ لینک ساب‌اسکریپشن پنل قابل دریافت است.
    """
    link = link.strip()
    if not link:
        return None

    info = {"protocol": None, "remark": None, "server": None, "port": None}

    try:
        if link.startswith("vmess://"):
            decoded = safe_b64decode(link[len("vmess://"):])
            if not decoded:
                return None
            obj = json.loads(decoded)
            info["protocol"] = "vmess"
            info["remark"] = obj.get("ps")
            info["server"] = obj.get("add")
            info["port"] = obj.get("port")

        elif link.startswith(("vless://", "trojan://", "ss://")):
            parsed = urlparse(link)
            info["protocol"] = parsed.scheme
            info["server"] = parsed.hostname
            info["port"] = parsed.port
            info["remark"] = unquote(parsed.fragment) if parsed.fragment else None
        else:
            return None
    except (json.JSONDecodeError, ValueError, TypeError):
        return None

    return info


def extract_expiry_from_remark(remark):
    """
    تلاش best-effort برای پیدا کردن یک تاریخ در نام کانفیگ
    (مثلا وقتی خود فروشنده تاریخ رو داخل remark نوشته: 'DE | Exp 2026-11-01')
    تضمینی برای وجود یا صحت این تاریخ نیست.
    """
    if not remark:
        return None
    match = re.search(r"(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})", remark)
    return match.group(1) if match else None


def print_single_config_status(info):
    print("─" * 50)
    name = info.get("remark") or info.get("server") or "کانفیگ بدون نام"
    print(f"🔗 {name}")
    print(f"   پروتکل: {info.get('protocol')}")
    print(f"   سرور:   {info.get('server')}:{info.get('port')}")
    guess_date = extract_expiry_from_remark(info.get("remark"))
    if guess_date:
        print(f"   تاریخ احتمالی (برداشت‌شده از نام): {guess_date}")
    print("   ⚠️ حجم/تاریخ دقیق در این نوع لینک موجود نیست؛ فقط لینک ساب‌اسکریپشن پنل این اطلاعات را می‌دهد.")


# ==================== منوی اصلی ====================

def add_subscription(data):
    url = input("لینک ساب‌اسکریپشن را وارد کن: ").strip()
    if not url.startswith(("http://", "https://")):
        print("❌ لینک معتبر نیست (باید با http:// یا https:// شروع شود).")
        return
    name = input("یک نام برای این ساب انتخاب کن (اختیاری، اینتر برای رد شدن): ").strip() or url
    data["subscriptions"].append({"name": name, "url": url})
    save_data(data)
    print("✅ اضافه شد.")


def add_single_config(data):
    link = input("لینک کانفیگ را وارد کن (vmess/vless/trojan/ss): ").strip()
    info = parse_single_config(link)
    if info is None:
        print("❌ فرمت کانفیگ شناخته نشد یا خراب است.")
        return
    data["single_configs"].append(link)
    save_data(data)
    print("✅ اضافه شد.")


def show_all_status(data):
    if not data["subscriptions"] and not data["single_configs"]:
        print("هیچ چیزی ثبت نشده. اول با گزینه 1 یا 2 چیزی اضافه کن.")
        return

    for sub in data["subscriptions"]:
        result = fetch_subscription(sub["url"])
        print_subscription_status(sub["name"], result)

    for link in data["single_configs"]:
        info = parse_single_config(link)
        if info:
            print_single_config_status(info)
        else:
            print("─" * 50)
            print(f"❌ این کانفیگ دیگر معتبر نیست: {link[:50]}...")
    print("─" * 50)


def remove_item(data):
    all_items = []
    for i, sub in enumerate(data["subscriptions"]):
        all_items.append(("sub", i, f"[ساب] {sub['name']}"))
    for i, link in enumerate(data["single_configs"]):
        all_items.append(("single", i, f"[تکی] {link[:40]}..."))

    if not all_items:
        print("چیزی برای حذف وجود ندارد.")
        return

    for idx, (_, _, label) in enumerate(all_items, 1):
        print(f"{idx}. {label}")

    choice = input("شماره مورد نظر برای حذف (یا Enter برای انصراف): ").strip()
    if not choice:
        return
    if not choice.isdigit() or not (1 <= int(choice) <= len(all_items)):
        print("❌ عدد نامعتبر.")
        return

    kind, real_idx, _ = all_items[int(choice) - 1]
    if kind == "sub":
        data["subscriptions"].pop(real_idx)
    else:
        data["single_configs"].pop(real_idx)
    save_data(data)
    print("✅ حذف شد.")


def main():
    data = load_data()
    while True:
        print("\n=== ⚡ Light Speed 🔥 ===")
        print("1. افزودن لینک ساب‌اسکریپشن")
        print("2. افزودن کانفیگ تکی")
        print("3. نمایش وضعیت همه (تاریخ انقضا / حجم باقی‌مانده)")
        print("4. حذف یک مورد")
        print("0. خروج")
        choice = input("انتخاب: ").strip()

        if choice == "1":
            add_subscription(data)
        elif choice == "2":
            add_single_config(data)
        elif choice == "3":
            show_all_status(data)
        elif choice == "4":
            remove_item(data)
        elif choice == "0":
            print("خدانگهدار 👋")
            break
        else:
            print("❌ گزینه نامعتبر.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nخدانگهدار 👋")
        sys.exit(0)
