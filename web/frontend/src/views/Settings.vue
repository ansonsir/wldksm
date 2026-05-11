<template>
  <div class="page-container">
    <PageHeader title="系统配置" subtitle="管理扫描、邮件、安全等全局设置" icon="Setting" />

    <!-- 主Tab导航 -->
    <el-tabs v-model="mainTabActive" type="border-card" >
      <!-- Tab 1: 扫描配置 -->
      <el-tab-pane label="扫描配置" name="scan">
        <el-card>
          <template #header>
            <span>扫描配置</span>
          </template>
          <el-form :model="configForm" label-width="150px">
            <el-form-item label="默认IP范围文件">
              <el-input v-model="configForm.ip_range_file" />
            </el-form-item>
            <el-form-item label="默认端口文件">
              <el-input v-model="configForm.ports_file" />
            </el-form-item>
            <el-form-item label="排除IP文件">
              <el-input v-model="configForm.exclude_ips_file" />
            </el-form-item>
            <el-form-item label="最大线程数">
              <el-slider v-model="configForm.max_workers" :min="1" :max="64" show-input />
            </el-form-item>
            <el-form-item label="Ulimit">
              <el-input-number v-model="configForm.ulimit" :min="1000" :max="65535" />
            </el-form-item>
            <el-form-item label="扫描超时(秒)">
              <el-input-number v-model="configForm.timeout" :min="30" :max="3600" />
            </el-form-item>
            <el-form-item label="扫描批次大小">
              <el-input-number v-model="configForm.batch_size" :min="1000" :max="50000" :step="1000" />
              <span style="margin-left: 10px; color: #999; font-size: 12px">RustScan 每批扫描的端口数，越大越快但占用更多资源</span>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveConfig">保存扫描配置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- Tab 2: 邮件配置 -->
      <el-tab-pane label="邮件配置" name="mail">
        <el-card>
          <template #header>
            <span>邮件配置</span>
          </template>
          
          <el-tabs v-model="mailTabActive">
            <!-- Tab 2.1: 邮件服务器设置 -->
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
            
            <!-- Tab 2.2: 默认收件人配置 -->
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
      </el-tab-pane>

      <!-- Tab 3: 安全设置 -->
      <el-tab-pane label="安全设置" name="security">
        <el-card style="margin-bottom: 20px">
          <template #header>
            <span>修改密码</span>
          </template>
          <el-form :model="passwordForm" label-width="150px" @submit.prevent="handleChangePassword">
            <el-form-item label="当前密码">
              <el-input v-model="passwordForm.old_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="新密码">
              <el-input v-model="passwordForm.new_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="确认新密码">
              <el-input v-model="passwordForm.confirm_password" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleChangePassword">修改密码</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card>
          <template #header>
            <span>双因素认证 (TOTP)</span>
          </template>
          
          <!-- 未启用TOTP -->
          <div v-if="!userInfo.totp_enabled">
            <el-alert
              title="启用双因素认证可以大大提高账户安全性"
              type="warning"
              :closable="false"
              show-icon
              style="margin-bottom: 20px"
            />
            <el-button type="primary" size="large" @click="showTotpSetup = true">
              启用TOTP
            </el-button>
          </div>
          
          <!-- 已启用TOTP -->
          <div v-else>
            <el-alert
              title="双因素认证已启用"
              type="success"
              :closable="false"
              show-icon
              style="margin-bottom: 20px"
            />
            <p style="color: #606266; margin-bottom: 20px">
              您的账户已启用双因素认证，每次登录时需要输入手机APP生成的动态验证码。
            </p>
            <!-- 只有管理员可以禁用TOTP -->
            <el-button v-if="userInfo.is_admin" type="danger" @click="handleDisableTotp">禁用TOTP</el-button>
            <el-alert
              v-else
              title="普通用户无法禁用双因素认证"
              type="info"
              :closable="false"
              show-icon
              style="margin-top: 15px"
            />
          </div>
        </el-card>

        <!-- TOTP设置对话框 -->
        <el-dialog v-model="showTotpSetup" title="设置双因素认证" width="500px">
          <TOTPSetup @success="handleTotpSuccess" />
        </el-dialog>

        <!-- 禁用TOTP对话框 -->
        <el-dialog v-model="showDisableTotp" title="禁用双因素认证" width="400px">
          <el-alert
            title="禁用后将降低账户安全性"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 20px"
          />
          <el-form @submit.prevent="confirmDisableTotp">
            <el-form-item label="动态验证码">
              <el-input v-model="disableTotpForm.totp_token" placeholder="请输入6位动态验证码" maxlength="6" />
            </el-form-item>
            <el-form-item>
              <el-button type="danger" @click="confirmDisableTotp">确认禁用</el-button>
              <el-button @click="showDisableTotp = false">取消</el-button>
            </el-form-item>
          </el-form>
        </el-dialog>
      </el-tab-pane>

      <!-- Tab 4: 用户管理（仅管理员） -->
      <el-tab-pane label="用户管理" name="users" v-if="userInfo.is_admin">
        <el-card>
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>用户管理</span>
              <el-button type="primary" @click="showCreateUser = true">创建用户</el-button>
            </div>
          </template>

          <el-table :data="userList" style="width: 100%">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="username" label="用户名" width="150" />
            <el-table-column prop="email" label="邮箱" width="200" />
            <el-table-column label="管理员" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_admin ? 'danger' : 'info'" size="small">
                  {{ row.is_admin ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="TOTP" width="80">
              <template #default="{ row }">
                <el-tag :type="row.totp_enabled ? 'success' : 'warning'" size="small">
                  {{ row.totp_enabled ? '已启用' : '未启用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="last_login" label="最后登录" width="180" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
                  {{ row.is_active ? '正常' : '锁定' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="280">
              <template #default="{ row }">
                <el-button size="small" @click="handleEditUser(row)">编辑</el-button>
                <el-button size="small" @click="handleResetPassword(row)">重置密码</el-button>
                <el-button size="small" type="danger" @click="handleDeleteUser(row)" :disabled="row.id === userInfo.id">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 创建用户对话框 -->
        <el-dialog v-model="showCreateUser" title="创建用户" width="500px">
          <el-form :model="createUserForm" label-width="120px">
            <el-form-item label="用户名">
              <el-input v-model="createUserForm.username" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="createUserForm.password" type="password" show-password />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="createUserForm.email" />
            </el-form-item>
            <el-form-item label="管理员">
              <el-switch v-model="createUserForm.is_admin" />
            </el-form-item>
            <el-form-item label="启用TOTP认证">
              <el-switch v-model="createUserForm.enable_totp" />
              <div style="color: #909399; font-size: 12px; margin-top: 5px">
                启用后，用户首次登录时需要设置TOTP双因素认证
              </div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleCreateUser">创建</el-button>
              <el-button @click="showCreateUser = false">取消</el-button>
            </el-form-item>
          </el-form>
        </el-dialog>

        <!-- 编辑用户对话框 -->
        <el-dialog v-model="showEditUser" title="编辑用户" width="600px">
          <el-form :model="editUserForm" label-width="120px">
            <el-form-item label="用户名">
              <el-input v-model="editUserForm.username" disabled />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="editUserForm.email" />
            </el-form-item>
            <el-form-item label="管理员">
              <el-switch v-model="editUserForm.is_admin" />
            </el-form-item>
            <el-form-item label="状态">
              <el-switch v-model="editUserForm.is_active" active-text="正常" inactive-text="锁定" />
            </el-form-item>
            
            <!-- TOTP管理 -->
            <el-divider>双因素认证（TOTP）管理</el-divider>
            <el-form-item label="TOTP状态">
              <el-tag v-if="editUserForm.totp_enabled" type="success" size="large">已启用</el-tag>
              <el-tag v-else type="info" size="large">未启用</el-tag>
            </el-form-item>
            <el-form-item label="TOTP操作">
              <el-button 
                v-if="!editUserForm.totp_enabled" 
                type="success" 
                @click="handleEnableTotp"
              >
                启用TOTP
              </el-button>
              <el-button 
                v-if="editUserForm.totp_enabled" 
                type="warning" 
                @click="handleDisableTotpForUser"
              >
                禁用TOTP
              </el-button>
              <el-button 
                v-if="editUserForm.totp_enabled" 
                type="danger" 
                @click="handleResetTotp"
              >
                重置TOTP
              </el-button>
            </el-form-item>
            <el-form-item v-if="editUserForm.totp_enabled">
              <el-alert
                title="重置TOTP后，用户需要重新扫码绑定"
                type="warning"
                :closable="false"
                show-icon
              />
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" @click="handleUpdateUser">保存</el-button>
              <el-button @click="showEditUser = false">取消</el-button>
            </el-form-item>
          </el-form>
        </el-dialog>

        <!-- 重置密码对话框 -->
        <el-dialog v-model="showResetPassword" title="重置密码" width="400px">
          <el-form :model="resetPasswordForm" label-width="100px">
            <el-form-item label="新密码">
              <el-input v-model="resetPasswordForm.password" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="confirmResetPassword">确认重置</el-button>
              <el-button @click="showResetPassword = false">取消</el-button>
            </el-form-item>
          </el-form>
        </el-dialog>
      </el-tab-pane>

      <!-- Tab 5: Webhook 通知 -->
      <el-tab-pane label="Webhook通知" name="webhook">
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
        </el-card>

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
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '@/components/PageHeader.vue'
import api from '@/api'
import TOTPSetup from '@/components/TOTPSetup.vue'

const route = useRoute()
const router = useRouter()
const mainTabActive = ref('scan')
const mailTabActive = ref('server')

// 用户信息
const userInfo = reactive({
  username: '',
  is_admin: false,
  totp_enabled: false
})

// 扫描配置
const configForm = reactive({
  ip_range_file: '',
  ports_file: '',
  exclude_ips_file: '',
  max_workers: 32,
  ulimit: 32768,
  timeout: 300,
  batch_size: 10000,
})

// 邮件配置
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

// 密码修改
const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: ''
})

// TOTP相关
const showTotpSetup = ref(false)
const showDisableTotp = ref(false)
const disableTotpForm = reactive({
  totp_token: ''
})

// 用户管理
const userList = ref([])
const showCreateUser = ref(false)
const showEditUser = ref(false)
const showResetPassword = ref(false)
const selectedUserId = ref(null)

const createUserForm = reactive({
  username: '',
  password: '',
  email: '',
  is_admin: false,
  enable_totp: false
})

const editUserForm = reactive({
  id: null,
  username: '',
  email: '',
  is_admin: false,
  is_active: true
})

const resetPasswordForm = reactive({
  password: ''
})

// Webhook 配置
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

// 处理Tab点击
const handleTabClick = (tab) => {
  // 可以在这里处理Tab切换逻辑
}

// 加载设置
const loadSettings = async () => {
  try {
    const configRes = await api.get('/api/config')
    if (configRes.success) {
      Object.assign(configForm, configRes.data)
    }
    const mailRes = await api.get('/api/mail/config')
    if (mailRes.success && mailRes.data) {
      mailConfigForm.smtp_server = mailRes.data.smtp_server || ''
      mailConfigForm.smtp_port = mailRes.data.smtp_port || 587
      mailConfigForm.smtp_user = mailRes.data.smtp_user || ''
      mailConfigForm.smtp_password = mailRes.data.smtp_password || ''
      mailConfigForm.smtp_ssl = mailRes.data.smtp_ssl !== false
      mailConfigForm.skip_login = mailRes.data.skip_login === true
      mailConfigForm.default_sender = mailRes.data.default_sender || ''
      recipientsForm.default_recipients = mailRes.data.default_recipients || ''
    }
    
    // 加载用户信息
    const userStr = localStorage.getItem('user_info')
    if (userStr) {
      const user = JSON.parse(userStr)
      userInfo.username = user.username
      userInfo.is_admin = user.is_admin
      userInfo.totp_enabled = user.totp_enabled
    }
    
    // 如果是管理员，加载用户列表
    if (userInfo.is_admin) {
      loadUserList()
    }

    // 加载 Webhook 配置
    loadWebhookConfigs()
  } catch (e) {
    console.error('加载设置失败:', e)
  }
}

// 加载用户列表
const loadUserList = async () => {
  try {
    const res = await api.get('/api/auth/users')
    if (res.success) {
      userList.value = res.data
    }
  } catch (e) {
    console.error('加载用户列表失败:', e)
  }
}

// 保存扫描配置
const saveConfig = async () => {
  try {
    const res = await api.post('/api/config', configForm)
    if (res.success) ElMessage.success('配置已保存')
  } catch (e) {}
}

// 保存邮件配置
const saveMailConfig = async () => {
  try {
    const res = await api.post('/api/mail/config', {
      ...mailConfigForm,
      default_recipients: recipientsForm.default_recipients,
    })
    if (res.success) ElMessage.success('邮件服务器配置已保存')
  } catch (e) {}
}

// 保存收件人配置
const saveRecipientsConfig = async () => {
  try {
    const res = await api.post('/api/mail/config', {
      ...mailConfigForm,
      default_recipients: recipientsForm.default_recipients,
    })
    if (res.success) ElMessage.success('默认收件人配置已保存')
  } catch (e) {}
}

// 测试邮件配置
const testMailConfig = async () => {
  try {
    const res = await api.post('/api/mail/test', mailConfigForm)
    if (res.success) {
      ElMessage.success(res.message)
    } else {
      ElMessage.error(res.message)
    }
  } catch (e) {}
}

// 修改密码
const handleChangePassword = async () => {
  if (!passwordForm.old_password || !passwordForm.new_password || !passwordForm.confirm_password) {
    ElMessage.error('请填写完整')
    return
  }
  
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    ElMessage.error('两次输入的密码不一致')
    return
  }
  
  try {
    const res = await api.post('/api/auth/change-password', {
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password
    })
    
    if (res.success) {
      ElMessage.success('密码修改成功')
      passwordForm.old_password = ''
      passwordForm.new_password = ''
      passwordForm.confirm_password = ''
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '修改失败')
  }
}

// TOTP设置成功
const handleTotpSuccess = async () => {
  showTotpSetup.value = false
  userInfo.totp_enabled = true
  
  // 更新本地存储
  const userStr = localStorage.getItem('user_info')
  if (userStr) {
    const user = JSON.parse(userStr)
    user.totp_enabled = true
    localStorage.setItem('user_info', JSON.stringify(user))
  }
  
  ElMessage.success('TOTP启用成功')
  
  // 如果是强制启用TOTP，跳转到首页
  if (route.query.force_totp === 'true') {
    ElMessage.success('双因素认证已启用，正在跳转到首页')
    setTimeout(() => {
      router.push('/dashboard')
    }, 1500)
  }
}

// 禁用TOTP
const handleDisableTotp = () => {
  showDisableTotp.value = true
}

// 确认禁用TOTP
const confirmDisableTotp = async () => {
  if (!disableTotpForm.totp_token) {
    ElMessage.error('请输入动态验证码')
    return
  }
  
  try {
    const res = await api.post('/api/auth/disable-totp', {
      totp_token: disableTotpForm.totp_token
    })
    
    if (res.success) {
      ElMessage.success('TOTP已禁用')
      showDisableTotp.value = false
      userInfo.totp_enabled = false
      disableTotpForm.totp_token = ''
      
      // 更新本地存储
      const userStr = localStorage.getItem('user_info')
      if (userStr) {
        const user = JSON.parse(userStr)
        user.totp_enabled = false
        localStorage.setItem('user_info', JSON.stringify(user))
      }
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '禁用失败')
  }
}

// 创建用户
const handleCreateUser = async () => {
  if (!createUserForm.username || !createUserForm.password) {
    ElMessage.error('用户名和密码不能为空')
    return
  }
  
  try {
    const res = await api.post('/api/auth/users', {
      username: createUserForm.username,
      password: createUserForm.password,
      email: createUserForm.email,
      is_admin: createUserForm.is_admin,
      enable_totp: createUserForm.enable_totp
    })
    
    if (res.success) {
      ElMessage.success('用户创建成功')
      showCreateUser.value = false
      createUserForm.username = ''
      createUserForm.password = ''
      createUserForm.email = ''
      createUserForm.is_admin = false
      createUserForm.enable_totp = false
      loadUserList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '创建失败')
  }
}

// 编辑用户
const handleEditUser = (user) => {
  editUserForm.id = user.id
  editUserForm.username = user.username
  editUserForm.email = user.email || ''
  editUserForm.is_admin = user.is_admin
  editUserForm.is_active = user.is_active
  editUserForm.totp_enabled = user.totp_enabled  // 添加TOTP状态
  showEditUser.value = true
}

// 启用用户TOTP
const handleEnableTotp = async () => {
  try {
    const res = await api.post(`/api/auth/users/${editUserForm.id}/enable-totp`)
    if (res.success) {
      ElMessage.success('TOTP已启用')
      editUserForm.totp_enabled = true
      // 更新用户列表
      loadUserList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '启用失败')
  }
}

// 禁用用户TOTP
const handleDisableTotpForUser = async () => {
  try {
    const res = await api.post(`/api/auth/users/${editUserForm.id}/disable-totp`)
    if (res.success) {
      ElMessage.success('TOTP已禁用')
      editUserForm.totp_enabled = false
      // 更新用户列表
      loadUserList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '禁用失败')
  }
}

// 重置用户TOTP
const handleResetTotp = async () => {
  try {
    const res = await ElMessageBox.confirm(
      '重置后，用户需要重新扫码绑定TOTP。是否继续？',
      '确认重置',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    if (res === 'confirm') {
      const response = await api.post(`/api/auth/users/${editUserForm.id}/reset-totp`)
      if (response.success) {
        ElMessage.success('TOTP已重置，用户需要重新扫码绑定')
        // 更新用户列表
        loadUserList()
        // 关闭编辑对话框
        showEditUser.value = false
      }
    }
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.error || '重置失败')
    }
  }
}

// 更新用户
const handleUpdateUser = async () => {
  if (!editUserForm.username) {
    ElMessage.error('用户名不能为空')
    return
  }
  
  try {
    const res = await api.put(`/api/auth/users/${editUserForm.id}`, {
      username: editUserForm.username,
      email: editUserForm.email,
      is_admin: editUserForm.is_admin,
      is_active: editUserForm.is_active
    })
    
    if (res.success) {
      ElMessage.success('用户信息更新成功')
      showEditUser.value = false
      loadUserList()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '更新失败')
  }
}

// 重置密码
const handleResetPassword = (user) => {
  selectedUserId.value = user.id
  resetPasswordForm.password = ''
  showResetPassword.value = true
}

// 确认重置密码
const confirmResetPassword = async () => {
  if (!resetPasswordForm.password) {
    ElMessage.error('密码不能为空')
    return
  }
  
  try {
    const res = await api.post(`/api/auth/users/${selectedUserId.value}/reset-password`, {
      password: resetPasswordForm.password
    })
    
    if (res.success) {
      ElMessage.success('密码重置成功')
      showResetPassword.value = false
      resetPasswordForm.password = ''
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '重置失败')
  }
}

// 删除用户
const handleDeleteUser = async (user) => {
  try {
    await ElMessageBox.confirm(`确定要删除用户 "${user.username}" 吗？`, '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    const res = await api.delete(`/api/auth/users/${user.id}`)
    if (res.success) {
      ElMessage.success('用户已删除')
      loadUserList()
    }
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.error || '删除失败')
    }
  }
}

// ========== Webhook 方法 ==========
const loadWebhookConfigs = async () => {
  try {
    const res = await api.get('/api/webhook/configs')
    if (res.success) {
      webhookConfigs.value = res.data || []
    }
  } catch (e) {
    console.error('加载Webhook配置失败:', e)
  }
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
    const res = await api.post('/api/webhook/configs', { ...webhookForm })
    if (res.success) {
      ElMessage.success('Webhook 配置已保存')
      showWebhookForm.value = false
      editingWebhook.value = null
      loadWebhookConfigs()
    }
  } catch (e) {}
}

const testWebhookItem = async (cfg) => {
  try {
    const res = await api.post('/api/webhook/test', {
      platform: cfg.platform,
      webhook_url: cfg.webhook_url,
      secret: cfg.secret,
    })
    if (res.success) {
      ElMessage.success('测试消息已发送')
    } else {
      ElMessage.error(res.message || '发送失败')
    }
  } catch (e) {}
}

const deleteWebhookItem = async (cfg) => {
  try {
    await ElMessageBox.confirm(`确定要删除 ${cfg.platform === 'dingtalk' ? '钉钉' : cfg.platform === 'wecom' ? '企业微信' : '飞书'} 的通知渠道吗？`, '确认删除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    const res = await api.delete(`/api/webhook/configs/${cfg.platform}`)
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

onMounted(() => {
  loadSettings()
  
  // 检查URL参数，自动切换到指定Tab
  const tab = route.query.tab
  if (tab) {
    mainTabActive.value = tab
  }
})
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
