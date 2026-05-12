import sqlite3
import os

db_path = "study_log.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. 删除 2024 年的脏数据
cursor.execute("DELETE FROM huawei_sleep_data WHERE date LIKE '2024-%'")
deleted = cursor.rowcount
print(f"✅ 已清理 {deleted} 条错误年份(2024)的脏数据。")

# 2. 验证主键情况
for table in ['huawei_sleep_data', 'atm_summary', 'atm_activities']:
    cursor.execute(f"PRAGMA table_info({table})")
    columns = cursor.fetchall()
    pk_cols = [col[1] for col in columns if col[5] > 0]
    print(f"📊 表 {table} 的主键列: {pk_cols if pk_cols else '无主键 (需要重建)'}")

conn.commit()
conn.close()
