<template>
  <div class="page-container">
    <PageHeader title="资产追踪" subtitle="追踪扫描结果变化，对比两次扫描差异" icon="TrendCharts" />

    <el-tabs v-model="activeTab" type="border-card">
      <!-- 扫描对比 Tab -->
      <el-tab-pane label="扫描对比" name="compare">
        <div class="compare-section">
          <div class="compare-selectors">
            <div class="selector-item">
              <span class="selector-label">旧扫描记录：</span>
              <el-select v-model="compareOldId" placeholder="选择旧版本" style="width:280px" filterable>
                <el-option
                  v-for="r in scanRecords"
                  :key="r.id"
                  :label="`#${r.id} - ${r.start_time} (${r.total_hosts || 0}台/${r.open_ports || 0}端口)`"
                  :value="r.id"
                />
              </el-select>
            </div>
            <div class="selector-item">
              <span class="selector-label">新扫描记录：</span>
              <el-select v-model="compareNewId" placeholder="选择新版本" style="width:280px" filterable>
                <el-option
                  v-for="r in scanRecords"
                  :key="r.id"
                  :label="`#${r.id} - ${r.start_time} (${r.total_hosts || 0}台/${r.open_ports || 0}端口)`"
                  :value="r.id"
                />
              </el-select>
            </div>
            <el-button type="primary" @click="doCompare" :loading="comparing" :disabled="!compareOldId || !compareNewId">
              <el-icon><Search /></el-icon> 开始对比
            </el-button>
          </div>

          <!-- 对比结果 -->
          <div v-if="compareResult" style="margin-top:20px">
            <el-row :gutter="16">
              <el-col :span="6">
                <el-statistic title="旧扫描主机数" :value="compareResult.total_old || 0" />
              </el-col>
              <el-col :span="6">
                <el-statistic title="新扫描主机数" :value="compareResult.total_new || 0" />
              </el-col>
              <el-col :span="6">
                <el-statistic title="新增主机" :value="(compareResult.new_hosts || []).length">
                  <template #suffix>
                    <el-tag v-if="(compareResult.new_hosts || []).length > 0" type="danger" size="small" effect="dark">+{{ compareResult.new_hosts.length }}</el-tag>
                  </template>
                </el-statistic>
              </el-col>
              <el-col :span="6">
                <el-statistic title="下线主机" :value="(compareResult.removed_hosts || []).length">
                  <template #suffix>
                    <el-tag v-if="(compareResult.removed_hosts || []).length > 0" type="warning" size="small" effect="dark">-{{ compareResult.removed_hosts.length }}</el-tag>
                  </template>
                </el-statistic>
              </el-col>
            </el-row>

            <!-- 新增主机 -->
            <div v-if="(compareResult.new_hosts || []).length > 0" style="margin-top:16px">
              <h4 style="margin:0 0 8px;font-size:14px;color:#e6a23c">
                <el-icon><Warning /></el-icon> 新增主机 ({{ compareResult.new_hosts.length }})
              </h4>
              <div class="host-tag-list">
                <el-tag v-for="ip in compareResult.new_hosts" :key="ip" type="danger" effect="plain" size="small">{{ ip }}</el-tag>
              </div>
            </div>

            <!-- 下线主机 -->
            <div v-if="(compareResult.removed_hosts || []).length > 0" style="margin-top:16px">
              <h4 style="margin:0 0 8px;font-size:14px;color:#909399">
                <el-icon><CircleClose /></el-icon> 下线主机 ({{ compareResult.removed_hosts.length }})
              </h4>
              <div class="host-tag-list">
                <el-tag v-for="ip in compareResult.removed_hosts" :key="ip" type="info" effect="plain" size="small">{{ ip }}</el-tag>
              </div>
            </div>

            <!-- 端口变更 -->
            <div v-if="(compareResult.port_changes || []).length > 0" style="margin-top:16px">
              <h4 style="margin:0 0 8px;font-size:14px;color:#409eff">
                <el-icon><Connection /></el-icon> 端口变更 ({{ compareResult.port_changes.length }} 台主机)
              </h4>
              <el-table :data="compareResult.port_changes" size="small" max-height="400" stripe>
                <el-table-column prop="ip" label="IP 地址" width="160" />
                <el-table-column label="新增端口" min-width="200">
                  <template #default="{ row }">
                    <el-tag v-for="p in (row.added || [])" :key="'a'+p" type="danger" size="small" effect="plain" style="margin:2px">{{ p }}</el-tag>
                    <span v-if="!row.added?.length" style="color:#c0c4cc">-</span>
                  </template>
                </el-table-column>
                <el-table-column label="移除端口" min-width="200">
                  <template #default="{ row }">
                    <el-tag v-for="p in (row.removed || [])" :key="'r'+p" type="success" size="small" effect="plain" style="margin:2px">{{ p }}</el-tag>
                    <span v-if="!row.removed?.length" style="color:#c0c4cc">-</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <!-- 无变更 -->
            <div v-if="noChanges" style="margin-top:20px;text-align:center;color:#909399">
              <el-icon size="40"><CircleCheckFilled /></el-icon>
              <p style="margin-top:8px">两次扫描结果完全一致，未检测到资产变更</p>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 资产趋势 Tab -->
      <el-tab-pane label="资产趋势" name="trend">
        <div class="trend-section">
          <div class="trend-controls">
            <span class="selector-label">统计天数：</span>
            <el-radio-group v-model="trendDays" @change="loadTrend">
              <el-radio-button :value="7">7天</el-radio-button>
              <el-radio-button :value="14">14天</el-radio-button>
              <el-radio-button :value="30">30天</el-radio-button>
              <el-radio-button :value="60">60天</el-radio-button>
              <el-radio-button :value="90">90天</el-radio-button>
            </el-radio-group>
            <el-button @click="loadTrend" :loading="trendLoading" size="small" style="margin-left:12px">刷新</el-button>
          </div>

          <div ref="trendChartRef" style="width:100%;height:350px;margin-top:16px"></div>

          <el-row :gutter="16" style="margin-top:16px">
            <el-col :span="8">
              <el-card shadow="hover">
                <el-statistic title="累计活跃 IP" :value="assetSummary.unique_ips || 0" />
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="hover">
                <el-statistic title="近期新增 IP (30天)" :value="assetSummary.recent_new_ips || 0" />
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="hover">
                <el-statistic title="历史峰值主机数" :value="assetSummary.peak?.hosts || 0">
                  <template #suffix>
                    <span style="font-size:12px;color:#909399">
                      / {{ assetSummary.peak?.ports || 0 }} 端口
                    </span>
                  </template>
                </el-statistic>
              </el-card>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Warning, CircleClose, CircleCheckFilled, Connection } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import PageHeader from '@/components/PageHeader.vue'
import api from '@/api'

const activeTab = ref('compare')

// --- 扫描对比 ---
const scanRecords = ref([])
const compareOldId = ref(null)
const compareNewId = ref(null)
const comparing = ref(false)
const compareResult = ref(null)

const noChanges = ref(false)

const loadScanRecords = async () => {
  try {
    const res = await api.get('/api/v1/scan/history?limit=100')
    if (res.success) {
      scanRecords.value = (res.data || []).filter(r => r.status === 'completed')
    }
  } catch (e) {}
}

const doCompare = async () => {
  if (!compareOldId.value || !compareNewId.value) return
  comparing.value = true
  compareResult.value = null
  noChanges.value = false
  try {
    const res = await api.post('/api/v1/assets/compare', {
      record_id_old: compareOldId.value,
      record_id_new: compareNewId.value,
    })
    if (res.success) {
      compareResult.value = res.data
      const d = res.data
      noChanges.value = (!d.new_hosts?.length && !d.removed_hosts?.length && !d.port_changes?.length)
    } else {
      ElMessage.error(res.message)
    }
  } catch (e) {}
  comparing.value = false
}

// --- 资产趋势 ---
const trendDays = ref(30)
const trendLoading = ref(false)
const trendChartRef = ref(null)
let trendChart = null
const assetSummary = ref({ unique_ips: 0, recent_new_ips: 0, peak: { hosts: 0, ports: 0 } })

const loadTrend = async () => {
  trendLoading.value = true
  try {
    const res = await api.get(`/api/v1/assets/trend?days=${trendDays.value}`)
    if (res.success) {
      renderTrendChart(res.data || [])
    }
  } catch (e) {}
  trendLoading.value = false
}

const loadAssetSummary = async () => {
  try {
    const res = await api.get('/api/v1/assets/summary')
    if (res.success) {
      assetSummary.value = res.data || {}
    }
  } catch (e) {}
}

const renderTrendChart = (data) => {
  if (!trendChartRef.value) return
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value)
  }
  trendChart.setOption({
    tooltip: {
      trigger: 'axis',
    },
    legend: {
      data: ['主机数', '端口数', '扫描次数'],
      bottom: 0,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '12%',
      top: '8%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: data.map(d => d.date),
      axisLabel: { rotate: 45 },
    },
    yAxis: [
      {
        type: 'value',
        name: '数量',
      },
      {
        type: 'value',
        name: '扫描次数',
      },
    ],
    series: [
      {
        name: '主机数',
        type: 'line',
        data: data.map(d => d.host_count),
        smooth: true,
        itemStyle: { color: '#409eff' },
        areaStyle: { color: 'rgba(64,158,255,0.1)' },
      },
      {
        name: '端口数',
        type: 'line',
        data: data.map(d => d.port_count),
        smooth: true,
        itemStyle: { color: '#67c23a' },
        areaStyle: { color: 'rgba(103,194,58,0.1)' },
      },
      {
        name: '扫描次数',
        type: 'bar',
        yAxisIndex: 1,
        data: data.map(d => d.scan_count),
        itemStyle: { color: '#e6a23c' },
        barMaxWidth: 20,
      },
    ],
  })
}

watch(activeTab, (val) => {
  if (val === 'trend') {
    nextTick(() => {
      loadTrend()
      if (trendChart) trendChart.resize()
    })
  }
})

onMounted(() => {
  loadScanRecords()
  loadAssetSummary()
})
</script>

<style scoped>
.compare-section,
.trend-section {
  padding: 8px 0;
}

.compare-selectors {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.selector-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.selector-label {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
  font-weight: 500;
}

.host-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.trend-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
