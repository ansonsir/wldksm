"""
通用工具模块
提取各版本中重复的通用函数
"""
import math
import os
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


def setup_logging(
    log_file: str = "logs/network_scan.log",
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
    # 确保日志目录存在
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    # 配置根日志器，确保所有模块的日志都能被捕获
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 避免重复添加处理器
    if root_logger.handlers:
        return logging.getLogger("NetworkScan")

    # 文件处理器（带 RotatingFileHandler 进行日志轮转，防止日志文件过大）
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_file, mode=file_mode, encoding='utf-8',
        maxBytes=10 * 1024 * 1024,  # 10MB 自动轮转
        backupCount=5  # 保留5个历史文件
    )
    file_handler.setLevel(level)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # 控制台处理器
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    return logging.getLogger("NetworkScan")


def format_duration(total_seconds: float) -> str:
    """
    将总秒数格式化为易读的时间字符串

    :param total_seconds: 总秒数
    :return: 格式化后的时间字符串
    """
    total_seconds_ceil = math.ceil(total_seconds)

    hours = total_seconds_ceil // 3600
    minutes = (total_seconds_ceil % 3600) // 60
    seconds = total_seconds_ceil % 60

    if hours > 0:
        return f"{hours}小时{minutes}分钟{seconds}秒"
    elif minutes > 0:
        return f"{minutes}分钟{seconds}秒"
    else:
        return f"{seconds}秒"


def load_text_file(filename: str, logger: logging.Logger, description: str = "数据") -> str:
    """
    通用文件加载函数，读取文本文件并过滤注释和空行

    :param filename: 文件路径
    :param logger: 日志记录器
    :param description: 数据描述（用于日志）
    :return: 以逗号分隔的字符串
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
            valid_lines = [
                line.strip()
                for line in lines
                if line.strip() and not line.startswith('#')
            ]

        if not valid_lines:
            logger.warning(f"{description}文件 {filename} 中没有有效数据")
            return ""

        result = ','.join(valid_lines)
        logger.info(f"从 {filename} 加载了 {len(valid_lines)} 条{description}")
        return result

    except FileNotFoundError:
        logger.error(f"{description}文件 {filename} 不存在！")
        raise
    except Exception as e:
        logger.error(f"读取{description}文件 {filename} 失败: {e}")
        raise


def parse_ip_range(ip_input: str) -> List[str]:
    """
    解析IP范围输入，支持多种格式：
    1. 单个IP: 192.168.1.1
    2. 多个IP（换行分隔）: 
       192.168.1.1
       192.168.1.2
    3. IP地址段: 192.168.1.1-192.168.1.100
    4. CIDR掩码段: 192.168.1.0/24
    
    :param ip_input: IP范围输入字符串
    :return: CIDR格式的IP范围列表
    """
    import ipaddress
    
    cidr_list = []
    lines = [line.strip() for line in ip_input.split('\n') if line.strip() and not line.strip().startswith('#')]
    
    for line in lines:
        try:
            # 格式 1 & 2: 单个IP或多个IP
            if '/' not in line and '-' not in line:
                # 验证是否为有效IP
                ip_obj = ipaddress.ip_address(line)
                cidr_list.append(f"{line}/32")
            
            # 格式 3: IP地址段 (192.168.1.1-192.168.1.100)
            elif '-' in line and '/' not in line:
                parts = line.split('-')
                if len(parts) == 2:
                    start_ip = ipaddress.ip_address(parts[0].strip())
                    end_ip = ipaddress.ip_address(parts[1].strip())
                    
                    # 计算最小的CIDR包含这个范围
                    # 简单处理：使用 /24 或更小
                    network = ipaddress.summarize_address_range(start_ip, end_ip)
                    for net in network:
                        cidr_list.append(str(net))
            
            # 格式 4: CIDR掩码段
            elif '/' in line:
                network = ipaddress.ip_network(line, strict=False)
                cidr_list.append(str(network))
            
            else:
                # 尝试作为CIDR处理
                network = ipaddress.ip_network(line, strict=False)
                cidr_list.append(str(network))
                
        except ValueError as e:
            raise ValueError(f"无效的IP范围格式 '{line}': {e}")
    
    return cidr_list


def parse_ports(port_input: str) -> str:
    """
    解析端口输入，支持多种格式：
    1. 单个端口: 80
    2. 多个端口（逗号分隔）: 22,80,443
    3. 端口段: 1-65535
    4. 多个端口（换行分隔）: 从文件读取
    
    注意：混合格式（如 22,80,443,8000-9000）不被 RustScan 支持
    
    :param port_input: 端口输入字符串
    :return: RustScan 可用的端口格式字符串（逗号分隔）
             如果是纯端口段（如 1-65535），返回原样，由 RustScanAPI 处理
    """
    if not port_input or not port_input.strip():
        return ''
    
    # 清理输入
    port_input = port_input.strip()
    
    # 如果包含换行，说明是文件格式，需要转换
    if '\n' in port_input:
        # 解析换行分隔的端口
        ports = []
        for line in port_input.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # 每行可能是单个端口、逗号分隔、或端口段
            if ',' in line or '-' in line:
                ports.append(line)
            else:
                try:
                    port = int(line)
                    if 1 <= port <= 65535:
                        ports.append(str(port))
                except ValueError:
                    pass
        return ','.join(ports)
    
    # 检测是否为纯端口段格式（如 1-65535）
    # 注意：混合格式（如 22,80,443,8000-9000）不被支持
    if '-' in port_input and ',' not in port_input:
        parts = port_input.split('-')
        if len(parts) == 2:
            try:
                start = int(parts[0].strip())
                end = int(parts[1].strip())
                if 1 <= start <= 65535 and 1 <= end <= 65535:
                    return port_input  # 返回原样，让 RustScanAPI 处理
            except ValueError:
                pass
    
    # 如果包含逗号，检查是否有端口段（不被支持）
    if ',' in port_input:
        parts = port_input.split(',')
        for part in parts:
            part = part.strip()
            if '-' in part:
                # 发现端口段，返回原始输入，让 RustScanAPI 报错
                return port_input
        # 所有部分都是单个端口，正常返回
        return port_input
    
    # 尝试解析为单个端口
    try:
        port = int(port_input)
        if 1 <= port <= 65535:
            return port_input
    except ValueError:
        pass
    
    # 否则直接返回（让 RustScan 处理）
    return port_input


def load_ip_ranges(filename: str, logger: logging.Logger) -> List[str]:
    """
    从文件中加载IP范围列表（支持单个或多个文件）

    :param filename: 包含CIDR格式IP范围的文件名，支持逗号分隔多个文件
    :param logger: 日志记录器
    :return: IP范围列表
    """
    try:
        # 支持逗号分隔的多个文件
        file_list = [f.strip() for f in filename.split(',') if f.strip()]
        
        all_ip_ranges = []
        for file_path in file_list:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    ip_ranges = [
                        line.strip()
                        for line in lines
                        if line.strip() and not line.startswith("#")
                    ]
                    all_ip_ranges.extend(ip_ranges)
                    logger.info(f"成功从 {file_path} 加载 {len(ip_ranges)} 个IP范围")
            except FileNotFoundError:
                logger.warning(f"IP范围文件 {file_path} 不存在，跳过")
            except Exception as e:
                logger.error(f"读取IP范围文件 {file_path} 失败: {e}")
                raise

        if not all_ip_ranges:
            logger.warning(f"所有IP范围文件中没有有效数据: {filename}")
            return []

        logger.info(f"总共加载 {len(all_ip_ranges)} 个IP范围（从 {len(file_list)} 个文件）")
        return all_ip_ranges

    except Exception as e:
        logger.error(f"加载IP范围文件失败: {e}")
        raise


def save_results(
    results: Dict[str, List[int]],
    scan_stats: dict,
    ports: str,
    filename: str,
    logger: logging.Logger
) -> Dict:
    """
    保存扫描结果到文件

    :param results: 扫描结果字典
    :param scan_stats: 扫描统计信息字典
    :param ports: 扫描的端口范围
    :param filename: 输出文件名
    :param logger: 日志记录器
    :return: 包含扫描统计信息的字典
    """
    try:
        # 确保输出目录存在
        Path(filename).parent.mkdir(parents=True, exist_ok=True)

        with open(filename, "w", encoding='utf-8') as f:
            f.write("# RustScan 网络扫描报告\n")
            f.write(f"# 扫描开始时间: {scan_stats['start_time']}\n")
            f.write(f"# 扫描完成时间: {scan_stats['end_time']}\n")
            f.write(f"# 扫描用时: {scan_stats['duration']}\n")
            f.write(f"# 扫描端口: {ports}\n")
            f.write(f"# 发现主机数: {len(results)}\n")
            f.write(f"# 成功扫描: {scan_stats.get('successful_scans', 0)}\n")
            f.write(f"# 失败扫描: {scan_stats.get('failed_scans', 0)}\n")
            f.write("#" + "="*60 + "\n")

            # 按IP排序输出
            for ip in sorted(results.keys(), key=lambda x: tuple(map(int, x.split('.')))):
                port_list = results[ip]
                f.write(f"{ip}  {port_list}\n")

        logger.info(f"结果已保存至 {filename}，共发现 {len(results)} 台主机")
        return scan_stats

    except Exception as e:
        logger.error(f"保存扫描结果失败: {e}")
        raise


def get_optimal_workers() -> int:
    """
    获取最优线程数
    基于CPU核心数计算，最多32个线程

    :return: 最优线程数
    """
    cpu_count = os.cpu_count() or 4
    return min(32, cpu_count * 4)
