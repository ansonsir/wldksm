import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import api, { secureGetItem, secureSetItem, fetchCsrfToken, clearCsrfToken } from '@/api'
import { ElMessage } from 'element-plus'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(secureGetItem('auth_token') || '')
  const userInfo = ref(JSON.parse(localStorage.getItem('user_info') || 'null'))

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => userInfo.value?.is_admin || false)
  const username = computed(() => userInfo.value?.username || '')

  function setAuth(newToken, user) {
    token.value = newToken
    userInfo.value = user
    secureSetItem('auth_token', newToken)
    localStorage.setItem('user_info', JSON.stringify(user))
    // 登录后异步获取 CSRF Token
    fetchCsrfToken().catch(() => {})
  }

  function clearAuth() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('auth_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user_info')
    localStorage.removeItem('_fp')
    clearCsrfToken()
  }

  async function logout(router) {
    try {
      await api.post('/api/auth/logout')
    } catch (e) {}
    clearAuth()
    ElMessage.success('已退出登录')
    router.push('/login')
  }

  return { token, userInfo, isLoggedIn, isAdmin, username, setAuth, clearAuth, logout }
})
