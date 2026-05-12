<template>
  <el-card>
    <template #header>
      <span>邮件配置</span>
    </template>
    <el-tabs v-model="mailTabActive">
      <el-tab-pane label="邮件服务器设置" name="server">
        <el-form :model="mailConfigForm" label-width="150px" style="margin-top: 20px">
          <el-form-item label="SMTP服务器">
            <el-input v-model="mailConfigForm.smtp_server" placeholder="如: smtp.example.com" />
          </el-form-item>
          <el-form-item label="SMTP端口">
            <el-input-number v-model="mailConfigForm.smtp_port" :min="1" :max="65535" />
          </el-form-item>
          <el-form-item label="用户名">
            <el-input v-model="mailConfigForm.smtp_user" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="mailConfigForm.smtp_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="使用SSL">
            <el-switch v-model="mailConfigForm.smtp_ssl" />
          </el-form-item>
          <el-form-item label="跳过登录">
            <el-switch v-model="mailConfigForm.skip_login" />
            <div style="color: #909399; font-size: 12px; margin-top: 5px;">
              适用于IP白名单认证的SMTP服务器（不需要用户名密码）
            </div>
          </el-form-item>
          <el-form-item label="默认发件人">
            <el-input v-model="mailConfigForm.default_sender" placeholder="如: scanner@example.com" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveMailConfig">保存服务器配置</el-button>
            <el-button @click="testMailConfig">测试连接</el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>
      <el-tab-pane label="默认收件人配置" name="recipients">
        <el-form :model="recipientsForm" label-width="150px" style="margin-top: 20px">
          <el-form-item label="默认收件人">
            <el-input
              v-model="recipientsForm.default_recipients"
              type="textarea"
              :rows="4"
              placeholder="支持单个或多个邮箱地址，多个邮箱用逗号或换行分隔&#10;示例：&#10;user1@example.com&#10;user2@example.com&#10;user3@example.com"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveRecipientsConfig">保存收件人配置</el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const mailTabActive = ref('server')

const mailConfigForm = reactive({
  smtp_server: '',
  smtp_port: 587,
  smtp_user: '',
  smtp_password: '',
  smtp_ssl: true,
  skip_login: false,
  default_sender: '',
})

const recipientsForm = reactive({
  default_recipients: '',
})

const loadMailConfig = async () => {
  try {
    const res = await api.get('/api/v1/mail/config')
    if (res.success && res.data) {
      mailConfigForm.smtp_server = res.data.smtp_server || ''
      mailConfigForm.smtp_port = res.data.smtp_port || 587
      mailConfigForm.smtp_user = res.data.smtp_user || ''
      mailConfigForm.smtp_password = res.data.smtp_password || ''
      mailConfigForm.smtp_ssl = res.data.smtp_ssl !== false
      mailConfigForm.skip_login = res.data.skip_login === true
      mailConfigForm.default_sender = res.data.default_sender || ''
      recipientsForm.default_recipients = res.data.default_recipients || ''
    }
  } catch (e) { /* handled by interceptor */ }
}

const saveMailConfig = async () => {
  try {
    const res = await api.post('/api/v1/mail/config', {
      ...mailConfigForm,
      default_recipients: recipientsForm.default_recipients,
    })
    if (res.success) ElMessage.success('邮件服务器配置已保存')
  } catch (e) { /* handled by interceptor */ }
}

const saveRecipientsConfig = async () => {
  try {
    const res = await api.post('/api/v1/mail/config', {
      ...mailConfigForm,
      default_recipients: recipientsForm.default_recipients,
    })
    if (res.success) ElMessage.success('默认收件人配置已保存')
  } catch (e) { /* handled by interceptor */ }
}

const testMailConfig = async () => {
  try {
    const res = await api.post('/api/v1/mail/test', mailConfigForm)
    if (res.success) {
      ElMessage.success(res.message)
    } else {
      ElMessage.error(res.message)
    }
  } catch (e) { /* handled by interceptor */ }
}

onMounted(loadMailConfig)
</script>
