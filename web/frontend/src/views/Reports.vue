<template>
  <div class="page-container">
    <PageHeader title="报告管理" subtitle="管理生成的扫描报告，支持下载和邮件发送" icon="Document">
      <template #extra>
        <el-button @click="loadReports" :icon="'Refresh'" size="small">刷新</el-button>
      </template>
    </PageHeader>

    <el-card>
      <div class="action-bar">
        <el-input v-model="searchKeyword" placeholder="搜索文件名..." size="small" style="width:240px" clearable @input="filterData">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <div style="flex:1"></div>
        <template v-if="selectedReports.length > 0">
          <el-tag type="info" size="small">已选 {{ selectedReports.length }} 项</el-tag>
          <el-button size="small" type="primary" @click="batchDownload">批量下载</el-button>
          <el-button size="small" type="danger" @click="batchDelete">批量删除</el-button>
        </template>
      </div>

      <el-table
        :data="pagedReports"
        style="width: 100%"
        empty-text="暂无报告"
        stripe
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="50" align="center" />
        <el-table-column type="index" label="#" width="55" align="center" />
        <el-table-column prop="name" label="文件名" min-width="240" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small" effect="plain">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="size" label="大小" width="90" align="center">
          <template #default="{ row }">
            {{ row.size ? (row.size / 1024).toFixed(1) + ' KB' : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="created" label="生成时间" width="155" align="center" />
        <el-table-column label="操作" width="200" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="downloadReport(row.path)">下载</el-button>
            <el-button size="small" type="success" @click="openSendMail(row)">邮件</el-button>
            <el-button size="small" type="danger" @click="deleteReport(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top:16px;display:flex;justify-content:flex-end">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="filteredReports.length"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
          small
        />
      </div>
    </el-card>

    <!-- 发送邮件 -->
    <el-dialog v-model="mailVisible" title="发送报告邮件" width="480px">
      <el-form :model="mailForm" label-width="80px">
        <el-form-item label="报告">{{ selectedReport?.name }}</el-form-item>
        <el-form-item label="收件人">
          <el-input v-model="mailForm.recipients" placeholder="多个邮箱逗号分隔" />
        </el-form-item>
        <el-form-item label="主题">
          <el-input v-model="mailForm.subject" />
        </el-form-item>
        <el-form-item label="正文">
          <el-input v-model="mailForm.body" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="mailVisible = false">取消</el-button>
        <el-button type="primary" @click="sendMail" :loading="sending">发送</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import api from '@/api'
import axios from 'axios'

const allReports = ref([])
const selectedReports = ref([])
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const mailVisible = ref(false)
const selectedReport = ref(null)
const mailForm = ref({ recipients: '', subject: '', body: '' })
const sending = ref(false)

const statusType = (s) => ({ completed:'success', running:'primary', failed:'danger', cancelled:'warning', unknown:'info' }[s] || 'info')
const statusText = (s) => ({ completed:'完成', running:'运行中', failed:'失败', cancelled:'已取消', unknown:'未知' }[s] || s)

const filteredReports = computed(() => {
  if (!searchKeyword.value) return allReports.value
  return allReports.value.filter(r => r.name?.toLowerCase().includes(searchKeyword.value.toLowerCase()))
})

const pagedReports = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredReports.value.slice(start, start + pageSize.value)
})

const filterData = () => { currentPage.value = 1 }

const loadReports = async () => {
  try {
    const res = await api.get('/api/reports')
    if (res.success) allReports.value = res.data || []
  } catch (e) {}
}

const handleSelectionChange = (sel) => { selectedReports.value = sel }

const deleteReport = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除 "${row.name}"？`, '确认', { type: 'warning' })
    const res = await api.post('/api/reports/delete', { paths: [row.path] })
    if (res.success) { ElMessage.success('已删除'); loadReports() }
    else { ElMessage.error(res.message || '失败') }
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

const batchDelete = async () => {
  if (!selectedReports.value.length) return
  try {
    await ElMessageBox.confirm(`确定删除 ${selectedReports.value.length} 个报告？`, '确认', { type: 'warning' })
    const res = await api.post('/api/reports/delete', { paths: selectedReports.value.map(r => r.path) })
    if (res.success) { ElMessage.success('批量删除成功'); selectedReports.value = []; loadReports() }
    else { ElMessage.error(res.message || '失败') }
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

const batchDownload = () => {
  selectedReports.value.forEach(r => { if (r.path) downloadReport(r.path) })
}

const downloadReport = async (path) => {
  if (!path) return ElMessage.warning('路径为空')
  try {
    const res = await axios.post('/api/reports/download', { path }, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url; a.download = path.split('/').pop()
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  } catch (e) { ElMessage.error('下载失败') }
}

const openSendMail = async (report) => {
  selectedReport.value = report
  try {
    const res = await api.get('/api/mail/config')
    const def = res.success ? (res.data?.default_recipients || '') : ''
    mailForm.value = {
      recipients: def,
      subject: `网络端口扫描报告 - ${report.name}`,
      body: `请查收附件中的网络端口扫描报告。\n\n报告: ${report.name}`
    }
  } catch (e) {
    mailForm.value = { recipients: '', subject: '', body: '' }
  }
  mailVisible.value = true
}

const sendMail = async () => {
  if (!mailForm.value.recipients.trim()) return ElMessage.warning('请输入收件人')
  sending.value = true
  try {
    const res = await api.post('/api/reports/send', {
      report_path: selectedReport.value.path,
      recipients: mailForm.value.recipients,
      subject: mailForm.value.subject,
      body: mailForm.value.body,
    })
    if (res.success) { ElMessage.success('发送成功'); mailVisible.value = false }
    else { ElMessage.error(res.message) }
  } catch (e) {}
  sending.value = false
}

onMounted(loadReports)
</script>
