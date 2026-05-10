import sqlite3
import os
import logging
from datetime import datetime

def patch():
    # 1. SQLite 补丁
    # 遍历所有可能的数据库文件，确保都打上补丁
    db_files = ['study_log.db', 'my_time_logger.db', 'database.db']
    
    new_cols = [
        ("sleep_cycles", "FLOAT"),
        ("awake_min", "FLOAT"),
        ("fall_asleep_min", "FLOAT"),
        ("wake_up_min", "FLOAT")
    ]
    
    for db_path in db_files:
        if os.path.exists(db_path):
            print(f"正在修补 SQLite 数据库: {db_path}")
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # 创建表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS huawei_sleep_data (
                        date TEXT PRIMARY KEY,
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
                        analysis_report TEXT,
                        updated_at TIMESTAMP
                    )
                ''')
                
                # 增加新列
                for col_name, col_type in new_cols:
                    try:
                        cursor.execute(f"ALTER TABLE huawei_sleep_data ADD COLUMN {col_name} {col_type}")
                        print(f"  - 新增列: {col_name}")
                    except sqlite3.OperationalError:
                        pass # 已存在
                
                conn.commit()
                conn.close()
                print(f"✅ {db_path} 修补完成。")
            except Exception as e:
                print(f"❌ 修补 {db_path} 失败: {e}")

    # 2. MySQL 补丁
    try:
        from database import StudyLogger
        db = StudyLogger()
        # 无论当前配置是啥，如果能连上 MySQL 就顺便也修补了
        print("尝试连接 MySQL 并修补...")
        conn = db._get_connection()
        if conn:
            cursor = conn.cursor()
            
            # 创建表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS huawei_sleep_data (
                    date VARCHAR(20) PRIMARY KEY,
                    sleep_score INT,
                    total_sleep_min INT,
                    deep_sleep_min INT,
                    light_sleep_min INT,
                    rem_sleep_min INT,
                    awake_count INT,
                    sleep_start VARCHAR(10),
                    sleep_end VARCHAR(10),
                    deep_sleep_ratio INT,
                    sleep_continuity INT,
                    breathing_score INT,
                    analysis_report TEXT,
                    updated_at DATETIME
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            ''')
            
            # 增加新列
            for col_name, col_type in new_cols:
                # MySQL 检查列是否存在稍显麻烦，直接尝试增加并忽略错误
                sql_type = "FLOAT" if col_type == "FLOAT" else "INT"
                try:
                    cursor.execute(f"ALTER TABLE huawei_sleep_data ADD COLUMN {col_name} {sql_type}")
                    print(f"  - MySQL 新增列: {col_name}")
                except Exception:
                    pass # 已存在
            
            conn.commit()
            print("✅ MySQL 数据库修补完成。")
    except Exception as e:
        print(f"MySQL 补丁跳过 (可能未配置或无法连接): {e}")

if __name__ == '__main__':
    patch()
