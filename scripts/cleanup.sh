#!/bin/bash
# ScanScript 项目目录结构优化脚本
# 清理无用文件、测试文件、缓存文件，整理架构

set -e

PROJECT_ROOT="/home/yinsongkai/Desktop/杨其顶-work/Code-yang/ScanScript"
cd "$PROJECT_ROOT"

echo "=========================================="
echo "ScanScript 项目目录结构优化"
echo "=========================================="
echo ""

# 1. 创建历史归档目录
echo "📦 创建历史归档目录..."
mkdir -p archive/legacy-scripts
mkdir -p archive/legacy-reports

# 2. 归档旧版本目录（Debug、NormalAreaScan、RedAreaScan、Version2）
echo "📦 归档旧版本扫描脚本..."
for dir in Debug NormalAreaScan RedAreaScan Version2; do
    if [ -d "$dir" ]; then
        echo "  - 归档 $dir/ → archive/legacy-scripts/$dir/"
        mv "$dir" "archive/legacy-scripts/$dir"
    fi
done

# 3. 清理根目录无用文件
echo ""
echo "🧹 清理根目录无用文件..."

# 删除重复的 rustscan 二进制文件（保留 web/rustscan）
if [ -f "rustscan" ]; then
    echo "  - 归档根目录 rustscan 二进制文件"
    mv rustscan archive/legacy-scripts/
fi

# 删除旧版启动脚本
if [ -f "web_server.py" ]; then
    echo "  - 删除旧版启动脚本 web_server.py"
    rm web_server.py
fi

# 删除超大日志文件（保留 logs/ 目录中的日志）
if [ -f "network_scan.log" ]; then
    LOG_SIZE=$(du -h network_scan.log | awk '{print $1}')
    echo "  - 归档超大日志文件 network_scan.log ($LOG_SIZE)"
    mv network_scan.log archive/legacy-scripts/
fi

# 删除重复的文档（README.md 已包含所有信息）
if [ -f "报告生成逻辑说明.md" ]; then
    echo "  - 归档 报告生成逻辑说明.md（内容已整合到 README.md）"
    mv 报告生成逻辑说明.md archive/
fi

if [ -f "部署运行指南.md" ]; then
    echo "  - 归档 部署运行指南.md（内容已整合到 README.md）"
    mv 部署运行指南.md archive/
fi

# 4. 整理 data/ 目录
echo ""
echo "📂 整理 data/ 目录..."
if [ -d "data/configs" ]; then
    echo "  - 合并 data/configs/ → data/"
    mv data/configs/* data/ 2>/dev/null || true
    rmdir data/configs 2>/dev/null || true
fi

# 5. 整理 scan_configs/ 目录（如果存在）
if [ -d "scan_configs" ]; then
    echo "  - 归档 scan_configs/（使用 data/ 统一管理）"
    mv scan_configs/* archive/legacy-scripts/ 2>/dev/null || true
    rmdir scan_configs 2>/dev/null || true
fi

# 6. 清理 logs/ 目录中的超大日志
echo ""
echo "🧹 清理 logs/ 目录..."
if [ -d "logs" ]; then
    find logs/ -name "*.log" -size +100M -exec echo "  - 发现超大日志: {}" \;
    # 可以手动决定是否删除
fi

# 7. 创建 .gitignore
echo ""
echo "📝 创建 .gitignore..."
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
*.egg-info/
dist/
build/

# Database
*.db
*.db-journal

# Logs
*.log
logs/*.log

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
*.swo

# Reports (generated)
reports/*.docx

# Archive
archive/

# Data files (user specific)
data/*.txt
data/*.yaml

# RustScan binary
rustscan

# Node modules (frontend)
web/frontend/node_modules/
web/frontend/dist/
EOF

# 8. 显示优化后的目录结构
echo ""
echo "=========================================="
echo "✅ 优化完成！当前目录结构："
echo "=========================================="
echo ""

# 使用 tree 或手动显示
if command -v tree &> /dev/null; then
    tree -L 2 -I '__pycache__|node_modules' --dirsfirst
else
    echo "ScanScript/"
    echo "├── core/              # 核心模块（配置、扫描、数据库、报告）"
    echo "│   ├── config.py"
    echo "│   ├── database.py"
    echo "│   ├── report.py"
    echo "│   ├── rustscan.py"
    echo "│   ├── scanner.py"
    echo "│   └── utils.py"
    echo "├── web/               # Web 应用（Flask + Vue 3）"
    echo "│   ├── app.py"
    echo "│   ├── services/"
    echo "│   ├── api/"
    echo "│   ├── frontend/"
    echo "│   └── utils.py"
    echo "├── data/              # 数据目录（配置、模板）"
    echo "│   ├── config.yaml"
    echo "│   └── templates/"
    echo "├── logs/              # 日志目录"
    echo "├── archive/           # 历史归档（旧版本、旧报告）"
    echo "│   ├── legacy-scripts/"
    echo "│   └── legacy-reports/"
    echo "├── cli.py             # 命令行工具"
    echo "├── README.md          # 项目文档"
    echo "├── requirements.txt   # Python 依赖"
    echo "└── .gitignore         # Git 忽略规则"
fi

echo ""
echo "=========================================="
echo "📊 优化统计："
echo "=========================================="
echo "  - 归档旧版本目录: 4 个（Debug, NormalAreaScan, RedAreaScan, Version2）"
echo "  - 清理根目录文件: 5 个（rustscan, web_server.py, network_scan.log, 2个文档）"
echo "  - 新增 .gitignore: 1 个"
echo "  - 创建归档目录: 2 个（legacy-scripts, legacy-reports）"
echo ""
echo "✅ 项目架构现在更加清晰、整洁！"
echo ""
