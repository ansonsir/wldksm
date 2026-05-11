"""
生成优化的报告模板
创建更科学、更清晰、更易懂的 Word 报告模板
"""
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml
from pathlib import Path

def set_cell_shading(cell, color):
    """设置单元格背景色"""
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)

def set_cell_border(cell, **kwargs):
    """设置单元格边框"""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = parse_xml(f'<w:tcBorders {nsdecls("w")}></w:tcBorders>')
    for edge, val in kwargs.items():
        element = parse_xml(
            f'<w:{edge} {nsdecls("w")} w:val="{val.get("val", "single")}" '
            f'w:sz="{val.get("sz", "4")}" w:space="0" '
            f'w:color="{val.get("color", "000000")}"/>'
        )
        tcBorders.append(element)
    tcPr.append(tcBorders)

def create_optimized_template(output_path: str):
    """创建优化的报告模板"""
    doc = Document()
    
    # 设置默认字体
    style = doc.styles['Normal']
    font = style.font
    font.name = '微软雅黑'
    font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    
    # 设置页边距
    for section in doc.sections:
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(3.18)
        section.right_margin = Cm(3.18)
    
    # === 标题 ===
    title = doc.add_heading('网络高危端口扫描报告', level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        run.font.color.rgb = RGBColor(0, 51, 102)
        run.font.size = Pt(26)
        run.font.name = '微软雅黑'
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    
    # 报告日期
    date_para = doc.add_paragraph()
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_run = date_para.add_run('报告日期：{{ report_date }}')
    date_run.font.size = Pt(12)
    date_run.font.color.rgb = RGBColor(102, 102, 102)
    
    doc.add_paragraph()  # 空行
    
    # === 第一部分：扫描概况 ===
    h1 = doc.add_heading('一、扫描概况', level=1)
    for run in h1.runs:
        run.font.color.rgb = RGBColor(0, 51, 102)
        run.font.size = Pt(16)
    
    # 概况表格 - 前4行使用2列布局
    overview_table = doc.add_table(rows=6, cols=2)
    overview_table.style = 'Table Grid'
    overview_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    
    # 前4行：基本信息（2列）
    basic_info = [
        ('扫描开始时间', '{{ scan_start_time }}'),
        ('扫描完成时间', '{{ scan_end_time }}'),
        ('扫描总耗时', '{{ scan_duration }}'),
        ('风险等级', '{{ p_risk_level }}'),
    ]
    
    for i, (label, value) in enumerate(basic_info):
        # 标签列
        label_cell = overview_table.rows[i].cells[0]
        label_cell.text = ''
        p = label_cell.paragraphs[0]
        run = p.add_run(label)
        run.bold = True
        run.font.size = Pt(10.5)
        run.font.color.rgb = RGBColor(0, 51, 102)
        set_cell_shading(label_cell, 'E8F4FC')
        label_cell.width = Cm(3.5)
        
        # 值列
        value_cell = overview_table.rows[i].cells[1]
        value_cell.text = ''
        p = value_cell.paragraphs[0]
        run = p.add_run(value)
        run.font.size = Pt(10.5)
        value_cell.width = Cm(12.5)
    
    # 第5行：扫描网段（合并单元格）
    label_cell = overview_table.rows[4].cells[0]
    label_cell.text = ''
    p = label_cell.paragraphs[0]
    run = p.add_run('扫描网段')
    run.bold = True
    run.font.size = Pt(10.5)
    run.font.color.rgb = RGBColor(0, 51, 102)
    set_cell_shading(label_cell, 'E8F4FC')
    
    # 合并第5行的两个单元格
    overview_table.rows[4].cells[0].merge(overview_table.rows[4].cells[1])
    value_cell = overview_table.rows[4].cells[0]
    # 在标签后添加内容
    p = value_cell.paragraphs[0]
    run = p.add_run('    {{ ip_range }}')
    run.font.size = Pt(10.5)
    
    # 第6行：扫描端口（合并单元格）
    label_cell = overview_table.rows[5].cells[0]
    label_cell.text = ''
    p = label_cell.paragraphs[0]
    run = p.add_run('扫描端口')
    run.bold = True
    run.font.size = Pt(10.5)
    run.font.color.rgb = RGBColor(0, 51, 102)
    set_cell_shading(label_cell, 'E8F4FC')
    
    # 合并第6行的两个单元格
    overview_table.rows[5].cells[0].merge(overview_table.rows[5].cells[1])
    value_cell = overview_table.rows[5].cells[0]
    # 在标签后添加内容
    p = value_cell.paragraphs[0]
    run = p.add_run('    {{ ports }}')
    run.font.size = Pt(10.5)
    
    doc.add_paragraph()  # 空行
    
    # === 第二部分：扫描结果摘要 ===
    h2 = doc.add_heading('二、扫描结果摘要', level=1)
    for run in h2.runs:
        run.font.color.rgb = RGBColor(0, 51, 102)
        run.font.size = Pt(16)
    
    # 摘要说明
    summary_intro = doc.add_paragraph()
    run = summary_intro.add_run('本次扫描共检测到 ')
    run.font.size = Pt(10.5)
    run = summary_intro.add_run('{{ total_devices_num }}')
    run.bold = True
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(204, 0, 0)
    run = summary_intro.add_run(' 台设备开放了高危端口，具体分类统计如下：')
    run.font.size = Pt(10.5)
    
    doc.add_paragraph()  # 空行
    
    # 服务分类统计表格
    h2_1 = doc.add_heading('2.1 服务分类统计', level=2)
    for run in h2_1.runs:
        run.font.color.rgb = RGBColor(0, 51, 102)
        run.font.size = Pt(14)
    
    category_table = doc.add_table(rows=7, cols=3)
    category_table.style = 'Table Grid'
    category_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    
    # 表头
    headers = ['服务类型', '设备数量', '占比']
    for i, header in enumerate(headers):
        cell = category_table.rows[0].cells[i]
        cell.text = ''
        p = cell.paragraphs[0]
        run = p.add_run(header)
        run.bold = True
        run.font.size = Pt(11)
        run.font.color.rgb = RGBColor(255, 255, 255)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_cell_shading(cell, '003366')
    
    # 数据行
    category_data = [
        ('FTP 服务', '{{ p_ftp_devices_num }}', '{{ ftp_percentage }}'),
        ('SSH 服务', '{{ p_ssh_devices_num }}', '{{ ssh_percentage }}'),
        ('RDP 服务', '{{ p_rdp_devices_num }}', '{{ rdp_percentage }}'),
        ('数据库服务', '{{ p_db_devices_num }}', '{{ db_percentage }}'),
        ('MQTT 服务', '{{ p_mqtt_devices_num }}', '{{ mqtt_percentage }}'),
        ('红区设备', '{{ p_redArea_devices_num }}', '{{ redarea_percentage }}'),
    ]
    
    for i, (service, count, percentage) in enumerate(category_data):
        row = category_table.rows[i + 1]
        for j, value in enumerate([service, count, percentage]):
            cell = row.cells[j]
            cell.text = ''
            p = cell.paragraphs[0]
            run = p.add_run(value)
            run.font.size = Pt(10.5)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if j > 0 else WD_ALIGN_PARAGRAPH.LEFT
            if i % 2 == 1:
                set_cell_shading(cell, 'F5F5F5')
    
    doc.add_paragraph()  # 空行
    
    # === 第三部分：详细统计信息 ===
    h3 = doc.add_heading('三、详细统计信息', level=1)
    for run in h3.runs:
        run.font.color.rgb = RGBColor(0, 51, 102)
        run.font.size = Pt(16)
    
    # 统一的服务统计表
    service_table = doc.add_table(rows=1, cols=3)
    service_table.style = 'Table Grid'
    service_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    
    # 表头
    headers = ['服务类型（端口）', '设备数量', '设备列表']
    for i, header in enumerate(headers):
        cell = service_table.rows[0].cells[i]
        cell.text = ''
        p = cell.paragraphs[0]
        run = p.add_run(header)
        run.bold = True
        run.font.size = Pt(11)
        run.font.color.rgb = RGBColor(255, 255, 255)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_cell_shading(cell, '003366')
    
    # 添加各服务类型数据行
    services = [
        ('FTP 服务（端口 21）', '{{ p_ftp_devices_num }}', '{{ p_ftp_devices_info }}'),
        ('SSH 服务（端口 22）', '{{ p_ssh_devices_num }}', '{{ p_ssh_devices_info }}'),
        ('RDP 服务（端口 3389）', '{{ p_rdp_devices_num }}', '{{ p_rdp_devices_info }}'),
        ('数据库服务（端口 1433/1521/3306/5432/6379 等）', '{{ p_db_devices_num }}', '{{ p_db_devices_info }}'),
        ('MQTT 服务（端口 1883/5672/8161 等）', '{{ p_mqtt_devices_num }}', '{{ p_mqtt_devices_info }}'),
        ('红区设备', '{{ p_redArea_devices_num }}', '{{ p_redArea_devices_info }}'),
    ]
    
    for idx, (service_type, count, devices) in enumerate(services):
        row = service_table.add_row()
        # 服务类型列
        row.cells[0].text = ''
        p = row.cells[0].paragraphs[0]
        run = p.add_run(service_type)
        run.font.size = Pt(10.5)
        run.bold = True
        # 设备数量列
        row.cells[1].text = ''
        p = row.cells[1].paragraphs[0]
        run = p.add_run(count)
        run.font.size = Pt(10.5)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        # 设备列表列
        row.cells[2].text = ''
        p = row.cells[2].paragraphs[0]
        run = p.add_run(devices)
        run.font.size = Pt(10.5)
        
        # 交替行背景色
        if idx % 2 == 1:
            for cell in row.cells:
                set_cell_shading(cell, 'F5F5F5')
    
    doc.add_paragraph()  # 空行
    
    # === 第四部分：端口分布统计 ===
    h4 = doc.add_heading('四、端口分布统计', level=1)
    for run in h4.runs:
        run.font.color.rgb = RGBColor(0, 51, 102)
        run.font.size = Pt(16)
    
    # 端口分布统计 - 使用文本段落，但格式化为类似表格的样式
    p = doc.add_paragraph()
    run = p.add_run('{{ p_port_distribution }}')
    run.font.size = Pt(10.5)
    
    doc.add_paragraph()  # 空行
    
    # === 第五部分：高风险设备 ===
    h5 = doc.add_heading('五、高风险设备', level=1)
    for run in h5.runs:
        run.font.color.rgb = RGBColor(0, 51, 102)
        run.font.size = Pt(16)
    
    # 高风险设备 - 使用文本段落，但格式化为类似表格的样式
    p = doc.add_paragraph()
    run = p.add_run('{{ p_high_risk_devices }}')
    run.font.size = Pt(10.5)
    
    # 保存模板
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    print(f"✅ 优化模板已保存: {output_path}")

if __name__ == '__main__':
    template_path = '/home/yinsongkai/Desktop/杨其顶-work/Code-yang/ScanScript/data/templates/optimized_v2.docx'
    create_optimized_template(template_path)
