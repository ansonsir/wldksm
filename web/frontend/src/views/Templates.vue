<template>
  <div class="page-container">
    <PageHeader title="模板管理" subtitle="管理 Word 报告生成模板" icon="Files" />

    <el-card>
      <el-row :gutter="24">
        <el-col :span="8">
          <div class="upload-section">
            <el-upload
              drag
              action="/api/templates/upload"
              :on-success="handleUploadSuccess"
              :on-error="handleUploadError"
              accept=".docx"
            >
              <el-icon class="upload-icon"><UploadFilled /></el-icon>
              <div class="upload-text">拖拽文件到此处或 <em>点击上传</em></div>
              <template #tip>
                <div class="upload-tip">仅支持 .docx 格式</div>
              </template>
            </el-upload>
          </div>
        </el-col>
        <el-col :span="16">
          <div class="template-list-header">已上传模板</div>
          <el-table :data="templates" style="width:100%" empty-text="暂无模板" size="small" max-height="340" stripe>
            <el-table-column prop="name" label="名称" min-width="120" show-overflow-tooltip />
            <el-table-column prop="source" label="来源" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.source === 'database' ? 'success' : 'info'" size="small" effect="plain">
                  {{ row.source === 'database' ? '数据库' : '文件' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="100" show-overflow-tooltip>
              <template #default="{ row }">{{ row.description || '-' }}</template>
            </el-table-column>
            <el-table-column prop="path" label="路径" min-width="140" show-overflow-tooltip />
            <el-table-column label="操作" width="140" align="center">
              <template #default="{ row }">
                <el-button size="small" @click="previewTemplate(row)">预览</el-button>
                <el-button size="small" type="danger" @click="deleteTemplate(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-col>
      </el-row>
    </el-card>

    <el-dialog v-model="previewVisible" title="模板预览" width="700px">
      <div v-if="previewData" style="max-height:500px;overflow-y:auto">
        <div style="font-weight:600;margin-bottom:12px;color:#303133">
          {{ previewData.name }} <el-tag size="small" effect="plain">共 {{ previewData.total }} 段</el-tag>
        </div>
        <div v-for="(text, idx) in previewData.paragraphs" :key="idx"
          style="margin-bottom:8px;padding:10px 14px;background:#f5f7fa;border-radius:6px;line-height:1.6;font-size:13px">
          {{ text }}
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import api from '@/api'

const templates = ref([])
const previewVisible = ref(false)
const previewData = ref(null)

const loadTemplates = async () => {
  try {
    const res = await api.get('/api/templates')
    if (res.success) templates.value = res.data
  } catch (e) {}
}

const previewTemplate = async (row) => {
  try {
    const res = await api.post('/api/templates/preview', { path: row.path })
    if (res.success) { previewData.value = res.data; previewVisible.value = true }
    else { ElMessage.error(res.message || '预览失败') }
  } catch (e) { ElMessage.error('预览失败') }
}

const deleteTemplate = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除 "${row.name}"？`, '确认', { type: 'warning' })
    const res = await api.post('/api/templates/delete', { id: row.id, path: row.path })
    if (res.success) { ElMessage.success('已删除'); loadTemplates() }
    else { ElMessage.error(res.message || '失败') }
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

const handleUploadSuccess = () => { ElMessage.success('上传成功'); loadTemplates() }
const handleUploadError = (err) => { ElMessage.error('上传失败: ' + (err.message || '未知错误')) }

onMounted(loadTemplates)
</script>

<style scoped>
.upload-section {
  border: 2px dashed #dce3f5;
  border-radius: 12px;
  padding: 20px;
  background: #fafbfc;
}
.upload-icon { font-size: 40px; color: #409eff; margin-bottom: 8px; }
.upload-text { font-size: 14px; color: #606266; }
.upload-text em { color: #409eff; font-style: normal; }
.upload-tip { font-size: 12px; color: #c0c4cc; margin-top: 4px; }
.template-list-header {
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
  font-size: 14px;
}
</style>
