# 安全审计报告 - 速率限制与 CSRF

## 文件: web/api/auth_api.py

### 漏洞 1: 登录接口缺少 IP 级别速率限制

- **漏洞类型**: 暴力破解
- **严重程度**: 高危
- **行号**: 第 39-112 行 (`/api/auth/login`)

- **问题描述**: 
  登录接口虽然有账户锁定机制（5次失败锁定30分钟），但攻击者可以使用不同的用户名进行**用户名枚举攻击**（通过不同响应判断用户是否存在），或对已知用户进行**分布式暴力破解**（切换IP绕过IP级别限制）。
  
  当前代码中 `ip_address` 一直为 `"unknown"`（第318行），实际未记录登录 IP，使 IP 级别防御失效。

- **问题代码**:
  ```python
  def authenticate(self, username: str, password: str, 
                   captcha_id: str, captcha_code: str) -> Dict:
      ip_address = "unknown"  # 由API层传入  <-- 始终为"unknown"
      user_agent = "unknown"
      # ...
  ```

- **修复建议**:
  ```python
  from web.rate_limit import limiter
  
  @auth_bp.route('/login', methods=['POST'])
  @limiter.limit("5 per minute")  # 每个IP每分钟最多5次
  def login():
      try:
          auth_service = _auth_service()
          data = request.get_json()
          # ...
          
          # 正确获取客户端 IP
          ip_address = request.headers.get('X-Forwarded-For', request.remote_addr) or "unknown"
          ip_address = ip_address.split(',')[0].strip()  # 取第一个 IP
          user_agent = request.headers.get('User-Agent', 'unknown')
          
          result = auth_service.authenticate(
              username, password, captcha_id, captcha_code,
              ip_address=ip_address,  # 传入实际 IP
              user_agent=user_agent
          )
  ```
  
  同时修改 `auth_service.authenticate` 方法签名:
  ```python
  def authenticate(self, username: str, password: str, 
                  captcha_id: str, captcha_code: str,
                  ip_address: str = "unknown",
                  user_agent: str = "unknown") -> Dict:
  ```

---

## 文件: web/services/auth_service.py

### 漏洞 2: 验证码存储在内存中，可能被耗尽

- **漏洞类型**: 拒绝服务 (DoS)
- **严重程度**: 中危
- **行号**: 第 34 行 (`_captcha_store`)

- **问题描述**: 
  验证码存储在进程内存中（`_captcha_store` 字典）。攻击者可以频繁请求 `/api/auth/captcha` 生成大量验证码（每次生成会存储到字典中），耗尽服务器内存。虽然 `_cleanup_captcha` 会清理过期验证码，但攻击者可以在短时间内生成大量验证码导致 OOM。

- **修复建议**:
  1. 对验证码生成接口也添加速率限制:
  ```python
  @auth_bp.route('/captcha', methods=['POST'])
  @limiter.limit("10 per minute")  # 限制验证码请求频率
  def get_captcha():
  ```
  
  2. 添加验证码数量上限:
  ```python
  MAX_CAPTCHA_COUNT = 100
  
  def generate_captcha(self) -> Tuple[str, str]:
      # 清理过期验证码
      self._cleanup_captcha()
      
      # 检查数量上限
      if len(_captcha_store) >= MAX_CAPTCHA_COUNT:
          # 删除最老的验证码
          oldest_id = min(_captcha_store.keys(), 
                         key=lambda k: _captcha_store[k]['expires'])
          del _captcha_store[oldest_id]
      
      # ... 继续生成
  ```

---

## 文件: web/app.py 和 web/frontend

### 漏洞 3: 缺少 CSRF 保护

- **漏洞类型**: CSRF（跨站请求伪造）
- **严重程度**: 中危
- **行号**: Web 应用整体

- **问题描述**: 
  当前系统使用 JWT Bearer Token 进行认证（Token 存储在 `Authorization` 头中）。虽然 JWT 方式本身不受传统 Cookie-based CSRF 影响，但如果前端将 Token 存储在 `localStorage` 中（如 `web/frontend/src/api/index.js` 第 13 行），则存在 XSS 窃取 Token 的风险。此外，系统未实现 CSRF Token 机制作为纵深防御。

- **问题代码** (前端):
  ```javascript
  // web/frontend/src/api/index.js
  const token = localStorage.getItem('auth_token')  // localStorage 易受 XSS 攻击
  if (token) {
      config.headers.Authorization = `Bearer ${token}`
  }
  ```

- **修复建议**:
  1. 使用 `httpOnly` cookie 存储 JWT（配合 Flask 设置）:
  ```python
  # 登录成功后设置 httpOnly cookie
  from flask import make_response
  
  response = make_response(jsonify({
      'success': True,
      'data': { 'user_info': result['user_info'] }
  }))
  response.set_cookie(
      'auth_token',
      result['token'],
      httponly=True,
      secure=True,  # 仅 HTTPS（生产环境需启用）
      samesite='Strict',  # 防 CSRF
      max_age=15 * 60  # 15分钟
  )
  return response
  ```
  
  2. 前端不再手动管理 Token:
  ```javascript
  // 使用 withCredentials 让浏览器自动发送 cookie
  const api = axios.create({
      baseURL: '',
      timeout: 30000,
      withCredentials: true,  // 自动发送 cookie
  })
  
  // 移除手动设置 Authorization 头的拦截器
  // 后端从 cookie 中读取 token
  ```
  
  3. 中间件从 cookie 读取 Token（增强）:
  ```python
  def require_auth(f):
      @functools.wraps(f)
      def decorated_function(*args, **kwargs):
          # 优先从 Authorization 头获取，回退到 cookie
          auth_header = request.headers.get('Authorization')
          token = None
          
          if auth_header:
              parts = auth_header.split()
              if len(parts) == 2 and parts[0].lower() == 'bearer':
                  token = parts[1]
          
          if not token:
              token = request.cookies.get('auth_token')
          
          if not token:
              return jsonify({'success': False, 'error': '缺少认证信息'}), 401
          # ...
  ```
