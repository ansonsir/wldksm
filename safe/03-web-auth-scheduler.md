# 安全审计报告 - 认证缺失与越权

## 文件: web/api/scheduler_api.py

### 漏洞 1: 定时任务 API 完全无认证

- **漏洞类型**: 越权漏洞（垂直越权）
- **严重程度**: 严重
- **行号**: 第 20-312 行（所有路由端点）

- **问题描述**: 
  **调度器 API 的所有端点都缺少认证装饰器**。这意味着任何可以访问服务的人（无需登录）都可以:
  - 查看所有定时任务 (`GET /api/scheduler/tasks`)
  - 创建/修改/删除定时任务 (`POST/PUT/DELETE`)
  - 立即执行扫描 (`POST /api/scheduler/tasks/:id/run`)
  - 停止正在运行的任务 (`POST /api/scheduler/tasks/:id/stop`)
  
  这是最严重的安全漏洞之一，攻击者可以随意创建扫描任务消耗系统资源，或删除所有定时任务。

- **问题代码**:
  ```python
  @scheduler_bp.route('/api/scheduler/tasks', methods=['GET'])
  # 缺少 @require_auth !!!
  def get_tasks():
      """获取所有定时任务"""
      active_only = request.args.get('active_only', 'false').lower() == 'true'
      tasks = scheduler.db.get_scheduled_tasks(active_only=active_only)
      # ...
  
  @scheduler_bp.route('/api/scheduler/tasks', methods=['POST'])
  # 缺少 @require_auth !!!
  def create_task():
      """创建定时任务"""
      # ...
  
  @scheduler_bp.route('/api/scheduler/tasks/<int:task_id>', methods=['PUT'])
  # 缺少 @require_auth !!!
  def update_task(task_id):
  
  @scheduler_bp.route('/api/scheduler/tasks/<int:task_id>', methods=['DELETE'])
  # 缺少 @require_auth !!!
  def delete_task(task_id):
  
  @scheduler_bp.route('/api/scheduler/tasks/<int:task_id>/run', methods=['POST'])
  # 缺少 @require_auth !!!
  def run_now(task_id):
  ```

- **修复建议**:
  ```python
  from web.middleware.auth_middleware import require_auth
  
  @scheduler_bp.route('/api/scheduler/tasks', methods=['GET'])
  @require_auth  # 添加认证
  def get_tasks():
      # ...
  
  @scheduler_bp.route('/api/scheduler/tasks', methods=['POST'])
  @require_auth
  def create_task():
      # ...
  
  @scheduler_bp.route('/api/scheduler/tasks/<int:task_id>', methods=['PUT'])
  @require_auth
  def update_task(task_id):
      # ...
  
  @scheduler_bp.route('/api/scheduler/tasks/<int:task_id>', methods=['DELETE'])
  @require_auth
  def delete_task(task_id):
      # ...
  
  @scheduler_bp.route('/api/scheduler/tasks/<int:task_id>/toggle', methods=['POST'])
  @require_auth
  def toggle_task(task_id):
      # ...
  
  @scheduler_bp.route('/api/scheduler/tasks/<int:task_id>/run', methods=['POST'])
  @require_auth
  def run_now(task_id):
      # ...
  
  @scheduler_bp.route('/api/scheduler/tasks/<int:task_id>/stop', methods=['POST'])
  @require_auth
  def stop_task(task_id):
      # ...
  ```

---

## 文件: web/routes/report_routes.py

### 漏洞 2: 模板管理接口缺少认证

- **漏洞类型**: 越权漏洞
- **严重程度**: 高危
- **行号**: 第 206-214 行、218-245 行、248-272 行、275-305 行

- **问题描述**: 
  以下模板相关接口全部缺少 `@require_auth` 装饰器:
  - `GET /api/templates` (第206行) - 未认证可查看模板列表
  - `POST /api/templates/upload` (第218行) - 未认证可上传文件
  - `POST /api/templates/delete` (第248行) - 未认证可删除文件
  - `POST /api/templates/preview` (第275行) - 未认证可预览文件内容

- **修复建议**:
  ```python
  @report_bp.route('/api/templates', methods=['GET'])
  @require_auth  # 添加认证
  def get_templates():
  
  @report_bp.route('/api/templates/upload', methods=['POST'])
  @require_auth  # 添加认证
  def upload_template():
  
  @report_bp.route('/api/templates/delete', methods=['POST'])
  @require_auth  # 添加认证
  def delete_template():
  
  @report_bp.route('/api/templates/preview', methods=['POST'])
  @require_auth  # 添加认证
  def preview_template():
  ```

---

## 文件: web/routes/dashboard_routes.py

### 漏洞 3: 统计数据接口缺少认证

- **漏洞类型**: 敏感信息泄露
- **严重程度**: 中危
- **行号**: 第 25-155 行

- **问题描述**: 
  `/api/stats` 接口未添加 `@require_auth` 装饰器，未认证用户可以获取详细的仪表盘统计信息，包括:
  - 扫描总次数、成功率
  - 今日扫描数据
  - 7天趋势数据
  - 端口风险等级分布
  - 漏洞主机 Top 10
  - 定时任务汇总
  
  这些信息属于内部运维数据，泄露后可能被攻击者用于侦察。

- **修复建议**:
  ```python
  @dashboard_bp.route('/api/stats', methods=['GET'])
  @require_auth  # 添加认证
  def get_stats():
      # ...
  
  @dashboard_bp.route('/api/assets/compare', methods=['POST'])
  @require_auth
  def compare_assets():
      # ...
  
  @dashboard_bp.route('/api/assets/trend', methods=['GET'])
  @require_auth
  def get_asset_trend():
      # ...
  
  @dashboard_bp.route('/api/assets/summary', methods=['GET'])
  @require_auth
  def get_asset_summary():
      # ...
  ```
