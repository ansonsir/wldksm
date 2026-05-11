# ScanScript v5.0 安全审计汇总报告

> **审计日期**: 2026-05-09
> **审计人员**: 安全工程师（AI辅助）
> **审计范围**: 全部源代码（core/ + web/ + frontend/）
> **审计方法**: 静态代码分析 + 架构审查

---

## 一、漏洞概览

| 等级 | 数量 | 说明 |
|------|------|------|
| **严重** | 3 | 命令注入、无认证API、文件上传 |
| **高危** | 7 | SSRF、敏感信息泄露、代码执行、暴力破解 |
| **中危** | 7 | CSRF、CORS、存储安全、信息泄露 |
| **低危** | 3 | 配置改进、CSP报告、路径限制 |

**总计: 20 个安全发现**

---

## 二、严重漏洞 (Critical)

| # | 漏洞 | 文件 | 描述 |
|---|------|------|------|
| 1 | 命令注入 | `core/rustscan.py` | RustScan 命令拼接用户输入的 IP/端口，可注入任意 Shell 命令 |
| 2 | 无认证API | `web/api/scheduler_api.py` | 定时任务 API 全部端点无 `@require_auth`，可被任意操作 |
| 3 | 文件上传 | `web/routes/report_routes.py` | 模板上传接口无认证 + 仅检查扩展名，可上传恶意文件 |

---

## 三、高危漏洞 (High)

| # | 漏洞 | 文件 | 描述 |
|---|------|------|------|
| 4 | SSRF | `web/webhook_service.py` | Webhook URL 未验证，可探测内网服务 |
| 5 | SMTP密码泄露 | `web/routes/config_routes.py` | GET /api/mail/config 返回明文 SMTP 密码 |
| 6 | 代码执行 | `core/report.py` | `ast.literal_eval()` 解析端口数据，存在潜在绕过风险 |
| 7 | 模板上传无认证 | `web/routes/report_routes.py` | 多个模板接口缺少 `@require_auth` |
| 8 | 暴力破解 | `web/api/auth_api.py` | 登录接口未记录真实 IP，IP 级限速失效 |
| 9 | 数据库文件暴露 | `core/database.py` | SQLite 文件位于项目根目录，可能被直接下载 |
| 10 | Token存储 | `web/frontend` | JWT 存储在 localStorage，易受 XSS 窃取 |

---

## 四、中危漏洞 (Medium)

| # | 漏洞 | 文件 | 描述 |
|---|------|------|------|
| 11 | CSRF缺失 | 全局 | 未实现 CSRF Token 或 SameSite Cookie 策略 |
| 12 | CORS过宽 | `web/app.py` | `CORS(app)` 允许所有来源跨域 |
| 13 | 明文密码日志 | `web/app.py` | 管理员初始密码明文输出到控制台 |
| 14 | SMTP明文存储 | `web/mail_service.py` | SMTP 密码明文存储在 SQLite |
| 15 | 统计信息泄露 | `web/routes/dashboard_routes.py` | /api/stats 无认证，泄露内部运维数据 |
| 16 | 验证码DoS | `web/services/auth_service.py` | 内存存储验证码，可被大量请求耗尽内存 |
| 17 | XML解析 | `core/template_manager.py` | 模板 XML 解析未使用 defusedxml，存在 XXE 风险 |

---

## 五、低危漏洞 (Low)

| # | 漏洞 | 文件 | 描述 |
|---|------|------|------|
| 18 | CSP报告缺失 | `web/app.py` | 未配置 CSP 违规报告端点 |
| 19 | 配置文件路径 | `core/config.py` | 配置路径可指向项目目录外 |
| 20 | v-html风险 | 前端组件 | 需排查所有 v-html / dangerouslyUseHTMLString 使用 |

---

## 六、修复优先级建议

### 第一优先级（立即修复）
1. **scheduler_api.py 添加认证** - 最简单但影响最大的修复
2. **template upload 添加认证 + 内容校验** - 阻止恶意文件上传
3. **命令注入修复** - 使用 `shell=False` + 参数列表方式调用

### 第二优先级（本周内）
4. **SSRF 修复** - 添加 URL 白名单和内网地址拒绝
5. **SMTP 密码不返回前端** - 修改 API 响应
6. **登录 IP 记录** - 启用真实 IP 记录和速率限制
7. **CORS 收紧** - 限制允许的来源

### 第三优先级（本月内）
8. **SMTP 密码加密存储** - 使用 Fernet 对称加密
9. **Token 存储改进** - 迁移到 httpOnly cookie
10. **CSRF 保护** - 添加 SameSite Cookie + CSRF Token
11. **数据库文件位置调整**

---

## 七、架构改进建议

1. **统一认证拦截器**: 使用 Flask `before_request` 钩子替代逐个添加装饰器
2. **API 网关模式**: 考虑引入 API 网关统一处理认证、限流、日志
3. **安全测试集成**: 在 CI/CD 中加入 `bandit`、`safety` 扫描
4. **依赖审计**: 定期运行 `pip-audit` 检查第三方库漏洞
5. **密钥管理**: 使用环境变量或密钥管理服务（如 HashiCorp Vault）管理敏感凭证

---

## 八、参考文档

| 报告 | 内容 |
|------|------|
| [01-core-scanner-rustscan.md](./01-core-scanner-rustscan.md) | 命令注入、输入验证、进程安全 |
| [02-core-report-template.md](./02-core-report-template.md) | 代码执行、文件上传、模板安全 |
| [03-web-auth-scheduler.md](./03-web-auth-scheduler.md) | 认证缺失、越权漏洞 |
| [04-web-ssrf-info-leak.md](./04-web-ssrf-info-leak.md) | SSRF、敏感信息泄露、CORS |
| [05-web-rate-limit-csrf.md](./05-web-rate-limit-csrf.md) | 速率限制、暴力破解、CSRF |
| [06-frontend-xss.md](./06-frontend-xss.md) | XSS、Token存储、CSP |
| [07-core-database-config.md](./07-core-database-config.md) | SQL注入、凭证存储、配置安全 |
