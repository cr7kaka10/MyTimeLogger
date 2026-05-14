import sqlite3

conn = sqlite3.connect('database.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", [r[0] for r in cur.fetchall()])

# 查最早的几条睡眠数据
cur.execute("SELECT date, sleep_score, total_sleep_min, deep_sleep_min, light_sleep_min, rem_sleep_min, awake_count, sleep_start, sleep_end FROM huawei_sleep_data ORDER BY date ASC LIMIT 5")
rows = cur.fetchall()
print("\n最早的睡眠记录:")
for r in rows:
    date, score, total, deep, light, rem, awake_cnt, s_start, s_end = r
    print(f"  date={date}, total_sleep_min={total}, start={s_start}, end={s_end}, deep={deep}, light={light}, rem={rem}")
    # 计算在床时间
    if s_start and s_end:
        sh, sm = map(int, s_start.split(':'))
        eh, em = map(int, s_end.split(':'))
        start_m = sh*60+sm
        end_m = eh*60+em
        if end_m < start_m: end_m += 24*60
        in_bed = end_m - start_m
        stages = (deep or 0) + (light or 0) + (rem or 0)
        print(f"    在床时间={in_bed}min, 阶段和={stages}min, 差值={in_bed - (total or 0):.0f}min")

conn.close()
