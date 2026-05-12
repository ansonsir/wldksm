#!/usr/bin/env python3
"""
网络扫描工具 - 统一入口
支持普通区域扫描和红区扫描
集成SQLite数据库和模板管理
支持Linux定时任务(cron)

用法:
    python main.py                    # 默认模式（普通区域扫描）
    python main.py --mode redarea     # 红区扫描模式
    python main.py --config config.yaml  # 指定配置文件
    python main.py --init-db          # 初始化数据库
    python main.py --template-list    # 列出模板
    python main.py --cron-setup       # 设置定时任务
"""
import argparse
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

from config import ConfigManager, setup_logging, ScanConfig
from network_scan import run_scan
from report import generate_report_with_db
from database import DatabaseManager, init_database, IPRange
from template_manager import TemplateManager


def create_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="网络端口扫描工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                          # 默认模式扫描
  %(prog)s --mode redarea           # 红区扫描（全端口）
  %(prog)s --config scan.yaml       # 使用配置文件
  %(prog)s --ip-range ips.txt --ports ports.txt  # 指定输入文件
  
IP范围管理（支持多区域）:
  %(prog)s --ip-add "10.0.0.0/24" "普通区,红区"   # 添加IP到多个区域
  %(prog)s --ip-import ips.txt "普通区"           # 从文件导入
  %(prog)s --ip-list                              # 列出所有IP范围
  
端口管理:
  %(prog)s --port-list                            # 列出所有端口
  %(prog)s --port-list 3                          # 列出高风险端口
  
定时任务管理:
  %(prog)s --cron-setup                           # 交互式设置定时任务
  %(prog)s --cron-quick "普通区" "02:00" "daily"  # 快速设置每天2点扫描
        """
    )
    
    parser.add_argument(
        "--mode",
        choices=["normal", "redarea"],
        default="normal",
        help="扫描模式: normal (普通区域) 或 redarea (红区全端口扫描)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        help="配置文件路径 (YAML格式)"
    )
    
    parser.add_argument(
        "--ip-range",
        type=str,
        dest="ip_range_file",
        help="IP范围文件路径"
    )
    
    parser.add_argument(
        "--ports",
        type=str,
        dest="ports_file",
        help="端口列表文件路径"
    )
    
    parser.add_argument(
        "--exclude",
        type=str,
        dest="exclude_ips_file",
        help="排除IP文件路径"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        dest="save_result_file",
        help="扫描结果输出文件"
    )
    
    parser.add_argument(
        "--template",
        type=str,
        dest="template_file",
        help="Word报告模板文件"
    )
    
    parser.add_argument(
        "--redarea",
        type=str,
        dest="redarea_file",
        help="红区网段文件路径"
    )
    
    parser.add_argument(
        "--workers",
        type=int,
        dest="max_workers",
        help="最大并发线程数"
    )
    
    parser.add_argument(
        "--log",
        type=str,
        dest="log_file",
        help="日志文件路径"
    )
    
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="不生成Word报告"
    )
    
    # 数据库管理命令
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="初始化数据库"
    )
    
    parser.add_argument(
        "--history",
        nargs="?",
        const="all",
        metavar="ID",
        help="显示扫描历史，可指定记录ID查看详情"
    )
    
    parser.add_argument(
        "--stats",
        action="store_true",
        help="显示扫描统计信息"
    )
    
    # 模板管理命令
    parser.add_argument(
        "--template-list",
        action="store_true",
        help="列出所有模板"
    )
    
    parser.add_argument(
        "--template-validate",
        metavar="NAME",
        help="验证指定模板"
    )
    
    parser.add_argument(
        "--template-preview",
        metavar="NAME",
        help="生成模板预览"
    )
    
    parser.add_argument(
        "--template-add",
        nargs=2,
        metavar=("PATH", "NAME"),
        help="添加模板 (路径 名称)"
    )
    
    parser.add_argument(
        "--template-guide",
        action="store_true",
        help="生成模板字段说明文档"
    )
    
    # IP范围管理命令
    parser.add_argument(
        "--ip-list",
        nargs="?",
        const="all",
        metavar="AREA",
        help="列出IP范围，可指定区域名称"
    )
    
    parser.add_argument(
        "--ip-add",
        nargs=2,
        metavar=("RANGE", "AREA"),
        help="添加IP范围 (CIDR格式 区域名称)"
    )
    
    parser.add_argument(
        "--ip-import",
        nargs=2,
        metavar=("FILE", "AREA"),
        help="从文件导入IP范围"
    )
    
    parser.add_argument(
        "--ip-export",
        nargs=2,
        metavar=("FILE", "AREA"),
        help="导出IP范围到文件"
    )
    
    parser.add_argument(
        "--ip-delete",
        type=int,
        metavar="ID",
        help="删除指定ID的IP范围"
    )
    
    # 端口管理命令
    parser.add_argument(
        "--port-list",
        nargs="?",
        const="all",
        metavar="RISK",
        help="列出端口信息，可指定风险等级(1/2/3)"
    )
    
    # 定时任务管理
    parser.add_argument(
        "--cron-setup",
        action="store_true",
        help="设置定时任务（交互式）"
    )
    
    parser.add_argument(
        "--cron-list",
        action="store_true",
        help="列出当前定时任务"
    )
    
    parser.add_argument(
        "--cron-remove",
        type=str,
        metavar="COMMENT",
        help="移除指定注释的定时任务"
    )
    
    parser.add_argument(
        "--cron-quick",
        nargs=3,
        metavar=("AREA", "TIME", "FREQ"),
        help="快速设置定时任务: 区域 时间 频率(daily/weekly/monthly)"
    )
    
    return parser


def merge_config(args: argparse.Namespace) -> ScanConfig:
    """
    合并命令行参数和配置文件
    
    :param args: 命令行参数
    :return: 合并后的配置
    """
    # 加载配置文件（如果指定）
    if args.config:
        config_manager = ConfigManager(args.config)
        config = config_manager.get_config()
    else:
        config = ScanConfig()
    
    # 命令行参数覆盖配置文件
    if args.ip_range_file:
        config.ip_range_file = args.ip_range_file
    if args.ports_file:
        config.ports_file = args.ports_file
    if args.exclude_ips_file:
        config.exclude_ips_file = args.exclude_ips_file
    if args.save_result_file:
        config.save_result_file = args.save_result_file
    if args.template_file:
        config.template_file = args.template_file
    if args.redarea_file:
        config.redarea_file = args.redarea_file
    if args.max_workers:
        config.max_workers = args.max_workers
    if args.log_file:
        config.log_file = args.log_file
    
    # 设置扫描模式
    config.scan_mode = args.mode
    
    # 红区模式特殊配置
    if args.mode == "redarea":
        config.ports = None  # 全端口扫描
        config.report_suffix = "红区端口扫描"
    
    return config


def print_banner():
    """打印程序横幅"""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║              网络端口扫描工具 v2.0                        ║
║                                                           ║
║  支持模式:                                                ║
║    - normal:  普通区域扫描（指定端口）                    ║
║    - redarea: 红区扫描（全端口 1-65535）                  ║
╚═══════════════════════════════════════════════════════════╝
    """
    print(banner)


class CronManager:
    """Linux定时任务管理器"""
    
    def __init__(self, logger=None):
        self.logger = logger
        self.script_path = Path(__file__).resolve()
        self.cron_comment_prefix = "# NetworkScan-"
    
    def list_cron_jobs(self) -> list:
        """列出当前用户的所有定时任务"""
        try:
            result = subprocess.run(
                ['crontab', '-l'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                # 过滤出NetworkScan相关的任务
                scan_jobs = []
                for i, line in enumerate(lines):
                    if self.cron_comment_prefix in line or 'main.py' in line:
                        scan_jobs.append((i, line))
                return scan_jobs
            return []
        except Exception as e:
            if self.logger:
                self.logger.error(f"获取定时任务失败: {e}")
            return []
    
    def add_cron_job(self, schedule: str, command: str, comment: str) -> bool:
        """
        添加定时任务
        
        :param schedule: cron时间表达式 (如 "0 2 * * *" 表示每天2点)
        :param command: 要执行的命令
        :param comment: 任务注释
        :return: 是否成功
        """
        try:
            # 获取现有crontab
            result = subprocess.run(
                ['crontab', '-l'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                current_crontab = result.stdout
            else:
                current_crontab = ""
            
            # 添加新任务
            new_job = f"\n{self.cron_comment_prefix}{comment}\n{schedule} {command}\n"
            new_crontab = current_crontab + new_job
            
            # 写入新crontab
            process = subprocess.Popen(
                ['crontab', '-'],
                stdin=subprocess.PIPE,
                text=True
            )
            process.communicate(input=new_crontab)
            
            if self.logger:
                self.logger.info(f"定时任务已添加: {comment}")
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"添加定时任务失败: {e}")
            return False
    
    def remove_cron_job(self, comment_keyword: str) -> bool:
        """移除指定注释的定时任务"""
        try:
            result = subprocess.run(
                ['crontab', '-l'],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return False
            
            lines = result.stdout.strip().split('\n')
            new_lines = []
            skip_next = False
            
            for line in lines:
                if skip_next:
                    skip_next = False
                    continue
                if comment_keyword in line:
                    skip_next = True  # 跳过下一行（实际的cron命令）
                    continue
                new_lines.append(line)
            
            new_crontab = '\n'.join(new_lines) + '\n'
            
            process = subprocess.Popen(
                ['crontab', '-'],
                stdin=subprocess.PIPE,
                text=True
            )
            process.communicate(input=new_crontab)
            
            if self.logger:
                self.logger.info(f"定时任务已移除: {comment_keyword}")
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"移除定时任务失败: {e}")
            return False
    
    def setup_interactive(self, config: ScanConfig) -> bool:
        """交互式设置定时任务"""
        print("\n" + "="*60)
        print("设置定时扫描任务")
        print("="*60)
        
        # 选择区域
        db = DatabaseManager(config.db_path)
        areas = db.get_scan_areas()
        print("\n可用扫描区域:")
        for i, area in enumerate(areas, 1):
            print(f"  {i}. {area.area_name} - {area.description}")
        
        try:
            area_idx = int(input("\n请选择区域 (输入数字): ")) - 1
            if area_idx < 0 or area_idx >= len(areas):
                print("无效选择")
                return False
            selected_area = areas[area_idx]
        except ValueError:
            print("请输入数字")
            return False
        
        # 选择频率
        print("\n扫描频率:")
        print("  1. 每天")
        print("  2. 每周")
        print("  3. 每月")
        print("  4. 自定义")
        
        freq_choice = input("\n请选择频率 (输入数字): ")
        
        if freq_choice == "1":
            time_str = input("请输入时间 (格式 HH:MM, 如 02:00): ")
            try:
                hour, minute = time_str.split(':')
                schedule = f"{minute} {hour} * * *"
            except:
                print("时间格式错误")
                return False
        elif freq_choice == "2":
            day = input("请输入星期几 (0=周日, 1=周一, ..., 6=周六): ")
            time_str = input("请输入时间 (格式 HH:MM): ")
            try:
                hour, minute = time_str.split(':')
                schedule = f"{minute} {hour} * * {day}"
            except:
                print("格式错误")
                return False
        elif freq_choice == "3":
            day = input("请输入日期 (1-31): ")
            time_str = input("请输入时间 (格式 HH:MM): ")
            try:
                hour, minute = time_str.split(':')
                schedule = f"{minute} {hour} {day} * *"
            except:
                print("格式错误")
                return False
        elif freq_choice == "4":
            print("\nCron表达式格式: 分 时 日 月 星期")
            print("示例: 0 2 * * * (每天2点)")
            schedule = input("请输入Cron表达式: ")
        else:
            print("无效选择")
            return False
        
        # 构建命令
        work_dir = Path(__file__).parent.resolve()
        log_file = f"cron_scan_{selected_area.area_name}_{datetime.now().strftime('%Y%m%d')}.log"
        command = f"cd {work_dir} && python3 {self.script_path} --mode {selected_area.area_name.lower()} --config config.yaml >> {log_file} 2>&1"
        
        comment = f"{selected_area.area_name}-{freq_choice}"
        
        print(f"\n将要添加的定时任务:")
        print(f"  时间: {schedule}")
        print(f"  命令: {command}")
        print(f"  注释: {comment}")
        
        confirm = input("\n确认添加? (y/n): ")
        if confirm.lower() == 'y':
            if self.add_cron_job(schedule, command, comment):
                print("定时任务添加成功！")
                return True
        else:
            print("已取消")
        
        return False
    
    def quick_setup(self, area_name: str, time_str: str, freq: str) -> bool:
        """快速设置定时任务"""
        try:
            hour, minute = time_str.split(':')
            
            if freq == "daily":
                schedule = f"{minute} {hour} * * *"
            elif freq == "weekly":
                schedule = f"{minute} {hour} * * 1"  # 每周一
            elif freq == "monthly":
                schedule = f"{minute} {hour} 1 * *"  # 每月1号
            else:
                print(f"不支持的频率: {freq}")
                return False
            
            work_dir = Path(__file__).parent.resolve()
            mode = "redarea" if "红区" in area_name else "normal"
            log_file = f"cron_scan_{area_name}_{datetime.now().strftime('%Y%m%d')}.log"
            command = f"cd {work_dir} && python3 {self.script_path} --mode {mode} --config config.yaml >> {log_file} 2>&1"
            comment = f"{area_name}-{freq}"
            
            return self.add_cron_job(schedule, command, comment)
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"快速设置失败: {e}")
            return False


def handle_cron_commands(args, config, logger):
    """处理定时任务相关命令"""
    cron_manager = CronManager(logger)
    
    if args.cron_list:
        jobs = cron_manager.list_cron_jobs()
        if jobs:
            print("\n当前扫描定时任务:")
            print(f"{'行号':<6} {'任务':<50}")
            print("-" * 60)
            for line_num, job in jobs:
                print(f"{line_num:<6} {job[:50]}")
        else:
            print("\n没有找到扫描相关的定时任务")
        return True
    
    if args.cron_setup:
        cron_manager.setup_interactive(config)
        return True
    
    if args.cron_remove:
        if cron_manager.remove_cron_job(args.cron_remove):
            print(f"已移除包含 '{args.cron_remove}' 的定时任务")
        else:
            print("移除失败")
        return True
    
    if args.cron_quick:
        area, time_str, freq = args.cron_quick
        if cron_manager.quick_setup(area, time_str, freq):
            print(f"定时任务已设置: {area} {time_str} {freq}")
        else:
            print("设置失败")
        return True
    
    return False


def handle_db_commands(args, config, logger):
    """处理数据库相关命令"""
    db = DatabaseManager(config.db_path, logger)
    
    if args.init_db:
        db.init_default_data()
        print("数据库初始化完成！")
        return True
    
    if args.stats:
        stats = db.get_statistics()
        print("\n扫描统计信息:")
        print(f"  总扫描次数: {stats['total_scans']}")
        print(f"  发现主机总数: {stats['total_hosts']}")
        print("\n  按状态统计:")
        for status, count in stats['status_counts'].items():
            print(f"    {status}: {count}")
        print("\n  按区域统计:")
        for area, count in stats['area_counts'].items():
            print(f"    {area}: {count}")
        return True
    
    if args.history:
        if args.history == "all":
            records = db.get_scan_records(limit=20)
            print("\n最近扫描记录:")
            print(f"{'ID':<5} {'区域':<10} {'状态':<12} {'主机数':<8} {'用时':<10} {'时间':<20}")
            print("-" * 70)
            for r in records:
                area = db.get_scan_area_by_id(r.area_id)
                area_name = area.area_name if area else "未知"
                print(f"{r.id:<5} {area_name:<10} {r.scan_status:<12} {r.total_hosts:<8} "
                      f"{r.duration_seconds//60}分{r.duration_seconds%60}秒{'':<3} {r.created_at:<20}")
        else:
            try:
                record_id = int(args.history)
                record = db.get_scan_record_by_id(record_id)
                if record:
                    print(f"\n扫描记录详情 (ID: {record_id}):")
                    print(f"  区域ID: {record.area_id}")
                    print(f"  状态: {record.scan_status}")
                    print(f"  开始时间: {record.start_time}")
                    print(f"  结束时间: {record.end_time}")
                    print(f"  用时: {record.duration_seconds} 秒")
                    print(f"  IP范围: {record.ip_ranges}")
                    print(f"  发现主机: {record.total_hosts}")
                    print(f"  开放端口: {record.open_ports_count}")
                    print(f"  结果文件: {record.result_file}")
                    print(f"  报告文件: {record.report_file}")
                    if record.error_message:
                        print(f"  错误信息: {record.error_message}")
                else:
                    print(f"未找到记录 ID: {record_id}")
            except ValueError:
                print("记录ID必须是整数")
        return True
    
    return False


def handle_ip_commands(args, config, logger):
    """处理IP范围相关命令（支持多区域）"""
    db = DatabaseManager(config.db_path, logger)
    
    if args.ip_list:
        if args.ip_list == "all":
            # 列出所有IP范围
            ip_ranges = db.get_ip_ranges()
            print("\n所有IP范围:")
            print(f"{'ID':<5} {'IP范围':<20} {'所属区域':<25} {'描述':<25} {'状态':<8}")
            print("-" * 90)
            for ip_range in ip_ranges:
                # 获取区域名称
                area_names = []
                for area_id in ip_range.area_ids:
                    area = db.get_scan_area_by_id(area_id)
                    if area:
                        area_names.append(area.area_name)
                areas_str = ", ".join(area_names) if area_names else "未分配"
                
                status = "启用" if ip_range.is_active else "禁用"
                print(f"{ip_range.id:<5} {ip_range.ip_range:<20} {areas_str:<25} "
                      f"{ip_range.description or '':<25} {status:<8}")
        else:
            # 列出指定区域的IP范围
            area = db.get_scan_area_by_name(args.ip_list)
            if area:
                ip_ranges = db.get_ip_ranges(area_id=area.id)
                print(f"\n区域 '{args.ip_list}' 的IP范围:")
                print(f"{'ID':<5} {'IP范围':<20} {'描述':<30} {'状态':<8}")
                print("-" * 70)
                for ip_range in ip_ranges:
                    status = "启用" if ip_range.is_active else "禁用"
                    print(f"{ip_range.id:<5} {ip_range.ip_range:<20} "
                          f"{ip_range.description or '':<30} {status:<8}")
            else:
                print(f"未找到区域: {args.ip_list}")
        return True
    
    if args.ip_add:
        ip_range_str, area_names_str = args.ip_add
        # 支持多个区域，用逗号分隔
        area_names = [name.strip() for name in area_names_str.split(',')]
        area_ids = []
        
        for area_name in area_names:
            area = db.get_scan_area_by_name(area_name)
            if area:
                area_ids.append(area.id)
            else:
                print(f"警告: 未找到区域 '{area_name}'")
        
        if not area_ids:
            print("错误: 未找到任何有效区域")
            return True
        
        ip_range = IPRange(
            ip_range=ip_range_str,
            description="",
            is_active=True,
            area_ids=area_ids
        )
        range_id = db.add_ip_range(ip_range)
        print(f"IP范围已添加，ID: {range_id}，所属区域: {', '.join(area_names)}")
        return True
    
    if args.ip_import:
        file_path, area_names_str = args.ip_import
        # 支持多个区域
        area_names = [name.strip() for name in area_names_str.split(',')]
        area_ids = []
        
        for area_name in area_names:
            area = db.get_scan_area_by_name(area_name)
            if area:
                area_ids.append(area.id)
        
        if not area_ids:
            print(f"未找到有效区域: {area_names_str}")
            return True
        
        success, fail = db.import_ip_ranges_from_file(file_path, area_ids)
        print(f"导入完成: 成功 {success} 条, 失败 {fail} 条")
        print(f"这些IP范围已关联到区域: {', '.join(area_names)}")
        return True
    
    if args.ip_export:
        file_path, area_name = args.ip_export
        if area_name.lower() == "all":
            area_id = None
        else:
            area = db.get_scan_area_by_name(area_name)
            if not area:
                print(f"未找到区域: {area_name}")
                return True
            area_id = area.id
        
        count = db.export_ip_ranges_to_file(file_path, area_id)
        print(f"已导出 {count} 条IP范围到: {file_path}")
        return True
    
    if args.ip_delete:
        if db.delete_ip_range(args.ip_delete):
            print(f"IP范围已删除，ID: {args.ip_delete}")
        else:
            print(f"删除失败，ID: {args.ip_delete}")
        return True
    
    return False


def handle_port_commands(args, config, logger):
    """处理端口相关命令"""
    db = DatabaseManager(config.db_path, logger)
    
    if args.port_list:
        if args.port_list == "all":
            ports = db.get_ports()
            print("\n所有端口信息:")
        else:
            try:
                risk_level = int(args.port_list)
                ports = db.get_ports(risk_level=risk_level)
                risk_text = {1: "低风险", 2: "中风险", 3: "高风险"}.get(risk_level, "未知")
                print(f"\n{risk_text}端口:")
            except ValueError:
                print("风险等级必须是 1, 2 或 3")
                return True
        
        print(f"{'端口':<8} {'服务':<15} {'协议':<6} {'风险':<8} {'描述':<40}")
        print("-" * 85)
        
        risk_map = {1: "低", 2: "中", 3: "高"}
        for port in ports:
            risk_str = risk_map.get(port.risk_level, "未知")
            print(f"{port.port_num:<8} {port.service_name:<15} {port.protocol:<6} "
                  f"{risk_str:<8} {port.description or '':<40}")
        
        print(f"\n总计: {len(ports)} 个端口")
        return True
    
    return False


def handle_template_commands(args, config, logger):
    """处理模板相关命令"""
    template_manager = TemplateManager(config.template_dir, logger=logger)
    
    if args.template_list:
        templates = template_manager.list_templates()
        print("\n可用模板列表:")
        print(f"{'名称':<20} {'来源':<12} {'描述':<30}")
        print("-" * 65)
        for t in templates:
            print(f"{t['name']:<20} {t['source']:<12} {t['description']:<30}")
        return True
    
    if args.template_validate:
        template_path = Path(config.template_dir) / f"{args.template_validate}.docx"
        if not template_path.exists():
            print(f"模板不存在: {template_path}")
            return True
        result = template_manager.validate_template(str(template_path))
        print(f"\n模板验证结果: {args.template_validate}")
        print(result)
        return True
    
    if args.template_preview:
        template_path = Path(config.template_dir) / f"{args.template_preview}.docx"
        if not template_path.exists():
            print(f"模板不存在: {template_path}")
            return True
        output = template_manager.preview_template(str(template_path))
        if output:
            print(f"预览文件已生成: {output}")
        return True
    
    if args.template_add:
        path, name = args.template_add
        success, msg = template_manager.add_template(path, name)
        print(msg)
        return True
    
    if args.template_guide:
        output = template_manager.generate_template_doc()
        print(f"模板说明文档已生成: {output}")
        return True
    
    return False


def main():
    """主函数"""
    # 解析命令行参数
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # 合并配置
    config = merge_config(args)
    
    # 设置日志
    logger = setup_logging(
        log_file=config.log_file,
        console_output=True,
        file_mode='a'
    )
    
    # 处理数据库命令
    if handle_db_commands(args, config, logger):
        return 0
    
    # 处理模板命令
    if handle_template_commands(args, config, logger):
        return 0
    
    # 处理IP范围命令
    if handle_ip_commands(args, config, logger):
        return 0
    
    # 处理端口命令
    if handle_port_commands(args, config, logger):
        return 0
    
    # 处理定时任务命令
    if handle_cron_commands(args, config, logger):
        return 0
    
    # 正常扫描流程
    print_banner()
    
    # 初始化数据库
    db = DatabaseManager(config.db_path, logger)
    
    # 获取区域ID
    area_id = None
    area_name = "普通区" if config.scan_mode == "normal" else "红区"
    area = db.get_scan_area_by_name(area_name)
    if area:
        area_id = area.id
    
    logger.info(f"启动扫描，模式: {config.scan_mode}, 区域: {area_name}")
    
    try:
        # 执行扫描（传入数据库管理器和区域ID）
        results, record_id = run_scan(config, logger=logger, db_manager=db, area_id=area_id)
        
        if not results:
            logger.warning("扫描未完成或未发现任何开放端口")
            return 1
        
        # 生成报告
        if not args.no_report:
            # 构建扫描元数据
            import time
            from datetime import datetime
            
            scan_start_time = time.time() - 3600  # 估算
            scan_end_time = time.time()
            
            # 加载IP范围用于显示
            from network_scan import FileLoader
            loader = FileLoader()
            try:
                ip_ranges = loader.load_ip_ranges(config.ip_range_file, logger)
                if len(ip_ranges) > 8:
                    ip_range_str = "\n".join(ip_ranges[:8]) + f"\n... (共{len(ip_ranges)}个网段)"
                else:
                    ip_range_str = "\n".join(ip_ranges)
            except:
                ip_range_str = "未知"
            
            # 加载端口信息
            if config.scan_mode == "redarea":
                ports_str = "1-65535 (全端口)"
            elif config.ports:
                ports_str = config.ports
            else:
                try:
                    ports_str = loader.load_text_file(config.ports_file, logger, "端口")
                except:
                    ports_str = "未知"
            
            scan_data = {
                "scan_start_time": datetime.fromtimestamp(scan_start_time).strftime("%Y-%m-%d %H:%M:%S"),
                "scan_end_time": datetime.fromtimestamp(scan_end_time).strftime("%Y-%m-%d %H:%M:%S"),
                "scan_duration": "计算中...",  # 实际应该从 scan_stats 获取
                "ip_range": ip_range_str,
                "ports": ports_str
            }
            
            # 确定输出文件名
            if config.scan_mode == "redarea":
                output_file = f"{time.strftime('%Y.%m.%d')}红区端口扫描.txt"
            else:
                output_file = f"{time.strftime('%Y.%m.%d')}{config.report_suffix}.docx"
            
            # 生成报告（使用数据库集成的版本）
            generate_report_with_db(
                scan_data=scan_data,
                result_file=config.save_result_file,
                output_file=output_file,
                area_name=area_name,
                template_dir=config.template_dir,
                redarea_file=config.redarea_file if config.scan_mode == "redarea" else None,
                logger=logger,
                db_manager=db,
                record_id=record_id
            )
        
        logger.info("扫描任务全部完成！")
        return 0
        
    except KeyboardInterrupt:
        logger.info("用户中断扫描")
        return 130
    except Exception as e:
        logger.error(f"扫描失败: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
