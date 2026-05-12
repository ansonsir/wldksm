<template>
  <el-card>
    <template #header>
      <div style="display: flex; justify-content: space-between; align-items: center">
        <span>通知渠道管理</span>
        <el-button type="primary" @click="showWebhookForm = true; editingWebhook = null">添加通知渠道</el-button>
      </div>
    </template>

    <el-empty v-if="webhookConfigs.length === 0" description="暂无通知渠道，点击上方按钮添加" :image-size="80" />

    <div v-else class="webhook-list">
      <div v-for="cfg in webhookConfigs" :key="cfg.platform" class="webhook-item">
        <div class="webhook-info">
          <span class="webhook-platform">
            {{ cfg.platform === 'dingtalk' ? '🔷 钉钉' : cfg.platform === 'wecom' ? '💬 企业微信' : '🐦 飞书' }}
          </span>
          <span class="webhook-url">{{ maskUrl(cfg.webhook_url) }}</span>
        </div>
        <div class="webhook-status">
          <el-tag :type="cfg.is_active ? 'success' : 'info'" size="small">
            {{ cfg.is_active ? '已启用' : '已禁用' }}
          </el-tag>
          <span v-if="cfg.is_active" style="font-size:12px;color:#909399;margin-left:8px">
            完成通知/高危通知
          </span>
        </div>
        <div class="webhook-actions">
          <el-button size="small" @click="editWebhook(cfg)">编辑</el-button>
          <el-button size="small" @click="testWebhookItem(cfg)">测试</el-button>
          <el-button size="small" type="danger" @click="deleteWebhookItem(cfg)">删除</el-button>
        </div>
      </div>
    </div>

    <!-- Webhook 编辑对话框 -->
    <el-dialog v-model="showWebhookForm" :title="editingWebhook ? '编辑通知渠道' : '添加通知渠道'" width="550px">
      <el-form :model="webhookForm" label-width="140px">
        <el-form-item label="平台类型">
          <el-select v-model="webhookForm.platform" placeholder="选择平台" :disabled="!!editingWebhook" style="width:100%">
            <el-option label="钉钉机器人" value="dingtalk" />
            <el-option label="企业微信机器人" value="wecom" />
            <el-option label="飞书机器人" value="feishu" />
          </el-select>
        </el-form-item>
        <el-form-item label="Webhook URL">
          <el-input v-model="webhookForm.webhook_url" placeholder="机器人的 Webhook 地址" />
        </el-form-item>
        <el-form-item label="签名密钥">
          <el-input v-model="webhookForm.secret" placeholder="安全设置的加签密钥（可选）" show-password />
        </el-form-item>
        <el-form-item label="启用通知">
          <el-switch v-model="webhookForm.is_active" />
        </el-form-item>
        <el-form-item label="扫描完成通知">
          <el-switch v-model="webhookForm.notify_on_complete" />
          <span style="font-size:12px;color:#909399;margin-left:8px">每次扫描完成后自动推送结果</span>
        </el-form-item>
        <el-form-item label="高危端口通知">
          <el-switch v-model="webhookForm.notify_on_high_risk" />
          <span style="font-size:12px;color:#909399;margin-left:8px">发现高危设备时特别提醒</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveWebhook">保存</el-button>
          <el-button @click="showWebhookForm = false">取消</el-button>
        </el-form-item>
      </el-form>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

const webhookConfigs = ref([])
const showWebhookForm = ref(false)
const editingWebhook = ref(null)
const webhookForm = reactive({
  platform: 'dingtalk',
  webhook_url: '',
  secret: '',
  is_active: false,
  notify_on_complete: true,
  notify_on_high_risk: true,
})

const loadWebhookConfigs = async () => {
  try {
    const res = await api.get('/api/v1/webhook/configs')
    if (res.success) webhookConfigs.value = res.data || []
  } catch (e) { /* handled by interceptor */ }
}

const maskUrl = (url) => {
  if (!url) return ''
  if (url.length <= 40) return url
  return url.substring(0, 25) + '...' + url.substring(url.length - 15)
}

const editWebhook = (cfg) => {
  editingWebhook.value = cfg
  webhookForm.platform = cfg.platform
  webhookForm.webhook_url = cfg.webhook_url
  webhookForm.secret = cfg.secret || ''
  webhookForm.is_active = !!cfg.is_active
  webhookForm.notify_on_complete = cfg.notify_on_complete !== false
  webhookForm.notify_on_high_risk = cfg.notify_on_high_risk !== false
  showWebhookForm.value = true
}

const saveWebhook = async () => {
  if (!webhookForm.platform || !webhookForm.webhook_url) {
    ElMessage.error('请填写平台类型和 Webhook URL')
    return
  }
  try {
    const res = await api.post('/api/v1/webhook/configs', { ...webhookForm })
    if (res.success) {
      ElMessage.success('Webhook 配置已保存')
      showWebhookForm.value = false
      editingWebhook.value = null
      loadWebhookConfigs()
    }
  } catch (e) { /* handled by interceptor */ }
}

const testWebhookItem = async (cfg) => {
  try {
    const res = await api.post('/api/v1/webhook/test', {
      platform: cfg.platform,
      webhook_url: cfg.webhook_url,
      secret: cfg.secret,
    })
    if (res.success) {
      ElMessage.success('测试消息已发送')
    } else {
      ElMessage.error(res.message || '发送失败')
    }
  } catch (e) { /* handled by interceptor */ }
}

const deleteWebhookItem = async (cfg) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除 ${cfg.platform === 'dingtalk' ? '钉钉' : cfg.platform === 'wecom' ? '企业微信' : '飞书'} 的通知渠道吗？`,
      '确认删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    const res = await api.delete(`/api/v1/webhook/configs/${cfg.platform}`)
    if (res.success) {
      ElMessage.success('已删除')
      loadWebhookConfigs()
    }
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.message || '删除失败')
    }
  }
}

onMounted(loadWebhookConfigs)
</script>

<style scoped>
.webhook-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.webhook-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  transition: all 0.2s;
  background: #fff;
}
.webhook-item:hover {
  border-color: #c6d0e0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.webhook-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}
.webhook-platform {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
.webhook-url {
  font-size: 12px;
  color: #909399;
  font-family: var(--font-mono);
}
.webhook-status {
  display: flex;
  align-items: center;
  margin: 0 20px;
}
.webhook-actions {
  display: flex;
  gap: 8px;
}
</style>
