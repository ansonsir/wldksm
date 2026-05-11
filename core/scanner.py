"""
网络扫描核心模块
统一的扫描逻辑，合并各版本 network_scan 功能
"""
import math
import time
import os
import signal
import logging
import tempfile
import subprocess
import ipaddress
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass, field

from core.config import ScanConfig
from core.rustscan import RustScanAPI
from core.utils import format_duration, load_text_file, load_ip_ranges, save_results, get_optimal_workers
from core.database import DatabaseManager, ScanRecord


def calculate_timeout(cidr: str, port_count: int, base_timeout: int = 300) -> int:
    """
    根据网段大小和端口数动态计算超时时间
    
    Args:
        cidr: CIDR 格式网段
        port_count: 端口数量
        base_timeout: 基础超时时间（秒）
        
    Returns:
        计算后的超时时间（秒）
    """
    try:
        net = ipaddress.ip_network(cidr, strict=False)
        host_count = net.num_addresses
        # 基础时间 + 每 IP 扫描时间 * 端口数
        # 经验值：每个 IP 每个端口约 0.001 秒
        dynamic_timeout = int(host_count * port_count * 0.001)
        return max(base_timeout, dynamic_timeout)
    except Exception:
        return base_timeout


def merge_ip_ranges(ip_ranges: List[str]) -> List[str]:
    """合并连续的IP网段，并将过大网段拆分为/16，平衡扫描效率与单次耗时"""
    import ipaddress
    try:
        networks = []
        for r in ip_ranges:
            try:
                networks.append(ipaddress.ip_network(r.strip(), strict=False))
            except ValueError:
                continue
        if not networks:
            return ip_ranges
        merged = list(ipaddress.collapse_addresses(networks))

        # 将过大的网段（前缀 < 18）拆分为 /18，避免单次扫描超时
        MAX_PREFIX = 18
        result = []
        for net in merged:
            if net.prefixlen < MAX_PREFIX:
                result.extend(str(subnet) for subnet in net.subnets(new_prefix=MAX_PREFIX))
            else:
                result.append(str(net))
        return result
    except Exception:
        return ip_ranges


def _get_original_ranges_in_merged(merged_range: str, original_ranges: List[str]) -> List[str]:
    """获取合并网段覆盖的原始网段列表（用于进度计算）"""
    import ipaddress
    try:
        merged_net = ipaddress.ip_network(merged_range, strict=False)
        return [r for r in original_ranges if ipaddress.ip_network(r, strict=False).subnet_of(merged_net)]
    except Exception:
        return []


@dataclass
class ScanStatistics:
    """扫描统计信息"""
    start_time: float
    end_time: Optional[float] = None
    total_hosts: int = 0
    successful_scans: int = 0
    failed_scans: int = 0
    current_progress: int = 0
    workers: int = 0
    logs: List[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    def to_dict(self) -> Dict:
        return {
            "start_time": datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": datetime.fromtimestamp(self.end_time or time.time()).strftime("%Y-%m-%d %H:%M:%S"),
            "duration": format_duration(self.duration),
            "total_hosts": self.total_hosts,
            "successful_scans": self.successful_scans,
            "failed_scans": self.failed_scans,
            "workers": self.workers,
        }

    def add_log(self, message: str):
        self.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        # 限制日志条数
        if len(self.logs) > 500:
            self.logs = self.logs[-400:]


class ScanOrchestrator:
    """扫描调度器 - 统一扫描入口"""

    def __init__(self, config: ScanConfig, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger("ScanOrchestrator")
        self.statistics = ScanStatistics(start_time=time.time())
        self._stop_requested = False
        self._current_executor = None
        self._active_scanners: List[RustScanAPI] = []  # 跟踪所有活跃的 RustScan 实例（用于精确终止）
        self._scanners_lock = __import__('threading').Lock()

    def scan_single_range(
        self,
        cidr: str,
        ports: Optional[str],
        exclude_ip: str,
        exclude_file: Optional[str] = None,
    ) -> Dict[str, List[int]]:
        """扫描单个CIDR网段"""
        if self._stop_requested:
            return {}

        try:
            self.logger.info(f"开始扫描网段: {cidr}")
            self.statistics.add_log(f"开始扫描: {cidr}")
            start_time = time.time()

            # 排除IP优先级：文件 > 命令行参数
            effective_exclude = ""
            if exclude_file and Path(exclude_file).exists():
                effective_exclude = exclude_file
            elif exclude_ip:
                effective_exclude = exclude_ip

            if ports:
                scanner = RustScanAPI(
                    target=cidr,
                    ports=ports,
                    ulimit=self.config.ulimit,
                    exclude_ip=effective_exclude,
                    timeout=self.config.timeout,
                    batch_size=getattr(self.config, 'batch_size', None),
                )
            else:
                scanner = RustScanAPI(
                    target=cidr,
                    scan_range="1-65535",
                    ulimit=self.config.ulimit,
                    exclude_ip=effective_exclude,
                    timeout=self.config.timeout,
                    batch_size=getattr(self.config, 'batch_size', None),
                )

            # 执行扫描并跟踪进程
            results = self._execute_scan_with_tracking(scanner)
            duration = time.time() - start_time

            if not isinstance(results, dict):
                self.logger.warning(f"扫描结果类型异常: {type(results)}，返回空字典")
                return {}

            self.statistics.successful_scans += 1
            self.logger.info(
                f"完成扫描 {cidr} | 耗时: {duration:.2f}s | 发现 {len(results)} 台主机"
            )
            self.statistics.add_log(
                f"完成扫描 {cidr} | 耗时: {duration:.2f}s | 发现 {len(results)} 台主机"
            )

            if results:
                for ip, port_list in results.items():
                    self.logger.info(f"  {ip}: {port_list}")

            return results

        except Exception as e:
            self.statistics.failed_scans += 1
            self.logger.error(f"扫描 {cidr} 失败: {str(e)}")
            self.statistics.add_log(f"扫描 {cidr} 失败: {str(e)}")
            return {}

    def _execute_scan_with_tracking(self, scanner: RustScanAPI) -> Dict[str, List[int]]:
        """执行扫描并跟踪 RustScan 实例（用于精确终止）"""
        with self._scanners_lock:
            self._active_scanners.append(scanner)
        try:
            return scanner.scan()
        finally:
            with self._scanners_lock:
                if scanner in self._active_scanners:
                    self._active_scanners.remove(scanner)

    def scan_all_ranges(
        self,
        ip_ranges: List[str],
        ports: Optional[str],
        exclude_ips: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, List[int]]:
        """扫描所有网段（支持网段合并优化）"""
        # 合并网段以减少 RustScan 调用次数
        merged_ranges = merge_ip_ranges(ip_ranges)
        original_total = len(ip_ranges)
        merged_total = len(merged_ranges)

        if merged_total < original_total:
            self.logger.info(
                f"网段合并: {original_total} 个网段 → {merged_total} 个网段"
            )
            self.statistics.add_log(
                f"网段合并: {original_total} 个网段 → {merged_total} 个网段"
            )

        self.statistics.total_hosts = original_total
        final_results = {}
        completed = 0
        start_time = time.time()

        # 排除IP写入临时文件（避免命令行过长）
        exclude_file = None
        if exclude_ips:
            exclude_list = [ip.strip() for ip in exclude_ips.split(",") if ip.strip()]
            if len(exclude_list) > 50:
                try:
                    fd, exclude_file = tempfile.mkstemp(suffix=".txt", prefix="exclude_")
                    with os.fdopen(fd, "w") as f:
                        for ip in exclude_list:
                            f.write(ip + "\n")
                    self.logger.info(f"排除IP已写入临时文件: {exclude_file} ({len(exclude_list)} 个)")
                except Exception as e:
                    self.logger.warning(f"排除IP文件写入失败，回退到命令行参数: {e}")
                    exclude_file = None

        # 动态计算线程数
        workers = min(merged_total, self.config.max_workers or get_optimal_workers())
        self.statistics.workers = workers
        self.logger.info(f"开始扫描 {merged_total} 个合并网段，线程数: {workers}")
        self.statistics.add_log(f"开始扫描 {merged_total} 个合并网段，线程数: {workers}")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            self._current_executor = executor
            future_to_merged = {
                executor.submit(
                    self.scan_single_range,
                    cidr,
                    ports,
                    exclude_ips if not exclude_file else "",
                    exclude_file,
                ): cidr
                for cidr in merged_ranges
            }

            merged_completed = 0
            for future in as_completed(future_to_merged):
                if self._stop_requested:
                    executor.shutdown(wait=False)
                    self.statistics.add_log("扫描已停止")
                    break

                cidr = future_to_merged[future]
                try:
                    result = future.result(timeout=self.config.timeout + 10)
                    final_results.update(result)
                    merged_completed += 1

                    # 计算该合并网段覆盖的原始网段数，用于平滑进度
                    covered = _get_original_ranges_in_merged(cidr, ip_ranges)
                    completed += len(covered) if covered else max(1, original_total // merged_total)
                    self.statistics.current_progress = min(completed, original_total)

                    # 计算进度信息
                    elapsed = time.time() - start_time
                    avg_time = elapsed / max(merged_completed, 1)
                    merged_remaining = max(0, merged_total - merged_completed)
                    estimated_remaining = avg_time * merged_remaining / max(1, workers)

                    if progress_callback:
                        progress_callback(
                            self.statistics.current_progress,
                            original_total,
                            f"已完成 {self.statistics.current_progress}/{original_total} 个网段 | 当前: {cidr} | 发现 {len(result)} 台主机",
                            current_cidr=cidr,
                            found_hosts=len(final_results),
                            open_ports=sum(len(p) for p in final_results.values()),
                            elapsed_time=int(elapsed),
                            estimated_remaining=int(estimated_remaining),
                        )

                except Exception as e:
                    self.logger.error(f"处理网段 {cidr} 时出错: {str(e)}")
                    self.statistics.failed_scans += 1
                    self.statistics.add_log(f"处理网段 {cidr} 出错: {str(e)}")

        # 清理临时文件
        if exclude_file and os.path.exists(exclude_file):
            try:
                os.remove(exclude_file)
            except Exception:
                pass

        self.statistics.end_time = time.time()
        self._current_executor = None
        return final_results

    def stop(self):
        """请求停止扫描（精确终止本调度器管理的 RustScan 进程，不影响其他任务）"""
        self._stop_requested = True
        self.logger.info("收到停止扫描请求，正在终止管理的 RustScan 进程...")
        self.statistics.add_log("收到停止扫描请求")
        
        # 精确终止本调度器管理的所有 RustScan 实例
        with self._scanners_lock:
            scanners = list(self._active_scanners)
        
        for scanner in scanners:
            try:
                scanner.terminate()
            except Exception as e:
                self.logger.warning(f"终止 RustScan 实例失败: {e}")
        
        if scanners:
            self.logger.info(f"已终止 {len(scanners)} 个 RustScan 实例")
            self.statistics.add_log(f"已终止 {len(scanners)} 个 RustScan 实例")
            
        # 如果有线程池，立即 shutdown
        if self._current_executor:
            try:
                self._current_executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass

    def is_stopped(self) -> bool:
        return self._stop_requested


def run_scan(
    config: ScanConfig,
    logger: Optional[logging.Logger] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    db_manager: Optional[DatabaseManager] = None,
    area_id: Optional[int] = None,
    ip_ranges_override: Optional[List[str]] = None,
    ports_override: Optional[str] = None,
) -> Tuple[Dict[str, List[int]], Optional[int]]:
    """
    运行扫描任务（统一入口）

    :param config: 扫描配置
    :param logger: 日志记录器
    :param progress_callback: 进度回调函数 (completed, total, message)
    :param db_manager: 数据库管理器
    :param area_id: 扫描区域ID
    :param ip_ranges_override: 覆盖IP范围
    :param ports_override: 覆盖端口
    :return: (扫描结果, 扫描记录ID)
    """
    if logger is None:
        from core.utils import setup_logging
        logger = setup_logging(config.log_file)

    orchestrator = ScanOrchestrator(config, logger)

    # 初始化数据库记录
    record_id = None
    if db_manager and area_id:
        record = ScanRecord(
            area_id=area_id,
            start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ip_ranges="",
            scan_status="running",
            result_file=config.save_result_file,
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

        # 加载IP范围
        if ip_ranges_override is not None:
            ip_ranges = ip_ranges_override
        else:
            ip_ranges = load_ip_ranges(config.ip_range_file, logger)

        if not ip_ranges:
            logger.error("IP范围列表为空，无法继续扫描")
            return {}, record_id

        # 加载端口配置
        if ports_override is not None:
            ports = ports_override
        elif config.scan_mode == "redarea":
            ports = None
            logger.info("红区扫描模式：扫描全部端口 (1-65535)")
        elif config.ports:
            ports = config.ports
            logger.info(f"使用配置中的端口: {ports}")
        else:
            ports = load_text_file(config.ports_file, logger, "端口")
            if not ports:
                logger.error("端口列表为空，无法继续扫描")
                return {}, record_id

        exclude_ips = load_text_file(config.exclude_ips_file, logger, "排除IP")

        # 更新数据库记录中的IP范围
        if db_manager and record_id:
            db_manager.update_scan_record(
                record_id,
                ip_ranges=",".join(ip_ranges)
            )

        # 执行扫描
        results = orchestrator.scan_all_ranges(ip_ranges, ports, exclude_ips, progress_callback)

        # 计算开放端口总数
        open_ports_count = sum(len(ports_list) for ports_list in results.values())

        # 保存结果
        save_results(
            results,
            orchestrator.statistics.to_dict(),
            ports or "1-65535",
            config.save_result_file,
            logger
        )

        # 更新数据库记录
        if db_manager and record_id:
            result_details = []
            for ip, port_list in results.items():
                for port in port_list:
                    result_details.append((ip, port, ""))

            if result_details:
                db_manager.add_scan_results_batch(record_id, result_details)

            db_manager.update_scan_record(
                record_id,
                end_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                duration_seconds=int(orchestrator.statistics.duration),
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
        logger.info(f"  - 成功扫描: {orchestrator.statistics.successful_scans} 个网段")
        logger.info(f"  - 失败扫描: {orchestrator.statistics.failed_scans} 个网段")
        logger.info("="*60)

        return results, record_id

    except KeyboardInterrupt:
        logger.warning("\n用户中断扫描任务")
        orchestrator.stop()
        if db_manager and record_id:
            db_manager.update_scan_record(
                record_id,
                end_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                duration_seconds=int(time.time() - orchestrator.statistics.start_time),
                scan_status="cancelled"
            )
        return {}, record_id

    except Exception as e:
        logger.error(f"扫描任务失败: {e}", exc_info=True)
        if db_manager and record_id:
            db_manager.update_scan_record(
                record_id,
                end_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                duration_seconds=int(time.time() - orchestrator.statistics.start_time),
                scan_status="failed",
                error_message=str(e)
            )
        raise
