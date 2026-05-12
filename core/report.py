"""
报告生成模块
基于 Version2，保留现有端口分类判断逻辑
"""
import time
import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from ipaddress import ip_network, ip_address

try:
    from docxtpl import DocxTemplate
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

from core.database import DatabaseManager
from core.template_manager import TemplateManager


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
    """报告数据分析器 - 保留原有判断逻辑"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("ReportAnalyzer")

        # 保留原有的端口分类判断逻辑
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
        """加载红区网段配置"""
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
        """加载扫描结果"""
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
        """解析单行扫描结果 - 安全版本"""
        parts = line.split()
        if len(parts) < 2:
            return None

        ip = parts[0].strip()

        try:
            ip_address(ip)
        except ValueError:
            self.logger.warning(f"无效的 IP 地址: {ip}")
            return None

        ports_str = parts[1].strip() if len(parts) > 1 else ""

        try:
            if ports_str.startswith('[') and ports_str.endswith(']'):
                # 安全解析：优先 JSON，回退手动解析（拒绝 ast.literal_eval）
                try:
                    ports = json.loads(ports_str)
                except json.JSONDecodeError:
                    # 回退：手动拆分逗号分隔的数字
                    inner = ports_str.strip('[]')
                    ports = [int(p.strip()) for p in inner.split(',') if p.strip()]
            else:
                ports = [int(p.strip()) for p in ports_str.split(',') if p.strip()]

            if not isinstance(ports, (list, tuple)):
                return None

            # 验证端口范围
            ports = [int(p) for p in ports if 1 <= int(p) <= 65535]
            if not ports:
                return None
            return DeviceInfo(ip=ip, ports=ports)

        except (ValueError, SyntaxError) as e:
            self.logger.warning(f"无法解析端口数据: {ports_str} - {e}")
            return None

    def analyze(self, enable_redarea: bool = False) -> Dict[str, Any]:
        """分析扫描数据 - 保留原有判断逻辑，增加科学统计"""
        result = {
            'total_devices_num': len(self.devices),
        }

        summary_lines = [f"一共检测到{len(self.devices)}台设备存在高危端口开放，其中"]

        # 按类别统计 - 保留原有逻辑
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

            # 概况摘要行
            if category.name == "FTP":
                summary_lines.append(f"21端口：{result[category.field_num]}")
            elif category.name == "SSH":
                summary_lines.append(f"22端口：{result[category.field_num]}")
            elif category.name == "RDP":
                summary_lines.append(f"3389端口：{result[category.field_num]}")
            elif category.name == "Database":
                summary_lines.append(f"数据库端口：{result[category.field_num]}")
            elif category.name == "MQTT":
                summary_lines.append(f"信息传输（MQTT等）：{result[category.field_num]}")

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
                    f"{d.ip} {{{', '.join(map(str, d.ports))}}}" for d in self.redarea_devices
                )
            summary_lines.append(f"红区：{result['p_redArea_devices_num']}")
        else:
            result['p_redArea_devices_num'] = "没有设备"
            result['p_redArea_devices_info'] = "没有设备\n"
            summary_lines.append(f"红区：没有设备")

        result['p_summary'] = '\n'.join(summary_lines)
        
        # === 新增：科学统计分析 ===
        # 1. 风险等级评估
        result['risk_level'] = self._calculate_risk_level(len(self.devices))
        
        # 2. 端口分布统计
        result['port_distribution'] = self._analyze_port_distribution()
        
        # 3. 高风险设备列表（开放多个高危端口的设备）
        result['high_risk_devices'] = self._identify_high_risk_devices()
        
        # 4. 安全建议
        result['security_recommendations'] = self._generate_security_recommendations(result)
        
        # 5. 统计汇总
        result['statistics_summary'] = self._generate_statistics_summary(result)
        
        # 6. 计算各服务类型的百分比
        total_devices = len(self.devices)
        if total_devices > 0:
            # 解析各服务类型的设备数量
            def extract_count(text):
                """从文本中提取设备数量"""
                if '没有设备' in text or '共检测到0台' in text:
                    return 0
                import re
                match = re.search(r'共检测到(\d+)台', text)
                return int(match.group(1)) if match else 0
            
            ftp_count = extract_count(result.get('p_ftp_devices_num', '0'))
            ssh_count = extract_count(result.get('p_ssh_devices_num', '0'))
            rdp_count = extract_count(result.get('p_rdp_devices_num', '0'))
            db_count = extract_count(result.get('p_db_devices_num', '0'))
            mqtt_count = extract_count(result.get('p_mqtt_devices_num', '0'))
            redarea_count = extract_count(result.get('p_redArea_devices_num', '0'))
            
            result['ftp_percentage'] = f"{ftp_count / total_devices * 100:.1f}%"
            result['ssh_percentage'] = f"{ssh_count / total_devices * 100:.1f}%"
            result['rdp_percentage'] = f"{rdp_count / total_devices * 100:.1f}%"
            result['db_percentage'] = f"{db_count / total_devices * 100:.1f}%"
            result['mqtt_percentage'] = f"{mqtt_count / total_devices * 100:.1f}%"
            result['redarea_percentage'] = f"{redarea_count / total_devices * 100:.1f}%"
        else:
            result['ftp_percentage'] = "0.0%"
            result['ssh_percentage'] = "0.0%"
            result['rdp_percentage'] = "0.0%"
            result['db_percentage'] = "0.0%"
            result['mqtt_percentage'] = "0.0%"
            result['redarea_percentage'] = "0.0%"
        
        return result

    def _analyze_redarea(self):
        """分析红区设备 - 保留原有逻辑"""
        for device in self.devices:
            try:
                ip = ip_address(device.ip)
                if any(ip in network for network in self.redarea_networks):
                    self.redarea_devices.append(device)
            except ValueError:
                continue

        self.logger.info(f"发现 {len(self.redarea_devices)} 台红区设备")
    
    def _calculate_risk_level(self, device_count: int) -> str:
        """计算风险等级"""
        if device_count == 0:
            return "低风险"
        elif device_count <= 10:
            return "中风险"
        elif device_count <= 50:
            return "高风险"
        else:
            return "极高风险"
    
    def _analyze_port_distribution(self) -> str:
        """分析端口分布情况"""
        port_counter = {}
        for device in self.devices:
            for port in device.ports:
                port_counter[port] = port_counter.get(port, 0) + 1
        
        if not port_counter:
            return "无端口数据"
        
        # 按出现次数排序
        sorted_ports = sorted(port_counter.items(), key=lambda x: x[1], reverse=True)
        
        lines = ["端口分布统计（按设备数量排序）："]
        for port, count in sorted_ports[:10]:  # 显示 top 10
            lines.append(f"  端口 {port}: {count} 台设备")
        
        return '\n'.join(lines)
    
    def _identify_high_risk_devices(self) -> str:
        """识别高风险设备（开放多个高危端口）"""
        high_risk = []
        for device in self.devices:
            if len(device.ports) >= 3:  # 开放 3 个及以上端口
                high_risk.append((device.ip, device.ports))
        
        if not high_risk:
            return "未发现高风险设备"
        
        # 按端口数量排序
        high_risk.sort(key=lambda x: len(x[1]), reverse=True)
        
        lines = [f"高风险设备列表（开放多个高危端口，共 {len(high_risk)} 台）："]
        for ip, ports in high_risk[:20]:  # 显示 top 20
            lines.append(f"  {ip}: {len(ports)} 个端口 - {', '.join(map(str, ports))}")
        
        if len(high_risk) > 20:
            lines.append(f"  ... 还有 {len(high_risk) - 20} 台高风险设备")
        
        return '\n'.join(lines)
    
    def _generate_security_recommendations(self, analysis_result: Dict[str, Any]) -> str:
        """生成安全建议"""
        recommendations = []
        device_count = analysis_result.get('total_devices_num', 0)
        
        if device_count == 0:
            return "本次扫描未发现高危端口，网络安全性良好。建议定期扫描以监控变化。"
        
        recommendations.append("安全整改建议：")
        recommendations.append("")
        
        # 根据检测到的服务类型给出建议
        ftp_num = analysis_result.get('p_ftp_devices_num', '')
        if '没有设备' not in ftp_num:
            recommendations.append("1. FTP 服务整改：")
            recommendations.append("   - 建议使用 SFTP 或 FTPS 替代明文 FTP")
            recommendations.append("   - 如无需使用，请关闭 21 端口")
            recommendations.append("")
        
        ssh_num = analysis_result.get('p_ssh_devices_num', '')
        if '没有设备' not in ssh_num:
            recommendations.append("2. SSH 服务整改：")
            recommendations.append("   - 建议禁用 root 登录，使用密钥认证")
            recommendations.append("   - 建议修改默认 22 端口")
            recommendations.append("   - 建议配置失败登录锁定策略")
            recommendations.append("")
        
        rdp_num = analysis_result.get('p_rdp_devices_num', '')
        if '没有设备' not in rdp_num:
            recommendations.append("3. RDP 服务整改：")
            recommendations.append("   - 建议启用网络级别认证 (NLA)")
            recommendations.append("   - 建议限制访问 IP 范围")
            recommendations.append("   - 建议修改默认 3389 端口")
            recommendations.append("")
        
        db_num = analysis_result.get('p_db_devices_num', '')
        if '没有设备' not in db_num:
            recommendations.append("4. 数据库服务整改：")
            recommendations.append("   - 建议禁止数据库端口对外暴露")
            recommendations.append("   - 建议使用强密码策略")
            recommendations.append("   - 建议定期更新数据库补丁")
            recommendations.append("")
        
        mqtt_num = analysis_result.get('p_mqtt_devices_num', '')
        if '没有设备' not in mqtt_num:
            recommendations.append("5. MQTT 服务整改：")
            recommendations.append("   - 建议启用 TLS 加密传输")
            recommendations.append("   - 建议配置访问控制列表 (ACL)")
            recommendations.append("")
        
        # 通用建议
        recommendations.append("6. 通用安全建议：")
        recommendations.append("   - 定期进行端口扫描和安全评估")
        recommendations.append("   - 建立端口开放审批流程")
        recommendations.append("   - 对不必要的端口立即关闭")
        recommendations.append("   - 部署入侵检测系统 (IDS)")
        recommendations.append("   - 定期审查和更新安全策略")
        
        return '\n'.join(recommendations)
    
    def _generate_statistics_summary(self, analysis_result: Dict[str, Any]) -> str:
        """生成统计汇总"""
        total = analysis_result.get('total_devices_num', 0)
        
        lines = ["扫描统计汇总：", ""]
        lines.append(f"总设备数: {total} 台")
        lines.append(f"风险等级: {analysis_result.get('risk_level', '未知')}")
        lines.append("")
        
        # 各类别统计
        categories = [
            ("FTP 服务", 'p_ftp_devices_num'),
            ("SSH 服务", 'p_ssh_devices_num'),
            ("RDP 服务", 'p_rdp_devices_num'),
            ("数据库服务", 'p_db_devices_num'),
            ("MQTT 服务", 'p_mqtt_devices_num'),
            ("红区设备", 'p_redArea_devices_num'),
        ]
        
        lines.append("分类统计：")
        for name, key in categories:
            value = analysis_result.get(key, '未知')
            # 提取数字
            if '没有设备' in value:
                count = 0
            else:
                # 从 "共检测到X台设备" 中提取 X
                import re
                match = re.search(r'(\d+)', value)
                count = int(match.group(1)) if match else 0
            
            percentage = (count / total * 100) if total > 0 else 0
            lines.append(f"  {name}: {count} 台 ({percentage:.1f}%)")
        
        return '\n'.join(lines)


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
        """生成报告"""
        try:
            # 构建概况文本
            overview_lines = [
                "本次网络高危端口扫描概况如下：",
                f"检测时间：{scan_data.get('scan_start_time', '')}",
                f"完成时间：{scan_data.get('scan_end_time', '')}",
                f"总耗时：{scan_data.get('scan_duration', '')}",
                "扫描目标：",
                f"    网段：",
            ]
            ip_range_text = scan_data.get('ip_range', '')
            for line in ip_range_text.split('\n'):
                overview_lines.append(f"    {line}")
            overview_lines.append("端口：")
            ports_text = scan_data.get('ports', '')
            # 端口按每行约40个字符换行显示
            if len(ports_text) > 50:
                port_list = ports_text.split(',')
                lines = []
                current = "    "
                for p in port_list:
                    if len(current) + len(p) + 1 > 55:
                        lines.append(current.rstrip(', '))
                        current = "    " + p + ", "
                    else:
                        current += p + ", "
                if current.strip():
                    lines.append(current.rstrip(', '))
                overview_lines.extend(lines)
            else:
                overview_lines.append(f"    {ports_text}")

            template_fields = {
                'report_date': time.strftime('%Y.%m.%d'),
                'scan_start_time': scan_data.get('scan_start_time', ''),
                'scan_end_time': scan_data.get('scan_end_time', ''),
                'scan_duration': scan_data.get('scan_duration', ''),
                'ip_range': scan_data.get('ip_range', ''),
                'ports': scan_data.get('ports', ''),
                'p_overview': '\n'.join(overview_lines),
                'p_summary': analysis_result.get('p_summary', ''),
                'p_conclusion': scan_data.get('conclusion', ''),
                # 新增科学统计字段
                'p_risk_level': analysis_result.get('risk_level', '未知'),
                'p_port_distribution': analysis_result.get('port_distribution', ''),
                'p_high_risk_devices': analysis_result.get('high_risk_devices', ''),
                'p_security_recommendations': analysis_result.get('security_recommendations', ''),
                'p_statistics_summary': analysis_result.get('statistics_summary', ''),
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
            f.write(f"风险等级: {fields.get('p_risk_level', '未知')}\n")
            f.write("\n" + "="*60 + "\n")
            f.write("详细统计\n")
            f.write("="*60 + "\n\n")

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

            if 'p_redArea_devices_num' in fields:
                f.write("\n【红区设备】\n")
                f.write(f"数量: {fields.get('p_redArea_devices_num', '未知')}\n")
                f.write(f"设备:\n{fields.get('p_redArea_devices_info', '无')}\n")
            
            # 新增：端口分布统计
            if fields.get('p_port_distribution'):
                f.write("\n" + "="*60 + "\n")
                f.write("端口分布统计\n")
                f.write("="*60 + "\n\n")
                f.write(f"{fields.get('p_port_distribution', '')}\n")
            
            # 新增：高风险设备
            if fields.get('p_high_risk_devices'):
                f.write("\n" + "="*60 + "\n")
                f.write("高风险设备\n")
                f.write("="*60 + "\n\n")
                f.write(f"{fields.get('p_high_risk_devices', '')}\n")
            
            # 新增：统计汇总
            if fields.get('p_statistics_summary'):
                f.write("\n" + "="*60 + "\n")
                f.write("统计汇总\n")
                f.write("="*60 + "\n\n")
                f.write(f"{fields.get('p_statistics_summary', '')}\n")
            
            # 新增：安全建议
            if fields.get('p_security_recommendations'):
                f.write("\n" + "="*60 + "\n")
                f.write("安全建议\n")
                f.write("="*60 + "\n\n")
                f.write(f"{fields.get('p_security_recommendations', '')}\n")

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
    """生成报告的便捷函数"""
    if logger is None:
        logger = logging.getLogger("Report")

    logger.info("开始生成扫描报告...")

    analyzer = ReportDataAnalyzer(logger)

    enable_redarea = False
    if redarea_file:
        enable_redarea = analyzer.load_redarea_networks(redarea_file)

    if not analyzer.load_scan_results(result_file):
        logger.error("无法加载扫描结果，报告生成失败")
        return False

    analysis_result = analyzer.analyze(enable_redarea=enable_redarea)

    generator = ReportGenerator(template_file, output_file, logger)
    success = generator.generate(scan_data, analysis_result)

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
    template_dir: str = "data/templates",
    redarea_file: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    db_manager: Optional[DatabaseManager] = None,
    record_id: Optional[int] = None
) -> bool:
    """使用数据库配置生成报告"""
    if logger is None:
        logger = logging.getLogger("Report")

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

# ==================== 多格式导出支持 ====================

def _build_export_data(scan_data: Dict[str, Any], analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """构建报告导出统一数据结构"""
    import re
    report = {
        'report_date': time.strftime('%Y.%m.%d'),
        'scan_start_time': scan_data.get('scan_start_time', ''),
        'scan_end_time': scan_data.get('scan_end_time', ''),
        'scan_duration': scan_data.get('scan_duration', ''),
        'ip_range': scan_data.get('ip_range', ''),
        'ports': scan_data.get('ports', ''),
        'total_devices': analysis_result.get('total_devices_num', 0),
        'risk_level': analysis_result.get('risk_level', ''),
    }

    categories = [
        ('ftp', 'FTP', 'p_ftp_devices_num', 'p_ftp_devices_info'),
        ('ssh', 'SSH', 'p_ssh_devices_num', 'p_ssh_devices_info'),
        ('rdp', 'RDP', 'p_rdp_devices_num', 'p_rdp_devices_info'),
        ('database', 'Database', 'p_db_devices_num', 'p_db_devices_info'),
        ('mqtt', 'MQTT', 'p_mqtt_devices_num', 'p_mqtt_devices_info'),
        ('redarea', 'RedArea', 'p_redArea_devices_num', 'p_redArea_devices_info'),
    ]
    report['categories'] = []
    for key, name, num_key, info_key in categories:
        num_text = analysis_result.get(num_key, '0')
        info_text = analysis_result.get(info_key, '')
        match = re.search(r'(\d+)', str(num_text)) if num_text else None
        count = int(match.group(1)) if match else 0
        ips = [line.strip() for line in info_text.strip().split('\n') if line.strip()] if info_text else []
        report['categories'].append({
            'key': key, 'name': name, 'count': count, 'ips': ips
        })

    report['port_distribution'] = analysis_result.get('port_distribution', '')
    report['high_risk_devices'] = analysis_result.get('high_risk_devices', '')
    report['security_recommendations'] = analysis_result.get('security_recommendations', '')
    report['statistics_summary'] = analysis_result.get('statistics_summary', '')
    return report


def generate_csv_report(
    scan_data: Dict[str, Any],
    analysis_result: Dict[str, Any],
    output_file: str,
    logger: Optional[logging.Logger] = None
) -> bool:
    """生成 CSV 格式报告"""
    import csv
    if logger is None:
        logger = logging.getLogger("Report")
    try:
        export = _build_export_data(scan_data, analysis_result)
        csv_file = output_file.replace('.docx', '.csv')
        with open(csv_file, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['报告日期', '扫描开始', '扫描结束', '扫描用时', '设备总数', '风险等级'])
            writer.writerow([
                export['report_date'], export['scan_start_time'], export['scan_end_time'],
                export['scan_duration'], export['total_devices'], export['risk_level']
            ])
            writer.writerow([])
            writer.writerow(['类别', '设备数量', '占比(%)', '设备IP列表'])
            total = export['total_devices'] or 1
            for cat in export['categories']:
                pct = round(cat['count'] / total * 100, 1) if total > 0 else 0
                writer.writerow([cat['name'], cat['count'], pct, '; '.join(cat['ips'][:20])])
        logger.info(f"CSV 报告已保存: {csv_file}")
        return True
    except Exception as e:
        logger.error(f"生成 CSV 报告失败: {e}")
        return False


def generate_json_report(
    scan_data: Dict[str, Any],
    analysis_result: Dict[str, Any],
    output_file: str,
    logger: Optional[logging.Logger] = None
) -> bool:
    """生成 JSON 格式报告"""
    if logger is None:
        logger = logging.getLogger("Report")
    try:
        export = _build_export_data(scan_data, analysis_result)
        json_file = output_file.replace('.docx', '.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(export, f, ensure_ascii=False, indent=2)
        logger.info(f"JSON 报告已保存: {json_file}")
        return True
    except Exception as e:
        logger.error(f"生成 JSON 报告失败: {e}")
        return False


def generate_html_report(
    scan_data: Dict[str, Any],
    analysis_result: Dict[str, Any],
    output_file: str,
    logger: Optional[logging.Logger] = None
) -> bool:
    """生成 HTML 格式报告"""
    if logger is None:
        logger = logging.getLogger("Report")
    try:
        export = _build_export_data(scan_data, analysis_result)
        html_file = output_file.replace('.docx', '.html')

        total = export['total_devices'] or 1

        cats_html = ''
        for cat in export['categories']:
            pct = round(cat['count'] / total * 100, 1) if total > 0 else 0
            cat_color = '#e6a23c' if cat['count'] > 0 else '#909399'
            cats_html += f'''
            <tr>
                <td>{cat['name']}</td>
                <td style="color:{cat_color};font-weight:600">{cat['count']}</td>
                <td>{pct}%</td>
                <td style="font-size:12px;max-width:400px;word-break:break-all">{
                    ', '.join(cat['ips'][:15])}{'...' if len(cat['ips']) > 15 else ''}</td>
            </tr>'''

        risk_colors = {'低风险': '#67c23a', '中风险': '#e6a23c', '高风险': '#f56c6c', '极高风险': '#f56c6c'}
        risk_color = risk_colors.get(export['risk_level'], '#909399')

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>网络端口扫描报告 - {export['report_date']}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 24px; background: #f5f7fa; color: #303133; }}
.container {{ max-width: 960px; margin: 0 auto; }}
.header {{ background: linear-gradient(135deg, #409eff, #337ecc); color: #fff; padding: 32px; border-radius: 12px; margin-bottom: 24px; }}
.header h1 {{ margin: 0 0 8px; font-size: 24px; }}
.header .meta {{ font-size: 13px; opacity: 0.85; }}
.card {{ background: #fff; border-radius: 10px; padding: 24px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }}
.card h2 {{ margin: 0 0 16px; font-size: 17px; color: #303133; border-bottom: 2px solid #409eff; padding-bottom: 8px; }}
.stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px; }}
.stat-item {{ background: #ecf5ff; border-radius: 8px; padding: 16px; text-align: center; }}
.stat-value {{ font-size: 28px; font-weight: 700; color: #409eff; }}
.stat-label {{ font-size: 12px; color: #909399; margin-top: 4px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #ebeef5; }}
th {{ background: #f5f7fa; font-weight: 600; color: #606266; }}
.footer {{ text-align: center; color: #c0c4cc; font-size: 12px; margin-top: 32px; padding: 16px; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
    <h1>网络端口扫描报告</h1>
    <div class="meta">报告日期: {export['report_date']} | 扫描时间: {export['scan_start_time']} ~ {export['scan_end_time']} | 用时: {export['scan_duration']}</div>
</div>

<div class="card">
    <h2>扫描概览</h2>
    <div class="stats-grid">
        <div class="stat-item"><div class="stat-value">{export['total_devices']}</div><div class="stat-label">发现设备</div></div>
        <div class="stat-item"><div class="stat-value" style="color:{risk_color}">{export['risk_level']}</div><div class="stat-label">风险等级</div></div>
        <div class="stat-item"><div class="stat-value">{len(export['categories'])}</div><div class="stat-label">服务类别</div></div>
    </div>
    <p style="font-size:13px;color:#606266">扫描网段: {export['ip_range']}</p>
    <p style="font-size:13px;color:#606266">扫描端口: {export['ports']}</p>
</div>

<div class="card">
    <h2>分类统计</h2>
    <table>
        <thead><tr><th>服务类型</th><th>设备数量</th><th>占比</th><th>受影响设备</th></tr></thead>
        <tbody>{cats_html}</tbody>
    </table>
</div>

<div class="card">
    <h2>安全建议</h2>
    <pre style="white-space:pre-wrap;font-size:13px;line-height:1.8;color:#606266;font-family:inherit;">{export['security_recommendations']}</pre>
</div>

<div class="card">
    <h2>统计汇总</h2>
    <pre style="white-space:pre-wrap;font-size:13px;line-height:1.6;color:#606266;font-family:'Courier New',monospace;">{export['statistics_summary']}</pre>
</div>

<div class="footer">由 ScanScript 自动生成 | {export['report_date']}</div>
</div>
</body>
</html>'''
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html)
        logger.info(f"HTML 报告已保存: {html_file}")
        return True
    except Exception as e:
        logger.error(f"生成 HTML 报告失败: {e}")
        return False
