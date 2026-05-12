import sqlite3
import os

db_path = "study_log.db"
if not os.path.exists(db_path):
    print("数据库不存在，无需迁移。")
    exit(0)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    print("🚀 开始迁移 atm_summary...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS atm_summary_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            updated_at TIMESTAMP
        )
    ''')
    cursor.execute("INSERT INTO atm_summary_new (date, updated_at) SELECT date, updated_at FROM atm_summary")
    cursor.execute("DROP TABLE atm_summary")
    cursor.execute("ALTER TABLE atm_summary_new RENAME TO atm_summary")
    print("✅ atm_summary 迁移成功！")

    print("🚀 开始迁移 huawei_sleep_data...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS huawei_sleep_data_new (
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
    
    # 获取旧表的列以动态构建 INSERT 语句，防止遗漏
    cursor.execute("PRAGMA table_info(huawei_sleep_data)")
    cols = [row[1] for row in cursor.fetchall() if row[1] != 'id']
    col_str = ", ".join(cols)
    
    cursor.execute(f'''
        INSERT INTO huawei_sleep_data_new ({col_str}) 
        SELECT {col_str} FROM huawei_sleep_data
    ''')
    cursor.execute("DROP TABLE huawei_sleep_data")
    cursor.execute("ALTER TABLE huawei_sleep_data_new RENAME TO huawei_sleep_data")
    print("✅ huawei_sleep_data 迁移成功！")

    conn.commit()
    print("🎉 数据库架构升级圆满完成！所有历史数据均已转移至新结构。")

except Exception as e:
    conn.rollback()
    print(f"❌ 迁移失败: {e}")
finally:
    conn.close()
