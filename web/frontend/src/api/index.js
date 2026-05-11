import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

const api = axios.create({
  baseURL: '',
  timeout: 30000,
})

// 浏览器指纹生成（用于 Token 绑定，降低 XSS 窃取风险）
function generateFingerprint() {
  const components = [
    navigator.userAgent,
    navigator.language,
    screen.colorDepth,
    screen.width + 'x' + screen.height,
    new Date().getTimezoneOffset(),
  ]
  return btoa(components.join('|'))
}

// 安全存储 Token（附带指纹校验）
function secureSetItem(key, value) {
  localStorage.setItem(key, value)
  if (key === 'auth_token') {
    localStorage.setItem('_fp', generateFingerprint())
  }
}

function secureGetItem(key) {
  if (key === 'auth_token' || key === 'refresh_token') {
    const storedFp = localStorage.getItem('_fp')
    if (storedFp && storedFp !== generateFingerprint()) {
      // 指纹不匹配，可能 Token 被跨域窃取
      localStorage.removeItem('auth_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user_info')
      localStorage.removeItem('_fp')
      localStorage.removeItem('csrf_token')
      router.push('/login')
      return null
    }
  }
  return localStorage.getItem(key)
}

// ==================== CSRF Token 管理 ====================

function secureSetCsrfToken(token) {
  localStorage.setItem('csrf_token', token)
}

function secureGetCsrfToken() {
  return localStorage.getItem('csrf_token')
}

/**
 * 从后端获取 CSRF Token
 * 在登录成功后调用，后续所有写请求携带此Token
 */
async function fetchCsrfToken() {
  try {
    const token = secureGetItem('auth_token')
    if (!token) return false
    const response = await axios.get('/api/auth/csrf-token', {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (response.data?.success && response.data?.data?.csrf_token) {
      secureSetCsrfToken(response.data.data.csrf_token)
      return true
    }
    return false
  } catch (e) {
    console.warn('获取CSRF Token失败:', e)
    return false
  }
}

function clearCsrfToken() {
  localStorage.removeItem('csrf_token')
}

// 请求拦截器：添加Authorization头和CSRF Token
api.interceptors.request.use(
  config => {
    const token = secureGetItem('auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    // 对状态变更请求（POST/PUT/DELETE）附加CSRF Token
    if (['post', 'put', 'delete', 'patch'].includes(config.method?.toLowerCase())) {
      const csrfToken = secureGetCsrfToken()
      if (csrfToken) {
        config.headers['X-CSRF-Token'] = csrfToken
      }
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器：处理401错误和token刷新
api.interceptors.response.use(
  response => {
    // 文件下载等需要原始响应的场景直接返回完整response
    if (response.config.responseType === 'blob') {
      return response
    }
    return response.data
  },
  async error => {
    const originalRequest = error.config
    
    // 处理401错误（未认证）
    if (error.response?.status === 401) {
      // 如果是刷新token的请求失败，直接跳转登录
      if (originalRequest.url === '/api/auth/refresh') {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('user_info')
        localStorage.removeItem('_fp')
        clearCsrfToken()
        router.push('/login')
        ElMessage.error('登录已过期，请重新登录')
        return Promise.reject(error)
      }
      
      // 尝试刷新token
      try {
        const refreshToken = secureGetItem('refresh_token')
        if (!refreshToken) {
          throw new Error('No refresh token')
        }
        
        const refreshResponse = await axios.post('/api/auth/refresh', {
          refresh_token: refreshToken
        })
        
        if (refreshResponse.data.success) {
          // 保存新token
          const { token, refresh_token } = refreshResponse.data.data
          secureSetItem('auth_token', token)
          secureSetItem('refresh_token', refresh_token)
          
          // 重试原请求
          originalRequest.headers.Authorization = `Bearer ${token}`
          return api(originalRequest)
        }
      } catch (refreshError) {
        // 刷新失败，清除本地数据，跳转登录页
        localStorage.removeItem('auth_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('user_info')
        localStorage.removeItem('_fp')
        clearCsrfToken()
        router.push('/login')
        ElMessage.warning('登录已过期（15分钟无操作），请重新登录')
      }
      
      return Promise.reject(error)
    }
    
    // 处理403错误（CSRF Token失效）
    if (error.response?.status === 403) {
      const errorMsg = error.response?.data?.error || ''
      if (errorMsg.includes('CSRF') && !originalRequest._csrfRetry) {
        originalRequest._csrfRetry = true
        const refreshed = await fetchCsrfToken()
        if (refreshed) {
          const csrfToken = secureGetCsrfToken()
          if (csrfToken) {
            originalRequest.headers['X-CSRF-Token'] = csrfToken
            return api(originalRequest)
          }
        }
      }
    }
    
    // 其他错误
    const msg = error.response?.data?.error || error.response?.data?.message || error.message || '请求失败'
    ElMessage.error(msg)
    return Promise.reject(error)
  }
)

export {
  secureSetItem,
  secureGetItem,
  fetchCsrfToken,
  clearCsrfToken,
}
export default api
