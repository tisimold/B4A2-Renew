import os
import time
import base64
import requests
from nacl.encoding import Base64Encoder
from nacl.public import PublicKey, SealedBox
from seleniumbase import SB

CONNECT_SID = os.environ["CONNECT_SID"]
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GITHUB_REPOSITORY", "")
TG_TOKEN = os.environ.get("TG_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

APP_ID = "f7ba0b0c-adf6-4f8d-a5b5-7b713fe2ff1c"
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

def wait_for_proxy(max_retries=10, interval=3):
    """等待 gost 代理就绪"""
    proxies = {"http": PROXY, "https": PROXY}
    for i in range(max_retries):
        try:
            resp = requests.get(
                "https://www.back4app.com",
                proxies=proxies,
                timeout=10
            )
            if resp.status_code < 500:
                print(f"Proxy is ready (attempt {i+1})")
                return True
        except Exception as e:
            print(f"Proxy not ready yet, retrying in {interval}s... (attempt {i+1}/{max_retries}): {e}")
            time.sleep(interval)
    return False

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
        pk_resp = requests.get(
            f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
            headers=headers,
            timeout=10
        )
        if pk_resp.status_code == 403:
            print("❌ GH_TOKEN 权限不足，请确保 PAT 有 repo 或 secrets write 权限")
            return False
        pk_resp.raise_for_status()
        pk_data = pk_resp.json()

        public_key = PublicKey(pk_data["key"].encode(), encoder=Base64Encoder)
        sealed_box = SealedBox(public_key)
        encrypted = sealed_box.encrypt(secret_value.encode())
        encrypted_b64 = base64.b64encode(encrypted).decode()

        put_resp = requests.put(
            f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}",
            headers=headers,
            json={
                "encrypted_value": encrypted_b64,
                "key_id": pk_data["key_id"]
            },
            timeout=10
        )
        if put_resp.status_code == 403:
            print("❌ GH_TOKEN 权限不足，无法写入 secret")
            return False
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
    # ── 先确认代理就绪 ──
    print("Checking proxy availability...")
    if not wait_for_proxy():
        msg = "❌ 代理连接失败，gost 未就绪，请检查 PROXY_URL 配置"
        print(msg)
        notify(msg)
        raise Exception(msg)
    print("Proxy is ready, starting browser...")

    with SB(uc=True, headless=True, proxy=PROXY) as sb:

        # ── 先打开根域名页面，确保可以设置 .back4app.com 的 cookie ──
        print("Opening back4app.com to set cookie...")
        sb.open("https://www.back4app.com")
        sb.sleep(2)

        # domain 设为 .back4app.com（带点号），所有子域共享
        sb.driver.execute_cdp_cmd("Network.setCookie", {
            "name": "connect.sid",
            "value": CONNECT_SID,
            "domain": ".back4app.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Lax"
        })
        print("Cookie injected to .back4app.com (shared across subdomains)")

        # ── 跳转到目标 App 页面（失败时最多重试3次）──
        max_nav_retries = 3
        nav_success = False

        for nav_attempt in range(max_nav_retries):
            print(f"Navigating to app page... (attempt {nav_attempt+1}/{max_nav_retries})")
            sb.open(APP_URL)
            sb.sleep(5)

            current_url = sb.get_current_url()
            print(f"Current URL: {current_url}")

            if "login" not in current_url.lower() and APP_ID in current_url:
                nav_success = True
                break

            print(f"Redirected to login or wrong page, retrying in 10s...")
            sb.sleep(10)

        if not nav_success:
            sb.save_screenshot("nav_failed.png")
            msg = f"❌ Cookie 已失效或导航失败，已重试 {max_nav_retries} 次，请手动更新 CONNECT_SID secret"
            print(msg)
            notify(msg)
            raise Exception(msg)

        # 截图检查是否成功进入
        sb.save_screenshot("after_cookie.png")
        print("Screenshot saved: after_cookie.png")
        print("Successfully reached target app page.")

        # ── 用 CDP 检查 cookie 是否被服务器刷新，如有则自动更新 secret ──
        try:
            result = sb.driver.execute_cdp_cmd("Network.getAllCookies", {})
            cookies = result.get("cookies", [])
            for cookie in cookies:
                if cookie["name"] == "connect.sid" and cookie["value"] != CONNECT_SID:
                    print("Detected updated connect.sid, updating GitHub secret...")
                    new_sid = cookie["value"]
                    if update_github_secret("CONNECT_SID", new_sid):
                        notify("🔄 connect.sid 已自动更新至 GitHub secret")
                    break
        except Exception as e:
            print(f"Cookie check skipped: {e}")

        # 滚动到底部确保左下角按钮渲染
        sb.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        sb.sleep(2)

        # 截图留档
        sb.save_screenshot("before_click.png")
        print("Screenshot saved: before_click.png")

        # ── 查找并点击 Redeploy App 按钮（带刷新重试，最多200次，每次等待15秒）──
        redeploy_index = None
        redeploy_text = None
        max_retries = 200
        retry_interval = 15  # 秒

        for attempt in range(max_retries):
            buttons = sb.find_elements("button")
            for i, btn in enumerate(buttons):
                if "redeploy" in btn.text.lower():
                    redeploy_index = i
                    redeploy_text = btn.text.strip()
                    break

            if redeploy_index is not None:
                break

            if attempt < max_retries - 1:
                print(f"Redeploy button not found, refreshing in {retry_interval}s... (attempt {attempt+1}/{max_retries})")
                sb.sleep(retry_interval)
                sb.refresh()
                sb.sleep(3)

        if redeploy_index is None:
            msg = "❌ 未找到 Redeploy App 按钮，已重试 200 次（约50分钟），可能当前无需部署或页面结构已变化"
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
