import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

// 创建axios实例
const http = axios.create({
  baseURL: '/',
  timeout: 30000,
})

// 请求拦截器
http.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
http.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    // 处理401未授权错误（token过期或无效）
    if (error.response && error.response.status === 401) {
      // 清除本地存储的token和用户信息
      localStorage.removeItem('auth_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user_info')
      
      // 显示提示消息
      ElMessage.warning('登录已过期，请重新登录')
      
      // 跳转到登录页
      router.push('/login')
    }
    
    return Promise.reject(error)
  }
)

export default http
