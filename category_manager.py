# -*- coding: utf-8 -*-
"""
分类管理模块 (category_manager.py)
==================================
负责本地的柳比歇夫时间分类（输入/输出/生活等）的 CRUD 操作。
纯本地 SQLite 存储，不参与当前的远程 MySQL 同步。
"""

import sqlite3
import uuid
import logging
from datetime import datetime

from utils import resource_path

# 预置分类数据
DEFAULT_CATEGORIES = [
    {"name": "阅读", "icon": "📖", "color": "#A3BE8C", "group_name": "输入", "sort_order": 1},
    {"name": "编程", "icon": "💻", "color": "#88C0D0", "group_name": "输入", "sort_order": 2},
    {"name": "听课", "icon": "🎧", "color": "#B48EAD", "group_name": "输入", "sort_order": 3},
    {"name": "写作", "icon": "✍️", "color": "#EBCB8B", "group_name": "输出", "sort_order": 1},
    {"name": "教学", "icon": "🎬", "color": "#D08770", "group_name": "输出", "sort_order": 2},
    {"name": "笔记", "icon": "📝", "color": "#81A1C1", "group_name": "输出", "sort_order": 3},
    {"name": "运动", "icon": "🏃", "color": "#A3BE8C", "group_name": "生活", "sort_order": 1},
    {"name": "饮食", "icon": "🍽️", "color": "#D08770", "group_name": "生活", "sort_order": 2},
    {"name": "社交", "icon": "💬", "color": "#88C0D0", "group_name": "生活", "sort_order": 3},
]


class CategoryManager:
    """本地分类管理器"""

    def __init__(self):
        self.db_path = resource_path("study_log.db")
        # 由于 database.py 中负责建表更清晰，这里只依赖表存在。
        # 但为安全起见，这里也加了 IF NOT EXISTS。
        self._ensure_table_exists()
        self._ensure_defaults()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _ensure_table_exists(self):
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    id          TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    icon        TEXT NOT NULL DEFAULT '📖',
                    color       TEXT NOT NULL DEFAULT '#5E81AC',
                    group_name  TEXT NOT NULL DEFAULT '输入',
                    sort_order  INTEGER NOT NULL DEFAULT 0,
                    is_active   INTEGER NOT NULL DEFAULT 1,
                    created_at  TEXT NOT NULL
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"分类表初始化失败: {e}")

    def _ensure_defaults(self):
        """如果分类表为空，则插入默认数据"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM categories")
            count = cursor.fetchone()[0]
            if count == 0:
                logging.info("分类表为空，正在插入预置分类...")
                now_str = datetime.now().isoformat()
                for cat in DEFAULT_CATEGORIES:
                    cursor.execute('''
                        INSERT INTO categories (id, name, icon, color, group_name, sort_order, is_active, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        str(uuid.uuid4()), cat['name'], cat['icon'], cat['color'], 
                        cat['group_name'], cat['sort_order'], 1, now_str
                    ))
                conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"检查预置分类失败: {e}")

    def get_all_active(self):
        """获取所有启用的分类"""
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM categories 
                WHERE is_active = 1 
                ORDER BY group_name, sort_order ASC
            ''')
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logging.error(f"查询分类失败: {e}")
            return []

    def get_grouped(self):
        """获取分组后的分类字典"""
        categories = self.get_all_active()
        grouped = {"输入": [], "输出": [], "生活": []}
        for cat in categories:
            grp = cat.get("group_name", "输入")
            if grp not in grouped:
                grouped[grp] = []
            grouped[grp].append(cat)
        # 确保按 sort_order 排序
        for grp in grouped:
            grouped[grp].sort(key=lambda x: x.get("sort_order", 0))
        return grouped

    def add_category(self, name, icon, color, group_name):
        """新增分类"""
        cat_id = str(uuid.uuid4())
        now_str = datetime.now().isoformat()
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            # 获取当前组的最大排序值
            cursor.execute("SELECT MAX(sort_order) FROM categories WHERE group_name = ?", (group_name,))
            max_order = cursor.fetchone()[0]
            next_order = (max_order or 0) + 1

            cursor.execute('''
                INSERT INTO categories (id, name, icon, color, group_name, sort_order, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (cat_id, name, icon, color, group_name, next_order, 1, now_str))
            conn.commit()
            conn.close()
            return cat_id
        except Exception as e:
            logging.error(f"新增分类失败: {e}")
            return None

    def update_category(self, cat_id, name=None, icon=None, color=None, group_name=None):
        """更新分类"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            updates = []
            params = []
            if name: updates.append("name = ?"); params.append(name)
            if icon: updates.append("icon = ?"); params.append(icon)
            if color: updates.append("color = ?"); params.append(color)
            if group_name: updates.append("group_name = ?"); params.append(group_name)

            if not updates: return False

            params.append(cat_id)
            cursor.execute(f"UPDATE categories SET {', '.join(updates)} WHERE id = ?", tuple(params))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"更新分类失败: {e}")
            return False

    def remove_category(self, cat_id):
        """软删除分类"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE categories SET is_active = 0 WHERE id = ?", (cat_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"删除分类失败: {e}")
            return False
