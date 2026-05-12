<template>
  <el-card>
    <template #header>
      <span>扫描配置</span>
    </template>
    <el-form :model="configForm" label-width="150px">
      <el-form-item label="默认IP范围文件">
        <el-input v-model="configForm.ip_range_file" />
      </el-form-item>
      <el-form-item label="默认端口文件">
        <el-input v-model="configForm.ports_file" />
      </el-form-item>
      <el-form-item label="排除IP文件">
        <el-input v-model="configForm.exclude_ips_file" />
      </el-form-item>
      <el-form-item label="最大线程数">
        <el-slider v-model="configForm.max_workers" :min="1" :max="64" show-input />
      </el-form-item>
      <el-form-item label="Ulimit">
        <el-input-number v-model="configForm.ulimit" :min="1000" :max="65535" />
      </el-form-item>
      <el-form-item label="扫描超时(秒)">
        <el-input-number v-model="configForm.timeout" :min="30" :max="3600" />
      </el-form-item>
      <el-form-item label="扫描批次大小">
        <el-input-number v-model="configForm.batch_size" :min="1000" :max="50000" :step="1000" />
        <span style="margin-left: 10px; color: #999; font-size: 12px">RustScan 每批扫描的端口数，越大越快但占用更多资源</span>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="saveConfig">保存扫描配置</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const configForm = reactive({
  ip_range_file: '',
  ports_file: '',
  exclude_ips_file: '',
  max_workers: 32,
  ulimit: 32768,
  timeout: 300,
  batch_size: 10000,
})

const loadConfig = async () => {
  try {
    const res = await api.get('/api/v1/config')
    if (res.success) Object.assign(configForm, res.data)
  } catch (e) {
    /* parent handles error */
  }
}

const saveConfig = async () => {
  try {
    const res = await api.post('/api/v1/config', configForm)
    if (res.success) ElMessage.success('配置已保存')
  } catch (e) {
    /* handled by interceptor */
  }
}

onMounted(loadConfig)
</script>
