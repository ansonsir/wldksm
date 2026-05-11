<template>
  <div class="page-container">
    <PageHeader title="定时任务" subtitle="管理自动化定时扫描任务" icon="Clock">
      <template #extra>
        <el-button type="primary" @click="showCreateDialog">
          <el-icon><Plus /></el-icon> 创建任务
        </el-button>
      </template>
    </PageHeader>

    <el-card>
      <!-- 统计汇总 -->
      <el-row :gutter="16" style="margin-bottom:16px">
        <el-col :span="6">
          <div class="summary-item blue">
            <span class="summary-val">{{ tasks.length }}</span>
            <span class="summary-label">总任务</span>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="summary-item green">
            <span class="summary-val">{{ tasks.filter(t => t.is_active).length }}</span>
            <span class="summary-label">已启用</span>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="summary-item orange">
            <span class="summary-val">{{ tasks.filter(t => t.last_run_status === 'running').length }}</span>
            <span class="summary-label">运行中</span>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="summary-item red">
            <span class="summary-val">{{ tasks.filter(t => t.last_run_status === 'failed').length }}</span>
            <span class="summary-label">失败</span>
          </div>
        </el-col>
      </el-row>

      <el-table :data="tasks" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="50" />
        <el-table-column prop="task_name" label="任务名称" width="140" show-overflow-tooltip />
        <el-table-column label="类型" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="typeColor(row.task_type)" size="small" effect="plain">{{ typeLabel(row.task_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="schedule_expr" label="调度表达式" width="130" />
        <el-table-column label="配置" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.use_default_config ? 'success' : 'warning'" size="small" effect="plain">
              {{ row.use_default_config ? '默认' : '自定义' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="下次执行" width="155">
          <template #default="{ row }">{{ row.next_run_time || '-' }}</template>
        </el-table-column>
        <el-table-column label="执行统计" width="170" align="center">
          <template #default="{ row }">
            <span style="font-size:12px">
              <span style="color:#909399">总{{ row.total_runs }}</span> &nbsp;
              <span style="color:#67C23A">✓{{ row.total_success }}</span> &nbsp;
              <span style="color:#F56C6C">✗{{ row.total_failed }}</span>
            </span>
          </template>
        </el-table-column>
        <el-table-column label="上次状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.last_run_status" :type="statusColor(row.last_run_status)" size="small" effect="plain">
              {{ statusLabel(row.last_run_status) }}
            </el-tag>
            <span v-else style="color:#c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="65" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.is_active" size="small" @change="toggleTask(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right" align="center">
          <template #default="{ row }">
            <el-button v-if="row.last_run_status === 'running'" size="small" type="danger" @click="stopTask(row)">停止</el-button>
            <el-button v-else size="small" @click="runNow(row)">立即执行</el-button>
            <el-button size="small" type="primary" @click="showEditDialog(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteTask(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑定时任务' : '创建定时任务'"
      width="680px"
    >
      <el-form :model="form" label-width="120px">
        <el-form-item label="任务名称" required>
          <el-input v-model="form.task_name" placeholder="例如：每日凌晨扫描" />
        </el-form-item>
        <el-form-item label="调度类型" required>
          <el-select v-model="form.task_type" @change="onTypeChange" style="width:100%">
            <el-option label="Cron 定时任务" value="cron" />
            <el-option label="间隔执行" value="interval" />
            <el-option label="一次性执行" value="once" />
          </el-select>
        </el-form-item>
        <el-form-item :label="scheduleLabel" required>
          <el-input v-model="form.schedule_expr" :placeholder="schedulePlaceholder" />
          <div style="color:#909399;font-size:12px;margin-top:4px">{{ scheduleHint }}</div>
        </el-form-item>
        <el-form-item label="配置方式">
          <el-radio-group v-model="form.use_default_config">
            <el-radio :label="true">系统默认</el-radio>
            <el-radio :label="false">自定义</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="!form.use_default_config">
          <el-divider content-position="left">自定义扫描参数</el-divider>
          <el-form-item label="IP范围">
            <el-input v-model="form.ip_ranges" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="端口">
            <el-input v-model="form.ports" placeholder="22,80,443 或 1-65535" />
          </el-form-item>
          <el-form-item label="排除IP">
            <el-input v-model="form.exclude_ips" placeholder="逗号分隔" />
          </el-form-item>
          <el-form-item label="线程数">
            <el-input-number v-model="form.max_workers" :min="1" :max="50" size="small" />
          </el-form-item>
          <el-form-item label="Ulimit">
            <el-input-number v-model="form.ulimit" :min="1000" :max="100000" :step="1000" size="small" />
          </el-form-item>
          <el-form-item label="超时(秒)">
            <el-input-number v-model="form.timeout" :min="60" :max="3600" :step="60" size="small" />
          </el-form-item>
        </template>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">
          {{ isEdit ? '更新' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import axios from 'axios'

const tasks = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)
const editingId = ref(null)

const form = reactive({
  task_name: '', task_type: 'cron', schedule_expr: '', use_default_config: true,
  ip_ranges: '', ports: '', exclude_ips: '', max_workers: 10, ulimit: 15000, timeout: 700, is_active: true,
})

const scheduleLabel = computed(() => ({ cron: 'Cron 表达式', interval: '间隔时间', once: '执行时间' }[form.task_type]))
const schedulePlaceholder = computed(() => ({ cron: '0 2 * * *（每天2点）', interval: '24h, 6h, 30m, 7d', once: '2024-01-15 09:00:00' }[form.task_type]))
const scheduleHint = computed(() => ({ cron: '分 时 日 月 周', interval: '数字+单位(h/m/d)', once: 'YYYY-MM-DD HH:MM:SS' }[form.task_type]))

const loadTasks = async () => {
  loading.value = true
  try {
    const res = await axios.get('/api/scheduler/tasks')
    if (res.data.success) tasks.value = res.data.data
  } catch (e) { ElMessage.error('加载失败') }
  finally { loading.value = false }
}

const showCreateDialog = () => {
  isEdit.value = false; editingId.value = null
  Object.assign(form, { task_name: '', task_type: 'cron', schedule_expr: '', use_default_config: true, ip_ranges: '', ports: '', exclude_ips: '', max_workers: 10, ulimit: 15000, timeout: 700, is_active: true })
  dialogVisible.value = true
}

const showEditDialog = (row) => {
  isEdit.value = true; editingId.value = row.id
  Object.assign(form, { task_name: row.task_name, task_type: row.task_type, schedule_expr: row.schedule_expr, use_default_config: row.use_default_config, ip_ranges: row.ip_ranges || '', ports: row.ports || '', exclude_ips: row.exclude_ips || '', max_workers: row.max_workers || 10, ulimit: row.ulimit || 15000, timeout: row.timeout || 700, is_active: row.is_active })
  dialogVisible.value = true
}

const onTypeChange = () => { form.schedule_expr = '' }

const submitForm = async () => {
  if (!form.task_name) return ElMessage.warning('请输入任务名称')
  if (!form.schedule_expr) return ElMessage.warning('请输入调度表达式')
  submitting.value = true
  try {
    if (isEdit.value) { await axios.put(`/api/scheduler/tasks/${editingId.value}`, form); ElMessage.success('已更新') }
    else { await axios.post('/api/scheduler/tasks', form); ElMessage.success('已创建') }
    dialogVisible.value = false; loadTasks()
  } catch (e) { ElMessage.error(e.response?.data?.message || '操作失败') }
  finally { submitting.value = false }
}

const toggleTask = async (row) => {
  try {
    await axios.post(`/api/scheduler/tasks/${row.id}/toggle`)
    ElMessage.success(row.is_active ? '已启用' : '已禁用')
  } catch (e) { ElMessage.error('操作失败'); row.is_active = !row.is_active }
}

const runNow = async (row) => {
  try {
    await ElMessageBox.confirm('确定立即执行？', '提示', { type: 'warning' })
    const res = await axios.post(`/api/scheduler/tasks/${row.id}/run`)
    if (res.data.success) { ElMessage.success('已开始执行'); loadTasks() }
  } catch (e) { if (e !== 'cancel') ElMessage.error(e.response?.data?.message || '失败') }
}

const stopTask = async (row) => {
  try {
    await ElMessageBox.confirm('确定停止该任务？', '警告', { type: 'error', confirmButtonText: '停止', cancelButtonText: '取消' })
    await axios.post(`/api/scheduler/tasks/${row.id}/stop`)
    ElMessage.success('已停止'); loadTasks()
  } catch (e) { if (e !== 'cancel') ElMessage.error('停止失败') }
}

const deleteTask = async (row) => {
  try {
    await ElMessageBox.confirm('确定删除该任务？', '警告', { type: 'warning' })
    await axios.delete(`/api/scheduler/tasks/${row.id}`)
    ElMessage.success('已删除'); loadTasks()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

const typeLabel = (t) => ({ cron: 'Cron', interval: '间隔', once: '一次性' }[t] || t)
const typeColor = (t) => ({ cron: 'primary', interval: 'success', once: 'info' }[t] || '')
const statusLabel = (s) => ({ success: '成功', failed: '失败', skipped: '跳过', running: '运行中' }[s] || s)
const statusColor = (s) => ({ success: 'success', failed: 'danger', skipped: 'info', running: 'warning' }[s] || '')

onMounted(loadTasks)
</script>

<style scoped>
.summary-item {
  text-align: center;
  padding: 14px 10px;
  border-radius: 10px;
  background: #f9fafb;
  border: 1px solid #e8eaed;
}
.summary-val {
  display: block;
  font-size: 24px;
  font-weight: 700;
}
.summary-label { font-size: 12px; color: #909399; }
.blue .summary-val { color: #409eff; }
.green .summary-val { color: #67c23a; }
.orange .summary-val { color: #e6a23c; }
.red .summary-val { color: #f56c6c; }
</style>
