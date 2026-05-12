"""
模板管理模块
基于 Version2 优化
"""
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass
from datetime import datetime

# XXE防护：在导入docxtpl之前用defusedxml安全替换stdlib XML解析器
try:
    import defusedxml
    defusedxml.defuse_stdlib()
    DOCX_XML_SAFE = True
except ImportError:
    DOCX_XML_SAFE = False

try:
    from docxtpl import DocxTemplate
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

from core.database import DatabaseManager, ReportTemplate


REQUIRED_FIELDS = [
    'report_date', 'scan_start_time', 'scan_end_time', 'scan_duration',
    'ip_range', 'ports', 'total_devices_num',
    'p_ftp_devices_num', 'p_ssh_devices_num', 'p_rdp_devices_num',
    'p_db_devices_num', 'p_mqtt_devices_num',
    'p_ftp_devices_info', 'p_ssh_devices_info', 'p_rdp_devices_info',
    'p_db_devices_info', 'p_mqtt_devices_info',
]

OPTIONAL_FIELDS = [
    'p_redArea_devices_num', 'p_redArea_devices_info',
]

PREVIEW_DATA = {
    'report_date': '2024.01.15',
    'scan_start_time': '2024-01-15 09:00:00',
    'scan_end_time': '2024-01-15 09:30:00',
    'scan_duration': '30分钟',
    'ip_range': '10.0.0.0/24\n192.168.1.0/24',
    'ports': '22,80,443,3389,3306',
    'total_devices_num': 5,
    'p_ftp_devices_num': '共检测到1台设备',
    'p_ssh_devices_num': '共检测到3台设备',
    'p_rdp_devices_num': '共检测到2台设备',
    'p_db_devices_num': '共检测到1台设备',
    'p_mqtt_devices_num': '没有设备',
    'p_ftp_devices_info': '10.0.0.5\n',
    'p_ssh_devices_info': '10.0.0.1\n10.0.0.2\n10.0.0.3\n',
    'p_rdp_devices_info': '10.0.0.2\n10.0.0.4\n',
    'p_db_devices_info': '10.0.0.3\n',
    'p_mqtt_devices_info': '没有设备\n',
    'p_redArea_devices_num': '共检测到1台设备',
    'p_redArea_devices_info': '10.0.0.1 [22, 80, 443]',
}


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool = True
    errors: List[str] = None
    warnings: List[str] = None
    missing_fields: List[str] = None
    found_fields: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.missing_fields is None:
            self.missing_fields = []
        if self.found_fields is None:
            self.found_fields = []

    def add_error(self, message: str):
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str):
        self.warnings.append(message)

    def __str__(self) -> str:
        lines = [f"验证结果: {'通过' if self.is_valid else '失败'}"]
        if self.errors:
            lines.append("错误:")
            lines.extend(f"  - {e}" for e in self.errors)
        if self.warnings:
            lines.append("警告:")
            lines.extend(f"  - {w}" for w in self.warnings)
        if self.missing_fields:
            lines.append(f"缺失字段: {', '.join(self.missing_fields)}")
        if self.found_fields:
            lines.append(f"发现字段: {', '.join(self.found_fields)}")
        return '\n'.join(lines)


class TemplateManager:
    """模板管理器"""

    def __init__(self, template_dir: str = "data/templates",
                 db_manager: Optional[DatabaseManager] = None,
                 logger: Optional[logging.Logger] = None):
        self.template_dir = Path(template_dir)
        self.template_dir.mkdir(exist_ok=True)
        self.db = db_manager
        self.logger = logger or logging.getLogger("TemplateManager")

        if not DOCX_AVAILABLE:
            self.logger.warning("未安装 docxtpl 库，模板功能受限")
        if not DOCX_XML_SAFE:
            self.logger.warning("未安装 defusedxml 库，XML解析缺少XXE防护")

    def list_templates(self) -> List[Dict]:
        """列出所有可用模板"""
        templates = []

        if self.db:
            db_templates = self.db.get_templates(active_only=True)
            for t in db_templates:
                templates.append({
                    'id': t.id,
                    'name': t.template_name,
                    'path': t.template_path,
                    'description': t.description,
                    'source': 'database'
                })

        if self.template_dir.exists():
            for file_path in self.template_dir.glob("*.docx"):
                existing = [t for t in templates if Path(t['path']).name == file_path.name]
                if not existing:
                    templates.append({
                        'id': None,
                        'name': file_path.stem,
                        'path': str(file_path),
                        'description': '文件系统模板',
                        'source': 'filesystem'
                    })

        return templates

    def validate_template(self, template_path: str, check_content: bool = True) -> ValidationResult:
        """验证模板文件"""
        result = ValidationResult()
        path = Path(template_path)

        if not path.exists():
            result.add_error(f"模板文件不存在: {template_path}")
            return result

        if path.suffix.lower() != '.docx':
            result.add_error(f"模板必须是 .docx 格式: {path.suffix}")
            return result

        file_size = path.stat().st_size
        if file_size == 0:
            result.add_error("模板文件为空")
            return result
        if file_size > 50 * 1024 * 1024:
            result.add_warning("模板文件过大，可能影响性能")

        if not DOCX_AVAILABLE or not check_content:
            return result

        try:
            docx = DocxTemplate(str(path))
            template_fields = self._extract_template_fields(docx)
            result.found_fields = list(template_fields)

            for field in REQUIRED_FIELDS:
                if field in template_fields:
                    template_fields.remove(field)
                else:
                    result.missing_fields.append(field)

            optional_found = []
            for field in OPTIONAL_FIELDS:
                if field in template_fields:
                    template_fields.remove(field)
                    optional_found.append(field)

            if template_fields:
                result.add_warning(f"模板包含未知字段: {', '.join(template_fields)}")

            if result.missing_fields:
                result.add_error(f"缺少必需字段: {', '.join(result.missing_fields)}")

            if optional_found:
                result.add_warning(f"发现可选字段（红区扫描用）: {', '.join(optional_found)}")

            try:
                docx.render(PREVIEW_DATA)
            except Exception as e:
                result.add_error(f"模板渲染测试失败: {e}")

        except Exception as e:
            result.add_error(f"无法解析模板文件: {e}")

        return result

    def _extract_template_fields(self, docx: 'DocxTemplate') -> Set[str]:
        """提取模板中的所有字段"""
        fields = set()
        try:
            xml = docx.get_xml()
            pattern = r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
            matches = re.findall(pattern, xml)
            fields.update(matches)
            pattern = r'{%\s*for\s+\w+\s+in\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*%}'
            matches = re.findall(pattern, xml)
            fields.update(matches)
        except Exception as e:
            self.logger.error(f"提取模板字段失败: {e}")
        return fields

    def preview_template(self, template_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """生成模板预览"""
        if not DOCX_AVAILABLE:
            self.logger.error("未安装 docxtpl，无法生成预览")
            return None

        path = Path(template_path)
        if not path.exists():
            self.logger.error(f"模板文件不存在: {template_path}")
            return None

        try:
            if output_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = self.template_dir / f"preview_{path.stem}_{timestamp}.docx"
            else:
                output_path = Path(output_path)

            docx = DocxTemplate(str(path))
            docx.render(PREVIEW_DATA)
            docx.save(str(output_path))

            self.logger.info(f"预览文件已生成: {output_path}")
            return str(output_path)

        except Exception as e:
            self.logger.error(f"生成预览失败: {e}")
            return None

    def add_template(self, template_path: str, name: Optional[str] = None,
                     area_id: Optional[int] = None, description: str = "") -> Tuple[bool, str]:
        """添加模板到管理系统"""
        source_path = Path(template_path)

        validation = self.validate_template(str(source_path))
        if not validation.is_valid:
            return False, f"模板验证失败:\n{validation}"

        template_name = name or source_path.stem
        dest_path = self.template_dir / f"{template_name}.docx"

        try:
            import shutil
            shutil.copy2(str(source_path), str(dest_path))

            if self.db:
                template = ReportTemplate(
                    template_name=template_name,
                    template_path=str(dest_path),
                    area_id=area_id,
                    description=description,
                    is_active=True
                )
                template_id = self.db.add_template(template)
                return True, f"模板已添加: {dest_path} (ID: {template_id})"
            else:
                return True, f"模板已复制到: {dest_path}"

        except Exception as e:
            return False, f"添加模板失败: {e}"

    def get_template_for_area(self, area_name: str) -> Optional[str]:
        """获取指定区域的推荐模板"""
        # 优先使用优化模板
        optimized_template = self.template_dir / 'optimized_v2.docx'
        if optimized_template.exists():
            self.logger.info(f"使用优化模板: {optimized_template}")
            return str(optimized_template)
        
        # 优先从数据库查找
        if self.db:
            area = self.db.get_scan_area_by_name(area_name)
            if area:
                templates = self.db.get_templates(area_id=area.id, active_only=True)
                if templates:
                    return templates[0].template_path

            templates = self.db.get_templates(active_only=True)
            if templates:
                return templates[0].template_path

        # 数据库无记录时回退到文件系统默认模板
        default_path = self.template_dir / "default.docx"
        if default_path.exists():
            return str(default_path)

        # 尝试目录下任意 .docx 模板
        if self.template_dir.exists():
            for file_path in self.template_dir.glob("*.docx"):
                return str(file_path)

        return None
