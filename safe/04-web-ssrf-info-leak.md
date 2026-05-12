# 安全审计报告 - SSRF 与敏感信息泄露

## 文件: web/webhook_service.py

### 漏洞 1: SSRF - Webhook URL 未验证

- **漏洞类型**: SSRF（服务端请求伪造）
- **严重程度**: 高危
- **行号**: 第 83-175 行（`_send_to_platform` 及其子方法）

- **问题描述**: 
  `_send_dingtalk`、`_send_wecom`、`_send_feishu` 方法直接使用用户配置的 `webhook_url` 发起 HTTP 请求 (`requests.post(url, ...)`)，未对 URL 进行任何验证。攻击者可以:
  1. 将 webhook URL 设置为内网地址（如 `http://127.0.0.1:6379/`），探测内网服务
  2. 利用服务器作为代理访问内部系统
  3. 通过 DNS rebinding 绕过简单的主机名检查

- **问题代码**:
  ```python
  def _send_dingtalk(self, config: WebhookConfig, scan_info: Dict) -> Tuple[bool, str]:
      url = config.webhook_url
      # ... 未验证 URL，直接请求
      resp = requests.post(url, json=payload, timeout=10)
  ```

- **修复建议**:
  ```python
  from urllib.parse import urlparse
  import ipaddress
  
  # 内网地址范围
  PRIVATE_NETWORKS = [
      ipaddress.ip_network('10.0.0.0/8'),
      ipaddress.ip_network('172.16.0.0/12'),
      ipaddress.ip_network('192.168.0.0/16'),
      ipaddress.ip_network('127.0.0.0/8'),
      ipaddress.ip_network('169.254.0.0/16'),
      ipaddress.ip_network('0.0.0.0/8'),
  ]
  
  # 允许的外部域名白名单
  ALLOWED_WEBHOOK_DOMAINS = {
      'dingtalk': ['oapi.dingtalk.com'],
      'wecom': ['qyapi.weixin.qq.com'],
      'feishu': ['open.feishu.cn'],
  }
  
  def _validate_webhook_url(platform: str, url: str) -> Tuple[bool, str]:
      """验证 Webhook URL 安全性"""
      try:
          parsed = urlparse(url)
          
          # 1. 必须使用 HTTPS
          if parsed.scheme != 'https':
              return False, "Webhook URL 必须使用 HTTPS"
          
          # 2. 解析主机名
          hostname = parsed.hostname
          if not hostname:
              return False, "无效的 URL 主机名"
          
          # 3. 检查是否为 IP 地址（拒绝内网 IP）
          try:
              ip = ipaddress.ip_address(hostname)
              for network in PRIVATE_NETWORKS:
                  if ip in network:
                      return False, f"拒绝内网地址: {hostname}"
              # 允许公网 IP
              return True, ""
          except ValueError:
              pass  # 不是 IP，继续域名检查
          
          # 4. 检查域名白名单
          if platform in ALLOWED_WEBHOOK_DOMAINS:
              allowed = ALLOWED_WEBHOOK_DOMAINS[platform]
              if not any(hostname == d or hostname.endswith('.' + d) for d in allowed):
                  return False, f"域名不在白名单中: {hostname}"
          
          return True, ""
      except Exception as e:
          return False, f"URL 验证失败: {e}"
  
  def _send_dingtalk(self, config: WebhookConfig, scan_info: Dict) -> Tuple[bool, str]:
      """发送钉钉机器人消息 - 安全增强版"""
      # 1. 验证 URL
      valid, error = _validate_webhook_url('dingtalk', config.webhook_url)
      if not valid:
          return False, f"Webhook URL 验证失败: {error}"
      
      url = config.webhook_url
      # 2. 签名处理 (HMAC-SHA256)
      if config.secret:
          timestamp = str(round(time.time() * 1000))
          sign = self._dingtalk_sign(timestamp, config.secret)
          url = f"{url}&timestamp={timestamp}&sign={sign}"
      
      # 3. 使用 session 控制连接
      session = requests.Session()
      session.mount('https://', requests.adapters.HTTPAdapter(
          max_retries=1,
          pool_connections=1,
          pool_maxsize=1
      ))
      
      try:
          resp = session.post(
              url, json=payload, timeout=10,
              allow_redirects=False  # 禁止重定向（防 SSRF 重定向绕过）
          )
          # ...
      finally:
          session.close()
  ```

---

## 文件: web/app.py

### 漏洞 2: 默认管理员密码明文输出到控制台

- **漏洞类型**: 敏感信息泄露
- **严重程度**: 中危
- **行号**: 第 93-97 行

- **问题描述**: 
  `_init_default_admin` 函数在首次创建管理员账户时，将随机生成的密码**明文打印到终端控制台**。如果日志被收集（如 Docker logs、systemd journal），密码将以明文形式持久存储。任何有权限查看日志的人都可以获取管理员密码。

- **问题代码**:
  ```python
  def _init_default_admin(db_manager, auth_service):
      admin = db_manager.get_user_by_username('admin')
      if not admin:
          password = ''.join(secrets.choice('...') for _ in range(12))
          # ...
          print("\n" + "="*70)
          print("【首次启动】默认管理员账户已创建")
          print(f"用户名: admin")
          print(f"密码: {password}")  # <-- 明文密码输出
          print("请立即登录并修改密码！")
  ```

- **修复建议**:
  ```python
  def _init_default_admin(db_manager, auth_service):
      """创建默认管理员账户（如果不存在）"""
      admin = db_manager.get_user_by_username('admin')
      if not admin:
          import secrets
          password = ''.join(secrets.choice(
              'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*'
          ) for _ in range(12))
          password_hash = auth_service.hash_password(password)
          db_manager.create_user(
              username='admin',
              password_hash=password_hash,
              email='admin@localhost',
              is_admin=True
          )
          
          # 安全方式：输出到单独文件，仅首次启动时可见
          credential_file = Path(__file__).parent.parent / 'data' / '.admin_initial_credentials'
          credential_file.parent.mkdir(parents=True, exist_ok=True)
          credential_file.write_text(
              f"Username: admin\nPassword: {password}\n"
              f"IMPORTANT: Login and change password immediately, then delete this file.\n"
          )
          credential_file.chmod(0o600)  # 仅文件所有者可读写
          
          import logging
          logger = logging.getLogger(__name__)
          logger.warning(
              "="*70 + "\n"
              "【首次启动】默认管理员账户已创建\n"
              "用户名: admin\n"
              f"初始凭据已保存至: {credential_file}\n"
              "请立即登录并修改密码，随后删除该凭据文件！\n"
              "="*70
          )
          # 使用 logging 而非 print，可配置日志不记录敏感信息
  ```

---

## 文件: web/routes/config_routes.py

### 漏洞 3: SMTP 密码返回前端

- **漏洞类型**: 敏感信息泄露
- **严重程度**: 高危
- **行号**: 第 163-176 行（`get_mail_config`）

- **问题描述**: 
  `GET /api/mail/config` 接口在响应中**包含 SMTP 密码明文** (`smtp_password`)。虽然接口有 `@require_auth` 保护，但如果攻击者通过 XSS 或其他方式获取了有效的 JWT Token，就可以直接读取 SMTP 密码。前端不应获取密码字段。

- **问题代码**:
  ```python
  @config_bp.route('/api/mail/config', methods=['GET'])
  @require_auth
  def get_mail_config():
      # ...
      return jsonify({
          'success': True,
          'data': {
              'smtp_server': settings.smtp_server,
              'smtp_port': settings.smtp_port,
              'smtp_user': settings.smtp_user,
              'smtp_password': settings.smtp_password,  # <-- 密码泄露
              # ...
          }
      })
  ```

- **修复建议**:
  ```python
  @config_bp.route('/api/mail/config', methods=['GET'])
  @require_auth
  def get_mail_config():
      try:
          _, db_manager, _ = _get_services()
          settings = db_manager.get_email_settings()
          if settings:
              return jsonify({
                  'success': True,
                  'data': {
                      'smtp_server': settings.smtp_server,
                      'smtp_port': settings.smtp_port,
                      'smtp_user': settings.smtp_user,
                      # 不返回密码，前端显示为 ******
                      'smtp_password': '********' if settings.smtp_password else '',
                      'smtp_ssl': bool(settings.smtp_ssl),
                      'skip_login': bool(settings.skip_login),
                      'default_sender': settings.default_sender,
                      'default_recipients': settings.default_recipients,
                  }
              })
          return jsonify({'success': True, 'data': {}})
      except Exception as e:
          return jsonify({'success': False, 'message': str(e)}), 500
  ```
  
  同时在 `POST /api/mail/config` 中处理密码更新:
  ```python
  @config_bp.route('/api/mail/config', methods=['POST'])
  @require_auth
  def save_mail_config():
      try:
          _, _, mailer = _get_services()
          data = request.get_json()
          
          # 如果密码字段是 '********'，表示未修改，保留原密码
          smtp_password = data.get('smtp_password', '')
          if smtp_password == '********':
              # 从数据库获取当前密码
              current_settings = mailer.db.get_email_settings()
              smtp_password = current_settings.smtp_password if current_settings else ''
          
          config = MailConfig(
              smtp_server=data.get('smtp_server', ''),
              smtp_port=data.get('smtp_port', 587),
              smtp_user=data.get('smtp_user', ''),
              smtp_password=smtp_password,
              # ...
          )
          # ...
  ```

---

## 文件: web/app.py

### 漏洞 4: CORS 配置过于宽松

- **漏洞类型**: CORS 配置不当
- **严重程度**: 中危
- **行号**: 第 34 行

- **问题描述**: 
  `CORS(app)` 使用默认配置，允许所有来源（`*`）进行跨域请求。虽然该工具是内网运维系统，但过度宽松的 CORS 结合内网其他恶意页面可能被利用进行跨域攻击。

- **修复建议**:
  ```python
  CORS(app, resources={
      r"/api/*": {
          "origins": ["http://localhost:5000", "http://127.0.0.1:5000"],
          "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
          "allow_headers": ["Content-Type", "Authorization"],
          "expose_headers": ["Content-Disposition"],
          "max_age": 3600,
      }
  })
  ```
