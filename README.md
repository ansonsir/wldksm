# 网络端口扫描工具 (ScanScript)

## 📖 项目简介

基于 RustScan 的高性能网络端口扫描工具，支持 Web 界面管理、批量扫描、报告生成和邮件通知。

## ✨ 核心功能

- **高性能扫描**：基于 RustScan，支持并发扫描
- **多格式 IP 输入**：支持单个 IP、多个 IP、IP 段、CIDR 掩码
- **多格式端口输入**：支持单个端口、多个端口、端口段
- **多文件配置**：支持多个 IP 范围文件配置
- **Web 管理界面**：Vue 3 + Element Plus 前端
- **报告生成**：自动生成 Word 格式扫描报告
- **邮件通知**：支持 SMTP 邮件发送报告
- **数据库存储**：扫描记录和配置持久化

## 🚀 快速开始

### 环境要求

- Python 3.8+
- RustScan（已安装到系统）
- Node.js 16+（仅开发时需要）

### 安装依赖

```bash
cd /home/yinsongkai/Desktop/杨其顶-work/Code-yang/ScanScript
pip install -r requirements.txt
```

### 启动服务

```bash
# 启动 Web 服务
cd /home/yinsongkai/Desktop/杨其顶-work/Code-yang/ScanScript
nohup python3 web/app.py > logs/web_server.log 2>&1 &

# 查看服务状态
lsof -ti:5000

# 查看日志
tail -f logs/web_server.log
```

### 访问界面

浏览器访问：`http://localhost:5000`

## 🔧 服务管理

### 启动服务

```bash
# 方式 1：后台启动（推荐）
cd /home/yinsongkai/Desktop/杨其顶-work/Code-yang/ScanScript
nohup python3 web/app.py > logs/web_server.log 2>&1 &

# 方式 2：前台启动（调试用）
cd /home/yinsongkai/Desktop/杨其顶-work/Code-yang/ScanScript
python3 web/app.py
```

### 停止服务

```bash
# 方式 1：优雅停止（推荐）
kill $(lsof -ti:5000)

# 方式 2：强制停止
kill -9 $(lsof -ti:5000)
```

### 重启服务

```bash
# 方式 1：平滑重启
kill $(lsof -ti:5000)
sleep 2
nohup python3 web/app.py > logs/web_server.log 2>&1 &

# 方式 2：一键重启脚本
kill $(lsof -ti:5000) 2>/dev/null; sleep 2; \
cd /home/yinsongkai/Desktop/杨其顶-work/Code-yang/ScanScript && \
nohup python3 web/app.py > logs/web_server.log 2>&1 &
```

### 查看服务状态

```bash
# 检查端口占用
lsof -ti:5000

# 查看进程信息
ps aux | grep "web/app.py" | grep -v grep

# 查看服务日志
tail -f logs/web_server.log

# 测试 API
curl -s http://localhost:5000/api/config | python3 -m json.tool
```

## 🛑 进程管理

### 扫描进程控制

#### 停止扫描任务

**Web 界面操作**：
1. 进入"扫描任务"页面
2. 点击"停止扫描"按钮

**后台处理**：
- 设置停止标志位
- 强制终止所有 RustScan 子进程
- 取消未开始的扫描任务

#### 强制终止扫描进程

```bash
# 查看所有 RustScan 进程
ps aux | grep rustscan | grep -v grep

# 优雅停止所有 RustScan 进程
pkill -15 -f rustscan

# 强制杀死所有 RustScan 进程（推荐）
pkill -9 -f rustscan

# 查看是否还有残留进程
ps aux | grep rustscan | grep -v grep
```

### 子进程管理

#### 查看子进程

```bash
# 查看 Flask 主进程及其子进程
ps aux | grep "web/app.py" | grep -v grep

# 查看 RustScan 子进程
ps aux | grep rustscan | grep -v grep

# 查看进程树
pstree -p $(lsof -ti:5000)
```

#### 强制清理所有相关进程

```bash
# 停止 Web 服务
kill -9 $(lsof -ti:5000) 2>/dev/null

# 强制终止所有 RustScan 进程
pkill -9 -f rustscan 2>/dev/null

# 清理可能的残留 Python 进程
pkill -9 -f "python3 web/app.py" 2>/dev/null

# 验证所有进程已清理
ps aux | grep -E "(rustscan|web/app.py)" | grep -v grep
```

### 进程信号说明

| 信号 | 命令 | 说明 |
|------|------|------|
| SIGTERM (15) | `kill -15 <pid>` | 优雅停止，等待清理 |
| SIGKILL (9) | `kill -9 <pid>` | 强制终止，立即杀死 |
| SIGHUP (1) | `kill -1 <pid>` | 重新加载配置 |

**推荐做法**：
1. 先尝试 SIGTERM（优雅停止）
2. 等待 3 秒
3. 如果未停止，使用 SIGKILL（强制终止）

```bash
# 优雅停止
kill -15 $(lsof -ti:5000)
sleep 3

# 检查是否停止
if lsof -ti:5000 > /dev/null 2>&1; then
    echo "服务未停止，强制终止..."
    kill -9 $(lsof -ti:5000)
fi
```

## 📁 项目结构

```
ScanScript/
├── core/                      # 核心模块
│   ├── config.py             # 配置管理
│   ├── database.py           # 数据库管理
│   ├── rustscan.py           # RustScan API 封装
│   ├── scanner.py            # 扫描引擎
│   ├── report.py             # 报告生成
│   └── utils.py              # 工具函数
├── web/                       # Web 服务
│   ├── app.py                # Flask 应用主入口
│   ├── mail_service.py       # 邮件服务
│   ├── services/             # 业务服务
│   │   └── scan_service.py   # 扫描任务管理
│   └── frontend/             # Vue 3 前端
│       ├── src/              # 源代码
│       └── dist/             # 构建产物
├── data/                      # 数据目录
│   ├── config.yaml           # 系统配置文件
│   ├── scan_data.db          # SQLite 数据库
│   ├── ip_ranges.txt         # IP 范围配置
│   ├── ports.txt             # 端口配置
│   ├── excludes.txt          # 排除 IP 配置
│   ├── redarea.txt           # 红区网段配置
│   ├── templates/            # 报告模板
│   └── reports/              # 生成的报告
├── logs/                      # 日志目录
│   ├── web_server.log        # Web 服务日志
│   └── network_scan.log      # 扫描日志
├── archive/                   # 归档目录（历史版本）
├── scripts/                   # 脚本目录
├── cli.py                     # 命令行工具
└── requirements.txt           # Python 依赖
```

## ⚙️ 配置说明

### 系统配置

配置文件：`data/config.yaml`

```yaml
# IP 范围配置（支持多文件，逗号分隔）
ip_range_file: data/ip_ranges.txt,data/redarea.txt

# 排除 IP 配置
exclude_ips_file: data/excludes.txt

# 端口配置
ports_file: data/ports.txt

# 扫描参数
max_workers: 10          # 并发线程数
ulimit: 15000           # 文件描述符限制
timeout: 700            # 扫描超时（秒）
batch_size: 14000       # 批次大小

# 邮件配置（通过 Web 界面配置，保存到数据库）
smtp_server: ''
smtp_port: 587
smtp_user: ''
smtp_password: ''
smtp_ssl: true
```

### IP 范围配置

**支持的格式**：

1. **单个 IP**：`192.168.1.1`
2. **多个 IP**（换行分隔）：
   ```
   192.168.1.1
   192.168.1.2
   ```
3. **IP 地址段**：`192.168.1.1-192.168.1.100`
4. **CIDR 掩码**：`10.0.0.0/24`
5. **混合格式**：可以任意组合

**多文件配置**：
```yaml
# data/config.yaml
ip_range_file: data/ip_ranges.txt,data/redarea.txt
```

### 端口配置

**支持的格式**：

1. **单个端口**：`80`
2. **多个端口**（逗号分隔）：`22,80,443,3389`
3. **端口段**：`1-65535`
4. **文件格式**（换行分隔）：从 `data/ports.txt` 读取

**注意**：混合格式（如 `22,80,8000-9000`）不被 RustScan 支持。

## 📊 使用示例

### Web 界面扫描

1. **访问界面**：`http://localhost:5000`
2. **扫描任务**：
   - IP 范围：留空（使用系统配置）或自定义
   - 端口：留空（使用系统配置）或自定义
   - 并发线程：调整并发数
   - 点击"开始扫描"
3. **查看进度**：实时显示扫描进度和结果
4. **下载报告**：扫描完成后生成 Word 报告

### 命令行扫描

```bash
# 使用默认配置扫描
python3 cli.py

# 指定 IP 范围
python3 cli.py --ip-ranges "10.0.0.0/24"

# 指定端口
python3 cli.py --ports "22,80,443"

# 全端口扫描
python3 cli.py --ports "1-65535"
```

## 🔍 故障排查

### 服务无法启动

```bash
# 检查端口是否被占用
lsof -ti:5000

# 如果端口被占用，停止旧服务
kill -9 $(lsof -ti:5000)

# 检查 Python 依赖
pip install -r requirements.txt

# 查看详细错误
python3 web/app.py
```

### 扫描结果为空

```bash
# 检查 RustScan 是否安装
which rustscan
rustscan --version

# 检查扫描日志
tail -f logs/network_scan.log

# 检查 IP 范围配置
head -10 data/ip_ranges.txt

# 测试单个 IP 扫描
curl -X POST http://localhost:5000/api/scan/start \
  -H "Content-Type: application/json" \
  -d '{"ip_ranges": "10.10.104.86", "ports": "5000"}'
```

### 邮件配置丢失

```bash
# 检查数据库中的邮件配置
sqlite3 data/scan_data.db "SELECT * FROM email_settings;"

# 查看服务日志
grep "数据库加载" logs/web_server.log

# 重新配置邮件
# 通过 Web 界面：系统配置 -> 邮件配置
```

### 进程无法终止

```bash
# 查找所有相关进程
ps aux | grep -E "(rustscan|web/app.py)" | grep -v grep

# 强制终止所有进程
pkill -9 -f rustscan
pkill -9 -f "python3 web/app.py"

# 验证进程已清理
ps aux | grep -E "(rustscan|web/app.py)" | grep -v grep
```

## 🛠️ 开发指南

### 前端开发

```bash
cd web/frontend

# 安装依赖
npm install

# 开发模式
npm run dev

# 构建生产版本
npm run build
```

### 后端开发

```bash
# 安装依赖
pip install -r requirements.txt

# 运行测试
python3 -m pytest

# 代码检查
flake8 core/ web/
```

## 📝 数据库管理

### 查看数据库

```bash
# 使用 sqlite3 查看
sqlite3 data/scan_data.db

# 查看所有表
.tables

# 查看邮件配置
SELECT * FROM email_settings;

# 查看扫描记录
SELECT * FROM scan_records ORDER BY start_time DESC LIMIT 10;
```

### 备份数据库

```bash
# 备份数据库
cp data/scan_data.db data/scan_data.db.backup.$(date +%Y%m%d)

# 恢复数据库
cp data/scan_data.db.backup.20260430 data/scan_data.db
```

## 🔒 安全建议

1. **修改默认端口**：不要使用 5000 端口
2. **配置防火墙**：限制访问 IP
3. **定期备份**：备份数据库和配置文件
4. **密码安全**：邮件密码存储在数据库，注意保护
5. **日志管理**：定期清理日志文件

## 📞 技术支持

- **日志位置**：`logs/web_server.log` 和 `logs/network_scan.log`
- **数据库位置**：`data/scan_data.db`
- **配置文件**：`data/config.yaml`

## 📄 许可证

本项目仅供内部使用。
