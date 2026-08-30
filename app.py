#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
import ctypes
import contextlib
import subprocess
import requests
from seleniumbase import SB

LOGIN_URL = "https://justrunmy.app/id/Account/Login"

# 账号密码和 TG 推送配置
EMAIL = os.environ.get("JUSTRUNMY_EMAIL") or ""        # 账号
PASSWORD = os.environ.get("JUSTRUNMY_PASSWORD") or ""  # 密码
TG_CHAT_ID = os.environ.get("TG_CHAT_ID") or ""        # TG 通知 chat_id（可选）
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""     # TG 通知 bot token（和chat_id同时填写）


def send_tg_message(status_icon, status_text, time_left):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送。")
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)

    if '@' in EMAIL:
        name, domain = EMAIL.split('@', 1)
        if len(name) > 4:
            masked_email = f"{name[:2]}****{name[-2:]}@{domain}"
        else:
            masked_email = f"{name}@{domain}"
    else:
        masked_email = EMAIL[:2] + '****'

    text = (
        f"🇩🇪 JustRunMy 续期通知\n\n"
        f"{status_icon} {status_text}\n"
        f"👤 账号: {masked_email}\n"
        f"⏱️ Expiration time: {time_left}\n"
        f"⏱️ Running time: {current_time_str}"
    )

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}

    try:
        # 将 time_left 规范为短格式，例如 "1d 11:59"
        def _short_time(s):
            if not s:
                return s
            m = re.search(r"(\d+)\s*(?:d|day|days)\b\s*([0-2]?\d:\d{2})", s, re.I)
            if m:
                return f"{m.group(1)}d {m.group(2)}"
            m = re.search(r"([0-2]?\d:\d{2})", s)
            if m:
                return m.group(1)
            return s

        payload = {"chat_id": TG_CHAT_ID, "text": text.replace(str(time_left), _short_time(str(time_left)))}
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("  📩 Telegram 通知发送成功！")
        else:
            print(f"  ⚠️ Telegram 通知发送失败: {r.text}")
    except Exception as e:
        print(f"  ⚠️ Telegram 通知发送异常: {e}")


_EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden')
            el.style.overflow = 'visible';
        el.style.minWidth = 'max-content';
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.includes('challenges.cloudflare.com')) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1';
        }
    });
    return 'done';
})()
"""

_EXISTS_JS = """
(function(){
    return document.querySelector('input[name="cf-turnstile-response"]') !== null;
})()
"""

_SOLVED_JS = """
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()
"""

_COORDS_JS = """
(function(){
    var iframes = document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        var src = iframes[i].src || '';
        if (src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges')) {
            var r = iframes[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
        }
    }
    var inp = document.querySelector('input[name="cf-turnstile-response"]');
    if (inp) {
        var p = inp.parentElement;
        for (var j = 0; j < 5; j++) {
            if (!p) break;
            var r = p.getBoundingClientRect();
            if (r.width > 100 && r.height > 30)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
            p = p.parentElement;
        }
    }
    return null;
})()
"""

_WININFO_JS = """
(function(){
    return {
        sx: window.screenX || 0,
        sy: window.screenY || 0,
        oh: window.outerHeight,
        ih: window.innerHeight
    };
})()
"""


def js_fill_input(sb, selector: str, text: str):
    safe_text = text.replace("\\", "\\\\").replace('"', '\\"')
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        if (nativeInputValueSetter) {{
            nativeInputValueSetter.call(el, "{safe_text}");
        }} else {{
            el.value = "{safe_text}";
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """)


def _activate_window():
    if os.name == "nt":
        return

    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls], capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _windows_mouse_click(x: int, y: int):
    try:
        user32 = ctypes.windll.user32
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.08)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.03)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
    except Exception:
        pass


def _xdotool_click(x: int, y: int):
    if os.name == "nt":
        _windows_mouse_click(x, y)
        return

    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")


def _click_turnstile(sb):
    try:
        coords = sb.execute_script(_COORDS_JS)
    except Exception as e:
        print(f"⚠️ 获取 Turnstile 坐标失败: {e}")
        return
    if not coords:
        print("⚠️ 无法定位 Turnstile 坐标")
        return
    try:
        wi = sb.execute_script(_WININFO_JS)
    except Exception:
        wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}

    bar = wi["oh"] - wi["ih"]
    ax = coords["cx"] + wi["sx"]
    ay = coords["cy"] + wi["sy"] + bar
    print(f"  🖱️ 物理级点击 Turnstile ({ax}, {ay})")
    _xdotool_click(ax, ay)


def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)

    if sb.execute_script(_SOLVED_JS):
        print("✅ 已静默通过")
        return True

    for _ in range(3):
        try:
            sb.execute_script(_EXPAND_JS)
        except Exception:
            pass
        time.sleep(0.5)

    for attempt in range(5):
        if sb.execute_script(_SOLVED_JS):
            print(f"✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
            return True
        try:
            sb.execute_script(_EXPAND_JS)
        except Exception:
            pass
        time.sleep(0.3)

        _click_turnstile(sb)

        for _ in range(8):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                print(f"✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
                return True
        print(f"⚠️ 第 {attempt + 1} 次未通过，重试...")

    print("❌ Turnstile 5 次验证均失败")
    return False


def login(sb) -> bool:
    print(f"🌐 打开登录页面: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=8)
    time.sleep(2)

    try:
        clicked = sb.execute_script("""
            var btns = document.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                if (btns[i].textContent.trim() === 'Accept All') {
                    btns[i].click();
                    return true;
                }
            }
            return false;
        """)
        if clicked:
            print("🍪 已关闭 Cookie 弹窗")
            time.sleep(1)
    except Exception:
        pass

    time.sleep(3)
    csrf_token = None
    try:
        csrf_token = sb.get_attribute('input[name="__RequestVerificationToken"]', 'value')
        if csrf_token:
            print("🔑 成功获取到验证令牌")
        else:
            print("⚠️ 警告：无法获取验证令牌，尝试继续...")
    except Exception as e:
        print(f"⚠️ 获取验证令牌时出错: {e}")

    try:
        sb.wait_for_element('input#login', timeout=15)
        print("📧 填写邮箱...")
        js_fill_input(sb, 'input#login', EMAIL)
        time.sleep(1)
        sb.wait_for_element('input#password', timeout=10)
        print("🔑 填写密码...")
        js_fill_input(sb, 'input#password', PASSWORD)
        time.sleep(1)
    except Exception as e:
        print(f"❌ 无法找到登录输入框: {e}")
        sb.save_screenshot("login_load_fail.png")
        return False

    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            return False
    else:
        print("ℹ️ 未检测到 Turnstile")

    time.sleep(1)
    print("🖱️ 点击登录按钮...")
    try:
        sb.execute_script('document.querySelector(\'button[type="submit"]\').click();')
    except Exception as e:
        print(f"⚠️ JavaScript 点击失败，尝试 CSS 选择器点击: {e}")
        try:
            sb.click('button[type="submit"]')
        except Exception:
            sb.execute_script("document.querySelectorAll('button').forEach(b => { if (b.textContent.includes('ID_SignIn')) b.click(); });")

    print("⏳ 等待登录结果...")
    time.sleep(5)

    current_url = sb.get_current_url()
    if current_url and current_url.lower() == "https://justrunmy.app/":
        print("✅ 登录成功！(已跳转到主页)")
        return True
    else:
        print(f"ℹ️ 当前页面 URL: {current_url}")
        page_source = sb.get_page_source().lower()
        if "invalid login attempt" in page_source:
            print("❌ 登录失败：用户名或密码错误。")
        else:
            print("❌ 登录失败：未知错误，请检查页面截图。")
        sb.save_screenshot("login_failed.png")
        return False


def click_button_by_text(sb, text: str) -> bool:
    """Try several selectors to click a button based on visible text or attributes."""
    selectors = [
        f'button[title="{text}"]',
        f'button[aria-label="{text}"]',
        f'button:has(span:contains("{text}"))',
        f'button:has(i:contains("{text}"))',
        f'button:contains("{text}")',
        f'span:contains("{text}")',
    ]
    for selector in selectors:
        try:
            sb.click(selector)
            return True
        except Exception:
            continue

    script = f"""
    (function() {{
        var expected = '{text}';
        function normalize(s) {{ return s.replace(/\s+/g, ' ').trim(); }}
        var elements = document.querySelectorAll('button, a, [role="button"]');
        for (var i = 0; i < elements.length; i++) {{
            var el = elements[i];
            if (el.getAttribute('title') === expected || el.getAttribute('aria-label') === expected) {{
                el.click();
                return true;
            }}
            if (normalize(el.textContent).indexOf(expected) !== -1) {{
                el.click();
                return true;
            }}
        }}
        return false;
    }})()
    """
    try:
        return bool(sb.execute_script(script))
    except Exception:
        return False


def normalize_timer_text(text: str) -> str:
    text = ' '.join(text.split())
    m = re.search(r"\\b\\d+\\s*(?:d|day|days)\\b\\s*\\d{1,2}:\\d{2}", text, re.I)
    if m:
        return m.group(0)
    m = re.search(r"\\b\\d{1,2}:\\d{2}\\b", text)
    return m.group(0) if m else text


def find_timer_text(sb) -> str:
    """Try several fallback selectors and text queries to find the timer countdown."""
    candidates = [
        'span.font-mono.text-xl',
        'span.font-mono.text-lg',
        'span.text-xl',
        'span:contains("day")',
        'span:contains("days")',
        'div:contains("day")',
        'div:contains("days")',
    ]
    for selector in candidates:
        try:
            text = sb.get_text(selector)
            if text and 'day' in text.lower():
                return normalize_timer_text(text)
        except Exception:
            continue

    script = """
    (function() {
        function normalize(s) { return s.replace(/\\s+/g, ' ').trim(); }
        var candidates = Array.from(document.querySelectorAll('span, div'));
        for (var i = 0; i < candidates.length; i++) {
            var text = normalize(candidates[i].textContent || '');
                if (text.match(/\\b\\d+\\s*day(s)?\\b/i) || text.match(/\\b\\d+\\s*hour(s)?\\b/i)) {
                return text;
            }
        }
        return '';
    })()
    """
    try:
        text = sb.execute_script(script)
        if text:
            return normalize_timer_text(text)
    except Exception:
        pass
    return ''


def renew(sb) -> bool:
    print("\\n" + "="*25)
    print("   🚀 开始自动续期流程")
    print("="*25)

    print("🌐 进入控制面板: https://justrunmy.app/panel/applications")
    sb.open("https://justrunmy.app/panel/applications")
    time.sleep(3)

    print("🖱️ 查找应用")
    try:
        sb.wait_for_element('span:contains("Free tier")', timeout=10)
        sb.click('span:contains("Free tier")')
        time.sleep(3)
        print(f"📍 成功进入应用详情页: {sb.get_current_url()}")
    except Exception as e:
        print(f"❌ 找不到包含 'Free tier' 的应用卡片: {e}")
        sb.save_screenshot("renew_app_not_found.png")
        send_tg_message("❌", "续期失败(找不到应用)", "未知")
        return False

    print("🖱️ 点击 Reset Timer 按钮...")
    if not click_button_by_text(sb, "Reset timer"):
        print("❌ 找不到 Reset Timer 按钮")
        sb.save_screenshot("renew_reset_btn_not_found.png")
        send_tg_message("❌", "续期失败(找不到按钮)", "未知")
        return False
    time.sleep(3)

    print("🛡️ 检查续期弹窗内是否需要 CF 验证...")
    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            print("❌ 弹窗内的 Turnstile 验证失败")
            sb.save_screenshot("renew_turnstile_fail.png")
            send_tg_message("❌", "续期失败(人机验证未过)", "未知")
            return False
    else:
        print("ℹ️ 弹窗内未检测到 Turnstile")

    print("🖱️ 点击 Just Reset 确认续期...")
    if not click_button_by_text(sb, "Just Reset"):
        print("❌ 找不到 Just Reset 按钮")
        sb.save_screenshot("renew_just_reset_not_found.png")
        send_tg_message("❌", "续期失败(无法确认)", "未知")
        return False
    print("⏳ 提交续期请求，等待服务器处理...")
    time.sleep(3)

    print("🔍 验证最终倒计时状态...")
    try:
        time.sleep(3)
        timer_text = find_timer_text(sb)
        if not timer_text:
            raise Exception('timer text not found')

        print(f"⏱️ 当前应用剩余时间: {timer_text}")
        if "1d 11" in timer_text.lower() or "2 days" in timer_text.lower():
            send_tg_message("✅", "续期成功", timer_text)
            return True
        else:
            print("⚠️ 倒计时文本已读取，但格式异常，请人工检查截图确认。")
            sb.save_screenshot("renew_warning.png")
            send_tg_message("⚠️", "续期异常(请检查)", timer_text)
            return True
    except Exception as e:
        print(f"⚠️ 读取倒计时失败，但流程已执行完毕: {e}")
        sb.save_screenshot("renew_timer_read_fail.png")
        send_tg_message("⚠️", "读取剩余时间失败", "未知")
        return False


def main():
    print("=" * 25)
    print("   JustRunMy.app 自动续期")
    print("=" * 25)

    use_proxy = os.environ.get("IS_PROXY", "false").lower() == "true"
    sb_kwargs = {"uc": True, "test": True, "headless": False}

    if use_proxy:
        proxy_str = "http://127.0.0.1:1081"
        print(f"🔗 挂载 Sing-box 代理: {proxy_str}")
        sb_kwargs["proxy"] = proxy_str
    else:
        print("🌐 未使用代理，直连访问")

    devnull = open(os.devnull, 'w')
    with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
        sb_cm = SB(**sb_kwargs)
        sb = sb_cm.__enter__()

    try:
        print("✅ 浏览器已启动")
        try:
            sb.open("https://api.ip.sb/ip")
            print(f"🌐 当前出口真实 IP: {sb.get_text('body')}")
        except Exception:
            pass

        if login(sb):
            renew(sb)
        else:
            print("\\n❌ 登录环节失败，终止后续续期操作。")
            send_tg_message("❌", "登录失败", "未知")
    finally:
        with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
            sb_cm.__exit__(None, None, None)
        devnull.close()


if __name__ == "__main__":
    main()
