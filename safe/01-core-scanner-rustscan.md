# 安全审计报告 - 命令注入漏洞

## 文件: core/rustscan.py

### 漏洞 1: 命令注入 - RustScan 命令拼接

- **漏洞类型**: 命令注入
- **严重程度**: 严重
- **行号**: 第 147-165 行 (`_build_command` 方法)

- **问题描述**: 
  `_build_command` 方法使用 f-string 直接将用户可控的 IP 地址、端口列表拼接到系统命令中。攻击者如果能够控制 IP 地址或端口参数，可以在其中注入任意 Shell 命令。虽然 IP 地址和端口通常由管理员通过配置文件或 API 传入，但如果配置文件被篡改或 API 参数未经过滤，攻击者可以执行任意系统命令，获得服务器 Shell 权限。

- **问题代码**:
  ```python
  def _build_command(self, ips: List[str], ports: List[int], **kwargs) -> str:
      # ...
      ip_arg = ','.join(ips) if len(ips) > 1 else ips[0]
      ports_arg = ','.join(str(p) for p in ports)
      
      cmd = (
          f"{self.rustscan_path} "
          f"-a {ip_arg} "
          f"-p {ports_arg} "
          # ...
      )
  ```

- **修复建议**:
  1. **IP 地址验证**: 在传入 RustScan 之前使用 `ipaddress` 模块严格验证每个 IP 是否为合法 IPv4 地址:
  ```python
  from ipaddress import ip_address, IPv4Address
  import shlex
  
  def _sanitize_ip(ip: str) -> str:
      """验证并清理 IP 地址"""
      try:
          addr = ip_address(ip.strip())
          if not isinstance(addr, IPv4Address):
              raise ValueError(f"仅支持 IPv4: {ip}")
          return str(addr)
      except ValueError:
          raise ValueError(f"无效的 IP 地址: {ip}")
  
  def _build_command(self, ips: List[str], ports: List[int], **kwargs) -> List[str]:
      """使用列表参数构建命令，避免 Shell 注入"""
      # 验证所有 IP
      sanitized_ips = [self._sanitize_ip(ip) for ip in ips]
      
      # 验证所有端口
      for port in ports:
          if not (1 <= port <= 65535):
              raise ValueError(f"无效端口号: {port}")
      
      # 构建安全的命令参数列表
      cmd = [
          str(self.rustscan_path),
          "-a", ','.join(sanitized_ips),
          "-p", ','.join(str(p) for p in ports),
          "-b", str(kwargs.get('batch_size', 5000)),
          "--ulimit", str(kwargs.get('ulimit', 5000)),
          "-t", str(kwargs.get('timeout', 700)),
      ]
      return cmd
  ```
  
  2. **使用列表参数调用 subprocess**: 在 `_execute` 方法中使用 `subprocess.Popen(cmd_list, shell=False)`:
  ```python
  def _execute(self, cmd_list: List[str], **kwargs):
      """安全执行命令"""
      process = subprocess.Popen(
          cmd_list,
          stdout=subprocess.PIPE,
          stderr=subprocess.PIPE,
          shell=False,  # 关键: 不使用 Shell
          text=True,
          start_new_session=True,
      )
      return process
  ```

---

### 漏洞 2: 进程组权限过高

- **漏洞类型**: 权限提升风险
- **严重程度**: 中危
- **行号**: `_execute` 方法中 `start_new_session=True` 的使用

- **问题描述**: 
  RustScan 以子进程方式运行。如果 RustScan 本身存在漏洞或被替换为恶意程序，攻击者可以通过 RustScan 进程获得与 Web 服务相同的权限。当前代码未对 RustScan 进程的权限进行限制。

- **修复建议**:
  1. 确保 Web 服务以最低权限用户运行（非 root）
  2. 对 RustScan 二进制文件进行完整性校验（SHA256）
  3. 使用 `resource` 模块限制子进程资源使用:
  ```python
  import resource
  
  def _set_process_limits():
      """限制子进程资源"""
      resource.setrlimit(resource.RLIMIT_CPU, (3600, 3600))  # 最多1小时
      resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 * 1024 * 1024, -1))  # 最多2GB内存
  
  # 在 Popen 中使用 preexec_fn
  process = subprocess.Popen(
      cmd_list,
      shell=False,
      start_new_session=True,
      preexec_fn=_set_process_limits,
  )
  ```

---

## 文件: core/scanner.py

### 漏洞 3: 扫描参数未充分验证

- **漏洞类型**: 输入验证不足
- **严重程度**: 中危
- **行号**: `scan_all_ranges` 方法

- **问题描述**: 
  `ScanOrchestrator.scan_all_ranges()` 接收用户传入的 IP 范围、端口和排除列表，虽然内部使用了 `parse_ip_range` 和 `parse_ports` 进行解析，但如果这些解析函数存在边界情况（如极大端口号、异常 IP 格式），可能导致 RustScan 行为异常或拒绝服务。

- **修复建议**:
  ```python
  def scan_all_ranges(self, ip_ranges, ports, exclude_ips, callback=None):
      """执行扫描 - 增加参数上限校验"""
      MAX_IP_RANGES = 10000
      MAX_PORTS = 65535
      
      if len(ip_ranges) > MAX_IP_RANGES:
          raise ValueError(f"IP 范围数量超过上限 ({MAX_IP_RANGES})")
      
      # 解析并验证
      parsed_ranges = parse_ip_range(ip_ranges)
      parsed_ports = parse_ports(ports)
      
      if len(parsed_ports) > MAX_PORTS:
          raise ValueError(f"端口数量超过上限 ({MAX_PORTS})")
      
      # 继续执行...
  ```
