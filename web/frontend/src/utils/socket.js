import { io } from 'socket.io-client'
import { ref } from 'vue'

const socket = ref(null)
const connected = ref(false)

function connect() {
  if (socket.value?.connected) return socket.value

  const token = localStorage.getItem('auth_token')
  socket.value = io('/', {
    path: '/socket.io',
    auth: { token: token ? `Bearer ${token}` : '' },
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    reconnectionAttempts: 10,
  })

  socket.value.on('connect', () => {
    connected.value = true
    console.log('[WS] 已连接')
  })

  socket.value.on('disconnect', () => {
    connected.value = false
    console.log('[WS] 已断开')
  })

  socket.value.on('connect_error', (err) => {
    console.warn('[WS] 连接错误:', err.message)
    connected.value = false
  })

  return socket.value
}

function disconnect() {
  if (socket.value) {
    socket.value.disconnect()
    socket.value = null
    connected.value = false
  }
}

function joinRoom(room) {
  if (socket.value?.connected) {
    socket.value.emit('join', { room })
  }
}

function leaveRoom(room) {
  if (socket.value?.connected) {
    socket.value.emit('leave', { room })
  }
}

function on(event, callback) {
  if (socket.value) {
    socket.value.on(event, callback)
  }
}

function off(event, callback) {
  if (socket.value) {
    socket.value.off(event, callback)
  }
}

export { connect, disconnect, joinRoom, leaveRoom, on, off, connected }
