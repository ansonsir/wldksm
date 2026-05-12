"""
database.py 模块单元测试
测试 DatabaseManager 核心 CRUD 操作
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import tempfile
import os
from core.database import DatabaseManager, ScanRecord


class TestDatabaseManager:
    """DatabaseManager 基础测试（使用临时数据库）"""

    @pytest.fixture
    def db(self):
        """创建临时数据库实例"""
        fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        mgr = DatabaseManager(db_path=db_path)
        yield mgr
        mgr.close()
        try:
            os.unlink(db_path)
        except Exception:
            pass

    def test_init_creates_tables(self, db):
        """初始化应创建所有表"""
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r['name'] for r in cursor.fetchall()]
        assert 'scan_records' in tables
        assert 'scan_results' in tables
        assert 'users' in tables
        assert 'scan_areas' in tables

    def test_init_default_data(self, db):
        """init_default_data 创建默认扫描区域和模板"""
        db.init_default_data()
        areas = db.get_scan_areas()
        area_names = [a.area_name for a in areas]
        assert '普通区' in area_names
        assert '红区' in area_names

    def test_create_and_get_user(self, db):
        """创建用户并读取"""
        from datetime import datetime
        db.create_user(
            username='testuser',
            password_hash='hashed_pw',
            email='test@example.com',
            is_admin=False
        )
        user = db.get_user_by_username('testuser')
        assert user is not None
        assert user.username == 'testuser'
        assert user.email == 'test@example.com'
        assert user.is_admin == 0

    def test_get_nonexistent_user(self, db):
        """查询不存在的用户应返回 None"""
        user = db.get_user_by_username('no_such_user')
        assert user is None

    def test_scan_record_crud(self, db):
        """扫描记录 创建/读取/列表 完整流程"""
        db.init_default_data()
        areas = db.get_scan_areas()
        area_id = areas[0].id

        # 创建
        record = ScanRecord(
            area_id=area_id,
            ip_ranges="192.168.1.0/24",
            result_file="test.txt",
            max_workers=10,
            ulimit=5000
        )
        record_id = db.create_scan_record(record)
        assert record_id > 0

        # 读取
        record = db.get_scan_record_by_id(record_id)
        assert record is not None
        assert record.area_id == area_id
        assert record.ip_ranges == "192.168.1.0/24"

        # 列表
        records = db.get_scan_records(limit=10)
        assert len(records) >= 1

    def test_record_not_found(self, db):
        """查询不存在的记录返回 None"""
        record = db.get_scan_record_by_id(99999)
        assert record is None
