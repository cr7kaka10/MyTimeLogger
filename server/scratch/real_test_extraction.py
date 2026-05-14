
import os
import json
import base64
import logging
from openai import OpenAI
from PIL import Image

# 模拟 sleep_statistics.py 中的逻辑
def clean_url(url):
    if not url: return ""
    url = url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[:-17]
    return url

def test_extraction():
    img_path = r"D:\WorkSpace\MyTimeLogger\document\微信图片_20260509170117_9_281.jpg"
    api_key = "4d5ba3e66af04c6db476f94b7506be36.dd05X0p66QBAARgx"
    base_url = "https://open.bigmodel.cn/api/paas/v4"
    model = "glm-4.6v-flash" # 用户指定的
    
    print(f"Testing with image: {img_path}")
    
    # 1. 预处理 (4096px HD)
    temp_path = img_path + ".test.jpg"
    with Image.open(img_path) as img:
        w, h = img.size
        print(f"Original size: {w}x{h}")
        if h > 2000:
            new_h = 4096 if h > 4096 else h
            new_w = int(w * (new_h / h))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            print(f"Resized to: {new_w}x{new_h}")
        img.convert("RGB").save(temp_path, "JPEG", quality=95)

    # 2. 读取并编码
    with open(temp_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    
    client = OpenAI(api_key=api_key, base_url=clean_url(base_url))
    
    prompt = """你是一个专业的数据提取助手。请从这张华为健康睡眠截图中提取以下字段并以严格的 JSON 格式返回：
sleep_score (睡眠得分, 整数), 
sleep_start (入睡时间, HH:mm), 
sleep_end (醒来时间, HH:mm), 
total_sleep_min (总睡眠时长, 分钟), 
deep_sleep_min (深睡时长, 分钟), 
light_sleep_min (浅睡时长, 分钟), 
rem_sleep_min (快速眼动时长, 分钟), 
deep_sleep_ratio (深睡比例, 整数,不带%).

注意：请重点关注图片下部的数值列表。如果某项没找到，请填 null。只返回 JSON 代码块。"""

    print("Sending request to GLM-4v...")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    {"type": "text", "text": prompt}
                ]
            }],
            max_tokens=1024,
            temperature=0.1
        )
        raw = response.choices[0].message.content.strip()
        print("\n--- Raw Response ---")
        print(raw)
        print("--------------------\n")
        
        # 尝试解析
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        
        data = json.loads(raw)
        print("Parsed Data:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == "__main__":
    test_extraction()
