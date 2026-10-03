<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, booksApi, type BookSummary, type Project } from '@/api/client'

const router = useRouter()
const projects = ref<Project[]>([])
const books = ref<Record<string, BookSummary>>({})
const showCreate = ref(false)
const newTitle = ref('')
const newSourceLang = ref('it')
const newTargetLang = ref('en')

async function load() {
  const [allProjects, allBooks] = await Promise.all([api.listProjects(), booksApi.listBooks()])
  projects.value = allProjects
  books.value = Object.fromEntries(allBooks.map((b) => [b.id, b]))
}

function open(p: Project) {
  const name = p.id in books.value ? 'book' : 'editor'
  router.push({ name, params: { id: p.id } })
}

async function create() {
  if (!newTitle.value.trim()) return
  const proj = await api.createProject({
    title: newTitle.value.trim(),
    source_lang: newSourceLang.value,
    target_lang: newTargetLang.value,
  })
  router.push({ name: 'editor', params: { id: proj.id } })
}

async function remove(id: string) {
  if (!confirm('Delete this project and all its translations?')) return
  await api.deleteProject(id)
  await load()
}

onMounted(load)
</script>

<template>
  <div class="max-w-4xl mx-auto p-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Projects</h1>
      <div class="flex gap-2">
        <button @click="router.push({ name: 'book-import' })"
          class="px-4 py-2 bg-white border border-blue-600 text-blue-700 rounded-lg hover:bg-blue-50 text-sm">
          Import a book (txt/docx)
        </button>
        <button @click="showCreate = !showCreate"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm">
          New Project
        </button>
      </div>
    </div>

    <div v-if="showCreate" class="bg-white rounded-lg border border-gray-200 p-4 mb-6">
      <div class="flex gap-3 items-end">
        <div class="flex-1">
          <label class="block text-sm text-gray-600 mb-1">Title</label>
          <input v-model="newTitle" @keyup.enter="create" placeholder="e.g. I Promessi Sposi"
            class="w-full border border-gray-300 rounded px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm text-gray-600 mb-1">Source</label>
          <input v-model="newSourceLang" class="w-20 border border-gray-300 rounded px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-sm text-gray-600 mb-1">Target</label>
          <input v-model="newTargetLang" class="w-20 border border-gray-300 rounded px-3 py-2 text-sm" />
        </div>
        <button @click="create" class="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700">
          Create
        </button>
      </div>
    </div>

    <div v-if="projects.length === 0" class="text-center text-gray-500 py-12">
      No projects yet. Create one to get started.
    </div>

    <div v-else class="space-y-3">
      <div v-for="p in projects" :key="p.id"
        class="bg-white rounded-lg border border-gray-200 p-4 flex items-center justify-between hover:border-gray-300 cursor-pointer"
        :data-project-id="p.id" @click="open(p)">
        <div>
          <h2 class="font-medium text-gray-900">{{ p.title }}</h2>
          <p class="text-sm text-gray-500">
            {{ p.source_lang }} &rarr; {{ p.target_lang }} &middot;
            <template v-if="books[p.id]">
              {{ books[p.id]!.bead_count }} beads, {{ books[p.id]!.reviewed_count }} reviewed
            </template>
            <template v-else>{{ p.pair_count }} paragraphs</template>
          </p>
        </div>
        <button @click.stop="remove(p.id)" class="text-gray-400 hover:text-red-500 text-sm px-2">
          Delete
        </button>
      </div>
    </div>
  </div>
</template>
