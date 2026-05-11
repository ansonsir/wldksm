<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-header">
        <h1>网络端口扫描工具</h1>
        <p>安全认证登录</p>
      </div>

      <!-- 登录表单 -->
      <el-form
        v-if="!needTotp"
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        class="login-form"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="请输入用户名"
            :prefix-icon="User"
            size="large"
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            size="large"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item prop="captcha_code">
          <div class="captcha-row">
            <el-input
              v-model="loginForm.captcha_code"
              placeholder="请输入验证码"
              size="large"
              style="flex: 1"
              @keyup.enter="handleLogin"
            />
            <img
              :src="captchaImage"
              class="captcha-image"
              @click="refreshCaptcha"
              title="点击刷新验证码"
            />
          </div>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            class="login-button"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>

      <!-- TOTP验证表单 -->
      <el-form
        v-else
        ref="totpFormRef"
        :model="totpForm"
        :rules="totpRules"
        class="login-form"
        @submit.prevent="handleTotpLogin"
      >
        <div class="totp-info">
          <el-icon size="48" color="#409EFF"><Lock /></el-icon>
          <p>请输入动态验证码</p>
          <p class="totp-hint">打开Google Authenticator或Microsoft Authenticator查看验证码</p>
        </div>

        <el-form-item prop="totp_token">
          <el-input
            v-model="totpForm.totp_token"
            placeholder="请输入6位动态验证码"
            size="large"
            maxlength="6"
            @keyup.enter="handleTotpLogin"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            class="login-button"
            @click="handleTotpLogin"
          >
            验证
          </el-button>
        </el-form-item>

        <el-form-item>
          <el-button size="large" class="login-button" @click="backToLogin">
            返回
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-footer">
        <p>© 2026 网络端口扫描工具</p>
      </div>
    </div>
    
    <!-- 首次登录修改密码对话框 -->
    <el-dialog
      v-model="showChangePassword"
      title="首次登录 - 请修改密码"
      width="500px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
    >
      <el-alert
        type="warning"
        :closable="false"
        style="margin-bottom: 20px"
      >
        <template #title>
          首次登录必须修改密码后才能继续使用系统
        </template>
      </el-alert>
      
      <el-form
        ref="changePasswordFormRef"
        :model="changePasswordForm"
        :rules="changePasswordRules"
        label-width="100px"
      >
        <el-form-item label="新密码" prop="new_password">
          <el-input
            v-model="changePasswordForm.new_password"
            type="password"
            placeholder="请输入新密码"
            show-password
          />
        </el-form-item>
        
        <el-form-item label="确认密码" prop="confirm_password">
          <el-input
            v-model="changePasswordForm.confirm_password"
            type="password"
            placeholder="请再次输入新密码"
            show-password
          />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button type="primary" @click="handleChangePassword" :loading="changingPassword">
          确认修改
        </el-button>
      </template>
    </el-dialog>
    
    <!-- TOTP设置对话框 -->
    <el-dialog
      v-model="showTotpSetup"
      title="绑定动态验证码"
      width="600px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
    >
      <el-alert
        type="info"
        :closable="false"
        style="margin-bottom: 20px"
      >
        <template #title>
          为了保障账户安全，请绑定动态验证码（OTP）
        </template>
      </el-alert>
      
      <TOTPSetup
        @success="handleTotpSetupSuccess"
        @cancel="handleTotpSetupCancel"
      />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'
import axios from 'axios'
import { secureSetItem, fetchCsrfToken } from '@/api'
import TOTPSetup from '@/components/TOTPSetup.vue'

const router = useRouter()
const loading = ref(false)
const needTotp = ref(false)
const captchaImage = ref('')
const loginFormRef = ref(null)
const totpFormRef = ref(null)

// 首次登录相关
const showChangePassword = ref(false)
const showTotpSetup = ref(false)
const changingPassword = ref(false)
const changePasswordFormRef = ref(null)
const currentUserId = ref(null)
const currentToken = ref(null)

const changePasswordForm = reactive({
  new_password: '',
  confirm_password: ''
})

const changePasswordRules = {
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, max: 50, message: '密码长度8-50位', trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: '请再次输入密码', trigger: 'blur' }
  ]
}

const loginForm = reactive({
  username: '',
  password: '',
  captcha_id: '',
  captcha_code: ''
})

const totpForm = reactive({
  totp_token: ''
})

const loginRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' }
  ],
  captcha_code: [
    { required: true, message: '请输入验证码', trigger: 'blur' },
    { len: 4, message: '验证码为4位字符', trigger: 'blur' }
  ]
}

const totpRules = {
  totp_token: [
    { required: true, message: '请输入动态验证码', trigger: 'blur' },
    { len: 6, message: '动态验证码为6位数字', trigger: 'blur' }
  ]
}

// 获取验证码
const refreshCaptcha = async () => {
  try {
    const response = await axios.post('/api/auth/captcha')
    if (response.data.success) {
      captchaImage.value = response.data.data.captcha_image
      loginForm.captcha_id = response.data.data.captcha_id
    }
  } catch (error) {
    console.error('获取验证码失败:', error)
  }
}

// 登录
const handleLogin = async () => {
  if (!loginFormRef.value) return
  
  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    loading.value = true
    try {
      const response = await axios.post('/api/auth/login', loginForm)
      
      if (response.data.success) {
        const data = response.data.data
        
        // 调试日志
        console.log('登录返回数据:', data)
        console.log('need_totp:', data.need_totp)
        console.log('need_totp_setup:', data.need_totp_setup)
        console.log('user_info:', data.user_info)
        
        if (data.need_totp) {
          // 需要TOTP验证（已启用TOTP的用户）
          needTotp.value = true
          // 保存 totp_session_token 用于 TOTP 第二步验证
          if (data.totp_session_token) {
            sessionStorage.setItem('totp_session_token', data.totp_session_token)
          }
          ElMessage.info('请输入动态验证码')
        } else if (data.need_totp_setup) {
          // 需要设置TOTP（未启用TOTP的用户，包括重置后需要重新设置的用户）
          secureSetItem('auth_token', data.token)
          secureSetItem('refresh_token', data.refresh_token)
          localStorage.setItem('user_info', JSON.stringify(data.user_info))
          
          // 获取CSRF Token
          fetchCsrfToken().catch(() => {})
          
          // 保存当前用户ID和token
          currentUserId.value = data.user_info.id
          currentToken.value = data.token
          
          // 检查是否首次登录（需要修改密码）
          if (data.user_info.first_login) {
            ElMessage.warning('首次登录，请先修改密码')
            showChangePassword.value = true
          } else {
            // 非首次登录，直接显示TOTP设置对话框
            ElMessage.warning('需要设置双因素认证')
            showTotpSetup.value = true
          }
        } else {
          // 已启用TOTP且验证通过，或者系统不强制TOTP
          secureSetItem('auth_token', data.token)
          secureSetItem('refresh_token', data.refresh_token)
          localStorage.setItem('user_info', JSON.stringify(data.user_info))
          
          // 获取CSRF Token
          fetchCsrfToken().catch(() => {})
          
          ElMessage.success('登录成功')
          
          // 检查是否首次登录
          if (data.user_info.first_login) {
            currentUserId.value = data.user_info.id
            currentToken.value = data.token
            showChangePassword.value = true
          } else {
            router.push('/dashboard')
          }
        }
      }
    } catch (error) {
      const errorMsg = error.response?.data?.message || error.response?.data?.error || '登录失败'
      ElMessage.error(errorMsg)
      
      // 刷新验证码
      refreshCaptcha()
      loginForm.captcha_code = ''
    } finally {
      loading.value = false
    }
  })
}

// TOTP验证
const handleTotpLogin = async () => {
  if (!totpFormRef.value) return
  
  // 防止重复提交
  if (loading.value) return
  
  await totpFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    loading.value = true
    try {
      const response = await axios.post('/api/auth/login/totp', {
        totp_token: totpForm.totp_token,
        totp_session_token: sessionStorage.getItem('totp_session_token') || ''
      })
      
      if (response.data.success) {
        const data = response.data.data
        
        secureSetItem('auth_token', data.token)
        secureSetItem('refresh_token', data.refresh_token)
        localStorage.setItem('user_info', JSON.stringify(data.user_info))
        
        // 获取CSRF Token
        fetchCsrfToken().catch(() => {})
        
        // 清除临时存储
        sessionStorage.removeItem('totp_session_token')
        
        ElMessage.success('登录成功')
        
        // 检查是否首次登录
        if (data.user_info.first_login) {
          // 保存当前用户ID和token，用于修改密码
          currentUserId.value = data.user_info.id
          currentToken.value = data.token
          
          // 显示修改密码对话框
          setTimeout(() => {
            showChangePassword.value = true
          }, 500)
        } else if (!data.user_info.totp_enabled) {
          // 如果未启用TOTP，显示TOTP设置对话框
          setTimeout(() => {
            showTotpSetup.value = true
          }, 500)
        } else {
          // 正常跳转
          setTimeout(() => {
            router.push('/dashboard')
          }, 300)
        }
      }
    } catch (error) {
      // 显示后端返回的错误信息
      const errorMsg = error.response?.data?.message || error.response?.data?.error || '验证失败'
      ElMessage.error(errorMsg)
      totpForm.totp_token = ''
    } finally {
      loading.value = false
    }
  })
}

// 返回登录页
const backToLogin = () => {
  needTotp.value = false
  totpForm.totp_token = ''
  sessionStorage.removeItem('totp_session_token')
}

// 首次登录修改密码
const handleChangePassword = async () => {
  if (!changePasswordFormRef.value) return
  
  await changePasswordFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    if (changePasswordForm.new_password !== changePasswordForm.confirm_password) {
      ElMessage.error('两次输入的密码不一致')
      return
    }
    
    changingPassword.value = true
    try {
      const response = await axios.post('/api/auth/change-password', {
        old_password: '',  // 首次登录不需要旧密码
        new_password: changePasswordForm.new_password,
        first_login: true  // 标记首次登录
      }, {
        headers: {
          'Authorization': `Bearer ${currentToken.value}`
        }
      })
      
      if (response.data.success) {
        ElMessage.success('密码修改成功')
        showChangePassword.value = false
        
        // 更新本地user_info
        const userInfo = JSON.parse(localStorage.getItem('user_info'))
        userInfo.first_login = false
        localStorage.setItem('user_info', JSON.stringify(userInfo))
        
        // 检查是否需要设置TOTP
        if (!userInfo.totp_enabled) {
          showTotpSetup.value = true
        } else {
          router.push('/dashboard')
        }
      }
    } catch (error) {
      ElMessage.error(error.response?.data?.error || '修改密码失败')
    } finally {
      changingPassword.value = false
    }
  })
}

// TOTP设置成功
const handleTotpSetupSuccess = async () => {
  showTotpSetup.value = false
  
  // 更新本地user_info
  const userInfo = JSON.parse(localStorage.getItem('user_info'))
  userInfo.totp_enabled = true
  localStorage.setItem('user_info', JSON.stringify(userInfo))
  
  ElMessage.success('动态验证码设置成功')
  router.push('/dashboard')
}

// TOTP设置取消
const handleTotpSetupCancel = () => {
  showTotpSetup.value = false
  ElMessage.warning('请先完成动态验证码设置')
}

// 页面加载时获取验证码
onMounted(() => {
  refreshCaptcha()
})
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 30%, #334155 70%, #0f172a 100%);
}

.login-box {
  width: 420px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  padding: 40px;
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.login-header h1 {
  font-size: 28px;
  color: #303133;
  margin: 0 0 8px 0;
  font-weight: 600;
}

.login-header p {
  font-size: 14px;
  color: #909399;
  margin: 0;
}

.login-form {
  margin-top: 20px;
}

.captcha-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.captcha-image {
  height: 40px;  /* 增加高度，与后端一致 */
  width: 140px;  /* 增加宽度，与后端一致 */
  cursor: pointer;
  border-radius: 6px;  /* 增加圆角 */
  transition: transform 0.2s, box-shadow 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);  /* 添加阴影，更清晰 */
  background: #fff;  /* 白色背景 */
}

.captcha-image:hover {
  transform: scale(1.05);  /* 悬停时放大 */
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);  /* 悬停时阴影更深 */
}

.login-button {
  width: 100%;
}

.totp-info {
  text-align: center;
  margin-bottom: 20px;
}

.totp-info p {
  margin: 12px 0 0 0;
  font-size: 16px;
  color: #303133;
  font-weight: 500;
}

.totp-hint {
  font-size: 12px;
  color: #909399;
  font-weight: normal !important;
}

.login-footer {
  margin-top: 30px;
  text-align: center;
}

.login-footer p {
  font-size: 12px;
  color: #94a3b8;
  margin: 0;
}
</style>
