# ScanScript v4.0 架构重构设计方案

> **方案性质**: 纯设计文档，供评估决策，不包含具体实现代码
> **设计目标**: 使项目架构更科学、模块更清晰、功能更完善、使用体验更好

---

## 目录

1. [现状问题分析](#1-现状问题分析)
2. [新架构总览](#2-新架构总览)
3. [后端架构设计](#3-后端架构设计)
4. [前端架构设计](#4-前端架构设计)
5. [页面功能结构设计](#5-页面功能结构设计)
6. [数据库设计优化](#6-数据库设计优化)
7. [API 设计规范](#7-api-设计规范)
8. [关键流程设计](#8-关键流程设计)
9. [改造路线图](#9-改造路线图)

---

## 1. 现状问题分析

### 1.1 架构层面

| 问题 | 说明 |
|------|------|
| **路由混装** | `web/app.py` 942 行，所有 API 路由、初始化、安全配置全塞在一个文件 |
| **循环依赖** | Scheduler ↔ ScanService 互相引用，需要先创建空壳再回头注入 |
| **配置双存** | 邮件配置既在 YAML 又在 DB，邮件密码明文存储于 YAML 中 |
| **无任务队列** | 扫描直接用线程跑，无队列缓冲、无并发控制上限 |
| **服务职责模糊** | `scan_service.py` 既管理任务生命周期又执行扫描逻辑 |
| **无健康检查** | 无法感知 APScheduler 状态、DB 连接状态、RustScan 可用性 |

### 1.2 功能层面

| 问题 | 说明 |
|------|------|
| **配置不热生效** | 修改 YAML 后必须重启服务（上次已修了一部分） |
| **无通知渠道** | 只能邮件通知，无 Webhook/钉钉/企业微信 |
| **无扫描对比** | 无法对比两次扫描结果的差异 |
| **无告警规则** | 发现高危端口后无法自动告警 |
| **日志查询弱** | 前端无法查看实时日志 |
| **单用户模型** | 虽有多用户表但无角色分级（管理员/操作员/只读） |

### 1.3 前端层面

| 问题 | 说明 |
|------|------|
| **功能割裂** | "扫描任务"和"扫描历史"分开，用户需在两个页面跳转 |
| **定时任务与扫描脱节** | 定时任务执行后的结果没有直接关联入口 |
| **报告列表混杂** | 数据库报告和文件系统报告混在一起 |
| **仪表盘简单** | 只有4个数字卡片，缺少趋势图、实时状态 |

---

## 2. 新架构总览

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端层 (Vue 3)                        │
│  视图 → 组件 → API 模块 → Axios                         │
├─────────────────────────────────────────────────────────┤
│                    网关层 (Flask)                        │
│  Blueprint 路由 → 请求校验 → 响应封装                    │
├─────────────────────────────────────────────────────────┤
│                    服务层 (Services)                     │
│  ScanService │ SchedulerService │ ReportService          │
│  NotifyService │ AlertService │ LogService               │
├─────────────────────────────────────────────────────────┤
│                    核心层 (Core)                         │
│  Scanner │ Reporter │ Config │ Database │ RustScanAPI    │
├─────────────────────────────────────────────────────────┤
│                    基础设施层                            │
│  SQLite │ APScheduler │ RustScan │ SMTP │ 文件系统       │
└─────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
ScanScript/
├── core/                          # 核心引擎（纯逻辑，无 Web 依赖）
│   ├── __init__.py
│   ├── config.py                  # 配置管理（统一入口）
│   ├── database.py               # 数据库（拆分为多个 Manager）
│   ├── scanner.py                # 扫描编排器
│   ├── rustscan.py               # RustScan API 封装
│   ├── reporter.py               # 报告生成引擎
│   ├── analyzer.py               # 数据分析与对比
│   ├── exceptions.py             # 自定义异常
│   └── utils.py                  # 工具函数
│
├── server/                        # Web 服务层（重命名自 web，语义更清晰）
│   ├── __init__.py
│   ├── app.py                    # Flask 工厂函数 + 启动（精简）
│   ├── extensions.py             # Flask 扩展初始化
│   │
│   ├── routes/                    # 路由层（Blueprint）
│   │   ├── __init__.py
│   │   ├── auth_routes.py        # 认证路由
│   │   ├── scan_routes.py        # 扫描路由
│   │   ├── scheduler_routes.py   # 定时任务路由
│   │   ├── report_routes.py      # 报告路由
│   │   ├── config_routes.py      # 配置路由
│   │   ├── dashboard_routes.py   # 仪表盘路由
│   │   └── log_routes.py         # 日志路由
│   │
│   ├── services/                  # 业务服务层
│   │   ├── __init__.py
│   │   ├── task_manager.py       # 任务队列与生命周期管理
│   │   ├── scheduler_service.py  # 定时任务调度
│   │   ├── scan_executor.py      # 扫描执行引擎
│   │   ├── report_service.py     # 报告生成服务
│   │   ├── notify_service.py     # 通知服务（邮件/Webhook）
│   │   ├── alert_service.py      # 告警规则引擎
│   │   └── log_service.py        # 日志查询服务
│   │
│   ├── middleware/                # 中间件
│   │   ├── auth.py
│   │   └── rate_limit.py
│   │
│   └── frontend/                  # Vue 3 前端
│       └── src/
│           ├── api/               # API 调用模块
│           ├── components/        # 通用组件
│           ├── composables/       # 组合式函数
│           ├── layouts/           # 布局组件
│           ├── router/            # 路由
│           ├── stores/            # Pinia 状态管理
│           ├── views/             # 页面视图
│           └── utils/             # 工具函数
│
├── data/                          # 数据文件（不变）
├── logs/                          # 日志（不变）
├── scripts/                       # 运维脚本
├── archive/                       # 历史归档（不变）
├── cli.py                         # 命令行入口
└── requirements.txt
```

---

## 3. 后端架构设计

### 3.1 Flask 应用工厂模式

```python
# server/app.py (精简后约80行)
def create_app(config_path=None):
    app = Flask(__name__)
    
    # 1. 加载配置
    app.config_manager = ConfigManager(config_path)
    
    # 2. 初始化扩展
    init_extensions(app)  # DB, Mailer, Scheduler 等
    
    # 3. 注册 Blueprint
    register_blueprints(app)
    
    # 4. 注册中间件
    register_middleware(app)
    
    # 5. 初始化默认数据
    init_default_data(app)
    
    return app
```

**优势**: 便于测试（每次创建独立 app 实例）、配置注入清晰

### 3.2 服务层职责拆分

```
                    ┌──────────────┐
                    │  Routes 层   │  只做参数校验 + 调用 Service + 返回响应
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼─────┐     ┌──────▼──────┐    ┌──────▼──────┐
   │TaskManager│    │SchedulerSvc │    │ReportService│
   │ 任务队列  │    │ 定时调度    │    │ 报告生成    │
   │ 并发控制  │    │ Cron/间隔   │    │ 对比分析    │
   └────┬─────┘    └──────┬──────┘    └──────┬──────┘
        │                 │                  │
        │          ┌──────▼──────┐           │
        └──────────► ScanExecutor◄───────────┘
                   │ 扫描执行    │
                   │ 进度跟踪    │
                   │ 进程管理    │
                   └──────┬──────┘
                          │
                   ┌──────▼──────┐
                   │ Core 引擎   │
                   │ Scanner     │
                   │ Reporter    │
                   └─────────────┘
```

#### 各服务职责

| 服务 | 职责 |
|------|------|
| **TaskManager** | 任务创建、状态管理、并发上限控制（最多 N 个扫描同时跑）、任务队列 |
| **SchedulerService** | 封装 APScheduler，定时触发、状态自愈、Cron/Interval/Once 三种模式 |
| **ScanExecutor** | 消费任务队列，调用 Core 引擎执行扫描，汇报进度 |
| **ReportService** | 报告生成、历史对比、模板匹配 |
| **NotifyService** | 邮件、Webhook、企业微信/钉钉通知渠道 |
| **AlertService** | 高危端口告警规则、阈值配置、自动通知 |
| **LogService** | 实时日志查询、日志级别过滤、日志下载 |

### 3.3 配置管理统一

```
                    ┌─────────────────┐
                    │   ConfigManager  │
                    │   (唯一入口)     │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐
        │ YAML 文件  │ │  数据库   │ │ 环境变量  │
        │ (扫描参数) │ │ (邮件/用户│ │ (密钥等)  │
        │            │ │  告警等)  │ │           │
        └───────────┘ └───────────┘ └───────────┘
```

**原则**:
- YAML → 静态扫描参数（IP范围、端口、线程数...）
- DB → 敏感/动态配置（邮件密码、告警规则、用户数据...）
- ENV → 运行环境密钥（FLASK_SECRET_KEY、JWT_SECRET...）
- **邮件密码不再明文存 YAML**，仅存 DB

### 3.4 任务队列与并发控制

```python
# 当前问题：create_task 后直接 execute_task，无队列缓冲

# 新设计：
# TaskManager 维护一个任务队列，限制同时执行的扫描数
class TaskManager:
    MAX_CONCURRENT_SCANS = 3  # 最多同时3个扫描任务
    
    def submit_task(self, params) -> str:
        """提交任务到队列，返回 task_id"""
        task = self._create_task(params)  # status=pending
        self._enqueue(task)
        return task.id
    
    def _enqueue(self, task):
        if self._running_count < self.MAX_CONCURRENT_SCANS:
            self._start_task(task)  # status=running
        else:
            self._queue.append(task)  # status=queued
    
    def _on_task_complete(self, task):
        self._running_count -= 1
        if self._queue:
            self._start_task(self._queue.pop(0))
```

---

## 4. 前端架构设计

### 4.1 整体布局

```
┌─────────────────────────────────────────────────────────┐
│  TopNav 顶栏                                              │
│  [Logo]  [系统名称]          [通知] [任务中心] [用户头像▼] │
├──────────┬──────────────────────────────────────────────┤
│ Sidebar  │  Content Area                                │
│          │                                              │
│ 📊 仪表盘 │  ┌─────────────────────────────────────────┐ │
│ 🎯 扫描中心│  │ 页面内容区域                            │ │
│ 📋 任务管理│  │                                         │ │
│ ⏰ 定时任务│  │                                         │ │
│ 📊 报告中心│  │                                         │ │
│ 📝 模板管理│  │                                         │ │
│ ⚙️ 系统设置│  │                                         │ │
│          │  └─────────────────────────────────────────┘ │
└──────────┴──────────────────────────────────────────────┘
```

### 4.2 技术选型

| 类别 | 技术 | 说明 |
|------|------|------|
| 框架 | Vue 3 (Composition API) | 保持现有 |
| UI 库 | Element Plus | 保持现有 |
| 状态管理 | Pinia | 替代当前零散的 reactive |
| 图表 | ECharts 5 | 仪表盘趋势图 |
| HTTP | Axios（封装拦截器） | 保持现有 |
| 路由 | Vue Router 4 | 保持现有 |

### 4.3 状态管理设计 (Pinia Stores)

```
stores/
├── auth.js          # 认证状态（token, userInfo, login/logout）
├── scan.js          # 扫描任务状态（active tasks, progress, results）
├── scheduler.js     # 定时任务状态
├── app.js           # 全局状态（sidebar collapsed, notifications）
└── settings.js      # 系统配置缓存
```

---

## 5. 页面功能结构设计

### 5.1 导航结构

```
├── 📊 仪表盘 (Dashboard)
│   ├── 总览统计
│   ├── 扫描趋势图
│   ├── 实时任务状态
│   └── 最近告警
│
├── 🎯 扫描中心 (Scan Center)        ← 合并 扫描任务 + 历史
│   ├── [Tab] 新建扫描
│   │   ├── 扫描模式选择（普通/红区/自定义）
│   │   ├── IP 范围配置（文本框 / 上传文件）
│   │   ├── 端口配置
│   │   ├── 高级选项（线程数、超时等）
│   │   └── 启动按钮
│   │
│   ├── [Tab] 运行中
│   │   ├── 实时进度条（每个任务）
│   │   ├── 实时日志流
│   │   └── 停止/暂停按钮
│   │
│   └── [Tab] 扫描历史
│       ├── 筛选器（时间、区域、状态）
│       ├── 对比模式（选2条记录对比差异）
│       ├── 批量操作（删除、导出）
│       └── 详情面板（点击展开）
│
├── ⏰ 定时任务 (Scheduler)
│   ├── 任务列表（名称/类型/Cron/状态/上次执行/下次执行）
│   ├── 创建/编辑定时任务弹窗
│   │   ├── 任务名称
│   │   ├── 触发类型（Cron / 间隔 / 一次性）
│   │   ├── 调度表达式（Cron 可视化选择器）
│   │   ├── 扫描配置（使用默认 / 自定义）
│   │   └── 通知设置（完成后发送邮件）
│   ├── 立即执行按钮
│   └── 执行记录（关联到扫描历史）
│
├── 📊 报告中心 (Reports)
│   ├── 报告列表（按时间倒序）
│   ├── 报告预览（在线查看报告内容）
│   ├── 报告对比（选择两次报告，高亮差异）
│   ├── 下载/发送邮件
│   └── 批量管理
│
├── 📝 模板管理 (Templates)
│   ├── 模板列表
│   ├── 上传新模板
│   ├── 设为默认
│   └── 预览/下载
│
├── ⚙️ 系统设置 (Settings)
│   ├── [Tab] 扫描配置
│   │   ├── IP 范围文件选择
│   │   ├── 端口文件
│   │   ├── 排除IP文件
│   │   ├── 并发参数
│   │   └── 超时设置
│   │
│   ├── [Tab] 通知设置
│   │   ├── 邮件服务器配置 + 测试连接
│   │   ├── Webhook 配置（钉钉/企业微信）
│   │   └── 告警规则（发现N个高危端口即告警）
│   │
│   ├── [Tab] 用户管理（管理员可见）
│   │   ├── 用户列表
│   │   ├── 新增用户（用户名/密码/角色）
│   │   └── 角色：管理员 / 操作员 / 只读
│   │
│   └── [Tab] 安全设置（当前用户）
│       ├── 修改密码
│       ├── TOTP 两步验证
│       └── 登录历史
│
└── 🔔 通知中心 (顶栏图标)
    ├── 扫描完成通知
    ├── 高危告警通知
    └── 系统异常通知
```

### 5.2 仪表盘详细设计

```
┌──────────────────────────────────────────────────────────┐
│ 📊 系统仪表盘                                            │
├──────────┬──────────┬──────────┬──────────┬──────────────┤
│ 总扫描   │ 成功     │ 发现主机 │ 开放端口 │ 今日告警     │
│ 128 次   │ 120 次   │ 2,456   │ 8,912   │ 3 条        │
├──────────┴──────────┴──────────┴──────────┴──────────────┤
│ ┌─────────────────────┐ ┌─────────────────────────────┐  │
│ │ 扫描趋势（近30天）  │ │ 端口分布（饼图）            │  │
│ │ 📈 折线图           │ │ 🍩 22/3389/3306/...         │  │
│ └─────────────────────┘ └─────────────────────────────┘  │
├──────────────────────────────────────────────────────────┤
│ ⏳ 正在运行的任务                                        │
│ ┌────────────────────────────────────────────────────┐   │
│ │ 红区巡检  ████████████░░░░░░  67%  剩余 3分钟     │   │
│ └────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────┤
│ 📋 最近完成的扫描                                        │
│ ┌────────────────────────────────────────────────────┐   │
│ │ 2026-05-09  每日巡检  完成  发现 45 台主机  5分钟  │   │
│ │ 2026-05-08  手动扫描  完成  发现 12 台主机  2分钟  │   │
│ └────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### 5.3 扫描中心 - 新建扫描详细设计

```
┌──────────────────────────────────────────────────────────┐
│ 🎯 新建扫描                                              │
├──────────────────────────────────────────────────────────┤
│ 扫描模式:  ○ 普通区域扫描    ○ 红区扫描(全端口)          │
│                                                          │
│ IP 范围:                                                  │
│ ┌────────────────────────────────────────────────────┐   │
│ │ 10.0.20.0/24                                       │   │
│ │ 10.1.62.0/24                                       │   │
│ │ ...                                                │   │
│ └────────────────────────────────────────────────────┘   │
│ ☑ 使用系统默认IP范围      [📁 从文件导入]                │
│                                                          │
│ 端口:                                                     │
│ ┌──────────────────────────┐  ☑ 使用系统默认端口         │
│ │ 22,80,443,3389,3306,...  │                              │
│ └──────────────────────────┘                              │
│                                                          │
│ ▶ 高级选项                                               │
│   并发线程数: [===10===]   超时时间: [700]秒              │
│   排除IP:     [📁 选择排除文件]                          │
│   通知设置:   ☑ 完成后发送邮件                           │
│              ☑ 发现高危端口时告警                        │
│                                                          │
│                    [ 开始扫描 ]  [ 保存为定时任务 ]       │
└──────────────────────────────────────────────────────────┘
```

### 5.4 报告对比功能详细设计

```
┌──────────────────────────────────────────────────────────┐
│ 📊 报告对比                                              │
├──────────────────────────────────────────────────────────┤
│ 报告A: [2026-05-09 每日巡检 ▼]   报告B: [2026-05-08 ▼]  │
├──────────────────────────────────────────────────────────┤
│                    对比结果                               │
│ ┌────────────────────────────────────────────────────┐   │
│ │ 📈 主机数量: 45 → 52  ↑ +7 (15.6%)                 │   │
│ │ 📈 端口数量: 128 → 156  ↑ +28 (21.9%)              │   │
│ ├────────────────────────────────────────────────────┤   │
│ │ 🆕 新增主机 (7 台):                                 │   │
│ │   10.0.20.55  [22, 80, 443]                        │   │
│ │   10.1.62.100 [3389]                                │   │
│ │   ...                                              │   │
│ ├────────────────────────────────────────────────────┤   │
│ │ 🔴 新增端口 (已在网络中的主机):                      │   │
│ │   10.0.20.10: +3306 (新增数据库端口!)               │   │
│ │   10.1.63.5:  +22 (新增SSH!)                        │   │
│ ├────────────────────────────────────────────────────┤   │
│ │ ✅ 已关闭端口:                                      │   │
│ │   10.30.221.8: -3389 (RDP已关闭)                    │   │
│ └────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

---

## 6. 数据库设计优化

### 6.1 表结构优化

```sql
-- 保持现有核心表，新增/优化以下：

-- 告警规则表
CREATE TABLE alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_name TEXT NOT NULL,
    rule_type TEXT NOT NULL,       -- 'port_open', 'new_host', 'port_change'
    condition_json TEXT NOT NULL,   -- 规则条件（JSON格式）
    notify_channels TEXT,           -- 通知渠道：'email,webhook'
    is_active BOOLEAN DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);

-- 通知历史表
CREATE TABLE notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,          -- 'email', 'webhook', 'dingtalk', 'wecom'
    recipient TEXT,
    subject TEXT,
    status TEXT,                   -- 'sent', 'failed'
    error_message TEXT,
    related_scan_id INTEGER,
    sent_at TEXT
);

-- 扫描对比记录表
CREATE TABLE scan_comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_a_id INTEGER NOT NULL,
    scan_b_id INTEGER NOT NULL,
    comparison_result TEXT,         -- JSON格式的对比结果
    created_at TEXT,
    FOREIGN KEY (scan_a_id) REFERENCES scan_records(id),
    FOREIGN KEY (scan_b_id) REFERENCES scan_records(id)
);

-- 系统事件日志表
CREATE TABLE system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,       -- 'scan_start', 'scan_complete', 'alert', 'error'
    event_level TEXT DEFAULT 'info', -- 'info', 'warning', 'error', 'critical'
    event_message TEXT,
    related_entity_type TEXT,       -- 'scan', 'scheduler', 'system'
    related_entity_id INTEGER,
    event_data TEXT,                -- JSON附加数据
    created_at TEXT
);
```

### 6.2 现有表优化

```sql
-- scheduled_tasks 表增加字段
ALTER TABLE scheduled_tasks ADD COLUMN notify_on_complete BOOLEAN DEFAULT 0;
ALTER TABLE scheduled_tasks ADD COLUMN notify_recipients TEXT;
ALTER TABLE scheduled_tasks ADD COLUMN alert_on_high_risk BOOLEAN DEFAULT 0;

-- users 表增加字段
ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'operator';  -- 'admin', 'operator', 'viewer'
ALTER TABLE users ADD COLUMN last_login_at TEXT;
ALTER TABLE users ADD COLUMN login_count INTEGER DEFAULT 0;
```

---

## 7. API 设计规范

### 7.1 URL 命名规范

```
/api/v1/资源/动作

# 示例
GET    /api/v1/scans              # 获取扫描历史列表
POST   /api/v1/scans              # 创建新扫描
GET    /api/v1/scans/:id          # 获取扫描详情
POST   /api/v1/scans/:id/stop     # 停止扫描
GET    /api/v1/scans/:id/results  # 获取扫描结果
DELETE /api/v1/scans/:id          # 删除扫描记录

POST   /api/v1/scans/compare      # 对比两次扫描

GET    /api/v1/scheduler/tasks    # 获取定时任务列表
POST   /api/v1/scheduler/tasks    # 创建定时任务
PUT    /api/v1/scheduler/tasks/:id # 更新定时任务
POST   /api/v1/scheduler/tasks/:id/run  # 立即执行

GET    /api/v1/reports            # 报告列表
GET    /api/v1/reports/:id        # 报告详情
GET    /api/v1/reports/:id/download # 下载报告
POST   /api/v1/reports/:id/send   # 发送报告

GET    /api/v1/alerts/rules       # 告警规则列表
POST   /api/v1/alerts/rules       # 创建告警规则

GET    /api/v1/logs               # 查询日志（支持过滤、分页）
GET    /api/v1/logs/download      # 下载日志

GET    /api/v1/system/health      # 健康检查
GET    /api/v1/system/stats       # 统计信息
```

### 7.2 统一响应格式

```json
{
    "code": 0,
    "message": "success",
    "data": {},
    "timestamp": "2026-05-09T12:00:00+08:00",
    "request_id": "uuid"
}
```

### 7.3 蓝图注册

```python
# server/routes/__init__.py
def register_blueprints(app):
    from server.routes.auth_routes import auth_bp
    from server.routes.scan_routes import scan_bp
    from server.routes.scheduler_routes import scheduler_bp
    from server.routes.report_routes import report_bp
    from server.routes.config_routes import config_bp
    from server.routes.dashboard_routes import dashboard_bp
    from server.routes.log_routes import log_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(scan_bp, url_prefix='/api/v1/scans')
    app.register_blueprint(scheduler_bp, url_prefix='/api/v1/scheduler')
    app.register_blueprint(report_bp, url_prefix='/api/v1/reports')
    app.register_blueprint(config_bp, url_prefix='/api/v1/config')
    app.register_blueprint(dashboard_bp, url_prefix='/api/v1')
    app.register_blueprint(log_bp, url_prefix='/api/v1/logs')
```

---

## 8. 关键流程设计

### 8.1 扫描任务完整流程

```
用户点击 [开始扫描]
       │
       ▼
Route: POST /api/v1/scans
       │ 参数校验
       ▼
TaskManager.submit_task(params)
       │
       ├─► 创建 TaskRecord (status=pending)
       ├─► 检查并发数
       │    ├─ 未达上限 → 立即启动
       │    └─ 已达上限 → 加入队列 (status=queued)
       │
       ▼
ScanExecutor.run(task)
       │
       ├─► 更新状态 (status=running)
       ├─► 加载 IP 范围 / 端口 / 排除IP
       ├─► 调用 Core Scanner 执行扫描
       │    ├─► 逐网段扫描（合并优化）
       │    ├─► 实时回调进度 → TaskManager → WebSocket/轮询 → 前端
       │    └─► 收集结果
       │
       ├─► 保存扫描结果到 DB
       ├─► 生成报告（异步）
       │    ├─► 加载模板
       │    ├─► 数据分析（端口分类、红区识别、风险评估）
       │    └─► 渲染 Word / TXT
       │
       ├─► 检查告警规则
       │    └─► 触发告警 → 通知渠道
       │
       ├─► 更新状态 (status=completed)
       └─► 通知 TaskManager → 启动下一个排队任务
```

### 8.2 定时任务执行流程

```
Scheduler Cron 触发
       │
       ▼
SchedulerService._execute_task(task_id)
       │
       ├─► 检查任务是否已在执行 → 跳过
       ├─► 获取任务配置
       │    ├─► use_default_config=True → 重新加载 YAML 配置
       │    └─► use_default_config=False → 使用任务自定义配置
       │
       ├─► 拼装扫描参数
       ├─► 调用 TaskManager.submit_task(params)
       │    └─► 与手动扫描走相同流程
       │
       ├─► 更新 next_run_time
       ├─► 记录执行日志
       └─► 发送通知（如果配置了）
```

### 8.3 报告对比流程

```
用户选择报告A + 报告B → 点击对比
       │
       ▼
ReportService.compare(scan_a_id, scan_b_id)
       │
       ├─► 从 DB 加载两次扫描的详细结果
       ├─► 对比分析：
       │    ├─► 新增主机:    IP_A中无，IP_B中有
       │    ├─► 消失主机:    IP_A中有，IP_B中无
       │    ├─► 新增端口:    同IP下端口新增
       │    └─► 关闭端口:    同IP下端口消失
       │
       ├─► 汇总统计
       │    ├─► 主机数变化
       │    ├─► 端口数变化
       │    └─► 风险等级变化
       │
       └─► 返回对比结果 → 前端渲染
```

---

## 9. 改造路线图

### Phase 1: 后端分层解耦（优先级：高）

| 任务 | 影响范围 | 风险 |
|------|---------|------|
| 1.1 拆分 app.py 为 Blueprint 路由 | 所有路由 | 中 |
| 1.2 拆分 scan_service 为 TaskManager + ScanExecutor | 扫描功能 | 中 |
| 1.3 重构 ConfigManager（YAML/DB/ENV 分层） | 配置管理 | 低 |
| 1.4 解决 Scheduler ↔ ScanService 循环依赖 | 定时任务 | 低 |

### Phase 2: 核心功能增强（优先级：高）

| 任务 | 说明 |
|------|------|
| 2.1 任务队列与并发控制 | 防止资源耗尽 |
| 2.2 健康检查 API | 实时感知系统状态 |
| 2.3 配置热加载完善 | 修改 YAML 无需重启（已部分实现） |
| 2.4 系统事件日志 | 审计追踪 |

### Phase 3: 前端重构（优先级：中）

| 任务 | 说明 |
|------|------|
| 3.1 引入 Pinia 状态管理 | 替代零散 reactive |
| 3.2 合并"扫描任务"和"扫描历史"为"扫描中心" | 功能内聚 |
| 3.3 仪表盘增加趋势图和实时状态 | 数据可视化 |
| 3.4 报告对比功能 | 新增核心功能 |

### Phase 4: 高级功能（优先级：低）

| 任务 | 说明 |
|------|------|
| 4.1 告警规则引擎 | 自动告警 |
| 4.2 多渠道通知（Webhook/钉钉/企微） | 扩展通知 |
| 4.3 角色权限分级 | 安全加固 |
| 4.4 实时日志查看 | 运维便利 |

---

## 附录：新旧对照

| 维度 | 现状 (v3.0) | 目标 (v4.0) |
|------|------------|------------|
| 后端架构 | 单文件 app.py (942行) | Blueprint 路由分层 (每个文件<200行) |
| 服务层 | scan_service 职责过重 | TaskManager + ScanExecutor + 5个专项服务 |
| 前端状态 | 零散 reactive | Pinia 统一管理 |
| 扫描入口 | "扫描任务"+"扫描历史"两个页面 | "扫描中心"一个页面，3个Tab |
| 报告功能 | 列表+下载 | 列表+预览+对比+批量管理 |
| 仪表盘 | 4个数字卡片 | 趋势图+实时状态+最近告警 |
| 通知渠道 | 仅邮件 | 邮件+Webhook+钉钉/企微 |
| 并发控制 | 无限制直接执行 | 队列+上限控制 |
| 日志查看 | 需SSH到服务器 | Web 前端实时查看 |
| 配置生效 | 大部分需重启 | 热加载（已部分实现） |
| 告警 | 无 | 规则引擎+自动通知 |
| 用户权限 | 仅管理员标记 | 管理员/操作员/只读三级 |

---

> **设计完，待评审。可根据实际需要选择部分或全部实施。**
