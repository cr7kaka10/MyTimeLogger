# -*- coding: utf-8 -*-
"""
分类管理模块 (category_manager.py) - 缓存与架构升级版
=====================================================
负责本地的柳比歇7时间分类的 CRUD 操作。
- 采用自增整数主键 (INT)
- 实现内存缓存 (Category Name -> ID Map) 以减少数据库压力
"""

import sqlite3
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
        self._name_to_id_cache = {}  # 内存缓存：{Name: ID}
        self._id_to_all_cache = {}   # 内存缓存：{ID: full_dict}
        
        self._ensure_table_exists()
        self._ensure_defaults()
        self.refresh_cache()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _ensure_table_exists(self):
        """初始化表结构，支持自增主键"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 检查旧表是否存在及其 ID 类型
            cursor.execute("PRAGMA table_info(categories)")
            cols = cursor.fetchall()
            if cols:
                # 检查 id 字段类型是否为 INTEGER
                id_col = next((c for c in cols if c[1] == 'id'), None)
                if id_col and 'INTEGER' not in id_col[2].upper():
                    logging.warning("分类表 ID 类型非 INTEGER，正在启动破坏性迁移...")
                    cursor.execute("ALTER TABLE categories RENAME TO categories_old")
                    # 创建新表（自增整数主键）
                    cursor.execute('''
                        CREATE TABLE categories (
                            id          INTEGER PRIMARY KEY AUTOINCREMENT,
                            name        TEXT NOT NULL,
                            icon        TEXT NOT NULL DEFAULT '📖',
                            color       TEXT NOT NULL DEFAULT '#5E81AC',
                            group_name  TEXT NOT NULL DEFAULT '输入',
                            sort_order  INTEGER NOT NULL DEFAULT 0,
                            is_active   INTEGER NOT NULL DEFAULT 1,
                            created_at  TEXT NOT NULL
                        )
                    ''')
                    # 尝试迁移数据（忽略 ID，由自增生成）
                    cursor.execute('''
                        INSERT INTO categories (name, icon, color, group_name, sort_order, is_active, created_at)
                        SELECT name, icon, color, group_name, sort_order, is_active, created_at FROM categories_old
                    ''')
                    cursor.execute("DROP TABLE categories_old")
                    conn.commit()
            else:
                # 表不存在，直接创建
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS categories (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
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
            logging.error(f"分类表初始化/迁移失败: {e}")

    def _ensure_defaults(self):
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
                        INSERT INTO categories (name, icon, color, group_name, sort_order, is_active, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        cat['name'], cat['icon'], cat['color'], 
                        cat['group_name'], cat['sort_order'], 1, now_str
                    ))
                conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"检查预置分类失败: {e}")

    def refresh_cache(self):
        """刷新内存缓存，减少数据库压力"""
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM categories WHERE is_active = 1")
            rows = cursor.fetchall()
            
            new_name_map = {}
            new_id_map = {}
            for row in rows:
                d = dict(row)
                new_name_map[d['name']] = d['id']
                new_id_map[d['id']] = d
            
            self._name_to_id_cache = new_name_map
            self._id_to_all_cache = new_id_map
            conn.close()
            # logger.info(f"分类缓存刷新成功: {len(new_name_map)} 条记录")
        except Exception as e:
            logging.error(f"刷新分类缓存失败: {e}")

    def get_id_by_name(self, name):
        """从缓存快速获取 ID"""
        return self._name_to_id_cache.get(name)

    def get_all_active(self):
        """返回缓存中的所有启用分类"""
        return sorted(self._id_to_all_cache.values(), key=lambda x: x.get("sort_order", 0))

    def get_grouped(self):
        categories = self.get_all_active()
        grouped = {"输入": [], "输出": [], "生活": []}
        for cat in categories:
            grp = cat.get("group_name", "输入")
            if grp not in grouped: grouped[grp] = []
            grouped[grp].append(cat)
        for grp in grouped:
            grouped[grp].sort(key=lambda x: x.get("sort_order", 0))
        return grouped

    def add_category(self, name, icon, color, group_name):
        now_str = datetime.now().isoformat()
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(sort_order) FROM categories WHERE group_name = ?", (group_name,))
            max_order = cursor.fetchone()[0]
            next_order = (max_order or 0) + 1

            cursor.execute('''
                INSERT INTO categories (name, icon, color, group_name, sort_order, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, icon, color, group_name, next_order, 1, now_str))
            new_id = cursor.lastrowid
            conn.commit()
            conn.close()
            self.refresh_cache()
            return new_id
        except Exception as e:
            logging.error(f"新增分类失败: {e}")
            return None

    def update_category(self, cat_id, name=None, icon=None, color=None, group_name=None):
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            updates, params = [], []
            if name: updates.append("name = ?"); params.append(name)
            if icon: updates.append("icon = ?"); params.append(icon)
            if color: updates.append("color = ?"); params.append(color)
            if group_name: updates.append("group_name = ?"); params.append(group_name)
            if not updates: return False
            params.append(cat_id)
            cursor.execute(f"UPDATE categories SET {', '.join(updates)} WHERE id = ?", tuple(params))
            conn.commit()
            conn.close()
            self.refresh_cache()
            return True
        except Exception as e:
            logging.error(f"更新分类失败: {e}")
            return False

    def remove_category(self, cat_id):
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE categories SET is_active = 0 WHERE id = ?", (cat_id,))
            conn.commit()
            conn.close()
            self.refresh_cache()
            return True
        except Exception as e:
            logging.error(f"删除分类失败: {e}")
            return False

    def reorder_categories(self, id_order_list):
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            for cat_id, order in id_order_list:
                cursor.execute("UPDATE categories SET sort_order = ? WHERE id = ?", (order, cat_id))
            conn.commit()
            conn.close()
            self.refresh_cache()
            return True
        except Exception as e:
            logging.error(f"批量排序更新失败: {e}")
            return False
