"""
网络扫描核心模块
统一的扫描逻辑，支持普通区域和红区扫描
集成数据库存储
"""
import math
import time
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from pathlib import Path
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass

from config import ScanConfig, setup_logging
from rustscan import RustScanAPI
from database import DatabaseManager, ScanRecord, ScanResultDetail


@dataclass
class ScanStatistics:
    """扫描统计信息"""
    start_time: float
    end_time: Optional[float] = None
    total_hosts: int = 0
    successful_scans: int = 0
    failed_scans: int = 0
    
    @property
    def duration(self) -> float:
        """扫描持续时间"""
        end = self.end_time or time.time()
        return end - self.start_time
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "start_time": datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": datetime.fromtimestamp(self.end_time or time.time()).strftime("%Y-%m-%d %H:%M:%S"),
            "duration": format_duration(self.duration),
            "total_hosts": self.total_hosts,
            "successful_scans": self.successful_scans,
            "failed_scans": self.failed_scans,
        }


class FileLoader:
    """文件加载工具类"""
    
    @staticmethod
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
    
    @staticmethod
    def load_ip_ranges(filename: str, logger: logging.Logger) -> List[str]:
        """
        从文件中加载IP范围列表
        
        :param filename: 包含CIDR格式IP范围的文件名
        :param logger: 日志记录器
        :return: IP范围列表
        """
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                ip_ranges = [
                    line.strip() 
                    for line in lines 
                    if line.strip() and not line.startswith("#")
                ]
            
            if not ip_ranges:
                logger.warning(f"IP范围文件 {filename} 中没有有效数据")
                return []
            
            logger.info(f"成功从 {filename} 加载 {len(ip_ranges)} 个IP范围")
            return ip_ranges
            
        except FileNotFoundError:
            logger.error(f"IP范围文件 {filename} 不存在！")
            raise
        except Exception as e:
            logger.error(f"读取IP范围文件 {filename} 失败: {e}")
            raise


class NetworkScanner:
    """网络扫描器"""
    
    def __init__(self, config: ScanConfig, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger("NetworkScanner")
        self.statistics = ScanStatistics(start_time=time.time())
        self._stop_requested = False
    
    def scan_single_range(
        self, 
        cidr: str, 
        ports: Optional[str], 
        exclude_ip: str,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> Dict[str, List[int]]:
        """
        扫描单个CIDR网段
        
        :param cidr: CIDR格式的IP范围
        :param ports: 端口范围（None 表示全端口扫描）
        :param exclude_ip: 排除的IP范围
        :param progress_callback: 进度回调函数
        :return: 开放端口的字典
        """
        if self._stop_requested:
            return {}
        
        try:
            self.logger.info(f"开始扫描网段: {cidr}")
            start_time = time.time()
            
            # 根据是否有 ports 参数决定扫描模式
            if ports:
                scanner = RustScanAPI(
                    target=cidr,
                    ports=ports,
                    ulimit=self.config.ulimit,
                    exclude_ip=exclude_ip
                )
            else:
                # 全端口扫描（红区模式）
                scanner = RustScanAPI(
                    target=cidr,
                    scan_range="1-65535",
                    ulimit=self.config.ulimit,
                    exclude_ip=exclude_ip
                )
            
            results = scanner.scan()
            duration = time.time() - start_time
            
            # 确保返回字典类型
            if not isinstance(results, dict):
                self.logger.warning(f"扫描结果类型异常: {type(results)}，返回空字典")
                return {}
            
            self.statistics.successful_scans += 1
            
            self.logger.info(
                f"完成扫描 {cidr} | 耗时: {duration:.2f}s | 发现 {len(results)} 台主机"
            )
            
            if results:
                self.logger.info("发现的主机及开放端口如下:")
                for ip, port_list in results.items():
                    self.logger.info(f"  {ip}: {port_list}")
            
            return results
            
        except Exception as e:
            self.statistics.failed_scans += 1
            self.logger.error(f"扫描 {cidr} 失败: {str(e)}")
            return {}
    
    def scan_all_ranges(
        self,
        ip_ranges: List[str],
        ports: Optional[str],
        exclude_ips: str,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> Dict[str, List[int]]:
        """
        扫描所有网段
        
        :param ip_ranges: IP范围列表
        :param ports: 端口范围（None 表示全端口扫描）
        :param exclude_ips: 排除的IP
        :param progress_callback: 进度回调函数
        :return: 合并后的扫描结果
        """
        self.statistics.total_hosts = len(ip_ranges)
        final_results = {}
        completed = 0
        
        self.logger.info(f"开始扫描 {len(ip_ranges)} 个网段，线程数: {self.config.max_workers}")
        
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            # 提交所有任务
            future_to_cidr = {
                executor.submit(
                    self.scan_single_range,
                    cidr,
                    ports,
                    exclude_ips,
                    progress_callback
                ): cidr
                for cidr in ip_ranges
            }
            
            # 处理完成的任务
            for future in as_completed(future_to_cidr):
                if self._stop_requested:
                    executor.shutdown(wait=False)
                    break
                
                cidr = future_to_cidr[future]
                try:
                    result = future.result(timeout=300)  # 5分钟超时
                    final_results.update(result)
                    completed += 1
                    
                    if progress_callback:
                        progress_callback(cidr, completed, len(ip_ranges))
                        
                except TimeoutError:
                    self.logger.error(f"扫描网段 {cidr} 超时")
                    self.statistics.failed_scans += 1
                except Exception as e:
                    self.logger.error(f"处理网段 {cidr} 时出错: {str(e)}")
                    self.statistics.failed_scans += 1
        
        self.statistics.end_time = time.time()
        return final_results
    
    def stop(self):
        """请求停止扫描"""
        self._stop_requested = True
        self.logger.info("收到停止扫描请求")


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


def save_results(
    results: Dict[str, List[int]],
    scan_stats: ScanStatistics,
    ports: str,
    filename: str,
    logger: logging.Logger
) -> Dict:
    """
    保存扫描结果到文件
    
    :param results: 扫描结果字典
    :param scan_stats: 扫描统计信息
    :param ports: 扫描的端口范围
    :param filename: 输出文件名
    :param logger: 日志记录器
    :return: 包含扫描统计信息的字典
    """
    try:
        stats_dict = scan_stats.to_dict()
        
        with open(filename, "w", encoding='utf-8') as f:
            f.write("# RustScan 网络扫描报告\n")
            f.write(f"# 扫描开始时间: {stats_dict['start_time']}\n")
            f.write(f"# 扫描完成时间: {stats_dict['end_time']}\n")
            f.write(f"# 扫描用时: {stats_dict['duration']}\n")
            f.write(f"# 扫描端口: {ports}\n")
            f.write(f"# 发现主机数: {len(results)}\n")
            f.write(f"# 成功扫描: {stats_dict['successful_scans']}\n")
            f.write(f"# 失败扫描: {stats_dict['failed_scans']}\n")
            f.write("#" + "="*60 + "\n")
            
            # 按IP排序输出
            for ip in sorted(results.keys(), key=lambda x: tuple(map(int, x.split('.')))):
                port_list = results[ip]
                f.write(f"{ip}  {port_list}\n")
        
        logger.info(f"结果已保存至 {filename}，共发现 {len(results)} 台主机")
        return stats_dict
        
    except Exception as e:
        logger.error(f"保存扫描结果失败: {e}")
        raise


def run_scan(
    config: ScanConfig,
    logger: Optional[logging.Logger] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    db_manager: Optional[DatabaseManager] = None,
    area_id: Optional[int] = None
) -> Tuple[Dict[str, List[int]], Optional[int]]:
    """
    运行扫描任务（统一入口）
    
    :param config: 扫描配置
    :param logger: 日志记录器（可选）
    :param progress_callback: 进度回调函数
    :param db_manager: 数据库管理器（可选）
    :param area_id: 扫描区域ID（用于数据库记录）
    :return: (扫描结果, 扫描记录ID)
    """
    # 设置日志
    if logger is None:
        logger = setup_logging(config.log_file)
    
    scanner = NetworkScanner(config, logger)
    loader = FileLoader()
    
    # 初始化数据库记录
    record_id = None
    if db_manager and area_id:
        record = ScanRecord(
            area_id=area_id,
            start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ip_ranges=",".join(loader.load_ip_ranges(config.ip_range_file, logger) or []),
            scan_status="running",
            result_file=config.save_result_file
        )
        record_id = db_manager.create_scan_record(record)
        logger.info(f"扫描记录已创建，ID: {record_id}")
    
    try:
        logger.info("="*60)
        logger.info("启动网络扫描任务")
        logger.info(f"扫描模式: {config.scan_mode}")
        logger.info(f"  - IP范围文件: {config.ip_range_file}")
        logger.info(f"  - 端口文件: {config.ports_file}")
        logger.info(f"  - 排除IP文件: {config.exclude_ips_file}")
        logger.info(f"  - 最大线程数: {config.max_workers}")
        logger.info("="*60)
        
        # 加载配置
        ip_ranges = loader.load_ip_ranges(config.ip_range_file, logger)
        if not ip_ranges:
            logger.error("IP范围列表为空，无法继续扫描")
            return {}
        
        # 加载端口配置
        if config.scan_mode == "redarea":
            # 红区模式：全端口扫描
            ports = None
            logger.info("红区扫描模式：扫描全部端口 (1-65535)")
        elif config.ports:
            # 配置中直接指定了端口
            ports = config.ports
            logger.info(f"使用配置中的端口: {ports}")
        else:
            # 从文件加载端口
            ports = loader.load_text_file(config.ports_file, logger, "端口")
            if not ports:
                logger.error("端口列表为空，无法继续扫描")
                return {}
        
        exclude_ips = loader.load_text_file(config.exclude_ips_file, logger, "排除IP")
        
        # 执行扫描
        results = scanner.scan_all_ranges(ip_ranges, ports, exclude_ips, progress_callback)
        
        # 计算开放端口总数
        open_ports_count = sum(len(ports_list) for ports_list in results.values())
        
        # 保存结果
        save_results(
            results,
            scanner.statistics,
            ports or "1-65535",
            config.save_result_file,
            logger
        )
        
        # 更新数据库记录
        if db_manager and record_id:
            # 保存扫描结果详情
            result_details = []
            for ip, port_list in results.items():
                for port in port_list:
                    result_details.append((ip, port, ""))
            
            if result_details:
                db_manager.add_scan_results_batch(record_id, result_details)
            
            # 更新扫描记录
            db_manager.update_scan_record(
                record_id,
                end_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                duration_seconds=int(scanner.statistics.duration),
                total_hosts=len(results),
                open_ports_count=open_ports_count,
                scan_status="completed"
            )
            logger.info(f"扫描记录已更新，ID: {record_id}")
        
        logger.info("="*60)
        logger.info(f"扫描任务完成！")
        logger.info(f"  - 扫描结果: {config.save_result_file}")
        logger.info(f"  - 发现主机: {len(results)} 台")
        logger.info(f"  - 开放端口: {open_ports_count} 个")
        logger.info(f"  - 成功扫描: {scanner.statistics.successful_scans} 个网段")
        logger.info(f"  - 失败扫描: {scanner.statistics.failed_scans} 个网段")
        logger.info("="*60)
        
        return results, record_id
        
    except KeyboardInterrupt:
        logger.warning("\n用户中断扫描任务")
        scanner.stop()
        # 更新数据库状态为取消
        if db_manager and record_id:
            db_manager.update_scan_record(
                record_id,
                end_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                duration_seconds=int(time.time() - scanner.statistics.start_time),
                scan_status="cancelled"
            )
        return {}, record_id
    except Exception as e:
        logger.error(f"扫描任务失败: {e}", exc_info=True)
        # 更新数据库状态为失败
        if db_manager and record_id:
            db_manager.update_scan_record(
                record_id,
                end_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                duration_seconds=int(time.time() - scanner.statistics.start_time),
                scan_status="failed",
                error_message=str(e)
            )
        raise


if __name__ == "__main__":
    # 示例用法
    config = ScanConfig()
    results, record_id = run_scan(config)
    print(f"扫描完成，共发现 {len(results)} 台主机")
    if record_id:
        print(f"扫描记录ID: {record_id}")
