"""
SQLite数据库管理模块
提供扫描区域、端口、模板、扫描记录的持久化管理
"""
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from contextlib import contextmanager


# 默认数据库路径
DEFAULT_DB_PATH = Path(__file__).parent / "scan_data.db"


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
    risk_level: int = 1  # 1-低, 2-中, 3-高
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
    result_file: str = ""
    report_file: str = ""
    scan_status: str = "running"  # running, completed, failed, cancelled
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
    """IP范围数据类 - 支持多区域归属"""
    id: Optional[int] = None
    ip_range: str = ""  # CIDR格式，如 10.0.0.0/24
    description: str = ""
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    area_ids: List[int] = None  # 关联的多个区域ID
    
    def __post_init__(self):
        if self.area_ids is None:
            self.area_ids = []


@dataclass
class IPRangeAreaMapping:
    """IP范围与区域映射关系表"""
    id: Optional[int] = None
    ip_range_id: int = 0
    area_id: int = 0
    created_at: Optional[str] = None


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: Optional[str] = None, logger: Optional[logging.Logger] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.logger = logger or logging.getLogger("DatabaseManager")
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
                    result_file TEXT,
                    report_file TEXT,
                    scan_status TEXT CHECK(scan_status IN ('running', 'completed', 'failed', 'cancelled')) DEFAULT 'running',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (area_id) REFERENCES scan_areas(id)
                )
            """)
            
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
            
            # 6. IP范围表（独立表，不直接关联区域）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ip_ranges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_range TEXT NOT NULL UNIQUE,  -- CIDR格式，如 10.0.0.0/24
                    description TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 7. IP范围与区域映射表（多对多关系）
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
            
            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_records_area ON scan_records(area_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_records_status ON scan_records(scan_status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_results_record ON scan_results(record_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_templates_area ON report_templates(area_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ip_range_mappings_range ON ip_range_area_mappings(ip_range_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ip_range_mappings_area ON ip_range_area_mappings(area_id)")
            
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
            
            # 初始化端口信息（来自 ports.txt）
            default_ports = [
                # 文件传输与远程管理
                (21, "FTP", "文件传输协议 - 明文传输，高风险", 3, "TCP"),
                (22, "SSH", "安全Shell远程登录 - 加密传输", 2, "TCP"),
                (23, "Telnet", "远程登录协议 - 明文传输，极高风险", 3, "TCP"),
                
                # Windows文件共享
                (445, "SMB", "Server Message Block - Windows文件共享，高风险", 3, "TCP"),
                
                # 数据同步
                (873, "RSYNC", "Rsync文件同步服务", 2, "TCP"),
                
                # 数据库服务
                (1433, "MSSQL", "Microsoft SQL Server - 微软数据库", 3, "TCP"),
                (1521, "Oracle", "Oracle数据库 - 企业级数据库", 3, "TCP"),
                (3306, "MySQL", "MySQL数据库 - 开源关系型数据库", 3, "TCP"),
                (5432, "PostgreSQL", "PostgreSQL数据库 - 开源对象关系型数据库", 3, "TCP"),
                (6379, "Redis", "Redis缓存数据库 - 内存键值存储", 3, "TCP"),
                (27017, "MongoDB", "MongoDB数据库 - NoSQL文档数据库", 3, "TCP"),
                (11211, "Memcached", "Memcached缓存服务 - 分布式内存缓存", 2, "TCP"),
                
                # 消息队列与MQTT
                (1883, "MQTT", "MQTT消息协议 - 物联网标准协议", 2, "TCP"),
                (5672, "AMQP", "AMQP高级消息队列 - RabbitMQ默认端口", 2, "TCP"),
                (15672, "RabbitMQ-Mgmt", "RabbitMQ管理界面", 2, "TCP"),
                (61616, "ActiveMQ", "ActiveMQ OpenWire协议", 2, "TCP"),
                (8161, "ActiveMQ-Mgmt", "ActiveMQ管理界面", 2, "TCP"),
                
                # 分布式协调
                (2181, "ZooKeeper", "ZooKeeper分布式协调服务", 2, "TCP"),
                (2375, "Docker", "Docker守护进程端口 - 容器管理", 3, "TCP"),
                
                # Web服务
                (8080, "HTTP-Proxy", "HTTP代理/替代端口 - 常见Web服务", 2, "TCP"),
                (8081, "HTTP-Alt", "HTTP替代端口", 2, "TCP"),
                (8082, "HTTP-Alt2", "HTTP替代端口", 2, "TCP"),
                (8088, "HTTP-Alt3", "HTTP替代端口", 2, "TCP"),
                (8443, "HTTPS-Alt", "HTTPS替代端口 - 常见Web安全服务", 2, "TCP"),
                (8888, "HTTP-Alt4", "HTTP替代端口 - 常见于代理和开发服务器", 2, "TCP"),
                
                # 远程桌面
                (3389, "RDP", "远程桌面协议 - Windows远程桌面", 3, "TCP"),
                (5900, "VNC", "VNC远程桌面 - 虚拟网络计算", 3, "TCP"),
                (5901, "VNC-1", "VNC显示端口:1", 3, "TCP"),
                (5902, "VNC-2", "VNC显示端口:2", 3, "TCP"),
                (5903, "VNC-3", "VNC显示端口:3", 3, "TCP"),
                (5904, "VNC-4", "VNC显示端口:4", 3, "TCP"),
                (5905, "VNC-5", "VNC显示端口:5", 3, "TCP"),
                
                # 应用服务器
                (7001, "WebLogic", "WebLogic应用服务器 - Oracle中间件", 2, "TCP"),
                (8848, "Nacos", "Nacos服务发现与配置中心", 2, "TCP"),
                
                # 搜索引擎
                (9200, "Elasticsearch", "Elasticsearch搜索引擎 - RESTful接口", 2, "TCP"),
                
                # 其他服务
                (5236, "达梦数据库", "达梦数据库 - 国产数据库", 3, "TCP"),
                (54321, "自定义服务", "自定义应用端口", 1, "TCP"),
            ]
            
            for port, service, desc, risk, proto in default_ports:
                cursor.execute("""
                    INSERT OR IGNORE INTO ports (port_num, service_name, description, risk_level, protocol)
                    VALUES (?, ?, ?, ?, ?)
                """, (port, service, desc, risk, proto))
            
            self.logger.info(f"默认数据初始化完成，共 {len(default_ports)} 个端口")
    
    # ==================== 扫描区域操作 ====================
    
    def get_scan_areas(self) -> List[ScanArea]:
        """获取所有扫描区域"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scan_areas ORDER BY id")
            rows = cursor.fetchall()
            return [ScanArea(**dict(row)) for row in rows]
    
    def get_scan_area_by_name(self, area_name: str) -> Optional[ScanArea]:
        """根据名称获取扫描区域"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scan_areas WHERE area_name = ?", (area_name,))
            row = cursor.fetchone()
            return ScanArea(**dict(row)) if row else None
    
    def get_scan_area_by_id(self, area_id: int) -> Optional[ScanArea]:
        """根据ID获取扫描区域"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scan_areas WHERE id = ?", (area_id,))
            row = cursor.fetchone()
            return ScanArea(**dict(row)) if row else None
    
    def add_scan_area(self, area: ScanArea) -> int:
        """添加扫描区域"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scan_areas (area_name, description, scan_ports, is_full_scan)
                VALUES (?, ?, ?, ?)
            """, (area.area_name, area.description, area.scan_ports, area.is_full_scan))
            return cursor.lastrowid
    
    # ==================== 端口信息操作 ====================
    
    def get_ports(self, risk_level: Optional[int] = None) -> List[PortInfo]:
        """获取端口信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if risk_level:
                cursor.execute("SELECT * FROM ports WHERE risk_level = ? ORDER BY port_num", (risk_level,))
            else:
                cursor.execute("SELECT * FROM ports ORDER BY port_num")
            rows = cursor.fetchall()
            return [PortInfo(**dict(row)) for row in rows]
    
    def get_port_by_number(self, port_num: int) -> Optional[PortInfo]:
        """根据端口号获取信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ports WHERE port_num = ?", (port_num,))
            row = cursor.fetchone()
            return PortInfo(**dict(row)) if row else None
    
    def add_port(self, port: PortInfo) -> bool:
        """添加端口信息"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO ports (port_num, service_name, description, risk_level, protocol)
                    VALUES (?, ?, ?, ?, ?)
                """, (port.port_num, port.service_name, port.description, port.risk_level, port.protocol))
                return True
        except Exception as e:
            self.logger.error(f"添加端口失败: {e}")
            return False
    
    # ==================== 模板操作 ====================
    
    def get_templates(self, area_id: Optional[int] = None, active_only: bool = True) -> List[ReportTemplate]:
        """获取报告模板"""
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
        """根据名称获取模板"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM report_templates WHERE template_name = ?", (name,))
            row = cursor.fetchone()
            return ReportTemplate(**dict(row)) if row else None
    
    def add_template(self, template: ReportTemplate) -> int:
        """添加模板"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO report_templates (template_name, template_path, area_id, description, is_active)
                VALUES (?, ?, ?, ?, ?)
            """, (template.template_name, template.template_path, template.area_id, 
                  template.description, template.is_active))
            return cursor.lastrowid
    
    def update_template_status(self, template_id: int, is_active: bool) -> bool:
        """更新模板状态"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE report_templates SET is_active = ? WHERE id = ?
                """, (is_active, template_id))
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"更新模板状态失败: {e}")
            return False
    
    # ==================== 扫描记录操作 ====================
    
    def create_scan_record(self, record: ScanRecord) -> int:
        """创建扫描记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scan_records (area_id, start_time, ip_ranges, scan_status, result_file)
                VALUES (?, ?, ?, ?, ?)
            """, (record.area_id, record.start_time, record.ip_ranges, 
                  record.scan_status, record.result_file))
            return cursor.lastrowid
    
    def update_scan_record(self, record_id: int, **kwargs) -> bool:
        """更新扫描记录"""
        allowed_fields = ['end_time', 'duration_seconds', 'total_hosts', 
                         'open_ports_count', 'result_file', 'report_file', 
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
        """获取扫描记录"""
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
        """根据ID获取扫描记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scan_records WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            return ScanRecord(**dict(row)) if row else None
    
    # ==================== 扫描结果操作 ====================
    
    def add_scan_result(self, result: ScanResultDetail) -> int:
        """添加扫描结果详情"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO scan_results (record_id, ip_address, port_num, service_name)
                VALUES (?, ?, ?, ?)
            """, (result.record_id, result.ip_address, result.port_num, result.service_name))
            return cursor.lastrowid
    
    def add_scan_results_batch(self, record_id: int, results: List[Tuple[str, int, str]]):
        """批量添加扫描结果"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT OR IGNORE INTO scan_results (record_id, ip_address, port_num, service_name)
                VALUES (?, ?, ?, ?)
            """, [(record_id, ip, port, service) for ip, port, service in results])
    
    def get_scan_results(self, record_id: int) -> List[ScanResultDetail]:
        """获取扫描结果详情"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM scan_results WHERE record_id = ? ORDER BY ip_address, port_num
            """, (record_id,))
            rows = cursor.fetchall()
            return [ScanResultDetail(**dict(row)) for row in rows]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # 总扫描次数
            cursor.execute("SELECT COUNT(*) FROM scan_records")
            stats['total_scans'] = cursor.fetchone()[0]
            
            # 各状态扫描次数
            cursor.execute("""
                SELECT scan_status, COUNT(*) FROM scan_records GROUP BY scan_status
            """)
            stats['status_counts'] = dict(cursor.fetchall())
            
            # 发现的主机总数
            cursor.execute("SELECT SUM(total_hosts) FROM scan_records")
            stats['total_hosts'] = cursor.fetchone()[0] or 0
            
            # 各区域扫描次数
            cursor.execute("""
                SELECT sa.area_name, COUNT(*) 
                FROM scan_records sr 
                JOIN scan_areas sa ON sr.area_id = sa.id 
                GROUP BY sa.area_name
            """)
            stats['area_counts'] = dict(cursor.fetchall())
            
            return stats
    
    # ==================== IP范围操作（支持多区域） ====================
    
    def add_ip_range(self, ip_range: IPRange) -> int:
        """
        添加IP范围，并建立与区域的映射关系
        
        :param ip_range: IP范围对象（包含area_ids列表）
        :return: IP范围ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 插入IP范围
            cursor.execute("""
                INSERT OR REPLACE INTO ip_ranges (ip_range, description, is_active)
                VALUES (?, ?, ?)
            """, (ip_range.ip_range, ip_range.description, ip_range.is_active))
            
            ip_range_id = cursor.lastrowid
            
            # 2. 建立区域映射关系
            for area_id in ip_range.area_ids:
                cursor.execute("""
                    INSERT OR IGNORE INTO ip_range_area_mappings (ip_range_id, area_id)
                    VALUES (?, ?)
                """, (ip_range_id, area_id))
            
            return ip_range_id
    
    def get_ip_ranges(self, area_id: Optional[int] = None, active_only: bool = True) -> List[IPRange]:
        """
        获取IP范围列表
        
        :param area_id: 区域ID（可选，None表示获取所有）
        :param active_only: 是否只获取启用的
        :return: IP范围列表（包含area_ids）
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if area_id:
                # 获取指定区域的IP范围
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
                # 获取所有IP范围
                sql = "SELECT * FROM ip_ranges"
                if active_only:
                    sql += " WHERE is_active = 1"
                sql += " ORDER BY ip_range"
                cursor.execute(sql)
            
            rows = cursor.fetchall()
            ip_ranges = []
            
            for row in rows:
                ip_range = IPRange(**dict(row))
                # 获取关联的区域ID
                ip_range.area_ids = self._get_ip_range_areas(conn, ip_range.id)
                ip_ranges.append(ip_range)
            
            return ip_ranges
    
    def _get_ip_range_areas(self, conn, ip_range_id: int) -> List[int]:
        """获取IP范围关联的所有区域ID"""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT area_id FROM ip_range_area_mappings WHERE ip_range_id = ?
        """, (ip_range_id,))
        return [row[0] for row in cursor.fetchall()]
    
    def get_ip_range_by_id(self, range_id: int) -> Optional[IPRange]:
        """根据ID获取IP范围"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ip_ranges WHERE id = ?", (range_id,))
            row = cursor.fetchone()
            if row:
                ip_range = IPRange(**dict(row))
                ip_range.area_ids = self._get_ip_range_areas(conn, ip_range.id)
                return ip_range
            return None
    
    def add_ip_range_to_area(self, ip_range_id: int, area_id: int) -> bool:
        """将IP范围添加到区域"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO ip_range_area_mappings (ip_range_id, area_id)
                    VALUES (?, ?)
                """, (ip_range_id, area_id))
                return True
        except Exception as e:
            self.logger.error(f"添加IP范围到区域失败: {e}")
            return False
    
    def remove_ip_range_from_area(self, ip_range_id: int, area_id: int) -> bool:
        """从区域移除IP范围"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM ip_range_area_mappings WHERE ip_range_id = ? AND area_id = ?
                """, (ip_range_id, area_id))
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"从区域移除IP范围失败: {e}")
            return False
    
    def update_ip_range_status(self, range_id: int, is_active: bool) -> bool:
        """更新IP范围状态"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE ip_ranges SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """, (is_active, range_id))
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"更新IP范围状态失败: {e}")
            return False
    
    def delete_ip_range(self, range_id: int) -> bool:
        """删除IP范围"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM ip_ranges WHERE id = ?", (range_id,))
                return cursor.rowcount > 0
        except Exception as e:
            self.logger.error(f"删除IP范围失败: {e}")
            return False
    
    def import_ip_ranges_from_file(self, file_path: str, area_ids: List[int]) -> Tuple[int, int]:
        """
        从文件导入IP范围（支持多区域）
        
        :param file_path: IP范围文件路径
        :param area_ids: 区域ID列表
        :return: (成功导入数量, 失败数量)
        """
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
            
            self.logger.info(f"IP范围导入完成: 成功 {success_count}, 失败 {fail_count}")
            
        except Exception as e:
            self.logger.error(f"读取IP范围文件失败: {e}")
        
        return success_count, fail_count
    
    def export_ip_ranges_to_file(self, file_path: str, area_id: Optional[int] = None) -> int:
        """
        导出IP范围到文件
        
        :param file_path: 输出文件路径
        :param area_id: 区域ID（可选，None表示导出所有）
        :return: 导出的数量
        """
        ip_ranges = self.get_ip_ranges(area_id=area_id, active_only=True)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("# IP范围列表\n")
                f.write(f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("#" + "="*50 + "\n\n")
                
                for ip_range in ip_ranges:
                    if ip_range.description:
                        f.write(f"{ip_range.ip_range}    # {ip_range.description}\n")
                    else:
                        f.write(f"{ip_range.ip_range}\n")
            
            self.logger.info(f"IP范围已导出到: {file_path}, 共 {len(ip_ranges)} 条")
            return len(ip_ranges)
            
        except Exception as e:
            self.logger.error(f"导出IP范围失败: {e}")
            return 0
    
    def close(self):
        """关闭数据库连接（上下文管理器会自动处理）"""
        pass


# 便捷函数
def init_database(db_path: Optional[str] = None) -> DatabaseManager:
    """初始化数据库并填充默认数据"""
    db = DatabaseManager(db_path)
    db.init_default_data()
    return db
