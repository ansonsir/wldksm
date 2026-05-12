<template>
  <div class="page-container">
    <PageHeader title="系统配置" subtitle="管理扫描、邮件、安全等全局设置" icon="Setting" />

    <el-tabs v-model="mainTabActive" type="border-card">
      <el-tab-pane label="扫描配置" name="scan">
        <SettingsScanConfig />
      </el-tab-pane>

      <el-tab-pane label="邮件配置" name="mail">
        <SettingsMailConfig />
      </el-tab-pane>

      <el-tab-pane label="安全设置" name="security">
        <SettingsSecurity />
      </el-tab-pane>

      <el-tab-pane label="用户管理" name="users" v-if="isAdmin">
        <SettingsUserManagement />
      </el-tab-pane>

      <el-tab-pane label="Webhook通知" name="webhook">
        <SettingsWebhookConfig />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SettingsScanConfig from '@/components/SettingsScanConfig.vue'
import SettingsMailConfig from '@/components/SettingsMailConfig.vue'
import SettingsSecurity from '@/components/SettingsSecurity.vue'
import SettingsUserManagement from '@/components/SettingsUserManagement.vue'
import SettingsWebhookConfig from '@/components/SettingsWebhookConfig.vue'

const route = useRoute()
const mainTabActive = ref('scan')

const userStr = localStorage.getItem('user_info')
const user = userStr ? JSON.parse(userStr) : {}
const isAdmin = computed(() => user.is_admin)

onMounted(() => {
  const tab = route.query.tab
  if (tab) mainTabActive.value = tab
})
</script>
