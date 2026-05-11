<template>
  <div class="page-container">
    <PageHeader title="扫描任务" subtitle="配置扫描参数并启动新的端口扫描任务" icon="Aim" />

    <el-card>
      <el-form :model="scanForm" label-width="110px" label-position="top" class="scan-form">
        <!-- 策略模板选择 -->
        <el-form-item label="扫描策略">
          <div class="policy-selector">
            <div
              v-for="policy in policies"
              :key="policy.id"
              class="policy-card"
              :class="{ active: selectedPolicy === policy.id }"
              @click="applyPolicy(policy)"
            >
              <div class="policy-name">{{ policy.name }}</div>
              <div class="policy-desc">{{ policy.description }}</div>
            </div>
            <div
              class="policy-card"
              :class="{ active: selectedPolicy === 'custom' }"
              @click="selectedPolicy = 'custom'"
            >
              <div class="policy-name">自定义</div>
              <div class="policy-desc">手动配置所有扫描参数</div>
            </div>
          </div>
        </el-form-item>

        <el-row :gutter="24">
          <el-col :span="16">
            <el-form-item label="IP 范围">
              <el-input
                v-model="scanForm.ip_ranges"
                type="textarea"
                :rows="6"
                placeholder="支持多种格式（每行一个）：&#10;1. 单个IP: 192.168.1.1&#10;2. 多个IP: 每行一个&#10;3. IP段: 192.168.1.1-192.168.1.100&#10;4. CIDR: 10.0.0.0/24&#10;&#10;留空将自动加载系统默认配置"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="端口">
              <el-input
                v-model="scanForm.ports"
                placeholder="单端口: 80&#10;多端口: 22,80,443&#10;端口段: 1-65535&#10;&#10;留空使用系统默认"
                type="textarea"
                :rows="6"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item label="排除 IP">
              <el-input
                v-model="scanForm.exclude_ips"
                placeholder="排除的IP，逗号分隔，留空从配置加载"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="并发线程">
              <el-slider v-model="scanForm.max_workers" :min="1" :max="64" show-input :show-input-controls="false" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item>
          <div class="scan-actions">
            <el-button type="primary" size="large" @click="startScan" :loading="scanning" :disabled="scanning">
              <el-icon><VideoPlay /></el-icon> 开始扫描
            </el-button>
            <el-button size="large" @click="stopScan" :disabled="!scanning || !currentTaskId" type="danger">
              <el-icon><VideoPause /></el-icon> 停止扫描
            </el-button>
          </div>
        </el-form-item>
      </el-form>

      <!-- 扫描进度 -->
      <div v-if="scanning || scanCompleted" class="scan-progress">
        <div class="progress-header">
          <span class="progress-title">
            <el-icon v-if="scanning" class="is-loading"><Loading /></el-icon>
            <el-icon v-else-if="scanCompleted" style="color:#67c23a"><CircleCheck /></el-icon>
            {{ scanning ? '扫描进行中' : '扫描完成' }}
          </span>
          <el-tag v-if="scanning" type="warning" size="small" effect="dark">进行中</el-tag>
          <el-tag v-else type="success" size="small" effect="dark">已完成</el-tag>
        </div>
        <el-progress :percentage="scanProgress" :status="scanProgressStatus" :stroke-width="10" />
        <div class="progress-info">{{ scanMessage }}</div>
      </div>

      <!-- 扫描日志 -->
      <div v-if="scanLogs.length > 0" style="margin-top:20px">
        <h4 style="margin:0 0 8px;font-size:14px;color:#303133">扫描日志</h4>
        <div class="log-container">{{ scanLogs.join('\n') }}</div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPlay, VideoPause, Loading, CircleCheck } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import api from '@/api'

const scanForm = reactive({
  ip_ranges: '',
  ports: '',
  exclude_ips: '',
  max_workers: 32,
})

const policies = ref([])
const selectedPolicy = ref('')

const scanning = ref(false)
const scanCompleted = ref(false)
const currentTaskId = ref('')
const scanProgress = ref(0)
const scanMessage = ref('')
const scanLogs = ref([])
let scanStatusTimer = null
let lastProgress = 0
let consecutiveSameProgress = 0
let currentPollInterval = 2000

const scanProgressStatus = computed(() => scanCompleted.value ? 'success' : '')

const formatTime = (s) => {
  if (!s || s < 0) return '0秒'
  const m = Math.floor(s / 60)
  return m > 0 ? `${m}分${s % 60}秒` : `${s}秒`
}

const loadScanDefaults = async () => {
  try {
    const res = await api.get('/api/scan/defaults')
    if (res.success) {
      const d = res.data
      if (!scanForm.ip_ranges && d.ip_ranges) scanForm.ip_ranges = d.ip_ranges
      if (!scanForm.ports && d.ports) scanForm.ports = d.ports
      if (!scanForm.exclude_ips && d.exclude_ips) scanForm.exclude_ips = d.exclude_ips
      if (d.max_workers) scanForm.max_workers = d.max_workers
    }
  } catch (e) {}
}

const loadPolicies = async () => {
  try {
    const res = await api.get('/api/scan/policies')
    if (res.success) {
      policies.value = res.data
    }
  } catch (e) {}
}

const applyPolicy = (policy) => {
  selectedPolicy.value = policy.id
  scanForm.ports = policy.ports
  scanForm.max_workers = policy.max_workers
}

const startScan = async () => {
  scanning.value = true
  scanCompleted.value = false
  scanProgress.value = 0
  scanMessage.value = '正在启动...'
  scanLogs.value = []

  try {
    const res = await api.post('/api/scan/start', {
      ip_ranges: scanForm.ip_ranges,
      ports: scanForm.ports,
      exclude_ips: scanForm.exclude_ips,
      max_workers: scanForm.max_workers,
    })
    if (res.success) {
      currentTaskId.value = res.data.task_id
      localStorage.setItem('running_task_id', res.data.task_id)
      ElMessage.success('扫描任务已启动')
      startStatusPolling()
    } else {
      ElMessage.error(res.message)
      scanning.value = false
      localStorage.removeItem('running_task_id')
    }
  } catch (e) {
    scanning.value = false
    localStorage.removeItem('running_task_id')
  }
}

const stopScan = async () => {
  if (!currentTaskId.value) return
  try {
    await api.post(`/api/scan/stop/${currentTaskId.value}`)
    ElMessage.info('已发送停止请求')
  } catch (e) {}
}

const startStatusPolling = () => {
  if (scanStatusTimer) clearInterval(scanStatusTimer)
  lastProgress = 0
  consecutiveSameProgress = 0
  currentPollInterval = 2000

  const poll = async () => {
    if (!currentTaskId.value) { clearInterval(scanStatusTimer); return }
    try {
      const res = await api.get(`/api/scan/status/${currentTaskId.value}`)
      if (res.success) {
        const d = res.data
        scanProgress.value = Math.round((d.progress / d.total) * 100) || 0
        if (d.status === 'running') {
          if (d.progress === lastProgress) {
            consecutiveSameProgress++
            if (consecutiveSameProgress >= 3) currentPollInterval = Math.min(currentPollInterval * 1.5, 10000)
          } else {
            consecutiveSameProgress = 0
            currentPollInterval = Math.max(currentPollInterval * 0.8, 1000)
          }
          lastProgress = d.progress
          if (scanStatusTimer) clearInterval(scanStatusTimer)
          scanStatusTimer = setInterval(poll, currentPollInterval)
        }
        let parts = [d.message]
        if (d.found_hosts > 0) parts.push(`${d.found_hosts} 台主机`)
        if (d.open_ports > 0) parts.push(`${d.open_ports} 端口`)
        if (d.elapsed_time > 0) parts.push(`已用 ${formatTime(d.elapsed_time)}`)
        if (d.estimated_remaining > 0) parts.push(`剩余 ${formatTime(d.estimated_remaining)}`)
        scanMessage.value = parts.join(' | ')
        if (d.status === 'completed') {
          scanning.value = false; scanCompleted.value = true
          clearInterval(scanStatusTimer); localStorage.removeItem('running_task_id')
          ElMessage.success('扫描完成！')
        } else if (d.status === 'failed' || d.status === 'cancelled') {
          scanning.value = false
          clearInterval(scanStatusTimer); localStorage.removeItem('running_task_id')
          ElMessage.warning(d.message)
        }
      }
    } catch (e) {}
  }
  scanStatusTimer = setInterval(poll, currentPollInterval)
}

onMounted(() => {
  loadScanDefaults()
  loadPolicies()
  const saved = localStorage.getItem('running_task_id')
  if (saved) {
    currentTaskId.value = saved
    scanning.value = true
    scanMessage.value = '恢复中...'
    api.get(`/api/scan/status/${saved}`).then(res => {
      if (res.success && res.data.status === 'running') startStatusPolling()
      else { scanning.value = false; scanCompleted.value = res.data?.status === 'completed'; localStorage.removeItem('running_task_id') }
    }).catch(() => { scanning.value = false; localStorage.removeItem('running_task_id') })
  }
})

onUnmounted(() => { if (scanStatusTimer) clearInterval(scanStatusTimer) })
</script>

<style scoped>
.scan-form :deep(.el-form-item__label) {
  font-weight: 600;
  color: #303133;
}
.policy-selector {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.policy-card {
  flex: 1;
  min-width: 180px;
  padding: 16px;
  border: 2px solid #e4e7ed;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: #fff;
}
.policy-card:hover {
  border-color: #409eff;
  background: #ecf5ff;
}
.policy-card.active {
  border-color: #409eff;
  background: linear-gradient(135deg, #ecf5ff, #d9ecff);
  box-shadow: 0 2px 8px rgba(64,158,255,0.15);
}
.policy-name {
  font-size: 15px;
  font-weight: 700;
  color: #303133;
  margin-bottom: 4px;
}
.policy-desc {
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
}
.scan-actions {
  display: flex;
  gap: 12px;
  padding-top: 8px;
}
.scan-progress {
  margin-top: 24px;
  padding: 20px;
  background: linear-gradient(135deg, #f8faff, #edf2ff);
  border: 1px solid #dce3f5;
  border-radius: 12px;
}
.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.progress-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
.progress-info {
  margin-top: 10px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.log-container {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 14px;
  border-radius: 8px;
  font-family: var(--font-mono);
  font-size: 12px;
  max-height: 300px;
  overflow-y: auto;
  white-space: pre-wrap;
  line-height: 1.6;
}
</style>
