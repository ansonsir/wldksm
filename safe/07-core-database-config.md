# 安全审计报告 - 数据库与配置安全

## 文件: core/database.py

### 漏洞 1: SQLite 数据库文件可被直接下载

- **漏洞类型**: 敏感信息泄露
- **严重程度**: 高危
- **行号**: 数据库文件路径配置

- **问题描述**: 
  SQLite 数据库文件 (`scan_data.db`) 位于项目根目录。如果 Web 服务器配置不当或存在路径穿越漏洞，攻击者可能直接下载数据库文件，获取所有用户凭据（bcrypt 哈希）、扫描记录、SMTP 配置等信息。

- **修复建议**:
  1. 将数据库文件移出 Web 可访问目录:
  ```python
  # core/database.py
  import os
  
  class DatabaseManager:
      def __init__(self, db_path: str = None):
          if db_path is None:
              # 数据库存储在非 Web 可访问目录
              base_dir = Path(__file__).parent.parent
              data_dir = base_dir / 'data'
              data_dir.mkdir(parents=True, exist_ok=True)
              self.db_path = data_dir / 'scan_data.db'
          # ...
  ```
  
  2. 设置严格的数据库文件权限:
  ```python
  if os.name == 'posix':
      os.chmod(self.db_path, 0o600)  # 仅所有者可读写
  ```

### 漏洞 2: 部分查询未使用参数化

- **漏洞类型**: SQL 注入
- **严重程度**: 中危
- **行号**: 需全局检查 `execute(f"...")` 或 `execute("..." + var + "...")`

- **问题描述**: 
  虽然大多数查询使用了参数化 `(?, ?, ...)`, 但需要确认是否有遗漏。特别需要检查动态表名、列名或 `ORDER BY` 子句。

- **修复建议**:
  ```bash
  # 排查所有可能存在 SQL 注入的位置
  grep -rn "execute(f\"" core/database.py
  grep -rn "execute.*%" core/database.py
  grep -rn "\+.*execute" core/database.py
  ```
  
  对于必须使用动态列名的情况，使用白名单验证:
  ```python
  ALLOWED_SORT_COLUMNS = {'id', 'created_at', 'scan_status', 'total_hosts'}
  ALLOWED_SORT_DIRECTIONS = {'ASC', 'DESC'}
  
  def get_scan_records_sorted(self, sort_by: str = 'id', order: str = 'ASC'):
      if sort_by not in ALLOWED_SORT_COLUMNS:
          raise ValueError(f"无效的排序字段: {sort_by}")
      if order.upper() not in ALLOWED_SORT_DIRECTIONS:
          raise ValueError(f"无效的排序方向: {order}")
      
      # 现在可以安全地使用 f-string
      query = f"SELECT * FROM scan_records ORDER BY {sort_by} {order}"
      cursor.execute(query)
  ```

---

## 文件: core/config.py

### 漏洞 3: YAML 配置文件中的敏感信息

- **漏洞类型**: 硬编码凭证 / 敏感信息泄露
- **严重程度**: 中危
- **行号**: YAML 中的 SMTP 密码字段

- **问题描述**: 
  SMTP 密码存储在 YAML 配置文件中 (`data/config.yaml`)。YAML 文件通常会被提交到版本控制（尽管项目有 `.gitignore`，但不可依赖），且任何能读取文件系统的人都可以获取 SMTP 密码。

- **修复建议**:
  ```python
  # core/config.py - 支持环境变量覆盖
  import os
  
  class ConfigManager:
      def get_config(self):
          config = self._load_from_yaml()
          
          # 环境变量覆盖（敏感字段）
          config.smtp_password = os.environ.get(
              'SMTP_PASSWORD', 
              config.smtp_password
          )
          config.jwt_secret = os.environ.get(
              'JWT_SECRET',
              config.jwt_secret
          )
          
          return config
      
      def save_to_yaml(self):
          """保存配置时排除敏感字段"""
          config = self._load_from_yaml()
          # 不保存密码到 YAML（由环境变量管理）
          config.smtp_password = ''
          self._write_yaml(config)
  ```

### 漏洞 4: 配置文件路径硬编码

- **漏洞类型**: 任意文件读取（低风险）
- **严重程度**: 低危
- **行号**: 配置中的文件路径字段

- **问题描述**: 
  配置中的文件路径字段（如 `ip_range_file`, `exclude_ips_file`）可能被用户配置为系统敏感文件路径（如 `/etc/passwd`），当系统读取这些文件时可能导致信息泄露。虽然已在 `core/utils.py` 中实现了路径穿越防护，但路径本身应被限制在项目目录下。

- **修复建议**:
  ```python
  # core/config.py
  def _validate_path(self, path_str: str, field_name: str) -> Path:
      """验证配置文件路径在项目目录下"""
      project_root = Path(__file__).parent.parent
      path = Path(path_str)
      
      if not path.is_absolute():
          path = project_root / path
      
      # 确保标准化路径后在项目目录下
      try:
          path.resolve().relative_to(project_root.resolve())
      except ValueError:
          raise ConfigError(
              f"配置字段 '{field_name}' 指向项目目录外的路径: {path_str}"
          )
      
      return path
  ```

---

## 文件: web/mail_service.py

### 漏洞 5: SMTP 密码明文存储在数据库

- **漏洞类型**: 敏感信息泄露
- **严重程度**: 中危
- **行号**: 第 64-80 行 (`save_to_db`), 第 47-62 行 (`_load_from_db`)

- **问题描述**: 
  邮件配置（包括 SMTP 密码）以明文形式存储在 SQLite 数据库的 `email_settings` 表中。任何能访问数据库的人都可以读取 SMTP 密码。建议至少使用可逆加密存储。

- **修复建议**:
  ```python
  from cryptography.fernet import Fernet
  import os
  
  class ReportMailer:
      # 加密密钥应从环境变量获取，或使用固定密钥文件
      _cipher = None
      
      @classmethod
      def _get_cipher(cls):
          if cls._cipher is None:
              key = os.environ.get('MAIL_ENCRYPTION_KEY')
              if not key:
                  key_file = Path(__file__).parent.parent / 'data' / '.mail_key'
                  if key_file.exists():
                      key = key_file.read_text().strip()
                  else:
                      key = Fernet.generate_key().decode()
                      key_file.parent.mkdir(parents=True, exist_ok=True)
                      key_file.write_text(key)
                      key_file.chmod(0o600)
              cls._cipher = Fernet(key.encode() if isinstance(key, str) else key)
          return cls._cipher
      
      def _encrypt_password(self, password: str) -> str:
          if not password:
              return ''
          return self._get_cipher().encrypt(password.encode()).decode()
      
      def _decrypt_password(self, encrypted: str) -> str:
          if not encrypted:
              return ''
          return self._get_cipher().decrypt(encrypted.encode()).decode()
      
      def save_to_db(self, config: MailConfig) -> bool:
          settings = EmailSettings(
              smtp_server=config.smtp_server,
              smtp_port=config.smtp_port,
              smtp_user=config.smtp_user,
              smtp_password=self._encrypt_password(config.smtp_password),  # 加密
              # ...
          )
          # ...
      
      def _load_from_db(self):
          settings = self.db.get_email_settings()
          if settings:
              self.config = MailConfig(
                  # ...
                  smtp_password=self._decrypt_password(settings.smtp_password),  # 解密
                  # ...
              )
  ```

  **依赖安装**: `pip install cryptography`
