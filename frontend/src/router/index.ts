import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'projects',
      component: () => import('@/views/ProjectList.vue'),
    },
    {
      path: '/project/:id',
      name: 'editor',
      component: () => import('@/views/ProjectEditor.vue'),
      props: true,
    },
    {
      path: '/book/import',
      name: 'book-import',
      component: () => import('@/views/BookImport.vue'),
    },
    {
      path: '/book/:id',
      name: 'book',
      component: () => import('@/views/BookView.vue'),
      props: true,
    },
    {
      path: '/import',
      name: 'import',
      component: () => import('@/views/ImportWizard.vue'),
    },
    {
      path: '/search',
      name: 'search',
      component: () => import('@/views/BookSearch.vue'),
    },
  ],
})

export default router
