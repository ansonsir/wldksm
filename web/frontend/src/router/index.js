import { createRouter, createWebHashHistory } from 'vue-router'
import Layout from '@/components/Layout.vue'

const routes = [
  // 登录页面（不需要认证）
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false }
  },
  // 主应用（需要认证）
  {
    path: '/',
    component: Layout,
    redirect: '/dashboard',
    meta: { requiresAuth: true },
    children: [
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue') },
      { path: 'scan', name: 'Scan', component: () => import('@/views/Scan.vue') },
      { path: 'scheduler', name: 'Scheduler', component: () => import('@/views/Scheduler.vue') },
      { path: 'history', name: 'History', component: () => import('@/views/History.vue') },
      { path: 'reports', name: 'Reports', component: () => import('@/views/Reports.vue') },
      { path: 'assets', name: 'Assets', component: () => import('@/views/Assets.vue') },
      { path: 'templates', name: 'Templates', component: () => import('@/views/Templates.vue') },
      { path: 'settings', name: 'Settings', component: () => import('@/views/Settings.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('auth_token')
  const userInfoStr = localStorage.getItem('user_info')
  let userInfo = null
  
  try {
    if (userInfoStr) {
      userInfo = JSON.parse(userInfoStr)
    }
  } catch (e) {
    console.error('解析用户信息失败:', e)
  }
  
  // 首次登录用户强制返回登录页（未完成改密）
  if (userInfo && userInfo.first_login) {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('user_info')
    sessionStorage.clear()
    if (to.path !== '/login') {
      next('/login')
      return
    }
  }
  
  // 需要认证的页面
  if (to.matched.some(record => record.meta.requiresAuth !== false) && to.path !== '/login') {
    if (!token) {
      // 未登录，跳转到登录页
      next('/login')
    } else if (userInfo && !userInfo.totp_enabled && to.path !== '/settings') {
      // 已登录但未启用TOTP，强制跳转到安全设置
      next('/settings?tab=security&force_totp=true')
    } else {
      next()
    }
  }
  // 已登录访问登录页，跳转到首页（首次登录用户除外）
  else if (to.path === '/login' && token && !(userInfo && userInfo.first_login)) {
    next('/dashboard')
  }
  // 其他情况（登录页或不需要认证的页面）
  else {
    next()
  }
})

export default router
