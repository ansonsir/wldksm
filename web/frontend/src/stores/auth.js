import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api'
import axios from 'axios'
import { ElMessage } from 'element-plus'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('auth_token') || '')
  const userInfo = ref(JSON.parse(localStorage.getItem('user_info') || 'null'))

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => userInfo.value?.is_admin || false)
  const username = computed(() => userInfo.value?.username || '')

  function setAuth(newToken, user) {
    token.value = newToken
    userInfo.value = user
    localStorage.setItem('auth_token', newToken)
    localStorage.setItem('user_info', JSON.stringify(user))
  }

  function clearAuth() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('auth_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user_info')
  }

  async function logout(router) {
    try {
      await axios.post('/api/auth/logout')
    } catch (e) {}
    clearAuth()
    ElMessage.success('已退出登录')
    router.push('/login')
  }

  return { token, userInfo, isLoggedIn, isAdmin, username, setAuth, clearAuth, logout }
})
