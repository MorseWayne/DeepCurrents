<template>
  <div class="sources">
    <el-card header="Information Sources">
      <el-table :data="sources" stripe v-loading="loading">
        <el-table-column prop="name" label="Name" />
        <el-table-column prop="url" label="URL" show-overflow-tooltip />
        <el-table-column prop="tier" label="Tier" width="80">
          <template #default="{ row }">
            <el-tag :type="tierType(row.tier)" size="small">T{{ row.tier }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Status" width="100">
          <template #default="{ row }">
            <el-tag :type="row.ok ? 'success' : 'danger'" size="small">
              {{ row.ok ? 'OK' : 'FAIL' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="failure_count" label="Failures" width="100" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

const sources = ref<any[]>([])
const loading = ref(false)

function tierType(tier: number): string {
  if (tier === 1) return 'danger'
  if (tier === 2) return 'warning'
  return 'info'
}

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await axios.get('/api/sources')
    sources.value = data
  } catch {
    sources.value = []
  } finally {
    loading.value = false
  }
})
</script>
