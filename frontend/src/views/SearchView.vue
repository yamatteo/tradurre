<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, type SearchResult, type SearchResponse } from '@/api/client'
import { useDebouncedRef } from '@/composables/useDebounce'

const router = useRouter()
const query = ref('')
const debouncedQuery = useDebouncedRef(query, 300)
const lang = ref<'both' | 'source' | 'target'>('both')
const results = ref<SearchResult[]>([])
const total = ref(0)
const loading = ref(false)

async function doSearch() {
  const q = debouncedQuery.value.trim()
  if (!q) {
    results.value = []
    total.value = 0
    return
  }
  loading.value = true
  try {
    const res = await api.search(q, lang.value)
    results.value = res.results
    total.value = res.total
  } finally {
    loading.value = false
  }
}

watch(debouncedQuery, doSearch)
watch(lang, doSearch)

function goToPair(result: SearchResult) {
  router.push({ name: 'editor', params: { id: result.project_id } })
}
</script>

<template>
  <div class="max-w-4xl mx-auto p-6">
    <h1 class="text-2xl font-bold text-gray-900 mb-4">Translation Memory Search</h1>

    <div class="flex gap-3 mb-6">
      <input v-model="query" placeholder="Search for a word or phrase..."
        class="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-blue-500" />
      <select v-model="lang" class="border border-gray-300 rounded-lg px-3 py-2 text-sm">
        <option value="both">Both</option>
        <option value="source">Source only</option>
        <option value="target">Target only</option>
      </select>
    </div>

    <div v-if="loading" class="text-gray-400 text-sm">Searching...</div>

    <div v-else-if="query.trim() && results.length === 0" class="text-gray-400 text-sm">
      No results found.
    </div>

    <div v-else class="space-y-3">
      <div v-if="total > 0" class="text-sm text-gray-500 mb-2">{{ total }} result{{ total > 1 ? 's' : '' }}</div>

      <div v-for="r in results" :key="r.pair_id"
        @click="goToPair(r)"
        class="bg-white rounded-lg border border-gray-200 p-4 hover:border-gray-300 cursor-pointer">
        <div class="flex items-center gap-2 mb-2">
          <span class="text-sm font-medium text-gray-700">{{ r.project_title }}</span>
          <span class="text-xs text-gray-400">#{{ r.position + 1 }}</span>
        </div>
        <div class="grid grid-cols-2 gap-4 text-sm">
          <div class="text-gray-600" v-html="r.source_snippet"></div>
          <div class="text-gray-900" v-html="r.target_snippet"></div>
        </div>
      </div>
    </div>
  </div>
</template>
