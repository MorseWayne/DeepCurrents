<template>
  <div class="dashboard">
    <el-row :gutter="20" class="stat-row">
      <el-col :span="6" v-for="stat in stats" :key="stat.label">
        <el-card shadow="hover">
          <el-statistic :title="stat.label" :value="stat.value" />
        </el-card>
      </el-col>
    </el-row>
    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="24">
        <el-card header="System Status">
          <el-descriptions :column="3" border>
            <el-descriptions-item label="Status">
              <el-tag :type="connected ? 'success' : 'danger'">
                {{ connected ? 'Connected' : 'Disconnected' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Uptime">
              {{ formatUptime(uptime) }}
            </el-descriptions-item>
            <el-descriptions-item label="Last Update">
              {{ lastUpdate }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const stats = ref([
  { label: 'Uptime (s)', value: 0 },
  { label: 'Reports', value: '-' },
  { label: 'Events', value: '-' },
  { label: 'Sources', value: '-' },
])

const connected = ref(false)
const uptime = ref(0)
const lastUpdate = ref('-')
let eventSource: EventSource | null = null

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return `${h}h ${m}m ${s}s`
}

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/system/status')
    stats.value[0].value = Math.round(data.uptime_seconds)
    uptime.value = data.uptime_seconds
    connected.value = true
  } catch {
    connected.value = false
  }

  // SSE connection
  eventSource = new EventSource('/api/system/stream')
  eventSource.addEventListener('status', (e: MessageEvent) => {
    const data = JSON.parse(e.data)
    uptime.value = data.uptime
    stats.value[0].value = Math.round(data.uptime)
    lastUpdate.value = new Date(data.timestamp * 1000).toLocaleTimeString()
    connected.value = true
  })
  eventSource.onerror = () => {
    connected.value = false
  }
})

onUnmounted(() => {
  eventSource?.close()
})
</script>

<style scoped>
.dashboard {
  padding: 4px;
}
.stat-row .el-card {
  text-align: center;
}
</style>
