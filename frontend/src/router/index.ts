import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'library',
      component: () => import('@/views/ProjectList.vue'),
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
      path: '/search',
      name: 'search',
      component: () => import('@/views/BookSearch.vue'),
    },
  ],
})

export default router
