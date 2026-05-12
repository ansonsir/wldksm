<template>
  <div>
    <!-- 修改密码 -->
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

    <!-- TOTP 双因素认证 -->
    <el-card>
      <template #header>
        <span>双因素认证 (TOTP)</span>
      </template>
      <!-- 未启用TOTP -->
      <div v-if="!totpEnabled">
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
        <el-button v-if="isAdmin" type="danger" @click="showDisableTotp = true">禁用TOTP</el-button>
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
  </div>
</template>

<script setup>
import { reactive, ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api'
import TOTPSetup from '@/components/TOTPSetup.vue'

const route = useRoute()
const router = useRouter()

const userStr = localStorage.getItem('user_info')
const user = userStr ? JSON.parse(userStr) : {}

const isAdmin = computed(() => user.is_admin)
const totpEnabled = ref(user.totp_enabled || false)

const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: ''
})

const showTotpSetup = ref(false)
const showDisableTotp = ref(false)
const disableTotpForm = reactive({ totp_token: '' })

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
    const res = await api.post('/api/v1/auth/change-password', {
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

const handleTotpSuccess = () => {
  showTotpSetup.value = false
  totpEnabled.value = true
  // 更新本地存储
  const info = JSON.parse(localStorage.getItem('user_info') || '{}')
  info.totp_enabled = true
  localStorage.setItem('user_info', JSON.stringify(info))
  ElMessage.success('TOTP启用成功')
  // 如果是强制启用TOTP，跳转到首页
  if (route.query.force_totp === 'true') {
    ElMessage.success('双因素认证已启用，正在跳转到首页')
    setTimeout(() => router.push('/dashboard'), 1500)
  }
}

const confirmDisableTotp = async () => {
  if (!disableTotpForm.totp_token) {
    ElMessage.error('请输入动态验证码')
    return
  }
  try {
    const res = await api.post('/api/v1/auth/disable-totp', {
      totp_token: disableTotpForm.totp_token
    })
    if (res.success) {
      ElMessage.success('TOTP已禁用')
      showDisableTotp.value = false
      totpEnabled.value = false
      disableTotpForm.totp_token = ''
      const info = JSON.parse(localStorage.getItem('user_info') || '{}')
      info.totp_enabled = false
      localStorage.setItem('user_info', JSON.stringify(info))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '禁用失败')
  }
}
</script>
