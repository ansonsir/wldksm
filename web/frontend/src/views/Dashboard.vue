<template>
  <div class="dashboard">
    <PageHeader title="系统概览" subtitle="实时监控扫描任务状态与安全态势" icon="DataAnalysis" />

    <!-- 健康状态横幅 -->
    <div class="health-banner">
      <div class="health-left">
        <el-tag :type="healthStatus.type" size="large" effect="dark" round>
          <span class="health-dot-inner"></span>
          {{ healthStatus.label }}
        </el-tag>
        <span class="health-sub">{{ healthStatus.detail }}</span>
      </div>
      <div class="health-right">
        <div class="health-chip" :class="healthInfo?.checks?.database === 'ok' ? 'ok' : 'err'">
          <span class="chip-dot"></span> 数据库
        </div>
        <div class="health-chip" :class="healthInfo?.checks?.scheduler?.running ? 'ok' : 'err'">
          <span class="chip-dot"></span> 调度器
        </div>
        <div class="health-chip ok">
          <span class="chip-dot"></span> {{ healthInfo?.checks?.active_scans ?? 0 }} 活跃扫描
        </div>
      </div>
    </div>

    <!-- 今日概览卡片 -->
    <div class="section-header">
      <span class="section-title">今日概览</span>
      <span class="section-date">{{ todayDate }}</span>
    </div>
    <div class="card-grid">
      <el-card class="stat-card" shadow="hover">
        <div class="stat-icon" style="background: linear-gradient(135deg, #ecf5ff, #d9ecff);color:#409eff">
          <el-icon size="22"><Document /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.today?.scans ?? 0 }}</div>
          <div class="stat-label">今日扫描</div>
        </div>
      </el-card>
      <el-card class="stat-card" shadow="hover">
        <div class="stat-icon" style="background: linear-gradient(135deg, #f0f9eb, #e1f3d8);color:#67c23a">
          <el-icon size="22"><Monitor /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.today?.hosts ?? 0 }}</div>
          <div class="stat-label">今日主机</div>
        </div>
      </el-card>
      <el-card class="stat-card" shadow="hover">
        <div class="stat-icon" style="background: linear-gradient(135deg, #fdf6ec, #faecd8);color:#e6a23c">
          <el-icon size="22"><Connection /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.today?.ports ?? 0 }}</div>
          <div class="stat-label">今日端口</div>
        </div>
      </el-card>
      <el-card class="stat-card" shadow="hover">
        <div class="stat-icon" :style="stats.success_rate >= 95 ? 'background:linear-gradient(135deg,#f0f9eb,#e1f3d8);color:#67c23a' : 'background:linear-gradient(135deg,#fef0f0,#fde2e2);color:#f56c6c'">
          <el-icon size="22"><CircleCheck /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.success_rate ?? 0 }}<span class="unit">%</span></div>
          <div class="stat-label">成功率</div>
        </div>
      </el-card>
    </div>

    <!-- 累计统计卡片 -->
    <div class="section-header">
      <span class="section-title">累计统计</span>
    </div>
    <div class="card-grid">
      <el-card class="stat-card" shadow="hover">
        <div class="stat-icon" style="background: linear-gradient(135deg, #ecf5ff, #d9ecff);color:#409eff">
          <el-icon size="22"><DataAnalysis /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.total_scans ?? 0 }}</div>
          <div class="stat-label">累计扫描</div>
        </div>
      </el-card>
      <el-card class="stat-card" shadow="hover">
        <div class="stat-icon" style="background: linear-gradient(135deg, #f0f9eb, #e1f3d8);color:#67c23a">
          <el-icon size="22"><Platform /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.total_hosts ?? 0 }}</div>
          <div class="stat-label">累计主机</div>
        </div>
      </el-card>
      <el-card class="stat-card" shadow="hover">
        <div class="stat-icon" style="background: linear-gradient(135deg, #fdf6ec, #faecd8);color:#e6a23c">
          <el-icon size="22"><Clock /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ formatDuration(stats.avg_duration?.avg) }}</div>
          <div class="stat-label">平均耗时</div>
        </div>
      </el-card>
      <el-card class="stat-card" shadow="hover">
        <div class="stat-icon" style="background: linear-gradient(135deg, #fef0f0, #fde2e2);color:#f56c6c">
          <el-icon size="22"><WarningFilled /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value" style="color:#f56c6c">{{ (stats.failed_count || 0) + (stats.cancelled_count || 0) }}</div>
          <div class="stat-label">失败/取消</div>
        </div>
      </el-card>
    </div>

    <!-- 图表区域 -->
    <el-row :gutter="20" style="margin-bottom:20px">
      <el-col :span="14">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-header">
              <span><el-icon size="16" style="color:#409eff;vertical-align:-2px"><TrendCharts /></el-icon> 7天扫描趋势</span>
            </div>
          </template>
          <v-chart :option="trendChartOption" style="height:300px" autoresize />
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-header">
              <span><el-icon size="16" style="color:#e6a23c;vertical-align:-2px"><PieChart /></el-icon> 端口风险等级</span>
            </div>
          </template>
          <v-chart :option="riskChartOption" style="height:300px" autoresize />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-bottom:20px">
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-header">
              <span><el-icon size="16" style="color:#67c23a;vertical-align:-2px"><Histogram /></el-icon> 任务状态分布</span>
            </div>
          </template>
          <v-chart :option="statusChartOption" style="height:260px" autoresize />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-header">
              <span><el-icon size="16" style="color:#409eff;vertical-align:-2px"><Odometer /></el-icon> 端口服务 Top5</span>
            </div>
          </template>
          <v-chart :option="portChartOption" style="height:260px" autoresize />
        </el-card>
      </el-col>
    </el-row>

    <!-- 主机排行 + 最近记录 -->
    <el-row :gutter="20">
      <el-col :span="10">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-header">
              <span><el-icon size="16" style="color:#f56c6c;vertical-align:-2px"><TrophyBase /></el-icon> 开放端口最多主机</span>
              <el-tag size="small" type="warning" effect="plain">Top 10</el-tag>
            </div>
          </template>
          <div class="host-list">
            <div v-for="(host, idx) in stats.top_hosts" :key="host.ip" class="host-row">
              <span class="host-rank" :class="'rank-' + (idx + 1)">{{ idx + 1 }}</span>
              <span class="host-ip">{{ host.ip }}</span>
              <el-tag size="small" type="warning" effect="plain">{{ host.ports }} 端口</el-tag>
            </div>
            <el-empty v-if="!stats.top_hosts?.length" description="暂无数据" :image-size="60" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="14">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-header">
              <span><el-icon size="16" style="color:#409eff;vertical-align:-2px"><List /></el-icon> 最近扫描记录</span>
            </div>
          </template>
          <el-table :data="recentRecords" size="small" empty-text="暂无扫描记录" stripe>
            <el-table-column prop="status" label="状态" width="80" align="center">
              <template #default="scope">
                <el-tag :type="statusType(scope.row.status)" size="small">{{ statusText(scope.row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="total_hosts" label="主机" width="70" align="center">
              <template #default="scope"><b style="color:#409eff">{{ scope.row.total_hosts || 0 }}</b></template>
            </el-table-column>
            <el-table-column prop="open_ports" label="端口" width="70" align="center">
              <template #default="scope"><b style="color:#e6a23c">{{ scope.row.open_ports || 0 }}</b></template>
            </el-table-column>
            <el-table-column prop="duration" label="用时" width="90" align="center">
              <template #default="scope">{{ formatTime(scope.row.duration) }}</template>
            </el-table-column>
            <el-table-column prop="start_time" label="开始时间" min-width="150" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { use } from 'echarts/core'
import { BarChart, PieChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { Document, Monitor, Connection, CircleCheck, DataAnalysis, Platform, Clock, WarningFilled, TrendCharts, PieChart as PieChartIcon, Histogram, Odometer, TrophyBase, List } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import api from '@/api'

use([BarChart, PieChart, LineChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer])

const appStore = useAppStore()
const stats = ref({})
const recentRecords = ref([])
const healthInfo = ref(null)

const todayDate = computed(() => new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }))

// --- 健康状态 ---
const healthStatus = computed(() => {
  if (appStore.systemStatus === 'offline') return { type: 'danger', label: '离线', detail: '不可用' }
  if (appStore.systemStatus === 'degraded') return { type: 'warning', label: '降级', detail: '部分服务异常' }
  return { type: 'success', label: '健康', detail: '所有服务正常运行' }
})

// --- 状态映射 ---
const statusType = (s) => ({ completed: 'success', running: 'primary', failed: 'danger', cancelled: 'warning' }[s] || 'info')
const statusText = (s) => ({ completed: '完成', running: '运行中', failed: '失败', cancelled: '已取消' }[s] || s)
const formatTime = (s) => {
  if (!s || s < 0) return '0秒'
  const m = Math.floor(s / 60)
  return m > 0 ? `${m}分${s % 60}秒` : `${s}秒`
}
const formatDuration = (s) => {
  if (!s || s < 0) return '-'
  if (s < 60) return `${s}秒`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}分`
  return `${Math.floor(m / 60)}时${m % 60}分`
}

// --- 7天趋势图 ---
const trendChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['扫描次数', '发现主机', '开放端口'], bottom: 0 },
  grid: { left: 50, right: 30, top: 20, bottom: 40 },
  xAxis: { type: 'category', data: stats.value.trend?.map(t => t.date) || [] },
  yAxis: [
    { type: 'value', name: '次数' },
    { type: 'value', name: '数量' }
  ],
  series: [
    { name: '扫描次数', type: 'bar', data: stats.value.trend?.map(t => t.scans) || [], itemStyle: { color: '#409eff', borderRadius: [4,4,0,0] }, barMaxWidth: 30 },
    { name: '发现主机', type: 'line', yAxisIndex: 1, data: stats.value.trend?.map(t => t.hosts) || [], itemStyle: { color: '#67c23a' }, smooth: true },
    { name: '开放端口', type: 'line', yAxisIndex: 1, data: stats.value.trend?.map(t => t.ports) || [], itemStyle: { color: '#e6a23c' }, smooth: true }
  ]
}))

// --- 风险等级饼图 ---
const riskChartOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { bottom: 0 },
  series: [{
    type: 'pie', radius: ['55%', '80%'], center: ['50%', '45%'], avoidLabelOverlap: false,
    label: { show: true, formatter: '{b}\n{c}' },
    data: [
      { value: stats.value.risk_distribution?.high || 0, name: '高风险', itemStyle: { color: '#f56c6c' } },
      { value: stats.value.risk_distribution?.medium || 0, name: '中风险', itemStyle: { color: '#e6a23c' } },
      { value: stats.value.risk_distribution?.low || 0, name: '低风险', itemStyle: { color: '#409eff' } }
    ]
  }]
}))

// --- 任务状态分布 ---
const statusChartOption = computed(() => {
  const counts = stats.value.status_counts || {}
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 60, right: 40, top: 10, bottom: 30 },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: ['完成', '失败', '已取消', '运行中'] },
    series: [{
      type: 'bar',
      data: [
        { value: counts.completed || 0, itemStyle: { color: '#67c23a', borderRadius: [0,4,4,0] } },
        { value: counts.failed || 0, itemStyle: { color: '#f56c6c', borderRadius: [0,4,4,0] } },
        { value: counts.cancelled || 0, itemStyle: { color: '#909399', borderRadius: [0,4,4,0] } },
        { value: counts.running || 0, itemStyle: { color: '#409eff', borderRadius: [0,4,4,0] } }
      ],
      label: { show: true, position: 'right' },
      barMaxWidth: 28
    }]
  }
})

// --- 端口服务 Top5 ---
const portChartOption = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 90, right: 40, top: 10, bottom: 20 },
  xAxis: { type: 'value', name: '发现次数' },
  yAxis: { type: 'category', data: (stats.value.top_ports || []).map(p => `${p.port} ${p.service}`).reverse(), inverse: true },
  series: [{
    type: 'bar',
    data: (stats.value.top_ports || []).map((p, i) => ({
      value: p.count,
      itemStyle: { color: ['#409eff','#67c23a','#e6a23c','#f56c6c','#909399'][i] || '#409eff', borderRadius: [0,4,4,0] }
    })).reverse(),
    label: { show: true, position: 'right' },
    barMaxWidth: 24
  }]
}))

// --- 加载数据 ---
const loadDashboard = async () => {
  try {
    const [statsRes, historyRes, healthRes] = await Promise.all([
      api.get('/api/v1/stats'),
      api.get('/api/v1/scan/history?limit=5'),
      fetch('/api/v1/system/health').then(r => r.json())
    ])
    if (statsRes.success) stats.value = statsRes.data
    if (historyRes.success) recentRecords.value = historyRes.data
    healthInfo.value = healthRes
  } catch (e) {}
}

onMounted(loadDashboard)
</script>

<style scoped>
.dashboard { max-width: 1600px; }

/* 健康横幅 */
.health-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(135deg, #f8faff 0%, #edf2ff 100%);
  border: 1px solid #dce3f5;
  border-radius: 12px;
  padding: 14px 24px;
  margin-bottom: 24px;
}
.health-left { display: flex; align-items: center; gap: 12px; }
.health-dot-inner {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  margin-right: 4px;
}
.health-sub { color: #6b7280; font-size: 13px; }
.health-right { display: flex; gap: 16px; }
.health-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  padding: 5px 14px;
  border-radius: 20px;
  background: #fff;
  border: 1px solid #e8eaed;
}
.health-chip.ok { background: #f0fdf4; color: #16a34a; border-color: #bbf7d0; }
.health-chip.err { background: #fef2f2; color: #dc2626; border-color: #fecaca; }
.chip-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }

/* 区块标题 */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-title {
  font-size: 15px;
  font-weight: 700;
  color: #303133;
  padding-left: 12px;
  border-left: 3px solid #409eff;
  line-height: 1.2;
}
.section-date {
  font-size: 13px;
  color: #909399;
}

/* 卡片网格 */
.card-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}
@media (max-width: 1200px) { .card-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 768px)  { .card-grid { grid-template-columns: 1fr; } }

.stat-card {
  cursor: default;
  transition: all 0.25s ease;
  border-radius: 12px !important;
}
.stat-card:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,0.1) !important; }
.stat-card :deep(.el-card__body) {
  display: flex; align-items: center; gap: 16px; padding: 20px !important;
}
.stat-icon {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.stat-value { font-size: 30px; font-weight: 700; color: #303133; line-height: 1.1; }
.stat-value .unit { font-size: 14px; font-weight: 400; color: #909399; margin-left: 2px; }
.stat-label { font-size: 13px; color: #909399; margin-top: 2px; }

/* 图表卡片 */
.chart-card {
  border-radius: 12px !important;
  height: 100%;
}

/* 卡片头部 */
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

/* 主机列表 */
.host-list { max-height: 380px; overflow-y: auto; }
.host-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid #f5f5f5;
  border-radius: 8px;
  transition: background 0.15s;
}
.host-row:hover { background: #f9fafb; }
.host-row:last-child { border-bottom: none; }
.host-rank {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  background: #f0f0f0;
  color: #909399;
  flex-shrink: 0;
}
.host-rank.rank-1 { background: linear-gradient(135deg, #fef0f0, #fde2e2); color: #dc2626; }
.host-rank.rank-2 { background: linear-gradient(135deg, #fdf6ec, #fae8c8); color: #d97706; }
.host-rank.rank-3 { background: linear-gradient(135deg, #ecf5ff, #d9ecff); color: #2563eb; }
.host-ip {
  flex: 1;
  font-size: 13px;
  font-family: var(--font-mono);
  color: #303133;
  font-weight: 500;
}
</style>
