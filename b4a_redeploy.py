import os
import requests
from seleniumbase import SB

EMAIL = os.environ["B4A_EMAIL"]
PASSWORD = os.environ["B4A_PASSWORD"]
TG_TOKEN = os.environ.get("TG_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

APP_ID = "90148b3e-2353-459f-a1f8-e34377e389bc"
APP_URL = f"https://containers.back4app.com/apps/{APP_ID}"
LOGIN_URL = f"https://www.back4app.com/login?return-url=https%3A%2F%2Fcontainers.back4app.com%2Fapps%2F{APP_ID}"
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
    """遍历所有 button，小写包含匹配关键字"""
    buttons = sb.find_elements("button")
    for btn in buttons:
        if keyword.lower() in btn.text.lower():
            return btn
    return None

def find_button_exact_text(sb, text):
    """完全匹配按钮文字（去除首尾空格后比较，忽略大小写）"""
    buttons = sb.find_elements("button")
    for btn in buttons:
        if btn.text.strip().lower() == text.strip().lower():
            return btn
    return None

def find_button_xpath(sb, keyword):
    """XPath 包含匹配兜底"""
    try:
        return sb.find_element(
            f'//button[contains(translate(text(),"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"{keyword.lower()}")]'
        )
    except:
        return None

def click_button_by_text(sb, keyword):
    """找到包含关键字的按钮并用 JS click 点击，避免 UC 模式 arguments 问题"""
    buttons = sb.find_elements("button")
    for i, btn in enumerate(buttons):
        if keyword.lower() in btn.text.lower():
            sb.execute_script(
                "var btns = document.querySelectorAll('button');"
                f"btns[{i}].scrollIntoView(true);"
                f"btns[{i}].click();"
            )
            return True
    return False

def run():
    with SB(uc=True, headless=True, proxy=PROXY) as sb:

        # ── 直接打开带 return-url 的登录页 ──
        print(f"Navigating to login page: {LOGIN_URL}")
        sb.open(LOGIN_URL)
        sb.sleep(3)
        sb.save_screenshot("login_page.png")
        print("Screenshot saved: login_page.png")

        # ── 填写邮箱和密码 ──
        sb.wait_for_element("input[placeholder='Email']", timeout=20)
        sb.type("input[placeholder='Email']", EMAIL)
        sb.type("input[placeholder='Password']", PASSWORD)

        # ── 点击 Continue 按钮（精确匹配，避免点到 Continue with Google）──
        print("Looking for Continue button...")
        clicked = click_button_by_text(sb, "continue")
        # 但要排除 "Continue with Google/Github"，用精确匹配重新实现
        # 重写：精确匹配 JS 点击
        buttons = sb.find_elements("button")
        continue_index = None
        for i, btn in enumerate(buttons):
            if btn.text.strip().lower() == "continue":
                continue_index = i
                break

        if continue_index is None:
            sb.save_screenshot("login_failed.png")
            msg = "❌ 未找到精确匹配的 Continue 登录按钮，请查看截图"
            print(msg)
            notify(msg)
            raise Exception(msg)

        print(f"Clicking Continue button at index {continue_index}...")
        sb.execute_script(
            "var btns = document.querySelectorAll('button');"
            f"btns[{continue_index}].scrollIntoView(true);"
            f"btns[{continue_index}].click();"
        )
        sb.sleep(5)

        # ── 登录结果判断 ──
        current_url = sb.get_current_url()
        print(f"Post-login URL: {current_url}")

        if "login" in current_url.lower():
            sb.save_screenshot("login_failed.png")
            msg = "❌ 登录失败，仍停留在登录页，请检查邮箱和密码"
            print(msg)
            notify(msg)
            raise Exception(msg)

        print("Login successful.")

        # ── 判断是否已自动跳转到目标 App 页面 ──
        if APP_ID not in current_url:
            print(f"Not redirected automatically, navigating to: {APP_URL}")
            sb.open(APP_URL)
            sb.sleep(5)
            current_url = sb.get_current_url()

        if APP_ID not in current_url:
            sb.save_screenshot("wrong_page.png")
            msg = f"❌ 未到达目标 App 页面，当前 URL: {current_url}"
            print(msg)
            notify(msg)
            raise Exception(msg)

        print("Successfully reached target app page.")

        # 滚动到底部确保左下角按钮渲染
        sb.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        sb.sleep(2)

        # 截图留档
        sb.save_screenshot("before_click.png")
        print("Screenshot saved: before_click.png")

        # ── 查找并点击 Redeploy App 按钮 ──
        buttons = sb.find_elements("button")
        redeploy_index = None
        redeploy_text = None
        for i, btn in enumerate(buttons):
            if "redeploy" in btn.text.lower():
                redeploy_index = i
                redeploy_text = btn.text.strip()
                break

        if redeploy_index is None:
            # XPath 兜底查找
            try:
                all_btns = sb.find_elements("button")
                for i, btn in enumerate(all_btns):
                    if "redeploy" in btn.text.lower():
                        redeploy_index = i
                        redeploy_text = btn.text.strip()
                        break
            except:
                pass

        if redeploy_index is None:
            msg = "❌ 未找到 Redeploy App 按钮，可能当前无需部署或页面结构已变化"
            print(msg)
            notify(msg)
            raise Exception(msg)

        print(f"Found button: '{redeploy_text}' at index {redeploy_index}, clicking...")
        sb.execute_script(
            "var btns = document.querySelectorAll('button');"
            f"btns[{redeploy_index}].scrollIntoView(true);"
            f"btns[{redeploy_index}].click();"
        )

        # ── 点击后确认：等待 Redeploy 按钮消失 ──
        click_confirmed = False
        for i in range(5):
            sb.sleep(3)
            print(f"Checking if button disappeared... attempt {i+1}/5")
            btn_check = find_button_by_text(sb, "redeploy")
            if btn_check is None:
                click_confirmed = True
                break

        # 截图确认点击后状态
        sb.save_screenshot("after_click.png")
        print("Screenshot saved: after_click.png")

        if click_confirmed:
            msg = "✅ Redeploy 成功，部署按钮已消失，Console 正在显示部署日志"
        else:
            msg = "⚠️ 已点击 Redeploy 按钮，但按钮未消失，请查看截图手动核对"

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
