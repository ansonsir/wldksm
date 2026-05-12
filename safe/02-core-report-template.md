# 安全审计报告 - 代码执行与文件上传

## 文件: core/report.py

### 漏洞 1: ast.literal_eval 代码执行风险

- **漏洞类型**: 代码执行（反序列化）
- **严重程度**: 高危
- **行号**: 第 158 行

- **问题描述**: 
  `_parse_result_line` 方法使用 `ast.literal_eval(ports_str)` 解析扫描结果文件中的端口列表。虽然 `ast.literal_eval` 比 `eval()` 安全，但它仍然可以解析复杂的数据结构，包括大数字、元组、字典等。如果扫描结果文件被恶意篡改（例如包含超大嵌套结构），可能导致内存耗尽（DoS）或解析异常。此外，`ast.literal_eval` 在某些 Python 版本中存在已知的绕过漏洞。

- **问题代码**:
  ```python
  def _parse_result_line(self, line: str) -> Optional[DeviceInfo]:
      # ...
      try:
          if ports_str.startswith('[') and ports_str.endswith(']'):
              ports = ast.literal_eval(ports_str)  # <-- 风险点
          else:
              ports = [int(p.strip()) for p in ports_str.split(',') if p.strip()]
      except (ValueError, SyntaxError) as e:
          # ...
  ```

- **修复建议**:
  ```python
  import json
  import re
  
  def _parse_result_line(self, line: str) -> Optional[DeviceInfo]:
      """解析单行扫描结果 - 安全版本"""
      parts = line.split()
      if len(parts) < 2:
          return None
      
      ip = parts[0].strip()
      
      # 严格验证 IP 格式
      if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
          self.logger.warning(f"无效的 IP 地址格式: {ip}")
          return None
      
      try:
          ip_address(ip)
      except ValueError:
          self.logger.warning(f"无效的 IP 地址: {ip}")
          return None
      
      ports_str = parts[1].strip() if len(parts) > 1 else ""
      
      try:
          # 使用安全的 JSON 解析替代 ast.literal_eval
          # 或者仅支持简单的逗号分隔格式
          if ports_str.startswith('[') and ports_str.endswith(']'):
              # JSON 解析（需要扫描结果输出 JSON 格式）
              ports_data = json.loads(ports_str)
              if not isinstance(ports_data, list):
                  return None
              ports = []
              for p in ports_data:
                  if not isinstance(p, int) or not (1 <= p <= 65535):
                      continue
                  ports.append(p)
          else:
              ports = []
              for p in ports_str.split(','):
                  p = p.strip()
                  if not p:
                      continue
                  port_num = int(p)
                  if not (1 <= port_num <= 65535):
                      continue
                  ports.append(port_num)
          
          if not ports:
              return None
          
          return DeviceInfo(ip=ip, ports=ports)
      
      except (ValueError, json.JSONDecodeError) as e:
          self.logger.warning(f"无法解析端口数据: {ports_str} - {e}")
          return None
  ```

---

## 文件: core/template_manager.py

### 漏洞 2: 模板文件上传 - 仅检查扩展名

- **漏洞类型**: 文件上传漏洞
- **严重程度**: 高危
- **行号**: 第 142-199 行 (`validate_template` 方法)

- **问题描述**: 
  `validate_template` 方法仅检查文件扩展名是否为 `.docx`（第 151 行），未验证文件的实际 MIME 类型和内容。攻击者可以上传一个扩展名为 `.docx` 的恶意文件（如嵌入宏病毒的 DOCX、带有 XML External Entity (XXE) 攻击的 OOXML 文件），当模板被渲染时可能导致信息泄露或服务器端请求伪造。

- **问题代码**:
  ```python
  def validate_template(self, template_path: str, check_content: bool = True) -> ValidationResult:
      # ...
      if path.suffix.lower() != '.docx':
          result.add_error(f"模板必须是 .docx 格式: {path.suffix}")
          return result
      # 仅检查文件大小，未检查实际内容
      file_size = path.stat().st_size
      # ...
  ```

- **修复建议**:
  ```python
  import zipfile
  from defusedxml import ElementTree as SafeElementTree
  
  def validate_template(self, template_path: str, check_content: bool = True) -> ValidationResult:
      """验证模板文件 - 安全增强版"""
      result = ValidationResult()
      path = Path(template_path)
      
      if not path.exists():
          result.add_error(f"模板文件不存在: {template_path}")
          return result
      
      # 1. 检查扩展名
      if path.suffix.lower() != '.docx':
          result.add_error(f"模板必须是 .docx 格式: {path.suffix}")
          return result
      
      # 2. 验证文件魔术字节（ZIP 文件头: PK\x03\x04）
      with open(path, 'rb') as f:
          magic = f.read(4)
          if magic != b'PK\x03\x04':
              result.add_error("文件不是有效的 OOXML/ZIP 格式")
              return result
      
      # 3. 验证 ZIP 结构完整性
      try:
          with zipfile.ZipFile(str(path), 'r') as zf:
              # 检查是否包含预期的 OOXML 文件
              required_files = ['[Content_Types].xml', 'word/document.xml']
              for req in required_files:
                  if req not in zf.namelist():
                      result.add_warning(f"缺少预期文件: {req}")
              
              # 拒绝包含宏的文档 (.docm)
              for name in zf.namelist():
                  if name.lower().endswith('.bin') and 'vba' in name.lower():
                      result.add_error("拒绝包含 VBA 宏的文档")
                      return result
              
              # 检查文件大小（解压后总大小）
              total_size = sum(info.file_size for info in zf.infolist())
              if total_size > 100 * 1024 * 1024:  # 100MB 上限
                  result.add_error("模板文件过大（解压后超过100MB）")
                  return result
      except zipfile.BadZipFile:
          result.add_error("文件不是有效的 ZIP 格式")
          return result
      
      # 4. 安全解析 XML（防止 XXE/Billion Laughs 攻击）
      try:
          with zipfile.ZipFile(str(path), 'r') as zf:
              xml_content = zf.read('word/document.xml')
              # 使用 defusedxml 安全解析
              SafeElementTree.fromstring(xml_content)
      except Exception as e:
          result.add_error(f"XML 解析失败（可能存在恶意内容）: {e}")
          return result
      
      # ... 继续原有的字段验证逻辑
  ```

  **依赖安装**: `pip install defusedxml`

---

## 文件: web/routes/report_routes.py

### 漏洞 3: 模板上传接口缺少认证和内容校验

- **漏洞类型**: 文件上传漏洞 + 越权
- **严重程度**: 严重
- **行号**: 第 218-245 行 (`upload_template`)

- **问题描述**: 
  `/api/templates/upload` 接口**缺少 `@require_auth` 装饰器**，任何未认证用户都可以上传模板文件。虽然检查了 `.docx` 扩展名，但未验证文件内容。结合 `template_manager.py` 中 `validate_template` 的不足，攻击者可以上传恶意 DOCX 文件到服务器。

- **问题代码**:
  ```python
  @report_bp.route('/api/templates/upload', methods=['POST'])
  # 缺少 @require_auth !!!
  def upload_template():
      """上传模板文件"""
      # ...
      if not file.filename.endswith('.docx'):
          return jsonify({'success': False, 'message': '只支持 .docx 文件'}), 400
      
      save_path = template_dir / file.filename
      file.save(str(save_path))  # 直接保存
  ```

- **修复建议**:
  ```python
  import uuid
  import magic  # python-magic
  
  @report_bp.route('/api/templates/upload', methods=['POST'])
  @require_auth  # 添加认证要求
  def upload_template():
      """上传模板文件"""
      if 'file' not in request.files:
          return jsonify({'success': False, 'message': '没有文件'}), 400
      
      file = request.files['file']
      if file.filename == '':
          return jsonify({'success': False, 'message': '文件名为空'}), 400
      
      # 1. 检查扩展名
      if not file.filename.lower().endswith('.docx'):
          return jsonify({'success': False, 'message': '只支持 .docx 文件'}), 400
      
      # 2. 读取文件头验证 MIME 类型
      file_content = file.read(512)
      file.seek(0)
      
      mime = magic.from_buffer(file_content, mime=True)
      if mime not in ('application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                      'application/zip'):
          return jsonify({'success': False, 'message': '文件类型不匹配'}), 400
      
      # 3. 使用安全文件名（防止路径穿越）
      safe_filename = f"{uuid.uuid4().hex}_{Path(file.filename).name}"
      safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', safe_filename)
      
      template_dir = project_root / "data" / "templates"
      template_dir.mkdir(parents=True, exist_ok=True)
      
      save_path = template_dir / safe_filename
      file.save(str(save_path))
      # ...
  ```

  **依赖安装**: `pip install python-magic`
