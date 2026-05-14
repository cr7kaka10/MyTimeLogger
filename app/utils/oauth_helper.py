# -*- coding: utf-8 -*-
"""
OAuth2 授权助手 - 用于获取滴答清单/TickTick 的 access_token
运行后会打开浏览器让你登录授权，自动获取并写入 config.json
"""
import json
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import httpx

CONFIG_PATH = "config.json"

def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    tt = config["ticktick_config"]
    host = tt.get("host", "dida365.com")
    client_id = tt["client_id"]
    client_secret = tt["client_secret"]
    
    redirect_uri = "http://localhost:18321/callback"
    scope = "tasks:read tasks:write"
    
    auth_url = f"https://{host}/oauth/authorize?" + urllib.parse.urlencode({
        "client_id": client_id,
        "scope": scope,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": "mytimelogger"
    })
    
    print(f"正在打开浏览器进行授权...")
    print(f"授权 URL: {auth_url}")
    webbrowser.open(auth_url)
    
    # 启动本地 HTTP 服务器等待回调
    code = None
    
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal code
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if code:
                self.wfile.write("✅ 授权成功！可以关闭此页面。".encode("utf-8"))
            else:
                self.wfile.write("❌ 授权失败。".encode("utf-8"))
        
        def log_message(self, format, *args):
            pass
    
    server = HTTPServer(("localhost", 18321), CallbackHandler)
    print("等待浏览器回调... (请在浏览器中完成登录授权)")
    server.handle_request()
    server.server_close()
    
    if not code:
        print("❌ 未获取到授权码!")
        return
    
    print(f"✅ 获取到授权码: {code[:10]}...")
    
    # 用 code 换 access_token
    token_url = f"https://{host}/oauth/token"
    resp = httpx.post(
        token_url,
        data={
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        verify=False
    )
    
    if resp.status_code != 200:
        print(f"❌ 获取 token 失败: {resp.status_code} {resp.text}")
        return
    
    token_data = resp.json()
    access_token = token_data.get("access_token", "")
    
    if not access_token:
        print(f"❌ 响应中没有 access_token: {token_data}")
        return
    
    # 写回 config.json
    config["ticktick_config"]["access_token"] = access_token
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    
    print(f"✅ access_token 已保存到 config.json!")
    print(f"Token: {access_token[:20]}...")

if __name__ == "__main__":
    main()
