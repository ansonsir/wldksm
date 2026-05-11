import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'

export const useAppStore = defineStore('app', () => {
  const systemStatus = ref('online')
  const sidebarCollapsed = ref(false)
  const notifications = ref([])

  async function checkHealth() {
    try {
      const res = await fetch('/api/system/health')
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

  return { systemStatus, sidebarCollapsed, notifications, checkHealth, addNotification, clearNotifications }
})
