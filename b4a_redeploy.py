import os
import requests
from seleniumbase import SB

EMAIL = os.environ["B4A_EMAIL"]
PASSWORD = os.environ["B4A_PASSWORD"]
TG_TOKEN = os.environ.get("TG_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

APP_URL = "https://containers.back4app.com/apps/90148b3e-2353-459f-a1f8-e34377e389bc"
PROXY = "http://127.0.0.1:8080"

def notify(msg):
    if TG_TOKEN and TG_CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT_ID, "text": f"[B4A] {msg}"},
                timeout=10
            )
        except Exception as e:
            print(f"TG notify failed: {e}")

def find_button_by_text(sb, keyword):
    """遍历所有 button，小写匹配关键字"""
    buttons = sb.find_elements("button")
    for btn in buttons:
        if keyword.lower() in btn.text.lower():
            return btn
    return None

def find_button_xpath(sb, keyword):
    """XPath 兜底匹配"""
    try:
        return sb.find_element(
            f'//button[contains(translate(text(),"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"{keyword.lower()}")]'
        )
    except:
        return None

def run():
    with SB(uc=True, headless=True, proxy=PROXY) as sb:

        # ── 登录 ──
        print("Navigating to login page...")
        sb.open("https://www.back4app.com/login")
        sb.wait_for_element("input[type='email']", timeout=20)
        sb.type("input[type='email']", EMAIL)
        sb.type("input[type='password']", PASSWORD)
        sb.click("button[type='submit']")
        sb.sleep(5)

        # ── 登录结果判断 ──
        current_url = sb.get_current_url()
        print(f"Post-login URL: {current_url}")

        # 如果还停留在登录页，说明登录失败
        if "login" in current_url.lower():
            sb.save_screenshot("login_failed.png")
            msg = "❌ 登录失败，仍停留在登录页，请检查邮箱和密码"
            print(msg)
            notify(msg)
            raise Exception(msg)

        print("Login successful, navigating to app page...")

        # ── 跳转到 App 页面 ──
        sb.open(APP_URL)
        sb.sleep(5)

        # ── 判断是否成功到达目标页面 ──
        current_url = sb.get_current_url()
        print(f"Current URL after navigation: {current_url}")

        # 检查 URL 是否包含目标 app 的 ID
        app_id = "90148b3e-2353-459f-a1f8-e34377e389bc"
        if app_id not in current_url:
            sb.save_screenshot("wrong_page.png")
            msg = f"❌ 未到达目标 App 页面，当前 URL: {current_url}"
            print(msg)
            notify(msg)
            raise Exception(msg)

        print("Successfully reached target app page.")

        # 滚动到底部确保左下角按钮渲染
        sb.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        sb.sleep(2)

        # 截图留档
        sb.save_screenshot("before_click.png")
        print("Screenshot saved: before_click.png")

        # ── 查找 Redeploy App 按钮 ──
        redeploy_btn = find_button_by_text(sb, "redeploy")
        if redeploy_btn is None:
            print("Text match failed, trying XPath fallback...")
            redeploy_btn = find_button_xpath(sb, "redeploy")

        if redeploy_btn is None:
            # 检查是否已经是 Upgrade 状态
            upgrade_btn = find_button_by_text(sb, "upgrade")
            if upgrade_btn:
                msg = "⚠️ 未找到 Redeploy 按钮，页面已显示 Upgrade 按钮，可能上次部署仍有效"
                print(msg)
                notify(msg)
                return

            msg = "❌ 未找到 Redeploy App 按钮，请检查页面结构或登录状态"
            print(msg)
            notify(msg)
            raise Exception(msg)

        # ── 滚动到按钮位置并点击 ──
        print(f"Found button: '{redeploy_btn.text}', clicking...")
        sb.execute_script("arguments[0].scrollIntoView(true);", redeploy_btn)
        sb.sleep(1)
        redeploy_btn.click()
        sb.sleep(5)

        # 截图确认点击后状态
        sb.save_screenshot("after_click.png")
        print("Screenshot saved: after_click.png")

        # ── 确认按钮文字变化 ──
        upgrade_btn = find_button_by_text(sb, "upgrade")
        if upgrade_btn:
            msg = f"✅ Redeploy 成功，按钮已变为：{upgrade_btn.text.strip()}"
        else:
            msg = "⚠️ 点击完成，但未检测到按钮文字变化，请查看截图确认"

        print(msg)
        notify(msg)

if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        err = f"❌ 脚本出错: {e}"
        print(err)
        notify(err)
        raise