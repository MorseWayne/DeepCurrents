<template>
  <div class="events">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>Event Stream</span>
          <el-select v-model="statusFilter" placeholder="All" clearable size="small" style="width: 140px" @change="refresh">
            <el-option label="Active" value="active" />
            <el-option label="Merged" value="merged" />
            <el-option label="Archived" value="archived" />
          </el-select>
        </div>
      </template>
      <el-table :data="events" stripe v-loading="loading">
        <el-table-column prop="title" label="Title" show-overflow-tooltip />
        <el-table-column prop="status" label="Status" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="article_count" label="Articles" width="100" />
        <el-table-column prop="updated_at" label="Updated" width="200">
          <template #default="{ row }">
            {{ row.updated_at ? new Date(row.updated_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

const events = ref<any[]>([])
const loading = ref(false)
const statusFilter = ref('')

async function refresh() {
  loading.value = true
  try {
    const params: any = { limit: 50 }
    if (statusFilter.value) params.status = statusFilter.value
    const { data } = await axios.get('/api/events', { params })
    events.value = data
  } catch {
    events.value = []
  } finally {
    loading.value = false
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
