<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { booksApi, type Book, type BookSegment } from '@/api/client'

const props = defineProps<{ id: string }>()

const book = ref<Book | null>(null)
const error = ref('')

const reviewedCount = computed(() => book.value?.beads.filter((b) => b.reviewed).length ?? 0)

function cellText(segments: BookSegment[]): string {
  return segments.map((s) => s.text).join(' ')
}

onMounted(async () => {
  try {
    book.value = await booksApi.getBook(props.id)
  } catch (e) {
    error.value = (e as Error).message
  }
})
</script>

<template>
  <div class="max-w-6xl mx-auto p-6">
    <p v-if="error" class="text-red-600">{{ error }}</p>
    <template v-else-if="book">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-3">
          <router-link to="/" class="text-gray-400 hover:text-gray-600">&larr;</router-link>
          <h1 class="text-xl font-bold text-gray-900" data-testid="book-title">{{ book.title }}</h1>
        </div>
        <p class="text-sm text-gray-500" data-testid="book-progress">
          reviewed {{ reviewedCount }} / {{ book.beads.length }}
        </p>
      </div>

      <div class="bg-white border border-gray-200 rounded-lg divide-y divide-gray-100">
        <div v-for="bead in book.beads" :key="bead.id" :data-bead-id="bead.id"
          class="grid grid-cols-2 gap-4 px-4 py-2 text-sm" data-testid="bead-row">
          <div>{{ cellText(bead.source) }}</div>
          <div>{{ cellText(bead.target) }}</div>
        </div>
      </div>
    </template>
  </div>
</template>
