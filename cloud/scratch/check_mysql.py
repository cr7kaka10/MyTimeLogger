import json
import pymysql

with open('config.json', 'r', encoding='utf-8') as f:
    c = json.load(f)
mc = c.get('mysql_config', {})

conn = pymysql.connect(
    host=mc['host'],
    port=int(mc.get('port', 3306)),
    user=mc['user'],
    password=mc['password'],
    database=mc['database'],
    charset='utf8mb4'
)
cur = conn.cursor()

# 列出所有日期
cur.execute("SELECT date, total_sleep_min, sleep_start, sleep_end, deep_sleep_min, light_sleep_min, rem_sleep_min FROM huawei_sleep_data ORDER BY date ASC")
rows = cur.fetchall()
print(f"共 {len(rows)} 条记录:")
for row in rows:
    date, total, s_start, s_end, deep, light, rem = row
    stages = (deep or 0) + (light or 0) + (rem or 0)
    print(f"  {date}: total={total}, start={s_start}, end={s_end}, stages={stages}")
    if s_start and s_end:
        sh, sm = map(int, str(s_start).split(':'))
        eh, em = map(int, str(s_end).split(':'))
        start_m = sh*60+sm
        end_m = eh*60+em
        if end_m < start_m: end_m += 24*60
        in_bed = end_m - start_m
        print(f"    在床={in_bed}min, total={total}, diff={in_bed-(total or 0):.0f}")

conn.close()
