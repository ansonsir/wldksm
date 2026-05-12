"""
模板管理模块
提供模板验证、预览、管理功能
"""
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass
from datetime import datetime

try:
    from docxtpl import DocxTemplate
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

from database import DatabaseManager, ReportTemplate


# 必需的模板字段
REQUIRED_FIELDS = [
    'report_date',
    'scan_start_time',
    'scan_end_time',
    'scan_duration',
    'ip_range',
    'ports',
    'total_devices_num',
    'p_ftp_devices_num',
    'p_ssh_devices_num',
    'p_rdp_devices_num',
    'p_db_devices_num',
    'p_mqtt_devices_num',
    'p_ftp_devices_info',
    'p_ssh_devices_info',
    'p_rdp_devices_info',
    'p_db_devices_info',
    'p_mqtt_devices_info',
]

# 可选字段（红区扫描使用）
OPTIONAL_FIELDS = [
    'p_redArea_devices_num',
    'p_redArea_devices_info',
]

# 示例数据用于模板预览
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
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    missing_fields: List[str]
    found_fields: List[str]
    
    def __init__(self):
        self.is_valid = True
        self.errors = []
        self.warnings = []
        self.missing_fields = []
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
    
    def __init__(self, template_dir: str = "templates", 
                 db_manager: Optional[DatabaseManager] = None,
                 logger: Optional[logging.Logger] = None):
        self.template_dir = Path(template_dir)
        self.template_dir.mkdir(exist_ok=True)
        self.db = db_manager
        self.logger = logger or logging.getLogger("TemplateManager")
        
        if not DOCX_AVAILABLE:
            self.logger.warning("未安装 docxtpl 库，模板功能受限")
    
    def list_templates(self) -> List[Dict]:
        """列出所有可用模板"""
        templates = []
        
        # 从数据库获取
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
        
        # 从文件系统获取
        if self.template_dir.exists():
            for file_path in self.template_dir.glob("*.docx"):
                # 检查是否已在数据库中
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
        """
        验证模板文件
        
        :param template_path: 模板文件路径
        :param check_content: 是否检查模板内容
        :return: 验证结果
        """
        result = ValidationResult()
        path = Path(template_path)
        
        # 1. 文件存在性检查
        if not path.exists():
            result.add_error(f"模板文件不存在: {template_path}")
            return result
        
        # 2. 文件扩展名检查
        if path.suffix.lower() != '.docx':
            result.add_error(f"模板必须是 .docx 格式: {path.suffix}")
            return result
        
        # 3. 文件大小检查
        file_size = path.stat().st_size
        if file_size == 0:
            result.add_error("模板文件为空")
            return result
        if file_size > 50 * 1024 * 1024:  # 50MB
            result.add_warning("模板文件过大，可能影响性能")
        
        if not DOCX_AVAILABLE or not check_content:
            return result
        
        # 4. 模板内容检查
        try:
            # 尝试加载模板
            docx = DocxTemplate(str(path))
            
            # 提取模板中的字段
            template_fields = self._extract_template_fields(docx)
            result.found_fields = list(template_fields)
            
            # 检查必需字段
            for field in REQUIRED_FIELDS:
                if field in template_fields:
                    template_fields.remove(field)
                else:
                    result.missing_fields.append(field)
            
            # 检查可选字段
            optional_found = []
            for field in OPTIONAL_FIELDS:
                if field in template_fields:
                    template_fields.remove(field)
                    optional_found.append(field)
            
            # 未知字段警告
            if template_fields:
                result.add_warning(f"模板包含未知字段: {', '.join(template_fields)}")
            
            # 评估结果
            if result.missing_fields:
                result.add_error(f"缺少必需字段: {', '.join(result.missing_fields)}")
            
            if optional_found:
                result.add_warning(f"发现可选字段（红区扫描用）: {', '.join(optional_found)}")
            
            # 5. 尝试渲染测试
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
            # 获取模板中的 jinja2 变量
            xml = docx.get_xml()
            
            # 匹配 {{ variable }} 或 {{ variable.attribute }}
            pattern = r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
            matches = re.findall(pattern, xml)
            fields.update(matches)
            
            # 匹配 {% for item in variable %}
            pattern = r'{%\s*for\s+\w+\s+in\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*%}'
            matches = re.findall(pattern, xml)
            fields.update(matches)
            
        except Exception as e:
            self.logger.error(f"提取模板字段失败: {e}")
        
        return fields
    
    def preview_template(self, template_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        生成模板预览
        
        :param template_path: 模板文件路径
        :param output_path: 预览文件输出路径（可选）
        :return: 预览文件路径
        """
        if not DOCX_AVAILABLE:
            self.logger.error("未安装 docxtpl，无法生成预览")
            return None
        
        path = Path(template_path)
        if not path.exists():
            self.logger.error(f"模板文件不存在: {template_path}")
            return None
        
        try:
            # 生成预览文件路径
            if output_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = self.template_dir / f"preview_{path.stem}_{timestamp}.docx"
            else:
                output_path = Path(output_path)
            
            # 渲染预览
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
        """
        添加模板到管理系统
        
        :param template_path: 模板文件路径
        :param name: 模板名称（可选，默认使用文件名）
        :param area_id: 关联的区域ID
        :param description: 模板描述
        :return: (是否成功, 消息)
        """
        source_path = Path(template_path)
        
        # 验证模板
        validation = self.validate_template(str(source_path))
        if not validation.is_valid:
            return False, f"模板验证失败:\n{validation}"
        
        # 确定模板名称
        template_name = name or source_path.stem
        
        # 复制到模板目录
        dest_path = self.template_dir / f"{template_name}.docx"
        
        try:
            import shutil
            shutil.copy2(str(source_path), str(dest_path))
            
            # 添加到数据库
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
    
    def remove_template(self, template_name: str) -> bool:
        """移除模板"""
        try:
            # 从数据库中禁用
            if self.db:
                template = self.db.get_template_by_name(template_name)
                if template:
                    self.db.update_template_status(template.id, False)
            
            # 删除文件
            template_path = self.template_dir / f"{template_name}.docx"
            if template_path.exists():
                template_path.unlink()
            
            return True
        except Exception as e:
            self.logger.error(f"移除模板失败: {e}")
            return False
    
    def get_template_for_area(self, area_name: str) -> Optional[str]:
        """
        获取指定区域的推荐模板
        
        :param area_name: 区域名称
        :return: 模板文件路径
        """
        if not self.db:
            # 默认模板
            default_path = self.template_dir / "default.docx"
            if default_path.exists():
                return str(default_path)
            return None
        
        # 从数据库查询
        area = self.db.get_scan_area_by_name(area_name)
        if area:
            templates = self.db.get_templates(area_id=area.id, active_only=True)
            if templates:
                return templates[0].template_path
        
        # 返回默认模板
        templates = self.db.get_templates(active_only=True)
        if templates:
            return templates[0].template_path
        
        return None
    
    def compare_templates(self, template_path1: str, template_path2: str) -> Dict:
        """
        比较两个模板的差异
        
        :param template_path1: 模板1路径
        :param template_path2: 模板2路径
        :return: 差异信息
        """
        result = {
            'template1': template_path1,
            'template2': template_path2,
            'fields1': [],
            'fields2': [],
            'common_fields': [],
            'only_in_1': [],
            'only_in_2': [],
        }
        
        if not DOCX_AVAILABLE:
            result['error'] = "未安装 docxtpl，无法比较"
            return result
        
        try:
            # 提取字段
            docx1 = DocxTemplate(template_path1)
            docx2 = DocxTemplate(template_path2)
            
            fields1 = self._extract_template_fields(docx1)
            fields2 = self._extract_template_fields(docx2)
            
            result['fields1'] = sorted(fields1)
            result['fields2'] = sorted(fields2)
            result['common_fields'] = sorted(fields1 & fields2)
            result['only_in_1'] = sorted(fields1 - fields2)
            result['only_in_2'] = sorted(fields2 - fields1)
            
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def generate_template_doc(self, output_path: str = "template_guide.txt"):
        """生成模板字段说明文档"""
        lines = [
            "=" * 60,
            "扫描报告模板字段说明",
            "=" * 60,
            "",
            "【必需字段】",
            "这些字段必须在模板中使用：",
            "",
        ]
        
        for field in REQUIRED_FIELDS:
            description = self._get_field_description(field)
            lines.append(f"  {{% raw %}}{{{{{field}}}}}{{% endraw %}} - {description}")
        
        lines.extend([
            "",
            "【可选字段】",
            "这些字段用于红区扫描报告：",
            "",
        ])
        
        for field in OPTIONAL_FIELDS:
            description = self._get_field_description(field)
            lines.append(f"  {{% raw %}}{{{{{field}}}}}{{% endraw %}} - {description}")
        
        lines.extend([
            "",
            "=" * 60,
            "使用示例",
            "=" * 60,
            "",
            "在 Word 模板中，使用双大括号包裹字段名：",
            "  例如：扫描日期：{{ report_date }}",
            "",
            "支持简单的条件判断：",
            "  {% raw %}{% if total_devices_num > 0 %}{% endraw %}",
            "    发现 {{ total_devices_num }} 台设备",
            "  {% raw %}{% else %}{% endraw %}",
            "    未发现设备",
            "  {% raw %}{% endif %}{% endraw %}",
            "",
        ])
        
        content = '\n'.join(lines)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return output_path
    
    def _get_field_description(self, field: str) -> str:
        """获取字段描述"""
        descriptions = {
            'report_date': '报告日期（格式：YYYY.MM.DD）',
            'scan_start_time': '扫描开始时间',
            'scan_end_time': '扫描结束时间',
            'scan_duration': '扫描用时（如：30分钟）',
            'ip_range': '扫描的IP范围',
            'ports': '扫描的端口',
            'total_devices_num': '发现设备总数',
            'p_ftp_devices_num': 'FTP服务设备数量',
            'p_ssh_devices_num': 'SSH服务设备数量',
            'p_rdp_devices_num': 'RDP服务设备数量',
            'p_db_devices_num': '数据库服务设备数量',
            'p_mqtt_devices_num': 'MQTT服务设备数量',
            'p_ftp_devices_info': 'FTP服务设备列表',
            'p_ssh_devices_info': 'SSH服务设备列表',
            'p_rdp_devices_info': 'RDP服务设备列表',
            'p_db_devices_info': '数据库服务设备列表',
            'p_mqtt_devices_info': 'MQTT服务设备列表',
            'p_redArea_devices_num': '红区设备数量（红区扫描用）',
            'p_redArea_devices_info': '红区设备列表（红区扫描用）',
        }
        return descriptions.get(field, '未知字段')


# 便捷函数
def quick_validate(template_path: str) -> bool:
    """快速验证模板"""
    manager = TemplateManager()
    result = manager.validate_template(template_path)
    print(result)
    return result.is_valid


def quick_preview(template_path: str, output_path: Optional[str] = None) -> Optional[str]:
    """快速生成预览"""
    manager = TemplateManager()
    return manager.preview_template(template_path, output_path)
