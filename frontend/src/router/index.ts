import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/dashboard' },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/Dashboard.vue'),
    },
    {
      path: '/reports',
      name: 'reports',
      component: () => import('@/views/Reports.vue'),
    },
    {
      path: '/events',
      name: 'events',
      component: () => import('@/views/Events.vue'),
    },
    {
      path: '/sources',
      name: 'sources',
      component: () => import('@/views/Sources.vue'),
    },
  ],
})

export default router
