import os
import base64
import requests
from nacl.encoding import Base64Encoder
from nacl.public import PublicKey, SealedBox
from seleniumbase import SB

CONNECT_SID = os.environ["CONNECT_SID"]
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GITHUB_REPOSITORY", "")  # Actions 内置变量，自动注入
TG_TOKEN = os.environ.get("TG_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

APP_ID = "90148b3e-2353-459f-a1f8-e34377e389bc"
APP_URL = f"https://containers.back4app.com/apps/{APP_ID}"
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

def update_github_secret(secret_name, secret_value):
    """通过 GitHub API 更新 repo secret"""
    if not GH_TOKEN or not GH_REPO:
        print("GH_TOKEN or GITHUB_REPOSITORY not available, skipping secret update")
        return False
    try:
        headers = {
            "Authorization": f"token {GH_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        # 获取仓库公钥
        pk_resp = requests.get(
            f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
            headers=headers,
            timeout=10
        )
        pk_resp.raise_for_status()
        pk_data = pk_resp.json()

        # 加密 secret 值
        public_key = PublicKey(pk_data["key"].encode(), encoder=Base64Encoder)
        sealed_box = SealedBox(public_key)
        encrypted = sealed_box.encrypt(secret_value.encode())
        encrypted_b64 = base64.b64encode(encrypted).decode()

        # 写入 secret
        put_resp = requests.put(
            f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}",
            headers=headers,
            json={
                "encrypted_value": encrypted_b64,
                "key_id": pk_data["key_id"]
            },
            timeout=10
        )
        put_resp.raise_for_status()
        print(f"GitHub secret '{secret_name}' updated successfully")
        return True
    except Exception as e:
        print(f"Failed to update GitHub secret: {e}")
        return False

def find_button_by_text(sb, keyword):
    """遍历所有 button，小写包含匹配关键字"""
    buttons = sb.find_elements("button")
    for btn in buttons:
        if keyword.lower() in btn.text.lower():
            return btn
    return None

def run():
    with SB(uc=True, headless=True, proxy=PROXY) as sb:

        # ── 先打开目标域名，再注入 cookie ──
        print("Opening app domain to set cookie...")
        sb.open("https://containers.back4app.com")
        sb.sleep(2)

        # 用 CDP Network.setCookie 注入，避免 domain mismatch 问题
        sb.driver.execute_cdp_cmd("Network.setCookie", {
            "name": "connect.sid",
            "value": CONNECT_SID,
            "url": "https://containers.back4app.com",
            "path": "/",
            "secure": True,
            "httpOnly": True
        })
        print("Cookie injected via CDP, navigating to app page...")

        # ── 跳转到目标 App 页面 ──
        sb.open(APP_URL)
        sb.sleep(5)

        # 截图检查是否成功进入
        sb.save_screenshot("after_cookie.png")
        print("Screenshot saved: after_cookie.png")

        # ── 判断是否成功到达目标页面 ──
        current_url = sb.get_current_url()
        print(f"Current URL: {current_url}")

        if "login" in current_url.lower():
            msg = "❌ Cookie 已失效，已被重定向到登录页，请手动更新 CONNECT_SID secret"
            print(msg)
            notify(msg)
            raise Exception(msg)

        if APP_ID not in current_url:
            sb.save_screenshot("wrong_page.png")
            msg = f"❌ 未到达目标 App 页面，当前 URL: {current_url}"
            print(msg)
            notify(msg)
            raise Exception(msg)

        print("Successfully reached target app page.")

        # ── 检查 cookie 是否被服务器刷新，如有则自动更新 secret ──
        cookies = sb.driver.get_cookies()
        for cookie in cookies:
            if cookie["name"] == "connect.sid" and cookie["value"] != CONNECT_SID:
                print("Detected updated connect.sid, updating GitHub secret...")
                new_sid = cookie["value"]
                if update_github_secret("CONNECT_SID", new_sid):
                    notify("🔄 connect.sid 已自动更新至 GitHub secret")
                break

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
