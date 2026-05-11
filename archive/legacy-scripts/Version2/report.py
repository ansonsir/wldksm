"""
报告生成模块
支持普通区域和红区扫描报告生成
集成数据库和模板管理
"""
import ast
import time
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from ipaddress import ip_network, ip_address, IPv4Address

try:
    from docxtpl import DocxTemplate
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

from database import DatabaseManager
from template_manager import TemplateManager


@dataclass
class PortCategory:
    """端口类别定义"""
    name: str
    ports: Set[int]
    field_num: str
    field_info: str


@dataclass
class DeviceInfo:
    """设备信息"""
    ip: str
    ports: List[int]
    categories: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """根据端口识别服务类别"""
        port_set = set(self.ports)
        categories = []
        
        if port_set & {21}:
            categories.append("FTP")
        if port_set & {22}:
            categories.append("SSH")
        if port_set & {3389}:
            categories.append("RDP")
        if port_set & {1433, 1521, 2181, 3306, 5432, 6379, 15672, 27017}:
            categories.append("Database")
        if port_set & {1883, 5672, 8161, 61616}:
            categories.append("MQTT")
        if port_set & {445}:
            categories.append("SMB")
        
        self.categories = categories


class ReportDataAnalyzer:
    """报告数据分析器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("ReportAnalyzer")
        
        # 定义端口类别
        self.port_categories = [
            PortCategory("FTP", {21}, "p_ftp_devices_num", "p_ftp_devices_info"),
            PortCategory("SSH", {22}, "p_ssh_devices_num", "p_ssh_devices_info"),
            PortCategory("RDP", {3389}, "p_rdp_devices_num", "p_rdp_devices_info"),
            PortCategory("Database", {1433, 1521, 2181, 3306, 5432, 6379, 15672, 27017}, 
                        "p_db_devices_num", "p_db_devices_info"),
            PortCategory("MQTT", {1883, 5672, 8161, 61616}, "p_mqtt_devices_num", "p_mqtt_devices_info"),
        ]
        
        self.devices: List[DeviceInfo] = []
        self.redarea_devices: List[DeviceInfo] = []
        self.redarea_networks: List = []
    
    def load_redarea_networks(self, redarea_file: str) -> bool:
        """
        加载红区网段配置
        
        :param redarea_file: 红区网段文件路径
        :return: 是否成功加载
        """
        try:
            path = Path(redarea_file)
            if not path.exists():
                self.logger.warning(f"红区网段文件不存在: {redarea_file}")
                return False
            
            with open(redarea_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    
                    try:
                        network = ip_network(line, strict=False)
                        self.redarea_networks.append(network)
                    except ValueError as e:
                        self.logger.error(f"第 {line_num} 行无效网段格式: {line} - {e}")
            
            self.logger.info(f"成功加载 {len(self.redarea_networks)} 个红区网段")
            return True
            
        except Exception as e:
            self.logger.error(f"加载红区网段文件失败: {e}")
            return False
    
    def load_scan_results(self, result_file: str) -> bool:
        """
        加载扫描结果
        
        :param result_file: 扫描结果文件路径
        :return: 是否成功加载
        """
        try:
            path = Path(result_file)
            if not path.exists():
                self.logger.error(f"扫描结果文件不存在: {result_file}")
                return False
            
            loaded_count = 0
            error_count = 0
            
            with open(result_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    
                    try:
                        device = self._parse_result_line(line)
                        if device:
                            self.devices.append(device)
                            loaded_count += 1
                    except Exception as e:
                        self.logger.error(f"第 {line_num} 行解析失败: {line} - {e}")
                        error_count += 1
            
            self.logger.info(f"成功加载 {loaded_count} 条扫描结果，失败 {error_count} 条")
            return loaded_count > 0
            
        except Exception as e:
            self.logger.error(f"加载扫描结果文件失败: {e}")
            return False
    
    def _parse_result_line(self, line: str) -> Optional[DeviceInfo]:
        """
        解析单行扫描结果
        
        :param line: 扫描结果行
        :return: DeviceInfo 对象或 None
        """
        # 支持两种格式:
        # 1. "IP  [port1, port2]" (原格式)
        # 2. "IP    port1,port2,port3" (红区格式)
        
        parts = line.split()
        if len(parts) < 2:
            return None
        
        ip = parts[0].strip()
        
        # 验证 IP 格式
        try:
            ip_address(ip)
        except ValueError:
            self.logger.warning(f"无效的 IP 地址: {ip}")
            return None
        
        # 解析端口
        ports_str = parts[1].strip() if len(parts) > 1 else ""
        
        try:
            # 尝试解析为 Python 列表格式
            if ports_str.startswith('[') and ports_str.endswith(']'):
                ports = ast.literal_eval(ports_str)
            else:
                # 尝试解析为逗号分隔的端口
                ports = [int(p.strip()) for p in ports_str.split(',') if p.strip()]
            
            if not isinstance(ports, (list, tuple)):
                return None
            
            ports = [int(p) for p in ports]
            return DeviceInfo(ip=ip, ports=ports)
            
        except (ValueError, SyntaxError) as e:
            self.logger.warning(f"无法解析端口数据: {ports_str} - {e}")
            return None
    
    def analyze(self, enable_redarea: bool = False) -> Dict[str, Any]:
        """
        分析扫描数据
        
        :param enable_redarea: 是否启用红区分析
        :return: 分析结果字典
        """
        result = {
            'total_devices_num': len(self.devices),
        }
        
        # 按类别统计
        for category in self.port_categories:
            devices_in_category = [
                d for d in self.devices 
                if set(d.ports) & category.ports
            ]
            
            count = len(devices_in_category)
            if count == 0:
                result[category.field_num] = "没有设备"
                result[category.field_info] = "没有设备\n"
            else:
                result[category.field_num] = f"共检测到{count}台设备"
                result[category.field_info] = '\n'.join(d.ip for d in devices_in_category) + '\n'
        
        # 红区分析
        if enable_redarea and self.redarea_networks:
            self._analyze_redarea()
            
            redarea_count = len(self.redarea_devices)
            if redarea_count == 0:
                result['p_redArea_devices_num'] = "没有设备"
                result['p_redArea_devices_info'] = "没有设备\n"
            else:
                result['p_redArea_devices_num'] = f"共检测到{redarea_count}台设备"
                result['p_redArea_devices_info'] = '\n'.join(
                    f"{d.ip} {d.ports}" for d in self.redarea_devices
                )
        
        return result
    
    def _analyze_redarea(self):
        """分析红区设备"""
        for device in self.devices:
            try:
                ip = ip_address(device.ip)
                if any(ip in network for network in self.redarea_networks):
                    self.redarea_devices.append(device)
            except ValueError:
                continue
        
        self.logger.info(f"发现 {len(self.redarea_devices)} 台红区设备")


class ReportGenerator:
    """报告生成器"""
    
    def __init__(
        self,
        template_file: str,
        output_file: str,
        logger: Optional[logging.Logger] = None
    ):
        self.template_file = template_file
        self.output_file = output_file
        self.logger = logger or logging.getLogger("ReportGenerator")
        
        if not DOCX_AVAILABLE:
            self.logger.error("未安装 docxtpl 库，无法生成 Word 报告")
    
    def generate(
        self,
        scan_data: Dict[str, str],
        analysis_result: Dict[str, Any],
        enable_docx: bool = True
    ) -> bool:
        """
        生成报告
        
        :param scan_data: 扫描元数据
        :param analysis_result: 分析结果
        :param enable_docx: 是否生成 Word 文档
        :return: 是否成功
        """
        try:
            # 合并数据
            template_fields = {
                'report_date': time.strftime('%Y.%m.%d'),
                'scan_start_time': scan_data.get('scan_start_time', ''),
                'scan_end_time': scan_data.get('scan_end_time', ''),
                'scan_duration': scan_data.get('scan_duration', ''),
                'ip_range': scan_data.get('ip_range', ''),
                'ports': scan_data.get('ports', ''),
                **analysis_result
            }
            
            # 生成文本报告
            self._generate_text_report(template_fields)
            
            # 生成 Word 报告
            if enable_docx and DOCX_AVAILABLE:
                self._generate_docx_report(template_fields)
            
            return True
            
        except Exception as e:
            self.logger.error(f"生成报告失败: {e}", exc_info=True)
            return False
    
    def _generate_text_report(self, fields: Dict[str, Any]):
        """生成文本格式报告"""
        text_file = self.output_file.replace('.docx', '.txt')
        
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write("="*60 + "\n")
            f.write("网络端口扫描报告\n")
            f.write("="*60 + "\n\n")
            f.write(f"报告日期: {fields.get('report_date', '')}\n")
            f.write(f"扫描开始: {fields.get('scan_start_time', '')}\n")
            f.write(f"扫描结束: {fields.get('scan_end_time', '')}\n")
            f.write(f"扫描用时: {fields.get('scan_duration', '')}\n")
            f.write(f"扫描范围: {fields.get('ip_range', '')}\n")
            f.write(f"扫描端口: {fields.get('ports', '')}\n")
            f.write(f"设备总数: {fields.get('total_devices_num', 0)}\n")
            f.write("\n" + "="*60 + "\n")
            f.write("详细统计\n")
            f.write("="*60 + "\n\n")
            
            # 输出各类别统计
            categories = [
                ("FTP 服务", 'p_ftp_devices_num', 'p_ftp_devices_info'),
                ("SSH 服务", 'p_ssh_devices_num', 'p_ssh_devices_info'),
                ("RDP 服务", 'p_rdp_devices_num', 'p_rdp_devices_info'),
                ("数据库服务", 'p_db_devices_num', 'p_db_devices_info'),
                ("MQTT 服务", 'p_mqtt_devices_num', 'p_mqtt_devices_info'),
            ]
            
            for name, num_key, info_key in categories:
                f.write(f"【{name}】\n")
                f.write(f"数量: {fields.get(num_key, '未知')}\n")
                f.write(f"设备:\n{fields.get(info_key, '无')}\n")
                f.write("-"*40 + "\n")
            
            # 红区设备
            if 'p_redArea_devices_num' in fields:
                f.write("\n【红区设备】\n")
                f.write(f"数量: {fields.get('p_redArea_devices_num', '未知')}\n")
                f.write(f"设备:\n{fields.get('p_redArea_devices_info', '无')}\n")
        
        self.logger.info(f"文本报告已保存: {text_file}")
    
    def _generate_docx_report(self, fields: Dict[str, Any]):
        """生成 Word 格式报告"""
        if not DOCX_AVAILABLE:
            return
        
        try:
            template_path = Path(self.template_file)
            if not template_path.exists():
                self.logger.error(f"模板文件不存在: {self.template_file}")
                return
            
            docx = DocxTemplate(str(template_path))
            docx.render(fields)
            docx.save(self.output_file)
            
            self.logger.info(f"Word 报告已保存: {self.output_file}")
            
        except Exception as e:
            self.logger.error(f"生成 Word 报告失败: {e}")


def generate_report(
    scan_data: Dict[str, str],
    result_file: str,
    template_file: str,
    output_file: str,
    redarea_file: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    db_manager: Optional[DatabaseManager] = None,
    record_id: Optional[int] = None
) -> bool:
    """
    生成报告的便捷函数
    
    :param scan_data: 扫描元数据
    :param result_file: 扫描结果文件
    :param template_file: Word 模板文件
    :param output_file: 输出文件路径
    :param redarea_file: 红区网段文件（可选）
    :param logger: 日志记录器
    :param db_manager: 数据库管理器（可选）
    :param record_id: 扫描记录ID（用于更新数据库）
    :return: 是否成功
    """
    if logger is None:
        logger = logging.getLogger("Report")
    
    logger.info("开始生成扫描报告...")
    
    # 数据分析
    analyzer = ReportDataAnalyzer(logger)
    
    # 加载红区配置
    enable_redarea = False
    if redarea_file:
        enable_redarea = analyzer.load_redarea_networks(redarea_file)
    
    # 加载扫描结果
    if not analyzer.load_scan_results(result_file):
        logger.error("无法加载扫描结果，报告生成失败")
        return False
    
    # 分析数据
    analysis_result = analyzer.analyze(enable_redarea=enable_redarea)
    
    # 生成报告
    generator = ReportGenerator(template_file, output_file, logger)
    success = generator.generate(scan_data, analysis_result)
    
    # 更新数据库记录
    if success and db_manager and record_id:
        db_manager.update_scan_record(
            record_id,
            report_file=output_file
        )
        logger.info(f"扫描记录已更新报告文件: {record_id}")
    
    if success:
        logger.info("报告生成完成")
    else:
        logger.error("报告生成失败")
    
    return success


def generate_report_with_db(
    scan_data: Dict[str, str],
    result_file: str,
    output_file: str,
    area_name: str = "普通区",
    template_dir: str = "templates",
    redarea_file: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    db_manager: Optional[DatabaseManager] = None,
    record_id: Optional[int] = None
) -> bool:
    """
    使用数据库配置生成报告
    
    :param scan_data: 扫描元数据
    :param result_file: 扫描结果文件
    :param output_file: 输出文件路径
    :param area_name: 区域名称（用于选择模板）
    :param template_dir: 模板目录
    :param redarea_file: 红区网段文件（可选）
    :param logger: 日志记录器
    :param db_manager: 数据库管理器
    :param record_id: 扫描记录ID
    :return: 是否成功
    """
    if logger is None:
        logger = logging.getLogger("Report")
    
    # 使用模板管理器获取模板
    template_manager = TemplateManager(template_dir, db_manager, logger)
    template_file = template_manager.get_template_for_area(area_name)
    
    if not template_file:
        logger.error(f"未找到区域 '{area_name}' 的模板")
        return False
    
    logger.info(f"使用模板: {template_file}")
    
    return generate_report(
        scan_data=scan_data,
        result_file=result_file,
        template_file=template_file,
        output_file=output_file,
        redarea_file=redarea_file,
        logger=logger,
        db_manager=db_manager,
        record_id=record_id
    )


if __name__ == "__main__":
    # 示例用法
    scan_data = {
        "scan_start_time": "2024-01-01 10:00:00",
        "scan_end_time": "2024-01-01 11:00:00",
        "scan_duration": "1小时",
        "ip_range": "10.0.0.0/24",
        "ports": "22,80,443"
    }
    
    generate_report(
        scan_data=scan_data,
        result_file="scan_results.txt",
        template_file="template.docx",
        output_file="report.docx",
        redarea_file="redArea_ips.txt"
    )
