"""
扫描配置文件
支持 YAML 配置文件覆盖默认配置
"""
import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# 默认路径配置
DEFAULT_BASE_DIR = Path(__file__).parent
DEFAULT_DB_PATH = DEFAULT_BASE_DIR / "scan_data.db"
DEFAULT_TEMPLATE_DIR = DEFAULT_BASE_DIR / "templates"


@dataclass
class ScanConfig:
    """扫描配置类"""
    # 文件路径配置
    ip_range_file: str = "ip_range.txt"
    exclude_ips_file: str = "exclude_ips.txt"
    ports_file: str = "ports.txt"
    save_result_file: str = "scan_results.txt"
    template_file: str = "template.docx"
    redarea_file: str = "redArea_ips.txt"
    log_file: str = "network_scan.log"
    
    # 扫描参数配置
    max_workers: int = 32
    ulimit: int = 32768
    
    # 端口配置（用于红区扫描）
    ports: Optional[str] = None  # None 表示从文件读取
    
    # 报告配置
    report_prefix: str = ""
    report_suffix: str = "_网络高危端口扫描报告"
    
    # 扫描模式: 'normal' 或 'redarea'
    scan_mode: str = "normal"
    
    # 数据库配置
    db_path: str = str(DEFAULT_DB_PATH)
    
    # 模板目录配置
    template_dir: str = str(DEFAULT_TEMPLATE_DIR)
    
    def __post_init__(self):
        """初始化后处理"""
        # 确保路径是绝对路径或相对于工作目录
        self.work_dir = Path.cwd()
        
        # 确保模板目录存在
        Path(self.template_dir).mkdir(parents=True, exist_ok=True)


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
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = ScanConfig()
        self.port_categories = PortCategories()
        self.logger = self._setup_internal_logger()
        
        if config_path and os.path.exists(config_path):
            self.load_from_yaml(config_path)
    
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
                        self.logger.info(f"从配置文件加载: {key} = {value}")
        except ImportError:
            self.logger.warning("未安装 PyYAML，跳过配置文件加载")
        except Exception as e:
            self.logger.error(f"加载配置文件失败: {e}")
    
    def get_config(self) -> ScanConfig:
        """获取当前配置"""
        return self.config
    
    def get_ports_config(self) -> PortCategories:
        """获取端口分类配置"""
        return self.port_categories


def setup_logging(
    log_file: str = "network_scan.log",
    level: int = logging.INFO,
    console_output: bool = True,
    file_mode: str = 'a'
) -> logging.Logger:
    """
    配置日志系统
    
    :param log_file: 日志文件路径
    :param level: 日志级别
    :param console_output: 是否输出到控制台
    :param file_mode: 文件模式 ('a' 追加, 'w' 覆盖)
    :return: 配置好的日志记录器
    """
    logger = logging.getLogger("NetworkScan")
    logger.setLevel(level)
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
    
    # 文件处理器
    file_handler = logging.FileHandler(log_file, mode=file_mode, encoding='utf-8')
    file_handler.setLevel(level)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # 控制台处理器
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    return logger
