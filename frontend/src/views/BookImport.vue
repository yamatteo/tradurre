<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { booksApi } from '@/api/client'

const router = useRouter()

const source = ref<File | null>(null)
const target = ref<File | null>(null)
const title = ref('')
const sourceLang = ref('fr')
const targetLang = ref('it')
const importing = ref(false)
const error = ref('')
const warnings = ref<string[]>([])
const bookId = ref('')

const canImport = computed(() => source.value !== null && target.value !== null && !importing.value)

function pickSource(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null
  source.value = file
  if (file) title.value = file.name.replace(/\.[^.]*$/, '')
}

function pickTarget(event: Event) {
  target.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

async function importBook() {
  if (!source.value || !target.value) return
  importing.value = true
  error.value = ''
  try {
    const result = await booksApi.importBook(
      source.value, target.value, title.value.trim(), sourceLang.value, targetLang.value,
    )
    if (result.warnings.length === 0) {
      router.push({ name: 'book', params: { id: result.id } })
    } else {
      bookId.value = result.id
      warnings.value = result.warnings
    }
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <div class="max-w-2xl mx-auto p-6">
    <div class="flex items-center gap-3 mb-6">
      <router-link to="/" class="text-gray-400 hover:text-gray-600">&larr;</router-link>
      <h1 class="text-2xl font-bold text-gray-900">Import a book</h1>
    </div>

    <div v-if="warnings.length" class="bg-white rounded-lg border border-amber-300 p-4 space-y-3">
      <p class="font-medium text-amber-800">The book was imported with warnings:</p>
      <ul class="list-disc pl-5 text-sm text-amber-900" data-testid="import-warnings">
        <li v-for="w in warnings" :key="w">{{ w }}</li>
      </ul>
      <button @click="router.push({ name: 'book', params: { id: bookId } })"
        class="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700">
        Continue
      </button>
    </div>

    <div v-else class="bg-white rounded-lg border border-gray-200 p-4 space-y-4">
      <div>
        <label for="source-file" class="block text-sm text-gray-600 mb-1">Original (French)</label>
        <input id="source-file" type="file" accept=".txt,.docx,.pdf" @change="pickSource" class="text-sm" />
      </div>
      <div>
        <label for="target-file" class="block text-sm text-gray-600 mb-1">Translation (Italian)</label>
        <input id="target-file" type="file" accept=".txt,.docx,.pdf" @change="pickTarget" class="text-sm" />
      </div>
      <div class="flex gap-3 items-end">
        <div class="flex-1">
          <label for="title" class="block text-sm text-gray-600 mb-1">Title</label>
          <input id="title" v-model="title" class="w-full border border-gray-300 rounded px-3 py-2 text-sm" />
        </div>
        <div>
          <label for="source-lang" class="block text-sm text-gray-600 mb-1">Source</label>
          <input id="source-lang" v-model="sourceLang" class="w-20 border border-gray-300 rounded px-3 py-2 text-sm" />
        </div>
        <div>
          <label for="target-lang" class="block text-sm text-gray-600 mb-1">Target</label>
          <input id="target-lang" v-model="targetLang" class="w-20 border border-gray-300 rounded px-3 py-2 text-sm" />
        </div>
      </div>
      <p v-if="error" class="text-sm text-red-600" data-testid="import-error">{{ error }}</p>
      <button :disabled="!canImport" @click="importBook"
        class="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed">
        {{ importing ? 'Importing…' : 'Import' }}
      </button>
    </div>
  </div>
</template>
