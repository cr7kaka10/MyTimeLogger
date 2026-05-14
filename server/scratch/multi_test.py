
import os
import json
import base64
from openai import OpenAI
from PIL import Image

def clean_url(url):
    if not url: return ""
    url = url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[:-17]
    return url

def test_extraction(filename):
    img_path = os.path.join(r"D:\WorkSpace\MyTimeLogger\document", filename)
    api_key = "4d5ba3e66af04c6db476f94b7506be36.dd05X0p66QBAARgx"
    base_url = "https://open.bigmodel.cn/api/paas/v4"
    model = "glm-4.6v-flash"
    
    temp_path = img_path + ".test.jpg"
    with Image.open(img_path) as img:
        w, h = img.size
        if h > 2000:
            new_h = 4096 if h > 4096 else h
            new_w = int(w * (new_h / h))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        img.convert("RGB").save(temp_path, "JPEG", quality=95)

    with open(temp_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    
    client = OpenAI(api_key=api_key, base_url=clean_url(base_url))
    
    prompt = """提取以下字段并以 JSON 返回：
sleep_date (截图中的日期, 如 '5月8日'),
sleep_score (整数), 
sleep_start (HH:mm), 
sleep_end (HH:mm), 
total_sleep_min (分钟), 
deep_sleep_min (分钟), 
light_sleep_min (分钟), 
rem_sleep_min (分钟), 
deep_sleep_ratio (整数),
awake_count (整数),
sleep_continuity (整数),
breathing_score (整数),
official_interpretation (底部解读全文).
注意：只返回 JSON 代码块。"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}, {"type": "text", "text": prompt}]}],
            max_tokens=1024,
            temperature=0.1
        )
        raw = response.choices[0].message.content.strip()
        if "```" in raw: raw = raw.split("```")[1].replace("json", "").strip()
        print(f"\n--- Results for {filename} ---")
        print(raw)
    except Exception as e:
        print(f"Error {filename}: {e}")
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

if __name__ == "__main__":
    for f in ["55.jpg", "58.jpg"]:
        test_extraction(f)
