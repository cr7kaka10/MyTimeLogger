import sqlite3

db_path = "study_log.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    print("🚀 开始修复 huawei_sleep_data 表结构错位...")
    
    # 1. 创建绝对标准的修复表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS huawei_sleep_data_fixed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            sleep_score INTEGER,
            total_sleep_min INTEGER,
            deep_sleep_min INTEGER,
            light_sleep_min INTEGER,
            rem_sleep_min INTEGER,
            awake_count INTEGER,
            sleep_start TEXT,
            sleep_end TEXT,
            deep_sleep_ratio INTEGER,
            sleep_continuity INTEGER,
            breathing_score INTEGER,
            sleep_cycles FLOAT,
            awake_min INTEGER,
            fall_asleep_min INTEGER,
            wake_up_min INTEGER,
            analysis_report TEXT,
            sleep_reflection TEXT,
            updated_at TIMESTAMP
        )
    ''')
    
    # 2. 严格按列名映射提取数据，丢弃错位的 id，让它重新自增
    # 在错位的表中，原来的 date 数据可能跑到了 TEXT 类型的字段里，我们需要精准抓取
    # 我们知道旧表中一定有 date 字符串，这里我们做容错处理
    cursor.execute("SELECT * FROM huawei_sleep_data")
    rows = cursor.fetchall()
    
    # 获取当前表的列名
    cursor.execute("PRAGMA table_info(huawei_sleep_data)")
    cols = [col[1] for col in cursor.fetchall()]
    
    # 找到 date 真正所在的数据列 (因为错位了，可能是在 id 列里)
    # 我们可以通过判断哪一列存的是 "2026-xx-xx" 格式来确认
    
    date_idx = cols.index('date')
    id_idx = cols.index('id') if 'id' in cols else -1
    
    # 严格映射插入
    for row in rows:
        # 如果 date 列存的其实是数字(错位)，而 id 列存的是日期
        actual_date = row[date_idx]
        if isinstance(actual_date, int) and id_idx != -1 and isinstance(row[id_idx], str):
            actual_date = row[id_idx]
            
        # 提取其他正常字段 (排除 date 和 id)
        other_fields = {}
        for i, col in enumerate(cols):
            if col not in ('id', 'date'):
                other_fields[col] = row[i]
                
        # 构建插入
        columns_to_insert = ['date'] + list(other_fields.keys())
        values_to_insert = [actual_date] + list(other_fields.values())
        
        placeholders = ', '.join(['?'] * len(values_to_insert))
        insert_sql = f"INSERT INTO huawei_sleep_data_fixed ({', '.join(columns_to_insert)}) VALUES ({placeholders})"
        cursor.execute(insert_sql, values_to_insert)

    # 3. 替换原表
    cursor.execute("DROP TABLE huawei_sleep_data")
    cursor.execute("ALTER TABLE huawei_sleep_data_fixed RENAME TO huawei_sleep_data")
    
    # 对于 atm_summary 也执行同样的严格修复以防万一
    print("🚀 检查并修复 atm_summary...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS atm_summary_fixed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            updated_at TIMESTAMP
        )
    ''')
    
    cursor.execute("SELECT * FROM atm_summary")
    atm_rows = cursor.fetchall()
    cursor.execute("PRAGMA table_info(atm_summary)")
    atm_cols = [col[1] for col in cursor.fetchall()]
    
    a_date_idx = atm_cols.index('date')
    a_id_idx = atm_cols.index('id') if 'id' in atm_cols else -1
    
    for row in atm_rows:
        actual_date = row[a_date_idx]
        if isinstance(actual_date, int) and a_id_idx != -1 and isinstance(row[a_id_idx], str):
            actual_date = row[a_id_idx]
            
        updated_at = row[atm_cols.index('updated_at')] if 'updated_at' in atm_cols else None
        
        cursor.execute("INSERT INTO atm_summary_fixed (date, updated_at) VALUES (?, ?)", (actual_date, updated_at))
        
    cursor.execute("DROP TABLE atm_summary")
    cursor.execute("ALTER TABLE atm_summary_fixed RENAME TO atm_summary")

    conn.commit()
    print("🎉 错位问题已彻底修复！列顺序和类型已严格归正。")

except Exception as e:
    conn.rollback()
    print(f"❌ 修复失败: {e}")
finally:
    conn.close()
