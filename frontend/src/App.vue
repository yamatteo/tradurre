<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <!-- The book screen has its own bars and "Library" link. -->
    <nav v-if="$route.name !== 'book'" class="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-6">
      <RouterLink to="/" class="text-lg font-semibold text-gray-900">Tradurre</RouterLink>
      <RouterLink to="/" class="text-sm text-gray-600 hover:text-gray-900"
        :class="{ 'text-gray-900 font-medium': $route.name === 'projects' }">
        Library
      </RouterLink>
      <RouterLink to="/search" class="text-sm text-gray-600 hover:text-gray-900"
        :class="{ 'text-gray-900 font-medium': $route.name === 'search' }">
        Search
      </RouterLink>
    </nav>
    <main>
      <RouterView />
    </main>
  </div>
</template>
