import math
from datetime import datetime
from rustscan import RustScanAPI
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import time
import logging
from report import Report

# 配置日志（记录扫描过程）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w+',
    filename='network_scan.log'
)
logger = logging.getLogger("NetworkScan")

num_cpus = os.cpu_count()
ip_range_file = "ip_range.txt"
exclude_ips_file = "exclude_ips.txt"
ports_file = "ports.txt"
save_result_file = "scan_results.txt"
report_file = "report.docx"
template_file = "template.docx"
redArea_file = "redArea_ips.txt"
scan_datas = {
    "scan_start_time": "",
    "scan_end_time": "",
    "scan_duration": "",
    "ip_range": "",
    "ports": ""
}


def load_exclude_ips(filename="exclude_ip.txt"):
    try:
        with open(filename, 'r') as f:
            exclude_ips = f.read().splitlines()
            exclude_ips = [ip.strip() for ip in exclude_ips if ip.strip() and not ip.startswith('#')]
        exclude_ips_str = ','.join(exclude_ips)
        return exclude_ips_str
    except FileNotFoundError:
        logger.error(f"扫描IP列表文件 {filename} 不存在！")
        raise


def load_ports(filename="ports.txt"):
    ports = []
    try:
        with open(filename, 'r') as f:
            line = f.read().splitlines()
            ports = [port.strip() for port in line if port.strip() and not port.startswith('#')]
        ports_str = ','.join(ports)
        return ports_str
    except FileNotFoundError:
        logger.error(f"扫描端口文件 {filename} 不存在！")
        raise


def load_ip_ranges(filename="ip_range.txt"):
    """
    从文件中加载IP范围列表
    :param filename: 包含CIDR格式IP范围的文件名
    :return: IP范围列表
    :raises FileNotFoundError: 文件不存在时抛出异常
    """
    ip_ranges = []
    try:
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):  # 跳过空行和注释
                    ip_ranges.append(line)
        info = f"成功从 {filename} 加载 {len(ip_ranges)} 个IP范围"
        print(info)
        logger.info(info)
        return ip_ranges
    except FileNotFoundError:
        logger.error(f"文件 {filename} 不存在！")
        raise


ports = load_ports(ports_file)
exclude_ips = load_exclude_ips(exclude_ips_file)


def scan_single_range(cidr: str, ports: str, exclude_ip: str) -> dict:
    """
    扫描单个CIDR网段
    :param cidr: CIDR格式的IP范围（如"10.0.0.0/8"）
    :param exclude_ip: 排除的IP范围
    :return: 开放端口的字典 {IP: [端口列表]}
    """
    try:
        logger.info(f"开始扫描网段: {cidr}")
        start_time = time.time()
        scanner = RustScanAPI(
            target=cidr,
            ports=ports,
            ulimit=32768,
            exclude_ip=exclude_ip
        )

        results = scanner.scan()
        duration = time.time() - start_time

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


def save_results(results: dict, scan_start_time: float, filename: str = "scan_results.txt"):
    """
    保存扫描结果到文件
    :param results: 扫描结果字典
    :param scan_start_time: 扫描开始时间
    :param filename: 输出文件名
    """
    scan_end_time = time.time()
    duration = scan_end_time - scan_start_time
    duration = format_duration(duration)
    start_time_str = datetime.fromtimestamp(scan_start_time).strftime("%Y-%m-%d %H:%M:%S")
    end_time_str = datetime.fromtimestamp(scan_end_time).strftime("%Y-%m-%d %H:%M:%S")
    with open(filename, "w") as f:
        f.write("# RustScan 网络扫描报告\n")
        f.write(f"# 扫描开始时间: {start_time_str}\n")
        f.write(f"# 扫描完成时间: {end_time_str}\n")
        f.write(f"# 扫描用时：{duration}\n")
        f.write(f"# 扫描端口: {ports}\n")
        for ip, port_list in results.items():
            f.write(f"{ip}  {port_list}\n")
    logger.info(f"结果已保存至 {filename}")
    scan_datas["scan_duration"] = duration
    scan_datas["scan_start_time"] = start_time_str
    scan_datas["scan_end_time"] = end_time_str


def main():
    scan_start_time = time.time()
    print("[+] 启动网络扫描任务...")
    print(f"网段读取于 {ip_range_file}")
    print(f"端口读取于 {ports_file}")
    print(f"排除IP读取于 {exclude_ips_file}")
    print("----------------------------------")
    """主扫描流程"""
    try:
        ip_ranges = load_ip_ranges(ip_range_file)
    except FileNotFoundError:
        print("❌ 错误：ip_range.txt 文件不存在！请先创建该文件")
        raise
    if not ip_ranges:
        print("⚠️ 警告：ip_range.txt 中没有有效的IP范围")
        raise
    final_results = {}
    max_works = int(num_cpus * 2.5)
    with ThreadPoolExecutor(max_workers=max_works) as executor:
        future_to_cidr = {
            executor.submit(scan_single_range, cidr, ports, exclude_ips): cidr
            for cidr in ip_ranges
        }
        for future in as_completed(future_to_cidr):
            cidr = future_to_cidr[future]
            try:
                result = future.result()
                final_results.update(result)
            except Exception as e:
                logger.error(f"处理 {cidr} 时出错: {str(e)}")
    save_results(final_results, scan_start_time, save_result_file)
    scan_datas["ip_range"] = ip_ranges
    scan_datas["ports"] = ports
    print(f"[+] 扫描完成！结果保存至 {save_result_file} ")
    print("----------------------------------")
    print("[+] 开始对扫描结果进行处理...")
    output_file = f"{time.strftime('%Y.%m.%d')}网络高危端口扫描报告.docx"
    report = Report(scan_datas, save_result_file, template_file, output_file, redArea_file)
    report.generate_report()
    print(f"[+] 扫描结果处理完成！结果保存至 {output_file} ")


if __name__ == "__main__":
    main()
