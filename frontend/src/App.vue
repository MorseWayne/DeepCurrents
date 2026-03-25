<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  DataAnalysis,
  Document,
  List,
  Connection,
} from '@element-plus/icons-vue'

const router = useRouter()
const isCollapse = ref(false)

const handleMenuSelect = (index: string) => {
  router.push(index)
}
</script>

<template>
  <el-container class="app-container">
    <el-aside :width="isCollapse ? '64px' : '220px'" class="app-aside">
      <div class="logo-area">
        <h2 v-show="!isCollapse">DeepCurrents</h2>
      </div>
      <el-menu
        default-active="/dashboard"
        class="app-menu"
        :collapse="isCollapse"
        @select="handleMenuSelect"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409eff"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <template #title>Dashboard</template>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><Document /></el-icon>
          <template #title>Reports</template>
        </el-menu-item>
        <el-menu-item index="/events">
          <el-icon><List /></el-icon>
          <template #title>Events</template>
        </el-menu-item>
        <el-menu-item index="/sources">
          <el-icon><Connection /></el-icon>
          <template #title>Sources</template>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="app-header">
        <el-button
          :icon="isCollapse ? 'Expand' : 'Fold'"
          @click="isCollapse = !isCollapse"
          text
        />
        <span class="header-title">AI-Driven Global Intelligence Engine</span>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style lang="scss">
html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
}

.app-container {
  height: 100%;
}

.app-aside {
  background-color: #304156;
  transition: width 0.3s;
  overflow: hidden;
}

.logo-area {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;

  h2 {
    margin: 0;
    font-size: 18px;
    white-space: nowrap;
  }
}

.app-menu {
  border-right: none;
}

.app-header {
  display: flex;
  align-items: center;
  border-bottom: 1px solid #e6e6e6;

  .header-title {
    margin-left: 12px;
    font-size: 14px;
    color: #606266;
  }
}

.app-main {
  background-color: #f0f2f5;
}
</style>
