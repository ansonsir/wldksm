#!/usr/bin/env python3
"""
网络扫描工具 - 命令行统一入口
支持普通区域扫描和红区扫描
"""
import argparse
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

from core.config import ConfigManager, ScanConfig
from core.scanner import run_scan
from core.report import generate_report_with_db
from core.database import DatabaseManager
from core.template_manager import TemplateManager
from core.utils import setup_logging, load_text_file, load_ip_ranges


def create_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="网络端口扫描工具 v4.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                          # 默认模式扫描
  %(prog)s --mode redarea           # 红区扫描（全端口）
  %(prog)s --config data/config.yaml  # 指定配置文件
        """
    )

    parser.add_argument(
        "--mode",
        choices=["normal", "redarea"],
        default="normal",
        help="扫描模式: normal (普通区域) 或 redarea (红区全端口扫描)"
    )

    parser.add_argument("--config", type=str, help="配置文件路径 (YAML格式)")
    parser.add_argument("--ip-range", type=str, dest="ip_range_file", help="IP范围文件路径")
    parser.add_argument("--ports", type=str, dest="ports_file", help="端口列表文件路径")
    parser.add_argument("--exclude", type=str, dest="exclude_ips_file", help="排除IP文件路径")
    parser.add_argument("--output", type=str, dest="save_result_file", help="扫描结果输出文件")
    parser.add_argument("--template", type=str, dest="template_file", help="Word报告模板文件")
    parser.add_argument("--redarea", type=str, dest="redarea_file", help="红区网段文件路径")
    parser.add_argument("--workers", type=int, dest="max_workers", help="最大并发线程数")
    parser.add_argument("--log", type=str, dest="log_file", help="日志文件路径")
    parser.add_argument("--no-report", action="store_true", help="不生成Word报告")

    # 数据库管理命令
    parser.add_argument("--init-db", action="store_true", help="初始化数据库")
    parser.add_argument("--history", nargs="?", const="all", metavar="ID", help="显示扫描历史")
    parser.add_argument("--stats", action="store_true", help="显示扫描统计信息")

    # 模板管理命令
    parser.add_argument("--template-list", action="store_true", help="列出所有模板")
    parser.add_argument("--template-add", nargs=2, metavar=("PATH", "NAME"), help="添加模板")

    # IP范围管理命令
    parser.add_argument("--ip-list", nargs="?", const="all", metavar="AREA", help="列出IP范围")
    parser.add_argument("--ip-import", nargs=2, metavar=("FILE", "AREA"), help="从文件导入IP范围")

    return parser


def merge_config(args: argparse.Namespace) -> ScanConfig:
    """合并命令行参数和配置文件"""
    if args.config:
        config_manager = ConfigManager(args.config)
        config = config_manager.get_config()
    else:
        config_manager = ConfigManager()
        config = config_manager.get_config()

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

    config.scan_mode = args.mode

    if args.mode == "redarea":
        config.ports = None
        config.report_suffix = "红区端口扫描"

    return config


def print_banner():
    """打印程序横幅"""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║              网络端口扫描工具 v4.0                        ║
║                                                           ║
║  支持模式:                                                ║
║    - normal:  普通区域扫描（指定端口）                    ║
║    - redarea: 红区扫描（全端口 1-65535）                  ║
╚═══════════════════════════════════════════════════════════╝
    """
    print(banner)


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
                    print(f"  状态: {record.scan_status}")
                    print(f"  开始时间: {record.start_time}")
                    print(f"  结束时间: {record.end_time}")
                    print(f"  用时: {record.duration_seconds} 秒")
                    print(f"  IP范围: {record.ip_ranges}")
                    print(f"  发现主机: {record.total_hosts}")
                    print(f"  结果文件: {record.result_file}")
                    print(f"  报告文件: {record.report_file}")
                else:
                    print(f"未找到记录 ID: {record_id}")
            except ValueError:
                print("记录ID必须是整数")
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

    if args.template_add:
        path, name = args.template_add
        success, msg = template_manager.add_template(path, name)
        print(msg)
        return True

    return False


def main():
    """主函数"""
    parser = create_argument_parser()
    args = parser.parse_args()

    config = merge_config(args)
    logger = setup_logging(
        log_file=config.log_file,
        console_output=True,
        file_mode='a'
    )

    if handle_db_commands(args, config, logger):
        return 0

    if handle_template_commands(args, config, logger):
        return 0

    print_banner()
    db = DatabaseManager(config.db_path, logger)

    area_id = None
    area_name = "普通区" if config.scan_mode == "normal" else "红区"
    area = db.get_scan_area_by_name(area_name)
    if area:
        area_id = area.id

    logger.info(f"启动扫描，模式: {config.scan_mode}, 区域: {area_name}")

    try:
        results, record_id = run_scan(config, logger=logger, db_manager=db, area_id=area_id)

        if not results:
            logger.warning("扫描未完成或未发现任何开放端口")
            return 1

        if not args.no_report:
            scan_start_time = time.time() - 3600
            scan_end_time = time.time()

            try:
                ip_ranges = load_ip_ranges(config.ip_range_file, logger)
                if len(ip_ranges) > 8:
                    ip_range_str = "\n".join(ip_ranges[:8]) + f"\n... (共{len(ip_ranges)}个网段)"
                else:
                    ip_range_str = "\n".join(ip_ranges)
            except:
                ip_range_str = "未知"

            if config.scan_mode == "redarea":
                ports_str = "1-65535 (全端口)"
            elif config.ports:
                ports_str = config.ports
            else:
                try:
                    ports_str = load_text_file(config.ports_file, logger, "端口")
                except:
                    ports_str = "未知"

            scan_data = {
                "scan_start_time": datetime.fromtimestamp(scan_start_time).strftime("%Y-%m-%d %H:%M:%S"),
                "scan_end_time": datetime.fromtimestamp(scan_end_time).strftime("%Y-%m-%d %H:%M:%S"),
                "scan_duration": "计算中...",
                "ip_range": ip_range_str,
                "ports": ports_str
            }

            if config.scan_mode == "redarea":
                output_file = f"{time.strftime('%Y.%m.%d')}红区端口扫描.txt"
            else:
                output_file = f"{time.strftime('%Y.%m.%d')}{config.report_suffix}.docx"

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
    import time
    sys.exit(main())
