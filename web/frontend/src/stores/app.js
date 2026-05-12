import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'

export const useAppStore = defineStore('app', () => {
  const systemStatus = ref('online')
  const sidebarCollapsed = ref(false)
  const darkMode = ref(localStorage.getItem('darkMode') === 'true')
  const notifications = ref([])

  // 初始化暗色模式
  if (darkMode.value) {
    document.documentElement.classList.add('dark')
  }

  function toggleDarkMode() {
    darkMode.value = !darkMode.value
    localStorage.setItem('darkMode', darkMode.value)
    document.documentElement.classList.toggle('dark', darkMode.value)
  }

  async function checkHealth() {
    try {
      const res = await fetch('/api/v1/system/health')
      const data = await res.json()
      systemStatus.value = data.status === 'healthy' ? 'online' : 'degraded'
      return data
    } catch (e) {
      systemStatus.value = 'offline'
      return null
    }
  }

  function addNotification(type, title, message) {
    notifications.value.unshift({
      id: Date.now(),
      type,
      title,
      message,
      time: new Date().toLocaleString()
    })
    if (notifications.value.length > 50) {
      notifications.value = notifications.value.slice(0, 50)
    }
  }

  function clearNotifications() {
    notifications.value = []
  }

  return { systemStatus, sidebarCollapsed, darkMode, notifications, checkHealth, toggleDarkMode, addNotification, clearNotifications }
})
