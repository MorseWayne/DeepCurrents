<template>
  <div class="reports">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>Intelligence Reports</span>
          <el-button type="primary" size="small" @click="refresh">Refresh</el-button>
        </div>
      </template>
      <el-table :data="reports" stripe v-loading="loading">
        <el-table-column prop="report_date" label="Date" width="140" sortable />
        <el-table-column prop="id" label="Report ID" show-overflow-tooltip />
        <el-table-column prop="created_at" label="Created" width="200">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="Actions" width="120" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="viewReport(row.id)">
              View
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" title="Report Detail" width="70%">
      <pre style="white-space: pre-wrap; font-size: 13px;">{{ reportDetail }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

const reports = ref<any[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const reportDetail = ref('')

async function refresh() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/reports?limit=20')
    reports.value = data
  } catch {
    reports.value = []
  } finally {
    loading.value = false
  }
}

async function viewReport(id: string) {
  try {
    const { data } = await axios.get(`/api/reports/${id}`)
    reportDetail.value = JSON.stringify(data, null, 2)
    dialogVisible.value = true
  } catch {
    reportDetail.value = 'Failed to load report'
    dialogVisible.value = true
  }
}

onMounted(refresh)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
