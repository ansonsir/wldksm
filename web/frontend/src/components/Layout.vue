<template>
  <el-container class="app-layout">
    <!-- 侧边栏 -->
    <el-aside :width="isCollapse ? '64px' : '220px'" class="app-sidebar">
      <div class="sidebar-header" @click="$router.push('/dashboard')">
        <div class="sidebar-logo">
          <el-icon size="26"><Monitor /></el-icon>
        </div>
        <transition name="fade">
          <div v-show="!isCollapse" class="sidebar-title">
            <span class="title-main">ScanScript</span>
            <span class="title-sub">端口扫描 v4.0</span>
          </div>
        </transition>
      </div>

      <el-menu
        :default-active="$route.path"
        :collapse="isCollapse"
        :collapse-transition="false"
        background-color="var(--sidebar-bg)"
        text-color="#a0a5b0"
        active-text-color="#ffffff"
        router
        class="sidebar-menu"
      >
        <el-menu-item index="/dashboard">
          <el-icon><HomeFilled /></el-icon>
          <span>概览</span>
        </el-menu-item>
        <el-menu-item index="/scan">
          <el-icon><Aim /></el-icon>
          <span>扫描任务</span>
        </el-menu-item>
        <el-menu-item index="/scheduler">
          <el-icon><Clock /></el-icon>
          <span>定时任务</span>
        </el-menu-item>
        <el-menu-item index="/history">
          <el-icon><List /></el-icon>
          <span>扫描历史</span>
        </el-menu-item>
        <el-menu-item index="/assets">
          <el-icon><TrendCharts /></el-icon>
          <span>资产追踪</span>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><Document /></el-icon>
          <span>报告管理</span>
        </el-menu-item>
        <el-menu-item index="/templates">
          <el-icon><Files /></el-icon>
          <span>模板管理</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系统配置</span>
        </el-menu-item>
      </el-menu>

      <!-- 侧边栏底部状态 -->
      <div class="sidebar-footer">
        <transition name="fade">
          <div v-show="!isCollapse" class="footer-status">
            <span class="status-dot" :class="appStore.systemStatus"></span>
            <span class="status-text">{{ statusLabel }}</span>
          </div>
        </transition>
        <div class="footer-collapse" @click="isCollapse = !isCollapse">
          <el-icon size="16"><Fold v-if="!isCollapse" /><Expand v-else /></el-icon>
        </div>
      </div>
    </el-aside>

    <!-- 主体 -->
    <el-container class="app-main-container">
      <!-- 顶部导航 -->
      <el-header height="56px" class="app-header">
        <div class="header-left">
          <div class="breadcrumb-nav">
            <el-icon size="14"><Location /></el-icon>
            <span class="breadcrumb-item" v-for="(item, idx) in breadcrumbs" :key="idx">
              <span v-if="idx > 0" class="breadcrumb-sep">/</span>
              {{ item }}
            </span>
          </div>
        </div>

        <div class="header-right">
          <!-- 暗色模式切换 -->
          <el-tooltip :content="appStore.darkMode ? '切换亮色模式' : '切换暗色模式'" placement="bottom">
            <div class="theme-toggle" @click="appStore.toggleDarkMode">
              <el-icon size="18"><Sunny v-if="appStore.darkMode" /><Moon v-else /></el-icon>
            </div>
          </el-tooltip>

          <!-- 健康状态 -->
          <el-tooltip :content="`系统状态: ${statusLabel}`" placement="bottom">
            <div class="health-indicator">
              <span class="pulse-dot" :class="appStore.systemStatus"></span>
            </div>
          </el-tooltip>

          <!-- 用户菜单 -->
          <el-dropdown @command="handleCommand" trigger="click" placement="bottom-end">
            <div class="user-menu-trigger">
              <el-avatar :size="32" icon="UserFilled" style="background:#409eff" />
              <span class="user-name">{{ authStore.username }}</span>
              <el-icon size="14" class="user-arrow"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="security">
                  <el-icon><Lock /></el-icon>
                  安全设置
                </el-dropdown-item>
                <el-dropdown-item command="users" v-if="authStore.isAdmin">
                  <el-icon><User /></el-icon>
                  用户管理
                </el-dropdown-item>
                <el-dropdown-item divided command="logout">
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 内容区 -->
      <el-main class="app-content">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { ElMessageBox } from 'element-plus'
import { Fold, Expand, Monitor, Location, Sunny, Moon } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const appStore = useAppStore()

const isCollapse = ref(false)

// 健康检查
let healthTimer = null
appStore.checkHealth()
healthTimer = setInterval(() => appStore.checkHealth(), 60000)

onUnmounted(() => {
  if (healthTimer) clearInterval(healthTimer)
})

const statusLabel = computed(() => {
  if (appStore.systemStatus === 'online') return '系统正常'
  if (appStore.systemStatus === 'degraded') return '部分异常'
  return '系统离线'
})

// 面包屑
const breadcrumbs = computed(() => {
  const titles = {
    '/dashboard': '概览', '/scan': '扫描任务', '/scheduler': '定时任务',
    '/history': '扫描历史', '/reports': '报告管理', '/templates': '模板管理',
    '/assets': '资产追踪', '/settings': '系统配置'
  }
  const current = titles[route.path] || route.path
  return ['首页', current]
})

const handleCommand = async (command) => {
  if (command === 'security') {
    router.push('/settings?tab=security')
  } else if (command === 'users') {
    router.push('/settings?tab=users')
  } else if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
      await authStore.logout(router)
    } catch {}
  }
}
</script>

<style scoped>
/* --- 整体布局 --- */
.app-layout {
  height: 100vh;
  overflow: hidden;
}

/* --- 侧边栏 --- */
.app-sidebar {
  background: var(--sidebar-bg);
  display: flex;
  flex-direction: column;
  transition: width var(--transition-normal);
  overflow: hidden;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.06);
  z-index: 100;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.sidebar-header:hover {
  background: var(--sidebar-hover);
}
.sidebar-logo {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, #409eff, #337ecc);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}
.sidebar-title {
  display: flex;
  flex-direction: column;
  white-space: nowrap;
  overflow: hidden;
}
.title-main {
  font-size: 17px;
  font-weight: 700;
  color: #ffffff;
  line-height: 1.2;
}
.title-sub {
  font-size: 11px;
  color: #6b7280;
  line-height: 1.2;
}

.sidebar-menu {
  flex: 1;
  border-right: none !important;
  padding: 8px 0;
  overflow-y: auto;
  overflow-x: hidden;
}
.sidebar-menu :deep(.el-menu-item) {
  margin: 2px 8px;
  border-radius: 8px;
  height: 44px;
  line-height: 44px;
  font-size: 14px;
  transition: all var(--transition-fast);
}
.sidebar-menu :deep(.el-menu-item:hover) {
  background: var(--sidebar-hover) !important;
  color: #d1d5db !important;
}
.sidebar-menu :deep(.el-menu-item.is-active) {
  background: var(--sidebar-active) !important;
  color: #60a5fa !important;
  font-weight: 600;
  border-left: 3px solid #409eff;
  border-radius: 0 8px 8px 0;
}
.sidebar-menu :deep(.el-menu-item .el-icon) {
  font-size: 18px;
}

/* 侧边栏底部 */
.sidebar-footer {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.footer-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #6b7280;
  white-space: nowrap;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-dot.online { background: #22c55e; box-shadow: 0 0 6px rgba(34, 197, 94, 0.5); }
.status-dot.degraded { background: #f59e0b; box-shadow: 0 0 6px rgba(245, 158, 11, 0.5); }
.status-dot.offline { background: #ef4444; box-shadow: 0 0 6px rgba(239, 68, 68, 0.5); }
.footer-collapse {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b7280;
  border-radius: 6px;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.footer-collapse:hover {
  background: var(--sidebar-hover);
  color: #d1d5db;
}

/* --- 主体容器 --- */
.app-main-container {
  flex-direction: column;
  overflow: hidden;
}

/* --- 顶部导航 --- */
.app-header {
  background: var(--header-bg);
  border-bottom: 1px solid var(--header-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
  z-index: 99;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
}
.breadcrumb-nav {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--neutral-text-light);
}
.breadcrumb-nav .el-icon {
  color: var(--brand-primary);
}
.breadcrumb-sep {
  color: #c0c4cc;
  margin: 0 4px;
  font-weight: 300;
}
.breadcrumb-item:last-child {
  color: var(--neutral-text-dark);
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.health-indicator {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  cursor: pointer;
  transition: background var(--transition-fast);
}
.health-indicator:hover {
  background: var(--el-fill-color-light, #f5f7fa);
}
.pulse-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  position: relative;
}
.pulse-dot::after {
  content: '';
  position: absolute;
  inset: -3px;
  border-radius: 50%;
  animation: pulse 2s ease infinite;
}
.pulse-dot.online { background: #22c55e; }
.pulse-dot.online::after { background: rgba(34, 197, 94, 0.3); }
.pulse-dot.degraded { background: #f59e0b; }
.pulse-dot.degraded::after { background: rgba(245, 158, 11, 0.3); }
.pulse-dot.offline { background: #ef4444; }
.pulse-dot.offline::after { background: rgba(239, 68, 68, 0.3); }
@keyframes pulse {
  0%   { transform: scale(1); opacity: 1; }
  100% { transform: scale(2.2); opacity: 0; }
}

.theme-toggle {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  cursor: pointer;
  color: var(--neutral-text-light);
  transition: all var(--transition-fast);
}
.theme-toggle:hover {
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--brand-primary);
}
html.dark .theme-toggle:hover {
  background: var(--el-fill-color, #2a2a3c);
}
.user-menu-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 8px;
  transition: background var(--transition-fast);
}
.user-menu-trigger:hover {
  background: var(--el-fill-color-light, #f5f7fa);
}
.user-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--neutral-text-dark);
}
.user-arrow {
  color: var(--neutral-text-light);
  transition: transform var(--transition-fast);
}

/* --- 内容区 --- */
.app-content {
  background: var(--neutral-bg);
  padding: 20px 24px;
  overflow-y: auto;
  overflow-x: hidden;
  height: calc(100vh - 56px);
}

/* --- 过渡动画 --- */
.page-enter-active {
  animation: pageIn 0.28s ease;
}
.page-leave-active {
  animation: pageOut 0.2s ease;
}
@keyframes pageIn {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes pageOut {
  from { opacity: 1; transform: translateY(0); }
  to   { opacity: 0; transform: translateY(-6px); }
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--transition-fast);
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
