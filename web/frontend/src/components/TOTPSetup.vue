<template>
  <div class="totp-setup-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <h3>设置双因素认证 (TOTP)</h3>
        </div>
      </template>

      <!-- 步骤1：显示二维码 -->
      <div v-if="step === 1" class="step-content">
        <el-alert
          title="使用手机扫描以下二维码"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 20px"
        />

        <div class="qr-code-container">
          <img :src="qrCode" alt="TOTP QR Code" class="qr-code" />
        </div>

        <el-divider>或手动输入密钥</el-divider>

        <div class="secret-key">
          <el-input v-model="secretKey" readonly>
            <template #append>
              <el-button @click="copySecret">复制</el-button>
            </template>
          </el-input>
        </div>

        <el-alert
          title="推荐使用 Google Authenticator 或 Microsoft Authenticator"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: 20px"
        />

        <el-button
          type="primary"
          size="large"
          style="margin-top: 20px; width: 100%"
          @click="step = 2"
        >
          下一步
        </el-button>
      </div>

      <!-- 步骤2：验证TOTP -->
      <div v-else-if="step === 2" class="step-content">
        <el-alert
          title="请输入手机APP显示的6位验证码"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 20px"
        />

        <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="handleVerify">
          <el-form-item prop="totp_token">
            <el-input
              v-model="form.totp_token"
              placeholder="请输入6位动态验证码"
              size="large"
              maxlength="6"
              @keyup.enter="handleVerify"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              size="large"
              :loading="loading"
              style="width: 100%"
              @click="handleVerify"
            >
              验证并启用
            </el-button>
          </el-form-item>

          <el-form-item>
            <el-button size="large" style="width: 100%" @click="step = 1">
              返回
            </el-button>
          </el-form-item>
        </el-form>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const props = defineProps({
  onSuccess: {
    type: Function,
    default: null
  }
})

const step = ref(1)
const loading = ref(false)
const qrCode = ref('')
const secretKey = ref('')
const formRef = ref(null)

const form = reactive({
  totp_token: ''
})

const rules = {
  totp_token: [
    { required: true, message: '请输入动态验证码', trigger: 'blur' },
    { len: 6, message: '验证码为6位数字', trigger: 'blur' }
  ]
}

// 初始化TOTP设置
const initTotpSetup = async () => {
  try {
    const response = await api.post('/api/v1/auth/setup-totp')
    if (response.success) {
      qrCode.value = response.data.qr_code
      secretKey.value = response.data.secret
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '设置TOTP失败')
  }
}

// 验证TOTP
const handleVerify = async () => {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (!valid) return

    loading.value = true
    try {
      const response = await api.post('/api/v1/auth/verify-totp-setup', {
        totp_token: form.totp_token
      })

      if (response.success) {
        ElMessage.success('TOTP启用成功')
        
        // 调用成功回调
        if (props.onSuccess) {
          props.onSuccess()
        }
      }
    } catch (error) {
      ElMessage.error(error.response?.data?.error || '验证失败')
      form.totp_token = ''
    } finally {
      loading.value = false
    }
  })
}

// 复制密钥
const copySecret = async () => {
  try {
    await navigator.clipboard.writeText(secretKey.value)
    ElMessage.success('密钥已复制到剪贴板')
  } catch (error) {
    ElMessage.error('复制失败，请手动复制')
  }
}

// 组件挂载时初始化
initTotpSetup()
</script>

<style scoped>
.totp-setup-container {
  max-width: 500px;
  margin: 0 auto;
}

.card-header h3 {
  margin: 0;
  font-size: 18px;
  color: #303133;
}

.step-content {
  padding: 10px 0;
}

.qr-code-container {
  text-align: center;
  margin: 20px 0;
}

.qr-code {
  max-width: 200px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  padding: 10px;
  background: white;
}

.secret-key {
  margin: 20px 0;
}

.el-divider {
  margin: 20px 0;
}
</style>
