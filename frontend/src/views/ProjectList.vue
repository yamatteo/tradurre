<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { booksApi, type BookSummary } from '@/api/client'

const router = useRouter()
const books = ref<BookSummary[]>([])
const error = ref('')
const bundleInput = ref<HTMLInputElement | null>(null)

async function load() {
  books.value = await booksApi.listBooks()
}

function open(book: BookSummary) {
  router.push({ name: 'book', params: { id: book.id } })
}

/** Restore a project bundle (SPEC §3.5) as a new book and open it. */
async function restoreBundle(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''  // the same file can be chosen again after an error
  if (!file) return
  error.value = ''
  try {
    const book = await booksApi.importBundle(file)
    router.push({ name: 'book', params: { id: book.id } })
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function remove(book: BookSummary) {
  if (!confirm(`Delete "${book.title}"? This can't be undone.`)) return
  error.value = ''
  try {
    await booksApi.deleteBook(book.id)
  } catch (e) {
    error.value = (e as Error).message
    return
  }
  await load()
}

onMounted(load)
</script>

<template>
  <div class="max-w-4xl mx-auto p-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Library</h1>
      <div class="flex gap-2">
        <button @click="router.push({ name: 'book-import' })"
          class="px-4 py-2 bg-white border border-blue-600 text-blue-700 rounded-lg hover:bg-blue-50 text-sm">
          Import a book (txt/docx/pdf)
        </button>
        <button data-testid="restore-bundle" @click="bundleInput?.click()"
          class="px-4 py-2 bg-white border border-blue-600 text-blue-700 rounded-lg hover:bg-blue-50 text-sm">
          Restore a bundle
        </button>
        <input ref="bundleInput" type="file" accept=".zip" data-testid="restore-bundle-file" class="hidden"
          @change="restoreBundle" />
      </div>
    </div>
    <p v-if="error" data-testid="library-error" class="mb-4 text-red-600">{{ error }}</p>

    <div v-if="books.length === 0" class="text-center text-gray-500 py-12">
      No books yet. Import one to get started.
    </div>

    <div v-else class="space-y-3">
      <div v-for="b in books" :key="b.id"
        class="bg-white rounded-lg border border-gray-200 p-4 flex items-center justify-between hover:border-gray-300 cursor-pointer"
        :data-book-id="b.id" @click="open(b)">
        <div>
          <h2 class="font-medium text-gray-900">{{ b.title }}</h2>
          <p class="text-sm text-gray-500">
            {{ b.source_lang.toUpperCase() }} &rarr; {{ b.target_lang.toUpperCase() }} &middot;
            {{ b.bead_count }} beads, {{ b.reviewed_count }} reviewed
          </p>
        </div>
        <button data-testid="delete-book" @click.stop="remove(b)" class="text-gray-400 hover:text-red-500 text-sm px-2">
          Delete
        </button>
      </div>
    </div>
  </div>
</template>
