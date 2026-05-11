<template>
  <div class="page-container">
    <PageHeader title="扫描历史" subtitle="查看所有已完成和运行中的扫描任务记录" icon="List">
      <template #extra>
        <el-button @click="loadHistory" :icon="'Refresh'" size="small">刷新</el-button>
      </template>
    </PageHeader>

    <el-card>
      <!-- 工具栏 -->
      <div class="action-bar">
        <el-input v-model="searchKeyword" placeholder="搜索IP地址..." size="small" style="width:220px" clearable @input="filterData">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="statusFilter" placeholder="状态筛选" size="small" style="width:140px" clearable @change="filterData">
          <el-option label="全部" value="" />
          <el-option label="已完成" value="completed" />
          <el-option label="运行中" value="running" />
          <el-option label="失败" value="failed" />
          <el-option label="已取消" value="cancelled" />
        </el-select>
        <div style="flex:1"></div>
        <template v-if="selectedRecords.length > 0">
          <el-tag type="info" size="small">已选 {{ selectedRecords.length }} 项</el-tag>
          <el-button size="small" type="primary" @click="batchDownload">批量下载</el-button>
          <el-button size="small" type="danger" @click="batchDelete">批量删除</el-button>
        </template>
      </div>

      <el-table
        :data="pagedRecords"
        style="width: 100%"
        empty-text="暂无扫描记录"
        stripe
        :default-sort="{ prop: 'start_time', order: 'descending' }"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="50" align="center" />
        <el-table-column type="index" label="#" width="55" align="center" />
        <el-table-column prop="status" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small" effect="plain">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_hosts" label="主机" width="70" align="center">
          <template #default="{ row }">
            <b style="color:#409eff">{{ row.total_hosts || 0 }}</b>
          </template>
        </el-table-column>
        <el-table-column prop="open_ports" label="端口" width="70" align="center">
          <template #default="{ row }">
            <b style="color:#e6a23c">{{ row.open_ports || 0 }}</b>
          </template>
        </el-table-column>
        <el-table-column prop="max_workers" label="线程" width="70" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="info" effect="plain">{{ row.max_workers || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="duration" label="用时" width="90" align="center">
          <template #default="{ row }">{{ formatTime(row.duration) }}</template>
        </el-table-column>
        <el-table-column prop="start_time" label="开始时间" width="155" />
        <el-table-column prop="end_time" label="结束时间" width="155" />
        <el-table-column label="操作" width="260" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewDetail(row)">详情</el-button>
            <el-button size="small" type="primary" v-if="row.report_file" @click="downloadReport(row.report_file)">报告</el-button>
            <el-button size="small" type="danger" @click="deleteRecord(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div style="margin-top:16px;display:flex;justify-content:flex-end">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="filteredRecords.length"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          background
          small
        />
      </div>
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog v-model="detailVisible" title="扫描详情" width="860px" :close-on-click-modal="false" @closed="handleDetailClose">
      <div v-if="detail" style="padding: 0 10px">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="状态">
            <el-tag :type="statusType(detail.status)" size="small">{{ statusText(detail.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="用时">{{ formatTime(detail.duration) }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ detail.start_time || '-' }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ detail.end_time || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="detail.status === 'running' && detail.current_total > 0" style="margin:16px 0">
          <el-progress :percentage="Math.round((detail.current_progress / detail.current_total) * 100) || 0" />
          <p style="font-size:13px;color:#606266;margin-top:6px;">
            {{ detail.current_message || '扫描中...' }}
            <template v-if="detail.found_hosts > 0"> | {{ detail.found_hosts }} 台主机</template>
            <template v-if="detail.open_ports_count > 0"> | {{ detail.open_ports_count }} 端口</template>
            <template v-if="detail.elapsed_time > 0"> | 已用 {{ formatTime(detail.elapsed_time) }}</template>
          </p>
        </div>

        <el-descriptions :column="2" border size="small" style="margin-top:16px">
          <el-descriptions-item label="发现主机">
            <b style="color:#409eff">{{ detail.total_hosts || 0 }}</b> 台
          </el-descriptions-item>
          <el-descriptions-item label="开放端口">
            <b style="color:#e6a23c">{{ detail.open_ports_count || 0 }}</b> 个
          </el-descriptions-item>
          <el-descriptions-item label="并发">{{ detail.max_workers || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Ulimit">{{ detail.ulimit || '-' }}</el-descriptions-item>
          <el-descriptions-item label="IP范围" :span="2">
            <div style="max-height:100px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;font-size:12px">{{ detail.ip_ranges || '-' }}</div>
          </el-descriptions-item>
        </el-descriptions>

        <template v-if="detail.report_file">
          <el-descriptions :column="1" border size="small" style="margin-top:16px">
            <el-descriptions-item label="报告">
              <div style="display:flex;align-items:center;gap:10px">
                <span style="font-size:12px;flex:1;word-break:break-all">{{ detail.report_file }}</span>
                <el-button size="small" type="primary" @click="downloadReport(detail.report_file)">下载</el-button>
              </div>
            </el-descriptions-item>
          </el-descriptions>
        </template>

        <div v-if="detail.error_message" style="margin-top:12px">
          <el-alert :title="detail.error_message" type="error" :closable="false" show-icon />
        </div>

        <h4 style="margin:16px 0 8px;font-size:14px;color:#303133">端口开放详情</h4>
        <el-table :data="detail?.details || []" max-height="320" size="small" empty-text="暂无数据" stripe style="width:100%">
          <el-table-column prop="ip" label="IP地址" width="180" show-overflow-tooltip />
          <el-table-column prop="port" label="端口" width="70" align="center" />
          <el-table-column prop="service" label="服务" min-width="120" show-overflow-tooltip />
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import api from '@/api'

const allRecords = ref([])
const selectedRecords = ref([])
const searchKeyword = ref('')
const statusFilter = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const detailVisible = ref(false)
const detail = ref(null)
let detailTimer = null

const statusType = (s) => ({ completed:'success', running:'primary', failed:'danger', cancelled:'warning' }[s] || 'info')
const statusText = (s) => ({ completed:'完成', running:'运行中', failed:'失败', cancelled:'已取消' }[s] || s)
const formatTime = (s) => {
  if (!s || s < 0) return '0秒'
  const m = Math.floor(s / 60)
  return m > 0 ? `${m}分${s % 60}秒` : `${s}秒`
}

// 筛选
const filteredRecords = computed(() => {
  let data = allRecords.value
  if (searchKeyword.value) {
    data = data.filter(r => r.ip_ranges?.toLowerCase().includes(searchKeyword.value.toLowerCase()))
  }
  if (statusFilter.value) {
    data = data.filter(r => r.status === statusFilter.value)
  }
  return data
})

const pagedRecords = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredRecords.value.slice(start, start + pageSize.value)
})

const filterData = () => {
  currentPage.value = 1
}

const loadHistory = async () => {
  try {
    const res = await api.get('/api/scan/history?limit=200')
    if (res.success) allRecords.value = res.data
  } catch (e) {}
}

const handleSelectionChange = (sel) => { selectedRecords.value = sel }

const deleteRecord = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除扫描记录 #${row.id}？`, '确认删除', { type: 'warning' })
    const res = await api.post('/api/scan/history/delete', { ids: [row.id] })
    if (res.success) { ElMessage.success('已删除'); loadHistory() }
    else { ElMessage.error(res.message || '删除失败') }
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

const batchDelete = async () => {
  if (!selectedRecords.value.length) return
  try {
    await ElMessageBox.confirm(`确定删除 ${selectedRecords.value.length} 条记录？`, '批量删除', { type: 'warning' })
    const res = await api.post('/api/scan/history/delete', { ids: selectedRecords.value.map(r => r.id) })
    if (res.success) { ElMessage.success('批量删除成功'); selectedRecords.value = []; loadHistory() }
    else { ElMessage.error(res.message || '删除失败') }
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

const batchDownload = () => {
  selectedRecords.value.forEach(r => { if (r.report_file) downloadReport(r.report_file) })
}

const viewDetail = async (row) => {
  try {
    const res = await api.get(`/api/scan/history/${row.id}`)
    if (res.success) {
      detail.value = res.data
      detailVisible.value = true
      if (row.status === 'running' && row.task_id) startDetailPolling(row.task_id)
    }
  } catch (e) {}
}

const startDetailPolling = (taskId) => {
  if (detailTimer) clearInterval(detailTimer)
  detailTimer = setInterval(async () => {
    try {
      const res = await api.get(`/api/scan/status/${taskId}`)
      if (res.success && detail.value) {
        const d = res.data
        Object.assign(detail.value, {
          status: d.status, current_progress: d.progress, current_total: d.total,
          current_message: d.message, found_hosts: d.found_hosts,
          open_ports_count: d.open_ports, elapsed_time: d.elapsed_time,
          estimated_remaining: d.estimated_remaining
        })
        if (d.status !== 'running') { clearInterval(detailTimer); detailTimer = null; loadHistory() }
      }
    } catch (e) {}
  }, 2000)
}

const handleDetailClose = () => {
  if (detailTimer) { clearInterval(detailTimer); detailTimer = null }
}

const downloadReport = async (path) => {
  if (!path) return ElMessage.warning('路径为空')
  try {
    const res = await api.post('/api/reports/download', { path }, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url; a.download = path.split('/').pop()
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  } catch (e) { ElMessage.error('下载失败') }
}

onMounted(loadHistory)
</script>
