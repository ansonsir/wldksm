# 安全审计报告 - 前端 XSS 与存储安全

## 文件: web/frontend/src/api/index.js

### 漏洞 1: Token 存储在 localStorage（XSS 风险）

- **漏洞类型**: 敏感信息泄露（XSS 利用链）
- **严重程度**: 高危
- **行号**: 第 13、44-45、56、64-67 行

- **问题描述**: 
  JWT Token 和 Refresh Token 存储在 `localStorage` 中，这意味着任何成功的 XSS 攻击都可以直接读取 Token 并发送给攻击者。虽然系统使用了 Vue 3（自动转义插值），但如果存在 DOM-XSS 或第三方库漏洞，Token 仍可能被窃取。

- **问题代码**:
  ```javascript
  // 存储
  localStorage.setItem('auth_token', token)
  localStorage.setItem('refresh_token', refresh_token)
  
  // 读取
  const token = localStorage.getItem('auth_token')
  const refreshToken = localStorage.getItem('refresh_token')
  ```

- **修复建议**:
  参考 [05-web-rate-limit-csrf.md](./05-web-rate-limit-csrf.md) 中的漏洞3修复方案，使用 `httpOnly` cookie 替代 localStorage。

  **短期缓解**（如果保留 localStorage 方案）:
  1. 添加 CSP 头限制脚本来源（已在 `security_config.py` 中配置）
  2. 实现 Token 绑定到客户端指纹:
  ```javascript
  // 生成浏览器指纹
  function generateFingerprint() {
      const components = [
          navigator.userAgent,
          navigator.language,
          screen.colorDepth,
          screen.width + 'x' + screen.height,
          new Date().getTimezoneOffset(),
      ]
      return btoa(components.join('|'))
  }
  
  // 存储时附带指纹
  const fingerprint = generateFingerprint()
  localStorage.setItem('auth_token', token)
  localStorage.setItem('fingerprint', fingerprint)
  
  // 请求时验证指纹（在拦截器中）
  api.interceptors.request.use(config => {
      const token = localStorage.getItem('auth_token')
      const fp = localStorage.getItem('fingerprint')
      if (token) {
          config.headers.Authorization = `Bearer ${token}`
          config.headers['X-Client-Fingerprint'] = fp
      }
      return config
  })
  ```

---

## 文件: web/frontend/src/views/Settings.vue, Scan.vue (等 Vue 组件)

### 漏洞 2: v-html 指令使用风险

- **漏洞类型**: XSS（存储型/反射型）
- **严重程度**: 高危
- **行号**: 所有使用 `v-html` 的位置（需检查）

- **问题描述**: 
  Element Plus 的 `el-message`、`el-notification` 等组件支持 HTML 内容。如果后端返回的数据中包含 HTML 并使用了 `v-html` 或 `dangerouslyUseHTMLString`，可能导致存储型 XSS。例如扫描结果中的 IP 地址、端口描述等字段如果被恶意篡改，可能注入恶意脚本。

- **修复建议**:
  1. 排查所有 `v-html` 使用:
  ```bash
  grep -r "v-html" web/frontend/src/
  grep -r "dangerouslyUseHTMLString" web/frontend/src/
  ```
  
  2. 使用安全替代方案:
  ```vue
  <!-- 不安全 -->
  <div v-html="userProvidedContent"></div>
  
  <!-- 安全：纯文本渲染 -->
  <div>{{ userProvidedContent }}</div>
  
  <!-- 安全：使用 DOMPurify 净化 -->
  <script setup>
  import DOMPurify from 'dompurify'
  const sanitizeHTML = (html) => DOMPurify.sanitize(html)
  </script>
  <template>
    <div v-html="sanitizeHTML(userProvidedContent)"></div>
  </template>
  ```

---

## 文件: web/frontend/src/components/Layout.vue

### 漏洞 3: 定时轮询健康检查可能暴露信息

- **漏洞类型**: 信息泄露（低风险）
- **严重程度**: 低危
- **行号**: `checkHealth` 调用

- **问题描述**: 
  前端每 60 秒轮询 `/api/system/health`。虽然该接口已豁免速率限制，但健康检查返回了数据库状态、调度器状态等内部信息。如果系统暴露在公网，这些信息可供攻击者侦察。

- **当前代码**: 第 159 行已使用 `@limiter.exempt`，这是合理的，但不需要额外修改。

---

## 文件: web/frontend/src/ (整体)

### 漏洞 4: 无 Content Security Policy 报表机制

- **漏洞类型**: 配置缺失
- **严重程度**: 低危
- **行号**: N/A

- **问题描述**: 
  CSP 头已配置（通过 `Talisman`），但未设置 `report-uri` 或 `report-to` 指令来收集违规报告，无法及时发现 XSS 攻击尝试。

- **修复建议**:
  ```python
  # web/app.py
  Talisman(app, content_security_policy={
      'default-src': "'self'",
      'script-src': "'self' 'unsafe-inline'",
      'style-src': "'self' 'unsafe-inline'",
      'img-src': "'self' data:",
      'report-uri': '/api/csp-report',  # 添加报告端点
  }, force_https=False)
  ```
  
  ```python
  # web/routes/dashboard_routes.py
  @dashboard_bp.route('/api/csp-report', methods=['POST'])
  @limiter.limit("30 per minute")
  def csp_report():
      """接收 CSP 违规报告"""
      import logging
      logger = logging.getLogger("CSP")
      report = request.get_json(silent=True)
      if report:
          logger.warning(f"CSP 违规: {json.dumps(report, indent=2)}")
      return jsonify({'success': True}), 204
  ```
