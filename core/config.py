"""
扫描配置文件
支持 YAML 配置文件覆盖默认配置
"""
import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


DEFAULT_BASE_DIR = Path(__file__).parent.parent
DEFAULT_DB_PATH = DEFAULT_BASE_DIR / "data" / "scan_data.db"
DEFAULT_TEMPLATE_DIR = DEFAULT_BASE_DIR / "data" / "templates"
DEFAULT_REPORT_DIR = DEFAULT_BASE_DIR / "data" / "reports"
DEFAULT_LOG_DIR = DEFAULT_BASE_DIR / "logs"
DEFAULT_CONFIG_PATH = DEFAULT_BASE_DIR / "data" / "config.yaml"


@dataclass
class ScanConfig:
    """扫描配置类"""
    # 文件路径配置
    ip_range_file: str = "data/ip_ranges.txt"  # 支持单个文件或逗号分隔的多个文件
    exclude_ips_file: str = "data/excludes.txt"
    ports_file: str = "data/ports.txt"
    save_result_file: str = "data/scan_results.txt"
    template_file: str = "data/templates/default.docx"
    redarea_file: str = "data/redarea.txt"
    log_file: str = "logs/network_scan.log"

    # 扫描参数配置
    max_workers: int = 32
    ulimit: int = 32768
    timeout: int = 300
    batch_size: int = 10000

    # 端口配置
    ports: Optional[str] = None

    # 报告配置
    report_prefix: str = ""
    report_suffix: str = "_网络高危端口扫描报告"

    # 扫描模式: 'normal' 或 'redarea'
    scan_mode: str = "normal"

    # 数据库配置
    db_path: str = str(DEFAULT_DB_PATH)
    template_dir: str = str(DEFAULT_TEMPLATE_DIR)
    report_dir: str = str(DEFAULT_REPORT_DIR)

    # 邮件配置
    smtp_server: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_ssl: bool = True
    default_sender: str = ""
    default_recipients: str = ""

    def __post_init__(self):
        """初始化后处理"""
        self.work_dir = Path.cwd()
        Path(self.template_dir).mkdir(parents=True, exist_ok=True)
        Path(self.report_dir).mkdir(parents=True, exist_ok=True)
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)


@dataclass
class PortCategories:
    """端口分类配置"""
    ftp: set = field(default_factory=lambda: {21})
    ssh: set = field(default_factory=lambda: {22})
    rdp: set = field(default_factory=lambda: {3389})
    db: set = field(default_factory=lambda: {1433, 1521, 2181, 3306, 5432, 6379, 15672, 27017})
    mqtt: set = field(default_factory=lambda: {1883, 5672, 8161, 61616})
    smb: set = field(default_factory=lambda: {445})


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_path: Optional[str] = None, db_manager=None):
        self.config = ScanConfig()
        self.port_categories = PortCategories()
        self.logger = self._setup_internal_logger()
        self.db = db_manager

        # 1. 先从 YAML 文件加载配置
        if config_path and os.path.exists(config_path):
            self.load_from_yaml(config_path)
        elif os.path.exists(DEFAULT_CONFIG_PATH):
            self.load_from_yaml(str(DEFAULT_CONFIG_PATH))
        
        # 2. 然后从数据库加载邮件配置（覆盖 YAML 中的配置）
        if self.db:
            self._load_email_from_db()

    def _setup_internal_logger(self) -> logging.Logger:
        """设置内部日志记录器"""
        logger = logging.getLogger("ConfigManager")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    def _load_email_from_db(self):
        """从数据库加载邮件配置"""
        try:
            settings = self.db.get_email_settings()
            if settings:
                # 更新邮件配置字段
                if settings.smtp_server:
                    self.config.smtp_server = settings.smtp_server
                    self.logger.info(f"从数据库加载: smtp_server = {settings.smtp_server}")
                if settings.smtp_port:
                    self.config.smtp_port = settings.smtp_port
                    self.logger.info(f"从数据库加载: smtp_port = {settings.smtp_port}")
                if settings.smtp_user:
                    self.config.smtp_user = settings.smtp_user
                    self.logger.info(f"从数据库加载: smtp_user = {settings.smtp_user}")
                if settings.smtp_password:
                    self.config.smtp_password = settings.smtp_password
                    self.logger.info("从数据库加载: smtp_password = ***")
                if settings.smtp_ssl is not None:
                    self.config.smtp_ssl = settings.smtp_ssl
                    self.logger.info(f"从数据库加载: smtp_ssl = {settings.smtp_ssl}")
                if settings.default_sender:
                    self.config.default_sender = settings.default_sender
                    self.logger.info(f"从数据库加载: default_sender = {settings.default_sender}")
                if settings.default_recipients:
                    self.config.default_recipients = settings.default_recipients
                    self.logger.info(f"从数据库加载: default_recipients = {settings.default_recipients}")
        except Exception as e:
            self.logger.warning(f"从数据库加载邮件配置失败: {e}")

    def load_from_yaml(self, config_path: str):
        """从 YAML 文件加载配置"""
        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if data:
                for key, value in data.items():
                    if hasattr(self.config, key):
                        setattr(self.config, key, value)
                        self.logger.info(f"从配置文件加载: {key} = {value if key != 'smtp_password' else '***'}")
            
            # 敏感字段优先使用环境变量（安全性）
            env_overrides = {
                'smtp_password': 'SMTP_PASSWORD',
                'smtp_user': 'SMTP_USER',
            }
            for attr, env_name in env_overrides.items():
                env_value = os.environ.get(env_name, '')
                if env_value and hasattr(self.config, attr):
                    setattr(self.config, attr, env_value)
                    self.logger.info(f"环境变量覆盖: {attr} (来自 {env_name})")
        except ImportError:
            self.logger.warning("未安装 PyYAML，跳过配置文件加载")
        except Exception as e:
            self.logger.error(f"加载配置文件失败: {e}")

    def reload_from_yaml(self, config_path: Optional[str] = None):
        """重新从 YAML 文件加载配置（用于配置热更新）"""
        path = config_path or str(DEFAULT_CONFIG_PATH)
        if os.path.exists(path):
            self.logger.info(f"重新加载配置文件: {path}")
            self.load_from_yaml(path)
            # 同时从数据库加载邮件配置
            if self.db:
                self._load_email_from_db()
        else:
            self.logger.warning(f"配置文件不存在: {path}，跳过重新加载")

    def save_to_yaml(self, config_path: Optional[str] = None):
        """保存配置到 YAML 文件（敏感字段不写入文件）"""
        try:
            import yaml
            path = config_path or str(DEFAULT_CONFIG_PATH)
            sensitive_keys = {'smtp_password'}
            data = {}
            for key in self.config.__dataclass_fields__:
                if key in sensitive_keys:
                    continue  # 不保存敏感字段到文件
                value = getattr(self.config, key)
                if isinstance(value, Path):
                    value = str(value)
                data[key] = value

            with open(path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False)
            self.logger.info(f"配置已保存到: {path}")
        except ImportError:
            self.logger.warning("未安装 PyYAML，无法保存配置")
        except Exception as e:
            self.logger.error(f"保存配置文件失败: {e}")

    def get_config(self) -> ScanConfig:
        """获取当前配置"""
        return self.config

    def get_ports_config(self) -> PortCategories:
        """获取端口分类配置"""
        return self.port_categories

    def update_config(self, **kwargs):
        """更新配置"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                self.logger.info(f"配置已更新: {key} = {value}")
