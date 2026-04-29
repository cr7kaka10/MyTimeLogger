"""
探索 aTimeLogger Pro 的写入 / 控制类 API
运行: python _explore_atimelogger_api.py
"""
import requests
import json

BASE = "https://app.atimelogger.pro"
CRED = {"username": "1033229709@qq.com", "password": "mufc130130131"}

sess = requests.Session()
sess.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Origin": BASE,
    "Referer": BASE + "/",
})

# ── 登录 ──────────────────────────────────────────────
r = sess.post(f"{BASE}/auth/jwt", json=CRED)
token_data = r.json()
token = token_data["token"]
sess.headers["Authorization"] = f"Bearer {token}"
print(f"[✓] 登录成功，token 前40: {token[:40]}...")

# ── 获取类型列表（typeId 用于后续控制）────────────────
types_resp = sess.get(f"{BASE}/api/types").json()
print(f"\n[✓] 活动类型 ({len(types_resp)} 个):")
for t in types_resp[:5]:
    print(f"    id={t['id']}, name={t['name']}, group={t['group']}")

first_type = types_resp[0]
type_id = first_type["id"]
print(f"\n用第一个类型测试: {first_type['name']} ({type_id})")

# ── 获取当前活动 ──────────────────────────────────────
cur = sess.get(f"{BASE}/api/activities").json()
print(f"\n[✓] 当前活动: {json.dumps(cur, ensure_ascii=False)[:300]}")

running_activity = None
if cur.get("activities"):
    for a in cur["activities"]:
        if a.get("status") == "RUNNING":
            running_activity = a
            break

# ── 测试各种写入接口 ──────────────────────────────────
write_tests = [
    # 尝试各种开始计时的姿势
    ("POST", "/api/activities",                   {"typeId": type_id}),
    ("POST", "/api/activities/start",             {"typeId": type_id}),
    ("POST", f"/api/activities/{type_id}/start",  {}),
    ("POST", "/api/intervals",                    {"typeId": type_id, "start": "2026-04-29T00:00:00Z", "finish": "2026-04-29T00:01:00Z"}),
    ("PUT",  "/api/activities",                   {"typeId": type_id}),
    # 如果有正在运行的，也测试停止
]
if running_activity:
    aid = running_activity["id"]
    write_tests += [
        ("POST", f"/api/activities/{aid}/stop",   {}),
        ("POST", "/api/activities/stop",          {"id": aid}),
        ("PATCH", f"/api/activities/{aid}",       {"status": "STOPPED"}),
    ]

print("\n── 写入接口探测 ──")
for method, path, body in write_tests:
    try:
        fn = getattr(sess, method.lower())
        if body:
            resp = fn(f"{BASE}{path}", json=body, timeout=8)
        else:
            resp = fn(f"{BASE}{path}", timeout=8)
        snippet = resp.text[:200].replace("\n", " ")
        print(f"  [{resp.status_code}] {method} {path} → {snippet}")
    except Exception as e:
        print(f"  [ERR] {method} {path} → {e}")

# ── 尝试直接写入历史记录（不同路径）─────────────────
print("\n── 历史记录写入探测 ──")
record_tests = [
    ("POST", "/api/records",      {"typeId": type_id, "start": 1000000, "finish": 1000060}),
    ("POST", "/api/entries",      {"typeId": type_id, "from": 1000000, "to": 1000060}),
    ("POST", "/api/time-entries", {"typeId": type_id, "from": 1000000, "to": 1000060}),
    ("POST", "/api/timelog",      {"typeId": type_id, "from": 1000000, "to": 1000060}),
    ("POST", "/api/interval",     {"typeId": type_id, "from": 1000000, "to": 1000060}),
    ("POST", "/api/intervals/create", {"typeId": type_id, "from": 1000000, "to": 1000060}),
]
for method, path, body in record_tests:
    try:
        fn = getattr(sess, method.lower())
        resp = fn(f"{BASE}{path}", json=body, timeout=8)
        snippet = resp.text[:200].replace("\n", " ")
        print(f"  [{resp.status_code}] {method} {path} → {snippet}")
    except Exception as e:
        print(f"  [ERR] {method} {path} → {e}")

print("\n完成。")
