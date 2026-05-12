import math
from datetime import datetime
from rustscan import RustScanAPI
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging
from pathlib import Path
from report import Report


class ScanConfig:
    """扫描配置类"""

    def __init__(self):
        self.ip_range_file = "ip_range.txt"
        self.exclude_ips_file = "exclude_ips.txt"
        self.ports_file = "ports.txt"
        self.save_result_file = "scan_results.txt"
        self.template_file = "template.docx"
        self.redarea_file = "redArea_ips.txt"
        self.log_file = "network_scan.log"
        # 最优线程数（根据实际测试确定）
        self.max_workers = 32
        # rustscan的ulimit参数（文件描述符限制，避免资源不足）
        self.ulimit = 32768


# 配置日志（记录扫描过程，同时输出到控制台和文件）
def setup_logging(log_file="network_scan.log"):
    """配置日志系统"""
    logger = logging.getLogger("NetworkScan")
    logger.setLevel(logging.INFO)

    # 清除已有的处理器
    logger.handlers.clear()

    # 文件处理器
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def load_text_file(filename, logger, description="数据"):
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
            valid_lines = [line.strip() for line in lines if line.strip() and not line.startswith('#')]

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


def load_ip_ranges(filename, logger):
    """
    从文件中加载IP范围列表
    :param filename: 包含CIDR格式IP范围的文件名
    :param logger: 日志记录器
    :return: IP范围列表
    :raises FileNotFoundError: 文件不存在时抛出异常
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            ip_ranges = [line.strip() for line in lines if line.strip() and not line.startswith("#")]

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


def scan_single_range(cidr: str, ports: str, exclude_ip: str, ulimit: int, logger) -> dict:
    """
    扫描单个CIDR网段
    :param cidr: CIDR格式的IP范围（如"10.0.0.0/8"）
    :param ports: 端口范围
    :param exclude_ip: 排除的IP范围
    :param ulimit: 文件描述符限制
    :param logger: 日志记录器
    :return: 开放端口的字典 {IP: [端口列表]}
    """
    try:
        logger.info(f"开始扫描网段: {cidr}")
        start_time = time.time()
        scanner = RustScanAPI(
            target=cidr,
            ports=ports,
            ulimit=ulimit,
            exclude_ip=exclude_ip
        )

        results = scanner.scan()
        duration = time.time() - start_time

        # 确保返回字典类型
        if not isinstance(results, dict):
            logger.warning(f"扫描结果类型异常: {type(results)}，返回空字典")
            return {}

        logger.info(f"完成扫描 {cidr} | 耗时: {duration:.2f}s | 发现 {len(results)} 台主机")
        return results

    except Exception as e:
        logger.error(f"扫描 {cidr} 失败: {str(e)}")
        return {}


def format_duration(total_seconds):
    """
    将总秒数格式化为 "XX小时XX分钟XX秒" 的字符串，向上取整
    :param total_seconds: 总秒数
    :return: 格式化后的时间字符串
    """
    # 向上取整到整数秒
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


def save_results(results: dict, scan_start_time: float, ports: str, filename: str, logger):
    """
    保存扫描结果到文件
    :param results: 扫描结果字典
    :param scan_start_time: 扫描开始时间戳
    :param ports: 扫描的端口范围
    :param filename: 输出文件名
    :param logger: 日志记录器
    :return: 包含扫描统计信息的字典
    """
    try:
        scan_end_time = time.time()
        duration = scan_end_time - scan_start_time
        duration_str = format_duration(duration)
        start_time_str = datetime.fromtimestamp(scan_start_time).strftime("%Y-%m-%d %H:%M:%S")
        end_time_str = datetime.fromtimestamp(scan_end_time).strftime("%Y-%m-%d %H:%M:%S")

        with open(filename, "w", encoding='utf-8') as f:
            f.write("# RustScan 网络扫描报告\n")
            f.write(f"# 扫描开始时间: {start_time_str}\n")
            f.write(f"# 扫描完成时间: {end_time_str}\n")
            f.write(f"# 扫描用时：{duration_str}\n")
            f.write(f"# 扫描端口: {ports}\n")
            f.write(f"# 发现主机数: {len(results)}\n")
            for ip, port_list in results.items():
                f.write(f"{ip}  {port_list}\n")

        logger.info(f"结果已保存至 {filename}，共发现 {len(results)} 台主机")

        # 返回扫描统计信息
        return {
            "scan_start_time": start_time_str,
            "scan_end_time": end_time_str,
            "scan_duration": duration_str,
            "ports": ports
        }
    except Exception as e:
        logger.error(f"保存扫描结果失败: {e}")
        raise


def main():
    """主扫描流程"""
    # 初始化配置
    config = ScanConfig()
    logger = setup_logging(config.log_file)

    scan_start_time = time.time()

    try:
        logger.info("=" * 50)
        logger.info("启动网络扫描任务")
        logger.info(f"配置信息:")
        logger.info(f"  - IP范围文件: {config.ip_range_file}")
        logger.info(f"  - 端口文件: {config.ports_file}")
        logger.info(f"  - 排除IP文件: {config.exclude_ips_file}")
        logger.info(f"  - 最大线程数: {config.max_workers}")
        logger.info("=" * 50)

        # 加载配置文件
        ip_ranges = load_ip_ranges(config.ip_range_file, logger)
        if not ip_ranges:
            logger.error("IP范围列表为空，无法继续扫描")
            return

        ports = load_text_file(config.ports_file, logger, "端口")
        if not ports:
            logger.error("端口列表为空，无法继续扫描")
            return

        exclude_ips = load_text_file(config.exclude_ips_file, logger, "排除IP")

        # 执行并发扫描
        logger.info(f"开始扫描 {len(ip_ranges)} 个网段...")
        final_results = {}

        with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
            future_to_cidr = {
                executor.submit(
                    scan_single_range,
                    cidr,
                    ports,
                    exclude_ips,
                    config.ulimit,
                    logger
                ): cidr
                for cidr in ip_ranges
            }

            for future in as_completed(future_to_cidr):
                cidr = future_to_cidr[future]
                try:
                    result = future.result()
                    final_results.update(result)
                except Exception as e:
                    logger.error(f"处理网段 {cidr} 时出错: {str(e)}")

        # 保存扫描结果
        scan_stats = save_results(
            final_results,
            scan_start_time,
            ports,
            config.save_result_file,
            logger
        )

        # 生成报告
        logger.info("=" * 50)
        logger.info("开始生成扫描报告")

        # 动态生成IP范围字符串（从实际加载的数据，最多显示前8个）
        if len(ip_ranges) > 8:
            ip_range_str = "\n".join(ip_ranges[:8]) + f"\n... (共{len(ip_ranges)}个网段，仅显示前8个)"
        else:
            ip_range_str = "\n".join(ip_ranges)

        scan_data = {
            "scan_start_time": scan_stats["scan_start_time"],
            "scan_end_time": scan_stats["scan_end_time"],
            "scan_duration": scan_stats["scan_duration"],
            "ip_range": ip_range_str,
            "ports": ports
        }

        output_file = f"{time.strftime('%Y.%m.%d')}_网络高危端口扫描报告.docx"
        report = Report(
            scan_data,
            config.save_result_file,
            config.template_file,
            output_file,
            config.redarea_file
        )
        report.generate_report()

        logger.info("=" * 50)
        logger.info(f"扫描任务完成！")
        logger.info(f"  - 扫描结果: {config.save_result_file}")
        logger.info(f"  - 报告文件: {output_file}")
        logger.info(f"  - 发现主机: {len(final_results)} 台")
        logger.info("=" * 50)

    except KeyboardInterrupt:
        logger.warning("\n用户中断扫描任务")
    except Exception as e:
        logger.error(f"扫描任务失败: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
