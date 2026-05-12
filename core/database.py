"""
SQLite数据库管理模块
基于 Version2 扩展，增加邮件配置和任务跟踪
"""
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from contextlib import contextmanager


DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "scan_data.db"


@dataclass
class ScanArea:
    """扫描区域数据类"""
    id: Optional[int] = None
    area_name: str = ""
    description: str = ""
    scan_ports: str = ""
    is_full_scan: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class PortInfo:
    """端口信息数据类"""
    port_num: int = 0
    service_name: str = ""
    description: str = ""
    risk_level: int = 1
    protocol: str = "TCP"
    created_at: Optional[str] = None


@dataclass
class ReportTemplate:
    """报告模板数据类"""
    id: Optional[int] = None
    template_name: str = ""
    template_path: str = ""
    area_id: Optional[int] = None
    description: str = ""
    is_active: bool = True
    created_at: Optional[str] = None


@dataclass
class ScanRecord:
    """扫描记录数据类"""
    id: Optional[int] = None
    area_id: int = 0
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: int = 0
    ip_ranges: str = ""
    total_hosts: int = 0
    open_ports_count: int = 0
    max_workers: int = 0
    ulimit: int = 0
    result_file: str = ""
    report_file: str = ""
    scan_status: str = "running"
    error_message: str = ""
    created_at: Optional[str] = None


@dataclass
class ScanResultDetail:
    """扫描结果详情数据类"""
    id: Optional[int] = None
    record_id: int = 0
    ip_address: str = ""
    port_num: int = 0
    service_name: str = ""
    created_at: Optional[str] = None


@dataclass
class IPRange:
    """IP范围数据类"""
    id: Optional[int] = None
    ip_range: str = ""
    description: str = ""
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    area_ids: List[int] = None

    def __post_init__(self):
        if self.area_ids is None:
            self.area_ids = []


@dataclass
class EmailSettings:
    """邮件设置数据类"""
    id: Optional[int] = None
    smtp_server: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_ssl: bool = True
    skip_login: bool = False  # 跳过登录（用于IP白名单认证的服务器）
    default_sender: str = ""
    default_recipients: str = ""
    updated_at: Optional[str] = None


@dataclass
class User:
    """用户数据类"""
    id: Optional[int] = None
    username: str = ""
    password_hash: str = ""
    email: str = ""
    totp_secret: Optional[str] = None
    totp_enabled: bool = False
    totp_reset: bool = False  # 是否需要重新设置TOTP（管理员重置后）
    is_active: bool = True
    is_admin: bool = False
    first_login: bool = True  # 是否首次登录（需要修改密码）
    last_login: Optional[str] = None
    login_fail_count: int = 0
    locked_until: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class LoginLog:
    """登录日志数据类"""
    id: Optional[int] = None
    user_id: Optional[int] = None
    username: str = ""
    ip_address: str = ""
    user_agent: str = ""
    login_status: str = ""  # success/failed/totp_failed/locked
    failure_reason: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class ScheduledTask:
    """定时任务数据类"""
    id: Optional[int] = None
    task_name: str = ""
    task_type: str = "cron"  # cron/interval/once
    schedule_expr: str = ""
    use_default_config: bool = True
    ip_ranges: str = ""
    ports: str = ""
    exclude_ips: str = ""
    max_workers: int = 10
    ulimit: int = 15000
    timeout: int = 700
    is_active: bool = True
    last_run_time: Optional[str] = None
    last_run_status: str = ""
    next_run_time: Optional[str] = None
    total_runs: int = 0
    total_success: int = 0
    total_failed: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DatabaseManager:
    """数据库管理器"""

    def __init__(self, db_path: Optional[str] = None, logger: Optional[logging.Logger] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.logger = logger or logging.getLogger("DatabaseManager")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    @contextmanager
    def _get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_database(self):
        """初始化数据库，创建表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # === 性能优化 PRAGMA ===
            # WAL 模式：提升并发读写性能，避免 "database is locked"
            cursor.execute("PRAGMA journal_mode=WAL")
            # busy_timeout：等待锁的最长时间（毫秒），避免立即报错
            cursor.execute("PRAGMA busy_timeout=5000")
            # synchronous=NORMAL：WAL 模式下足够安全，比 FULL 快很多
            cursor.execute("PRAGMA synchronous=NORMAL")
            # 缓存大小：负值表示 KB，-20000 = 20MB
            cursor.execute("PRAGMA cache_size=-20000")
            # 启用外键约束
            cursor.execute("PRAGMA foreign_keys=ON")
            # 临时表存储在内存中
            cursor.execute("PRAGMA temp_store=MEMORY")
            self.logger.info("SQLite 性能优化已启用 (WAL模式, busy_timeout=5s)")

            # 1. 扫描区域分类表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scan_areas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    area_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    scan_ports TEXT,
                    is_full_scan BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 2. 端口信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ports (
                    port_num INTEGER PRIMARY KEY,
                    service_name TEXT,
                    description TEXT,
                    risk_level INTEGER CHECK(risk_level IN (1, 2, 3)) DEFAULT 1,
                    protocol TEXT DEFAULT 'TCP',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 3. 报告模板表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS report_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_name TEXT NOT NULL,
                    template_path TEXT NOT NULL,
                    area_id INTEGER,
                    description TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (area_id) REFERENCES scan_areas(id)
                )
            """)

            # 4. 扫描记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scan_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    area_id INTEGER NOT NULL,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    duration_seconds INTEGER DEFAULT 0,
                    ip_ranges TEXT,
                    total_hosts INTEGER DEFAULT 0,
                    open_ports_count INTEGER DEFAULT 0,
                    max_workers INTEGER DEFAULT 0,
                    ulimit INTEGER DEFAULT 0,
                    result_file TEXT,
                    report_file TEXT,
                    scan_status TEXT CHECK(scan_status IN ('running', 'completed', 'failed', 'cancelled')) DEFAULT 'running',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (area_id) REFERENCES scan_areas(id)
                )
            """)

            # 兼容旧表：添加 max_workers 和 ulimit 字段
            try:
                cursor.execute("ALTER TABLE scan_records ADD COLUMN max_workers INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE scan_records ADD COLUMN ulimit INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

            # 5. 扫描结果详情表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scan_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id INTEGER NOT NULL,
                    ip_address TEXT NOT NULL,
                    port_num INTEGER NOT NULL,
                    service_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (record_id) REFERENCES scan_records(id) ON DELETE CASCADE,
                    UNIQUE(record_id, ip_address, port_num)
                )
            """)

            # 6. IP范围表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ip_ranges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_range TEXT NOT NULL UNIQUE,
                    description TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 7. IP范围与区域映射表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ip_range_area_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_range_id INTEGER NOT NULL,
                    area_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (ip_range_id) REFERENCES ip_ranges(id) ON DELETE CASCADE,
                    FOREIGN KEY (area_id) REFERENCES scan_areas(id) ON DELETE CASCADE,
                    UNIQUE(ip_range_id, area_id)
                )
            """)

            # 8. 邮件设置表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS email_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    smtp_server TEXT DEFAULT '',
                    smtp_port INTEGER DEFAULT 587,
                    smtp_user TEXT DEFAULT '',
                    smtp_password TEXT DEFAULT '',
                    smtp_ssl BOOLEAN DEFAULT 1,
                    skip_login BOOLEAN DEFAULT 0,
                    default_sender TEXT DEFAULT '',
                    default_recipients TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 迁移：添加skip_login字段（如果不存在）
            try:
                cursor.execute("ALTER TABLE email_settings ADD COLUMN skip_login BOOLEAN DEFAULT 0")
                conn.commit()
                self.logger.info("已添加email_settings.skip_login字段")
            except Exception:
                pass  # 字段已存在

            # 9. 定时任务表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT NOT NULL,
                    task_type TEXT NOT NULL DEFAULT 'cron',
                    schedule_expr TEXT NOT NULL,
                    use_default_config BOOLEAN DEFAULT 1,
                    ip_ranges TEXT,
                    ports TEXT,
                    exclude_ips TEXT,
                    max_workers INTEGER DEFAULT 10,
                    ulimit INTEGER DEFAULT 15000,
                    timeout INTEGER DEFAULT 700,
                    is_active BOOLEAN DEFAULT 1,
                    last_run_time TIMESTAMP,
                    last_run_status TEXT,
                    next_run_time TIMESTAMP,
                    total_runs INTEGER DEFAULT 0,
                    total_success INTEGER DEFAULT 0,
                    total_failed INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 10. 用户表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    email VARCHAR(100) DEFAULT '',
                    totp_secret VARCHAR(32),
                    totp_enabled BOOLEAN DEFAULT 0,
                    totp_reset BOOLEAN DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    is_admin BOOLEAN DEFAULT 0,
                    first_login BOOLEAN DEFAULT 1,
                    last_login TIMESTAMP,
                    login_fail_count INTEGER DEFAULT 0,
                    locked_until TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 迁移：添加first_login字段（如果不存在）
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN first_login BOOLEAN DEFAULT 1")
                conn.commit()
                self.logger.info("已添加users.first_login字段")
                
                # 将现有用户的first_login设置为0（因为他们已经登录过了）
                cursor.execute("UPDATE users SET first_login = 0 WHERE id > 0")
                conn.commit()
                self.logger.info("已将现有用户的first_login设置为0")
            except Exception:
                pass  # 字段已存在
            
            # 迁移：添加totp_reset字段（如果不存在）
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN totp_reset BOOLEAN DEFAULT 0")
                conn.commit()
                self.logger.info("已添加users.totp_reset字段")
            except Exception:
                pass  # 字段已存在

            # 11. 登录日志表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS login_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username VARCHAR(50),
                    ip_address VARCHAR(45),
                    user_agent TEXT,
                    login_status VARCHAR(20),
                    failure_reason VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            # 12. 会话黑名单表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_blacklist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id VARCHAR(255) UNIQUE NOT NULL,
                    blacklisted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 13. Webhook 配置表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webhook_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    webhook_url TEXT NOT NULL DEFAULT '',
                    secret TEXT DEFAULT '',
                    is_active BOOLEAN DEFAULT 0,
                    notify_on_complete BOOLEAN DEFAULT 1,
                    notify_on_high_risk BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(platform)
                )
            """)

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_records_area ON scan_records(area_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_records_status ON scan_records(scan_status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_records_created ON scan_records(created_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_results_record ON scan_results(record_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_results_ip ON scan_results(ip_address)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_templates_area ON report_templates(area_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ip_range_mappings_range ON ip_range_area_mappings(ip_range_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ip_range_mappings_area ON ip_range_area_mappings(area_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_active ON scheduled_tasks(is_active)")

            self.logger.info("数据库表结构初始化完成")

    def init_default_data(self):
        """初始化默认数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 初始化扫描区域
            default_areas = [
                ("普通区", "普通网络区域，扫描指定高危端口", "22,80,443,3389,1433,1521,3306,5432,6379,27017,1883,5672", 0),
                ("红区", "红区网络，全端口扫描", "1-65535", 1),
            ]

            for area_name, desc, ports, is_full in default_areas:
                cursor.execute("""
                    INSERT OR IGNORE INTO scan_areas (area_name, description, scan_ports, is_full_scan)
                    VALUES (?, ?, ?, ?)
                """, (area_name, desc, ports, is_full))

            # 初始化端口信息
            default_ports = [
                (21, "FTP", "文件传输协议 - 明文传输，高风险", 3, "TCP"),
                (22, "SSH", "安全Shell远程登录 - 加密传输", 2, "TCP"),
                (23, "Telnet", "远程登录协议 - 明文传输，极高风险", 3, "TCP"),
                (445, "SMB", "Server Message Block - Windows文件共享，高风险", 3, "TCP"),
                (873, "RSYNC", "Rsync文件同步服务", 2, "TCP"),
                (1433, "MSSQL", "Microsoft SQL Server", 3, "TCP"),
                (1521, "Oracle", "Oracle数据库", 3, "TCP"),
                (3306, "MySQL", "MySQL数据库", 3, "TCP"),
                (5432, "PostgreSQL", "PostgreSQL数据库", 3, "TCP"),
                (6379, "Redis", "Redis缓存数据库", 3, "TCP"),
                (27017, "MongoDB", "MongoDB数据库", 3, "TCP"),
                (11211, "Memcached", "Memcached缓存服务", 2, "TCP"),
                (1883, "MQTT", "MQTT消息协议", 2, "TCP"),
                (5672, "AMQP", "AMQP高级消息队列", 2, "TCP"),
                (15672, "RabbitMQ-Mgmt", "RabbitMQ管理界面", 2, "TCP"),
                (61616, "ActiveMQ", "ActiveMQ OpenWire协议", 2, "TCP"),
                (8161, "ActiveMQ-Mgmt", "ActiveMQ管理界面", 2, "TCP"),
                (2181, "ZooKeeper", "ZooKeeper分布式协调服务", 2, "TCP"),
                (2375, "Docker", "Docker守护进程端口", 3, "TCP"),
                (3389, "RDP", "远程桌面协议 - Windows远程桌面", 3, "TCP"),
                (5900, "VNC", "VNC远程桌面", 3, "TCP"),
                (8080, "HTTP-Proxy", "HTTP代理/替代端口", 2, "TCP"),
                (8443, "HTTPS-Alt", "HTTPS替代端口", 2, "TCP"),
            ]

            for port, service, desc, risk, proto in default_ports:
                cursor.execute("""
                    INSERT OR IGNORE INTO ports (port_num, service_name, description, risk_level, protocol)
                    VALUES (?, ?, ?, ?, ?)
                """, (port, service, desc, risk, proto))

            # 初始化默认邮件设置
            cursor.execute("""
                INSERT OR IGNORE INTO email_settings (id, smtp_server, smtp_port, smtp_ssl)
                VALUES (1, '', 587, 1)
            """)

            self.logger.info(f"默认数据初始化完成")

    # ==================== 扫描区域操作 ====================

    def get_scan_areas(self) -> List[ScanArea]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scan_areas ORDER BY id")
            rows = cursor.fetchall()
            return [ScanArea(**dict(row)) for row in rows]

    def get_scan_area_by_name(self, area_name: str) -> Optional[ScanArea]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scan_areas WHERE area_name = ?", (area_name,))
            row = cursor.fetchone()
            return ScanArea(**dict(row)) if row else None

    def get_scan_area_by_id(self, area_id: int) -> Optional[ScanArea]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scan_areas WHERE id = ?", (area_id,))
            row = cursor.fetchone()
            return ScanArea(**dict(row)) if row else None

    # ==================== 扫描记录操作 ====================

    def create_scan_record(self, record: ScanRecord) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scan_records (area_id, start_time, ip_ranges, scan_status, result_file, max_workers, ulimit)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (record.area_id, record.start_time, record.ip_ranges,
                  record.scan_status, record.result_file, record.max_workers, record.ulimit))
            return cursor.lastrowid

    def update_scan_record(self, record_id: int, **kwargs) -> bool:
        allowed_fields = ['end_time', 'duration_seconds', 'total_hosts',
                         'open_ports_count', 'max_workers', 'ulimit',
                         'result_file', 'report_file',
                         'scan_status', 'error_message']

        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return False

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                sql = f"UPDATE scan_records SET {set_clause} WHERE id = ?"
                cursor.execute(sql, (*updates.values(), record_id))
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"更新扫描记录失败: {e}")
            return False

    def get_scan_records(self, area_id: Optional[int] = None,
                        status: Optional[str] = None,
                        limit: int = 100) -> List[ScanRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            sql = "SELECT * FROM scan_records WHERE 1=1"
            params = []

            if area_id:
                sql += " AND area_id = ?"
                params.append(area_id)
            if status:
                sql += " AND scan_status = ?"
                params.append(status)

            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [ScanRecord(**dict(row)) for row in rows]

    def get_scan_record_by_id(self, record_id: int) -> Optional[ScanRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scan_records WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            return ScanRecord(**dict(row)) if row else None

    # ==================== 扫描结果操作 ====================

    def add_scan_results_batch(self, record_id: int, results: List[Tuple[str, int, str]]):
        """批量插入扫描结果（优化版：事务控制 + 分块插入）"""
        CHUNK_SIZE = 500  # 每批 500 条
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 使用单个事务
            cursor.execute("BEGIN TRANSACTION")
            try:
                for i in range(0, len(results), CHUNK_SIZE):
                    chunk = results[i:i+CHUNK_SIZE]
                    cursor.executemany(
                        "INSERT OR IGNORE INTO scan_results (record_id, ip_address, port_num, service_name) VALUES (?, ?, ?, ?)",
                        [(record_id, ip, port, service) for ip, port, service in chunk]
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get_scan_results(self, record_id: int) -> List[ScanResultDetail]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM scan_results WHERE record_id = ? ORDER BY ip_address, port_num
            """, (record_id,))
            rows = cursor.fetchall()
            return [ScanResultDetail(**dict(row)) for row in rows]

    def get_statistics(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            stats = {}

            cursor.execute("SELECT COUNT(*) FROM scan_records")
            stats['total_scans'] = cursor.fetchone()[0]

            cursor.execute("""
                SELECT scan_status, COUNT(*) FROM scan_records GROUP BY scan_status
            """)
            stats['status_counts'] = dict(cursor.fetchall())

            cursor.execute("SELECT SUM(total_hosts) FROM scan_records")
            stats['total_hosts'] = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT sa.area_name, COUNT(*)
                FROM scan_records sr
                JOIN scan_areas sa ON sr.area_id = sa.id
                GROUP BY sa.area_name
            """)
            stats['area_counts'] = dict(cursor.fetchall())

            return stats

    # ==================== 邮件设置操作 ====================

    def get_email_settings(self) -> Optional[EmailSettings]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM email_settings WHERE id = 1")
            row = cursor.fetchone()
            return EmailSettings(**dict(row)) if row else None

    def update_email_settings(self, settings: EmailSettings) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO email_settings
                    (id, smtp_server, smtp_port, smtp_user, smtp_password,
                     smtp_ssl, skip_login, default_sender, default_recipients, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (settings.smtp_server, settings.smtp_port, settings.smtp_user,
                      settings.smtp_password, settings.smtp_ssl, settings.skip_login,
                      settings.default_sender, settings.default_recipients))
                return True
        except Exception as e:
            self.logger.error(f"更新邮件设置失败: {e}")
            return False

    # ==================== IP范围操作 ====================

    def add_ip_range(self, ip_range: IPRange) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO ip_ranges (ip_range, description, is_active)
                VALUES (?, ?, ?)
            """, (ip_range.ip_range, ip_range.description, ip_range.is_active))
            ip_range_id = cursor.lastrowid

            for area_id in ip_range.area_ids:
                cursor.execute("""
                    INSERT OR IGNORE INTO ip_range_area_mappings (ip_range_id, area_id)
                    VALUES (?, ?)
                """, (ip_range_id, area_id))

            return ip_range_id

    def get_ip_ranges(self, area_id: Optional[int] = None, active_only: bool = True) -> List[IPRange]:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if area_id:
                sql = """
                    SELECT ir.* FROM ip_ranges ir
                    JOIN ip_range_area_mappings map ON ir.id = map.ip_range_id
                    WHERE map.area_id = ?
                """
                params = [area_id]
                if active_only:
                    sql += " AND ir.is_active = 1"
                sql += " ORDER BY ir.ip_range"
                cursor.execute(sql, params)
            else:
                sql = "SELECT * FROM ip_ranges"
                if active_only:
                    sql += " WHERE is_active = 1"
                sql += " ORDER BY ip_range"
                cursor.execute(sql)

            rows = cursor.fetchall()
            ip_ranges = []

            for row in rows:
                ip_range = IPRange(**dict(row))
                ip_range.area_ids = self._get_ip_range_areas(conn, ip_range.id)
                ip_ranges.append(ip_range)

            return ip_ranges

    def _get_ip_range_areas(self, conn, ip_range_id: int) -> List[int]:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT area_id FROM ip_range_area_mappings WHERE ip_range_id = ?
        """, (ip_range_id,))
        return [row[0] for row in cursor.fetchall()]

    def delete_ip_range(self, range_id: int) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM ip_ranges WHERE id = ?", (range_id,))
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"删除IP范围失败: {e}")
            return False

    def import_ip_ranges_from_file(self, file_path: str, area_ids: List[int]) -> Tuple[int, int]:
        success_count = 0
        fail_count = 0

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    try:
                        ip_range = IPRange(
                            ip_range=line,
                            description="",
                            is_active=True,
                            area_ids=area_ids
                        )
                        self.add_ip_range(ip_range)
                        success_count += 1
                    except Exception as e:
                        self.logger.error(f"导入IP范围失败 {line}: {e}")
                        fail_count += 1

        except Exception as e:
            self.logger.error(f"读取IP范围文件失败: {e}")

        return success_count, fail_count

    # ==================== 模板操作 ====================

    def get_templates(self, area_id: Optional[int] = None, active_only: bool = True) -> List[ReportTemplate]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            sql = "SELECT * FROM report_templates WHERE 1=1"
            params = []

            if area_id:
                sql += " AND area_id = ?"
                params.append(area_id)
            if active_only:
                sql += " AND is_active = 1"

            sql += " ORDER BY id"
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [ReportTemplate(**dict(row)) for row in rows]

    def get_template_by_name(self, name: str) -> Optional[ReportTemplate]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM report_templates WHERE template_name = ?", (name,))
            row = cursor.fetchone()
            return ReportTemplate(**dict(row)) if row else None

    def add_template(self, template: ReportTemplate) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO report_templates (template_name, template_path, area_id, description, is_active)
                VALUES (?, ?, ?, ?, ?)
            """, (template.template_name, template.template_path, template.area_id,
                  template.description, template.is_active))
            return cursor.lastrowid

    def delete_template(self, template_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM report_templates WHERE id = ?", (template_id,))
            return cursor.rowcount > 0

    # ==================== 定时任务操作 ====================

    def add_scheduled_task(self, task: ScheduledTask) -> int:
        """添加定时任务，返回任务ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scheduled_tasks (
                    task_name, task_type, schedule_expr, use_default_config,
                    ip_ranges, ports, exclude_ips, max_workers, ulimit, timeout,
                    is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.task_name, task.task_type, task.schedule_expr, task.use_default_config,
                task.ip_ranges, task.ports, task.exclude_ips, task.max_workers,
                task.ulimit, task.timeout, task.is_active
            ))
            return cursor.lastrowid

    def get_scheduled_task(self, task_id: int) -> Optional[ScheduledTask]:
        """获取单个定时任务"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            return ScheduledTask(**dict(row)) if row else None

    def get_scheduled_tasks(self, active_only: bool = False) -> List[ScheduledTask]:
        """获取所有定时任务"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            sql = "SELECT * FROM scheduled_tasks"
            if active_only:
                sql += " WHERE is_active = 1"
            sql += " ORDER BY id DESC"
            cursor.execute(sql)
            rows = cursor.fetchall()
            return [ScheduledTask(**dict(row)) for row in rows]

    def update_scheduled_task(self, task_id: int, **kwargs) -> bool:
        """更新定时任务"""
        if not kwargs:
            return False

        fields = []
        values = []
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(value)
        
        fields.append("updated_at = CURRENT_TIMESTAMP")
        values.append(task_id)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            sql = f"UPDATE scheduled_tasks SET {', '.join(fields)} WHERE id = ?"
            cursor.execute(sql, values)
            return cursor.rowcount > 0

    def delete_scheduled_task(self, task_id: int) -> bool:
        """删除定时任务"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
            return cursor.rowcount > 0

    def update_task_execution_record(self, task_id: int, status: str) -> bool:
        """更新任务执行记录（执行时间、状态、统计）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 获取当前统计
            cursor.execute(
                "SELECT total_runs, total_success, total_failed FROM scheduled_tasks WHERE id = ?",
                (task_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            
            total_runs = row["total_runs"]
            total_success = row["total_success"]
            total_failed = row["total_failed"]
            
            # 只在最终状态时增加 total_runs
            if status in ("success", "failed", "skipped"):
                total_runs += 1
            
            if status == "success":
                total_success += 1
            elif status == "failed":
                total_failed += 1
            # running 状态不增加计数
            
            cursor.execute("""
                UPDATE scheduled_tasks 
                SET last_run_time = ?, last_run_status = ?,
                    total_runs = ?, total_success = ?, total_failed = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (now, status, total_runs, total_success, total_failed, task_id))
            return cursor.rowcount > 0

    def close(self):
        pass

    # ==================== 用户管理方法 ====================

    def create_user(self, username: str, password_hash: str, email: str = "", is_admin: bool = False) -> int:
        """创建用户"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash, email, is_admin, first_login) VALUES (?, ?, ?, ?, 1)",
                (username, password_hash, email, is_admin)
            )
            return cursor.lastrowid

    def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if row:
                return User(**dict(row))
            return None

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return User(**dict(row))
            return None

    def update_user_login(self, user_id: int, success: bool = True) -> bool:
        """更新用户登录信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if success:
                cursor.execute(
                    "UPDATE users SET last_login = ?, login_fail_count = 0, locked_until = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (now, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE users SET login_fail_count = login_fail_count + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (user_id,)
                )
            return cursor.rowcount > 0

    def lock_user(self, user_id: int, duration_minutes: int) -> bool:
        """锁定用户账户"""
        from datetime import timedelta
        with self._get_connection() as conn:
            cursor = conn.cursor()
            locked_until = (datetime.now() + timedelta(minutes=duration_minutes)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "UPDATE users SET locked_until = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (locked_until, user_id)
            )
            return cursor.rowcount > 0

    def reset_user_password(self, user_id: int, new_password_hash: str) -> bool:
        """重置用户密码"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET password_hash = ?, first_login = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_password_hash, user_id)
            )
            return cursor.rowcount > 0

    def update_user_totp(self, user_id: int, totp_secret: str, enabled: bool) -> bool:
        """更新用户TOTP设置"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET totp_secret = ?, totp_enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (totp_secret, enabled, user_id)
            )
            return cursor.rowcount > 0

    def update_user_info(self, user_id: int, username: str, email: str, 
                        is_admin: bool, is_active: bool) -> bool:
        """
        更新用户基本信息
        
        Args:
            user_id: 用户ID
            username: 用户名
            email: 邮箱
            is_admin: 是否管理员
            is_active: 是否激活
            
        Returns:
            是否成功
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET username = ?, email = ?, is_admin = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (username, email, is_admin, is_active, user_id)
            )
            return cursor.rowcount > 0

    # ==================== 登录日志方法 ====================

    def create_login_log(self, user_id: Optional[int], username: str, ip_address: str,
                        user_agent: str, login_status: str, failure_reason: Optional[str] = None) -> int:
        """创建登录日志"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO login_logs (user_id, username, ip_address, user_agent, login_status, failure_reason) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, username, ip_address, user_agent, login_status, failure_reason)
            )
            return cursor.lastrowid

    def get_login_logs(self, limit: int = 100, user_id: Optional[int] = None) -> List[LoginLog]:
        """获取登录日志"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute(
                    "SELECT * FROM login_logs WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                    (user_id, limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM login_logs ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
            rows = cursor.fetchall()
            return [LoginLog(**dict(row)) for row in rows]

    # ==================== 会话黑名单方法 ====================

    def add_session_to_blacklist(self, session_id: str) -> bool:
        """将会话ID加入黑名单"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO session_blacklist (session_id) VALUES (?)",
                (session_id,)
            )
            return cursor.rowcount > 0

    def is_session_blacklisted(self, session_id: str) -> bool:
        """检查会话是否在黑名单中"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM session_blacklist WHERE session_id = ?", (session_id,))
            return cursor.fetchone() is not None

    def cleanup_expired_blacklist(self, max_age_hours: int = 168) -> int:
        """
        清理过期的黑名单记录
        JWT access token 有效期 15 分钟，refresh token 7 天，
        超过 7 天（168 小时）的黑名单记录可以安全删除
        
        Args:
            max_age_hours: 最大保留时间（小时），默认 168（7天）
        Returns:
            删除的记录数
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM session_blacklist WHERE blacklisted_at < datetime('now', ?)",
                    (f'-{max_age_hours} hours',)
                )
                deleted = cursor.rowcount
                if deleted > 0:
                    self.logger.info(f"已清理 {deleted} 条过期黑名单记录")
                return deleted
        except Exception as e:
            self.logger.error(f"清理黑名单失败: {e}")
            return 0

    # ==================== Webhook 配置操作 ====================

    def get_webhook_configs(self) -> List[Dict]:
        """获取所有 Webhook 配置"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM webhook_configs ORDER BY id")
            return [dict(row) for row in cursor.fetchall()]

    def save_webhook_config(self, platform: str, config: Dict) -> bool:
        """保存 Webhook 配置"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO webhook_configs 
                    (platform, webhook_url, secret, is_active, notify_on_complete, notify_on_high_risk, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(platform) DO UPDATE SET
                        webhook_url = excluded.webhook_url,
                        secret = excluded.secret,
                        is_active = excluded.is_active,
                        notify_on_complete = excluded.notify_on_complete,
                        notify_on_high_risk = excluded.notify_on_high_risk,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    platform,
                    config.get('webhook_url', ''),
                    config.get('secret', ''),
                    config.get('is_active', False),
                    config.get('notify_on_complete', True),
                    config.get('notify_on_high_risk', True),
                ))
                return True
        except Exception as e:
            self.logger.error(f"保存 Webhook 配置失败: {e}")
            return False

    def delete_webhook_config(self, platform: str) -> bool:
        """删除 Webhook 配置"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM webhook_configs WHERE platform = ?", (platform,))
            return cursor.rowcount > 0

    # ==================== 资产变更追踪 ====================

    def compare_scan_results(self, record_id_old: int, record_id_new: int) -> Dict[str, Any]:
        """
        对比两次扫描结果，识别资产变更
        
        Returns:
            {
                'new_hosts': [ip, ...],           # 新增主机
                'removed_hosts': [ip, ...],        # 下线主机
                'port_changes': [                  # 端口变更
                    {'ip': str, 'added': [ports], 'removed': [ports]}
                ],
                'total_old': int,
                'total_new': int
            }
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取旧扫描的 IP-端口映射
            cursor.execute(
                "SELECT ip_address, port_num FROM scan_results WHERE record_id = ?",
                (record_id_old,)
            )
            old_data = {}
            for row in cursor.fetchall():
                old_data.setdefault(row['ip_address'], set()).add(row['port_num'])
            
            # 获取新扫描的 IP-端口映射
            cursor.execute(
                "SELECT ip_address, port_num FROM scan_results WHERE record_id = ?",
                (record_id_new,)
            )
            new_data = {}
            for row in cursor.fetchall():
                new_data.setdefault(row['ip_address'], set()).add(row['port_num'])
            
            old_ips = set(old_data.keys())
            new_ips = set(new_data.keys())
            
            # 新增/下线主机
            new_hosts = sorted(new_ips - old_ips)
            removed_hosts = sorted(old_ips - new_ips)
            
            # 端口变更
            port_changes = []
            common_ips = old_ips & new_ips
            for ip in sorted(common_ips):
                old_ports = old_data[ip]
                new_ports = new_data[ip]
                if old_ports != new_ports:
                    added = sorted(new_ports - old_ports)
                    removed = sorted(old_ports - new_ports)
                    if added or removed:
                        port_changes.append({
                            'ip': ip,
                            'added': added,
                            'removed': removed
                        })
            
            return {
                'new_hosts': new_hosts,
                'removed_hosts': removed_hosts,
                'port_changes': port_changes,
                'total_old': len(old_ips),
                'total_new': len(new_ips)
            }

    def get_asset_trend(self, days: int = 30) -> List[Dict]:
        """
        获取资产数量变化趋势（用于 Dashboard 图表）
        
        Args:
            days: 统计最近多少天
        Returns:
            [{'date': str, 'host_count': int, 'port_count': int}, ...]
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            trend = []
            for i in range(days - 1, -1, -1):
                cursor.execute("""
                    SELECT 
                        COALESCE(SUM(total_hosts), 0) as host_count,
                        COALESCE(SUM(open_ports_count), 0) as port_count,
                        COUNT(*) as scan_count
                    FROM scan_records 
                    WHERE date(created_at) = date('now', ? || ' days')
                    AND scan_status = 'completed'
                """, (str(-i),))
                row = cursor.fetchone()
                from datetime import datetime, timedelta
                day_date = (datetime.now() - timedelta(days=i)).strftime('%m/%d')
                trend.append({
                    'date': day_date,
                    'host_count': row['host_count'] or 0,
                    'port_count': row['port_count'] or 0,
                    'scan_count': row['scan_count'] or 0
                })
            return trend
