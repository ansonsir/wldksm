# ScanScript 项目开发记忆文档

> 本文件由 Qoder AI 助手根据项目开发历史自动生成，包含完整的项目上下文记忆。  
> 切换到新目录后，将此文件内容提供给 Qoder 即可延续开发上下文。

---

## 一、项目概述

### 1.1 项目定位
**ScanScript** 是基于 RustScan 的高性能网络端口扫描工具，面向安全运维人员提供可视化管理能力。

### 1.2 核心功能架构
| 模块 | 功能 |
|------|------|
| 扫描引擎 | 并发调用 RustScan，支持 IP 段/CIDR/多文件输入、端口段/列表输入 |
| Web 管理界面 | Vue 3 实现任务控制、实时进度、结果查看与 Word 报告下载 |
| 持久化层 | SQLite 存储扫描记录、邮件配置、系统参数 |
| 通知能力 | SMTP 邮件自动发送扫描报告 |
| 扩展能力 | 支持红区网段、排除IP、自定义模板等企业级配置 |

---

## 二、技术栈

### 2.1 后端
- **语言**: Python 3.8+
- **框架**: Flask >= 2.0.0
- **核心依赖**:
  - `Flask-CORS>=4.0.0` — 跨域支持
  - `docxtpl>=0.16.0` + `python-docx>=0.8.11` — Word报告生成
  - `PyYAML>=6.0` — 配置解析
  - `APScheduler>=3.10.0` — 定时任务
  - `bcrypt`, `PyJWT`, `flask-login` — 认证与安全
  - `pyotp>=2.9.0` — TOTP双因素认证
  - `captcha>=0.5.0` — 图形验证码
  - `cryptography>=41.0.0` — Fernet加密（SMTP密码）
  - `defusedxml>=0.7.0` — XXE防护
  - `flask-limiter>=3.5.0` — API限流
  - `flask-talisman>=1.1.0` — CSP安全头
  - `Pillow>=10.0.0` + `qrcode>=7.4.2` — TOTP二维码
- **数据库**: SQLite (`data/scan_data.db`)

### 2.2 前端
- **框架**: Vue 3 + Vite
- **UI库**: Element Plus
- **状态管理**: Pinia
- **图表**: ECharts
- **HTTP**: Axios（封装实例 `api`）

### 2.3 底层引擎
- **RustScan** — 系统级已安装，非Python包

---

## 三、项目架构

### 3.1 目录结构
```
ScanScript/
├── core/                    # 核心模块
│   ├── config.py            # 配置管理器（YAML加载、路径安全校验）
│   ├── database.py          # 数据库管理器（SQLite、WAL模式）
│   ├── exceptions.py        # 自定义异常
│   ├── report.py            # 报告生成（json.loads安全解析）
│   ├── rustscan.py          # RustScan调用封装（shell=False安全）
│   ├── scanner.py           # 扫描器主逻辑
│   ├── template_manager.py  # 模板管理（defusedxml XXE防护）
│   └── utils.py             # 工具函数（日志系统）
├── web/                     # Web应用
│   ├── app.py               # Flask工厂函数（Talisman CSP、CORS）
│   ├── scheduler.py         # 定时任务调度器（APScheduler）
│   ├── mail_service.py      # 邮件服务（Fernet加密SMTP密码）
│   ├── webhook_service.py   # Webhook通知（SSRF防护）
│   ├── rate_limit.py        # 共享Limiter实例
│   ├── security_config.py   # 安全配置常量
│   ├── api/                 # API Blueprint
│   │   ├── auth_api.py      # 认证API（登录/验证码/TOTP/CSRF）
│   │   └── scheduler_api.py # 调度器API（全部@require_auth）
│   ├── routes/              # 路由 Blueprint
│   │   ├── config_routes.py # 配置管理路由
│   │   ├── scan_routes.py   # 扫描任务路由
│   │   ├── report_routes.py # 报告路由（ZIP魔术字节+路径穿越防护）
│   │   └── dashboard_routes.py # 仪表盘路由（CSP报告端点）
│   ├── middleware/
│   │   └── auth_middleware.py # JWT认证+CSRF装饰器
│   ├── services/
│   │   ├── auth_service.py  # 认证服务（密码/TOTP/Captcha/CSRF）
│   │   ├── scan_service.py  # 扫描服务
│   │   ├── task_manager.py  # 任务管理器
│   │   └── scan_executor.py # 扫描执行器
│   └── frontend/            # Vue 3 前端
│       └── src/
│           ├── api/index.js # Axios封装（JWT+CSRF拦截器）
│           ├── stores/      # Pinia状态管理
│           ├── views/       # 视图组件
│           ├── components/  # 通用组件
│           └── router/      # 路由配置
├── data/                    # 数据目录
│   ├── config.yaml          # 主配置文件
│   ├── scan_data.db         # SQLite数据库
│   ├── templates/           # 报告模板
│   ├── reports/             # 生成的报告
│   ├── ip_ranges.txt        # IP范围文件
│   ├── redarea.txt          # 红区IP文件
│   ├── excludes.txt         # 排除IP文件
│   └── ports.txt            # 端口列表
├── logs/                    # 日志目录
├── scripts/                 # 辅助脚本
├── requirements.txt         # Python依赖
└── cli.py                   # CLI入口
```

---

## 四、开发规范与常见陷阱

### 4.1 前端 API 调用规范（重要！）
**必须使用封装的 `api` 实例，禁止使用裸 `axios`！**

```js
// ✅ 正确：使用封装的api实例（自动携带Authorization + CSRF Token）
import api from '@/api'
const res = await api.get('/api/scheduler/tasks')
if (res.success) { ... }  // api响应拦截器已解包response.data

// ❌ 错误：裸axios不会携带认证头
import axios from 'axios'
const res = await axios.get('/api/scheduler/tasks')  // → 401 缺少认证信息
```

**响应结构差异**：
- `api` 实例返回 `{success, data, message}`（已解包）
- 裸 `axios` 返回完整的 AxiosResponse 对象

**文件下载例外**：blob 响应 `api` 拦截器返回完整 response 对象（`res.data` 是 blob）。

### 4.2 后端服务依赖注入规范
中间件必须通过 `current_app.config` 获取服务实例：

```python
# ✅ 正确
from flask import current_app
auth_service = current_app.config['auth_service']
db_manager = current_app.config['db_manager']

# ❌ 错误：v4.0重构后不再直接导出
from web.app import auth_service  # ImportError!
```

### 4.3 Flask secret_key 持久化
`app.secret_key` 必须持久化存储（`web/data/.flask_secret`），否则每次重启 TOTP 登录 session 失效。

---

## 五、构建与部署

### 5.1 前端构建
```bash
cd web/frontend && npm run build
```

### 5.2 服务启停
```bash
# 停止服务
kill $(lsof -ti:5000)

# 后台启动
cd /home/yinsongkai/Desktop/杨其顶-work/Code-yang/ScanScript
nohup python3 web/app.py > logs/web_server.log 2>&1 &

# 健康检查
curl http://127.0.0.1:5000/api/system/health
```

### 5.3 健康验证标准流程
1. 终止占用5000端口进程 → 等待2秒
2. nohup启动 → 等待3秒
3. `curl /api/system/health` 确认 `status: healthy`
4. 检查日志确认定时任务加载成功

---

## 六、主要功能实现历史

### 6.1 v4.0 架构升级
- **后端**: Blueprint路由架构，app.py工厂模式，TaskManager/ScanExecutor服务解耦
- **前端**: Pinia全局状态管理（auth.js/app.js store）
- **新增**: `/api/system/health` 健康检查API
- **修复**: 前后端错误字段统一为 `message`，Flask secret_key持久化
- **关键文件**: `web/routes/__init__.py`, `web/services/task_manager.py`, `web/services/scan_executor.py`, `web/frontend/src/stores/auth.js`, `web/frontend/src/stores/app.js`

### 6.2 v5.0 全面升级
- **P0修复**: RustScan进程组隔离（防止并发扫描互相终止）
- **P0修复**: SMTP密码改为环境变量存储 → 后续升级为Fernet加密
- **P1修复**: JWT黑名单自动清理机制
- **P1修复**: 报告下载路径穿越防护增强
- **P2优化**: SQLite WAL模式提升并发性能
- **P2优化**: API响应格式统一为 `{success, data, message}`
- **新功能**: 资产变更追踪、多渠道Webhook通知（钉钉/企业微信/飞书）、扫描策略模板

### 6.3 UI风格系统性优化
- 全局CSS设计系统变量（颜色、间距、字体）
- Layout.vue升级（健康状态监控、面包屑导航、响应式侧边栏）
- PageHeader.vue通用组件（图标、标题、副标题、操作区插槽）
- Dashboard.vue：8卡片 + 4 ECharts图表 + 健康横幅

### 6.4 Dashboard大屏数据可视化
- 后端 `/api/stats` 扩展12个维度（今日统计、7天趋势、风险分布、Top主机/端口、定时任务汇总等）
- 前端 ECharts：趋势组合图、风险饼图、状态横条图、端口排名图

### 6.5 定时任务调度系统
- **每日巡检任务** (ID 15/21)：CronTrigger 显式指定 `Asia/Shanghai` 时区
- `misfire_grace_time=86400` 避免错过执行
- APScheduler 状态自愈：检测 `STATE_STOPPED` 自动调用 `start()` 重启
- 配置热加载：`_execute_task` 前调用 `reload_from_yaml()`
- 日志系统：`RotatingFileHandler` 防止日志爆炸

---

## 七、安全实现

### 7.1 严重漏洞修复（10项）
1. **scheduler_api.py**: 7个端点全部添加 `@require_auth`
2. **report_routes.py**: 模板端点认证 + ZIP魔术字节验证 + 路径穿越防护
3. **rustscan.py**: `shell=False` + 参数列表 + `preexec_fn` 资源限制（CPU 3600s/Memory 4GB） + `json.loads` 替代 `ast.literal_eval`
4. **webhook_service.py**: HTTPS强制 + 内网IP拒绝 + 平台域名白名单
5. **config_routes.py**: SMTP密码掩码（GET返回`'********'` + POST占位符处理）
6. **auth_api.py + auth_service.py**: 客户端真实IP提取（`X-Forwarded-For` + `request.remote_addr`）+ 修复 `ip_address` 被硬编码覆盖bug
7. **report.py**: `json.loads` 替代 `ast.literal_eval` + 端口范围验证
8. **app.py**: CORS限定localhost + 管理员初始密码写入 `data/.admin_initial_credentials`（chmod 600）
9. **前端Token**: 浏览器指纹绑定 + `secureGetItem`/`secureSetItem` 防XSS窃取

### 7.2 中危漏洞修复（7项）
1. **CSRF保护**: `@require_csrf` 装饰器 + `/api/auth/csrf-token` 端点 + JWT签名CSRF Token（8小时有效）
2. **CORS过宽**: 限定 `localhost:5000` 来源（上轮已修复）
3. **明文密码日志**: SMTP密码日志掩码（上轮已修复）
4. **SMTP明文存储**: Fernet对称加密，密钥文件 `data/.smtp_fernet_key`（chmod 600）
5. **统计信息泄露**: `/api/stats`, `/api/assets/*` 添加 `@require_auth`
6. **验证码DoS**: 单IP每分钟10次 + 全局100条上限 + `@limiter.limit("10 per minute")`
7. **XML XXE**: `defusedxml.defuse_stdlib()` 在导入 docxtpl 前全局替换 XML 解析器

### 7.3 低危漏洞修复（3项）
1. **CSP报告缺失**: `POST /api/csp-report` 端点 + Talisman CSP `report-uri`
2. **配置文件路径**: `_resolve_safe_paths()` 方法确保所有文件路径在项目目录内
3. **v-html风险**: 前端无使用（0处匹配）

### 7.4 CSRF Token 完整机制
```
登录成功 → fetchCsrfToken() → 存入 localStorage
    ↓
每次 POST/PUT/DELETE → api拦截器自动注入 X-CSRF-Token 头
    ↓
403 CSRF 过期 → 拦截器自动刷新Token → 重试请求
    ↓
登出/401过期 → clearCsrfToken()
```

**前端集成文件**：
- `api/index.js`: CSRF Token 存储/拦截器/自动刷新
- `stores/auth.js`: 登录后获取 + 登出清理
- `Login.vue`: 3条登录成功路径调用 `fetchCsrfToken()`

---

## 八、关键 Bug 修复记录

| Bug | 根因 | 修复 |
|-----|------|------|
| 登录400错误 | 前后端错误字段名不匹配（`error` vs `message`） | 前端优先读 `message`，回退 `error` |
| TOTP会话过期 | Flask session cookie 浏览器兼容问题 | JWT Token 替代 session（5分钟有效期） |
| 500 ImportError | 中间件直接 `from web.app import auth_service` | 改用 `current_app.config['auth_service']` |
| 健康检查429限流 | Flask-Limiter 默认限制50次/小时 | `@limiter.exempt` 豁免 + 前端轮询降频至60秒 |
| 定时任务15未执行 | CronTrigger 未指定时区 + misfire_grace_time 过小 | 显式 `Asia/Shanghai` + `misfire=86400` |
| APScheduler 状态异常 | 后台线程意外退出导致 STATE_STOPPED | 状态检测 + 自动 `start()` 重启 |
| RustScan进程互相终止 | 并发扫描共享进程组 | 每个子进程独立进程组 |
| auth_service IP覆盖 | `authenticate()` 方法体硬编码 `ip_address="unknown"` | 删除硬编码行 |
| Scheduler页面401 | 裸 `axios` 不携带 Authorization 头 | 统一改用 `api` 实例 |
| Reports/History下载失败 | 同上 + blob响应拦截器问题 | `api` 实例 + blob返回完整response |

---

## 九、前端最佳实践

### 9.1 API调用模式
```js
import api from '@/api'

// GET请求
const res = await api.get('/api/scheduler/tasks')
if (res.success) { this.tasks = res.data }

// POST请求（自动携带CSRF Token）
await api.post('/api/scheduler/tasks', formData)

// 文件下载
const res = await api.post('/api/reports/download', { path }, { responseType: 'blob' })
// res 是完整 AxiosResponse，res.data 是 Blob
```

### 9.2 状态管理
```js
// auth store
import { useAuthStore } from '@/stores/auth'
const auth = useAuthStore()
auth.setAuth(token, userInfo)  // 自动获取CSRF Token
auth.logout(router)             // 自动携带CSRF Token + 清理
```

### 9.3 组件规范
- 使用 `PageHeader` 组件统一页面标题栏
- 遵循 `style.css` 设计系统变量
- 使用 Element Plus 组件，保持UI一致性

---

## 十、文件参考地图

### 核心后端文件
| 文件 | 职责 |
|------|------|
| `web/app.py` | Flask 工厂函数、Talisman CSP、CORS、服务初始化 |
| `web/scheduler.py` | APScheduler 调度器（状态自愈、配置热加载） |
| `web/mail_service.py` | SMTP邮件（Fernet加密密码） |
| `web/webhook_service.py` | Webhook通知（SSRF防护） |
| `core/config.py` | 配置管理（YAML加载、路径安全校验） |
| `core/database.py` | SQLite数据库（WAL模式、JWT黑名单清理） |
| `core/rustscan.py` | RustScan调用（`shell=False` + 资源限制） |
| `core/scanner.py` | 扫描器主逻辑（进程组隔离） |
| `core/template_manager.py` | 模板管理（defusedxml XXE防护） |
| `core/report.py` | 报告生成（`json.loads` 安全解析） |
| `web/services/auth_service.py` | 认证服务（密码/TOTP/Captcha/CSRF/JWT） |
| `web/middleware/auth_middleware.py` | `@require_auth` + `@require_admin` + `@require_csrf` |
| `web/rate_limit.py` | 共享 Flask-Limiter 实例 |

### 核心前端文件
| 文件 | 职责 |
|------|------|
| `src/api/index.js` | Axios封装（JWT+CSRF拦截器、指纹绑定） |
| `src/stores/auth.js` | 认证状态管理 |
| `src/views/Login.vue` | 登录页（验证码/TOTP/CSRF集成） |
| `src/views/Dashboard.vue` | 仪表盘大屏（ECharts图表） |
| `src/views/Scheduler.vue` | 定时任务管理 |
| `src/components/PageHeader.vue` | 通用页面标题组件 |
| `src/style.css` | 全局设计系统 |

### API路由清单
| 路由前缀 | 蓝图 | 认证要求 |
|----------|------|----------|
| `/api/auth/*` | auth_bp | 部分公开（login/captcha），其余 `@require_auth` |
| `/api/scheduler/*` | scheduler_bp | 全部 `@require_auth` |
| `/api/stats` | dashboard_bp | `@require_auth` |
| `/api/assets/*` | dashboard_bp | `@require_auth` |
| `/api/system/health` | dashboard_bp | `@limiter.exempt`（公开） |
| `/api/csp-report` | dashboard_bp | `@limiter.limit("30 per minute")` |
| `/api/reports/*` | report_bp | 全部 `@require_auth` |
| `/api/scan/*` | scan_bp | 全部 `@require_auth` |
| `/api/config/*` | config_bp | 全部 `@require_auth` |

---

## 十一、环境配置要点

### 11.1 默认配置
- IP范围文件: `data/redarea.txt`（通过 `config.yaml` 的 `ip_range_file` 字段配置）
- 数据库: `data/scan_data.db`（SQLite WAL模式）
- 日志: `logs/network_scan.log` + `logs/web_server.log`
- Web端口: `5000`

### 11.2 敏感文件
| 文件 | 用途 | 权限 |
|------|------|------|
| `data/.admin_initial_credentials` | 管理员初始密码（登录后应删除） | 600 |
| `web/data/.jwt_secret` | JWT签名密钥 | - |
| `web/data/.flask_secret` | Flask session密钥 | - |
| `data/.smtp_fernet_key` | SMTP密码Fernet加密密钥 | 600 |

### 11.3 环境变量
- `SMTP_PASSWORD` / `SMTP_USER`: 可覆盖YAML中的SMTP配置

---

> **文档版本**: 基于截至 2026-05-11 的项目开发历史生成  
> **切换目录后使用**: 将此文件路径提供给 Qoder，即可延续全部项目上下文记忆
