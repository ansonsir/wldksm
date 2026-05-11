import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

const api = axios.create({
  baseURL: '',
  timeout: 30000,
})

// 请求拦截器：添加Authorization头
api.interceptors.request.use(
  config => {
    const token = localStorage.getItem('auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器：处理401错误和token刷新
api.interceptors.response.use(
  response => response.data,
  async error => {
    const originalRequest = error.config
    
    // 处理401错误（未认证）
    if (error.response?.status === 401) {
      // 如果是刷新token的请求失败，直接跳转登录
      if (originalRequest.url === '/api/auth/refresh') {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('user_info')
        router.push('/login')
        ElMessage.error('登录已过期，请重新登录')
        return Promise.reject(error)
      }
      
      // 尝试刷新token
      try {
        const refreshToken = localStorage.getItem('refresh_token')
        if (!refreshToken) {
          throw new Error('No refresh token')
        }
        
        const refreshResponse = await axios.post('/api/auth/refresh', {
          refresh_token: refreshToken
        })
        
        if (refreshResponse.data.success) {
          // 保存新token
          const { token, refresh_token } = refreshResponse.data.data
          localStorage.setItem('auth_token', token)
          localStorage.setItem('refresh_token', refresh_token)
          
          // 重试原请求
          originalRequest.headers.Authorization = `Bearer ${token}`
          return api(originalRequest)
        }
      } catch (refreshError) {
        // 刷新失败，清除本地数据，跳转登录页
        localStorage.removeItem('auth_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('user_info')
        router.push('/login')
        ElMessage.warning('登录已过期（15分钟无操作），请重新登录')
      }
      
      return Promise.reject(error)
    }
    
    // 其他错误
    const msg = error.response?.data?.error || error.response?.data?.message || error.message || '请求失败'
    ElMessage.error(msg)
    return Promise.reject(error)
  }
)

export default api
