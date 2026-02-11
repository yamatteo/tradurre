<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Placeholder from '@tiptap/extension-placeholder'
import { api, type Project, type Pair, type SearchResponse } from '@/api/client'
import { useScrollSync } from '@/composables/useScrollSync'

const props = defineProps<{ id: string }>()

const project = ref<Project | null>(null)
const pairs = ref<Pair[]>([])
const viewMode = ref<'side-by-side' | 'interleaved'>('side-by-side')
const saveStatus = ref<Record<string, string>>({})

// Scroll sync
const sourceCol = ref<HTMLElement>()
const targetCol = ref<HTMLElement>()
const scrollSyncEnabled = computed(() => viewMode.value === 'side-by-side')
useScrollSync(sourceCol, targetCol, scrollSyncEnabled)

// Export dropdown
const showExportMenu = ref(false)

// Status config
const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
  draft: { label: 'Draft', color: 'text-gray-600', bg: 'bg-gray-200' },
  in_progress: { label: 'In progress', color: 'text-yellow-700', bg: 'bg-yellow-200' },
  review: { label: 'Review', color: 'text-blue-700', bg: 'bg-blue-200' },
  done: { label: 'Done', color: 'text-green-700', bg: 'bg-green-200' },
}
const statusOrder = ['draft', 'in_progress', 'review', 'done']

// Status summary
const statusSummary = computed(() => {
  const counts: Record<string, number> = {}
  for (const p of pairs.value) {
    counts[p.status] = (counts[p.status] || 0) + 1
  }
  return statusOrder.filter(s => counts[s]).map(s => `${counts[s]} ${statusConfig[s]!.label.toLowerCase()}`)
})

// Search panel
const showSearchPanel = ref(false)
const searchQuery = ref('')
const searchResults = ref<SearchResponse | null>(null)
let searchTimer: ReturnType<typeof setTimeout> | undefined

function onSearchInput() {
  clearTimeout(searchTimer)
  if (!searchQuery.value.trim()) { searchResults.value = null; return }
  searchTimer = setTimeout(async () => {
    searchResults.value = await api.search(searchQuery.value, 'both', props.id)
  }, 400)
}

function openSearchPanel() {
  const sel = window.getSelection()?.toString().trim() || ''
  if (sel) searchQuery.value = sel
  showSearchPanel.value = true
  if (searchQuery.value) onSearchInput()
}

function onKeydown(e: KeyboardEvent) {
  if (e.ctrlKey && e.shiftKey && e.key === 'F') {
    e.preventDefault()
    openSearchPanel()
  }
  if (e.key === 'Escape' && showSearchPanel.value) {
    showSearchPanel.value = false
  }
}

async function load() {
  project.value = await api.getProject(props.id)
  pairs.value = await api.listPairs(props.id)
}

// Debounced save for a pair
const saveTimers: Record<string, ReturnType<typeof setTimeout>> = {}

function debouncedSave(pairId: string, field: 'source_html' | 'target_html', html: string) {
  saveStatus.value[pairId] = 'saving...'
  clearTimeout(saveTimers[pairId])
  saveTimers[pairId] = setTimeout(async () => {
    await api.updatePair(pairId, { [field]: html })
    saveStatus.value[pairId] = 'saved'
    setTimeout(() => {
      if (saveStatus.value[pairId] === 'saved') {
        saveStatus.value[pairId] = ''
      }
    }, 2000)
  }, 1500)
}

async function addPair() {
  if (!project.value) return
  const pair = await api.createPair(props.id, {
    source_html: '<p></p>',
    target_html: '<p></p>',
    source_text: '',
    target_text: '',
  })
  pairs.value.push(pair)
}

async function insertPairAfter(index: number) {
  if (!project.value) return
  const pair = await api.createPair(props.id, {
    source_html: '<p></p>',
    target_html: '<p></p>',
    source_text: '',
    target_text: '',
    position: index + 1,
  })
  pairs.value.splice(index + 1, 0, pair)
  pairs.value.forEach((p, i) => { p.position = i })
}

async function removePair(pairId: string, index: number) {
  await api.deletePair(pairId)
  pairs.value.splice(index, 1)
  pairs.value.forEach((p, i) => { p.position = i })
}

async function cycleStatus(pair: Pair) {
  const idx = statusOrder.indexOf(pair.status)
  const next = statusOrder[(idx + 1) % statusOrder.length]!
  pair.status = next
  await api.updatePair(pair.id, { status: next })
}

async function mergePair(pair: Pair, index: number) {
  await api.mergePair(pair.id)
  pairs.value = await api.listPairs(props.id)
}

function exportFile(format: string, mode: string) {
  showExportMenu.value = false
  window.open(`/api/v1/projects/${props.id}/export?format=${format}&mode=${mode}`)
}

onMounted(() => {
  load()
  window.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div v-if="project" class="h-[calc(100vh-49px)] flex flex-col">
    <!-- Toolbar -->
    <div class="bg-white border-b border-gray-200 px-6 py-2 flex items-center gap-4 shrink-0">
      <h1 class="font-semibold text-gray-900">{{ project.title }}</h1>
      <span class="text-sm text-gray-500">{{ project.source_lang }} &rarr; {{ project.target_lang }}</span>
      <span v-if="statusSummary.length" class="text-xs text-gray-400">{{ statusSummary.join(', ') }}</span>
      <div class="flex-1" />
      <div class="flex gap-1 bg-gray-100 rounded-lg p-0.5">
        <button @click="viewMode = 'side-by-side'"
          :class="viewMode === 'side-by-side' ? 'bg-white shadow-sm' : ''"
          class="px-3 py-1 text-sm rounded-md">
          Side by side
        </button>
        <button @click="viewMode = 'interleaved'"
          :class="viewMode === 'interleaved' ? 'bg-white shadow-sm' : ''"
          class="px-3 py-1 text-sm rounded-md">
          Interleaved
        </button>
      </div>
      <!-- Export dropdown -->
      <div class="relative">
        <button @click="showExportMenu = !showExportMenu"
          class="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50">
          Export
        </button>
        <div v-if="showExportMenu"
          class="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-10 w-48">
          <button @click="exportFile('docx', 'target')" class="block w-full text-left px-4 py-1.5 text-sm hover:bg-gray-50">Translation .docx</button>
          <button @click="exportFile('docx', 'source')" class="block w-full text-left px-4 py-1.5 text-sm hover:bg-gray-50">Source .docx</button>
          <button @click="exportFile('docx', 'parallel')" class="block w-full text-left px-4 py-1.5 text-sm hover:bg-gray-50">Parallel .docx</button>
          <hr class="my-1 border-gray-100" />
          <button @click="exportFile('txt', 'target')" class="block w-full text-left px-4 py-1.5 text-sm hover:bg-gray-50">Translation .txt</button>
          <button @click="exportFile('txt', 'source')" class="block w-full text-left px-4 py-1.5 text-sm hover:bg-gray-50">Source .txt</button>
          <button @click="exportFile('txt', 'parallel')" class="block w-full text-left px-4 py-1.5 text-sm hover:bg-gray-50">Parallel .txt</button>
        </div>
      </div>
      <button @click="openSearchPanel" class="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50" title="Ctrl+Shift+F">
        Search
      </button>
      <button @click="addPair" class="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700">
        + Paragraph
      </button>
    </div>

    <!-- Main content area with optional search panel -->
    <div class="flex-1 flex overflow-hidden">
      <!-- Editor area -->
      <div class="flex-1 flex flex-col overflow-hidden">
        <!-- Side-by-side mode -->
        <div v-if="viewMode === 'side-by-side'" class="flex-1 flex overflow-hidden">
          <!-- Source column -->
          <div class="w-1/2 overflow-y-auto border-r border-gray-200 bg-gray-50 p-4" ref="sourceCol">
            <div class="text-xs text-gray-400 uppercase tracking-wider mb-3">Source</div>
            <div v-for="(pair, i) in pairs" :key="pair.id" class="mb-4" :data-pair-index="i">
              <PairEditor
                :html="pair.source_html"
                :readonly="false"
                placeholder="Source text..."
                @update="(html: string) => { pair.source_html = html; debouncedSave(pair.id, 'source_html', html) }"
              />
            </div>
          </div>
          <!-- Target column -->
          <div class="w-1/2 overflow-y-auto bg-white p-4" ref="targetCol">
            <div class="text-xs text-gray-400 uppercase tracking-wider mb-3">Translation</div>
            <div v-for="(pair, i) in pairs" :key="pair.id" class="mb-4" :data-pair-index="i">
              <div class="flex items-start gap-2">
                <button @click="cycleStatus(pair)"
                  :class="[statusConfig[pair.status]?.bg, statusConfig[pair.status]?.color]"
                  class="text-xs px-1.5 py-0.5 rounded mt-1 shrink-0" :title="'Click to cycle status'">
                  {{ statusConfig[pair.status]?.label }}
                </button>
                <div class="flex-1">
                  <PairEditor
                    :html="pair.target_html"
                    placeholder="Start translating..."
                    @update="(html: string) => { pair.target_html = html; debouncedSave(pair.id, 'target_html', html) }"
                  />
                </div>
                <div class="flex flex-col gap-1 shrink-0 mt-1">
                  <span v-if="saveStatus[pair.id]" class="text-xs text-gray-400 whitespace-nowrap">
                    {{ saveStatus[pair.id] }}
                  </span>
                  <button @click="insertPairAfter(i)" class="text-xs text-gray-400 hover:text-blue-600" title="Insert pair after">+ins</button>
                  <button v-if="i < pairs.length - 1" @click="mergePair(pair, i)" class="text-xs text-gray-400 hover:text-orange-600" title="Merge with next">merge</button>
                  <button @click="removePair(pair.id, i)" class="text-xs text-gray-400 hover:text-red-500" title="Remove">del</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Interleaved mode -->
        <div v-else class="flex-1 overflow-y-auto p-6">
          <div class="max-w-3xl mx-auto space-y-6">
            <div v-for="(pair, i) in pairs" :key="pair.id"
              class="bg-white rounded-lg border border-gray-200 p-4">
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                  <span class="text-xs text-gray-400">#{{ i + 1 }}</span>
                  <button @click="cycleStatus(pair)"
                    :class="[statusConfig[pair.status]?.bg, statusConfig[pair.status]?.color]"
                    class="text-xs px-1.5 py-0.5 rounded" :title="'Click to cycle status'">
                    {{ statusConfig[pair.status]?.label }}
                  </button>
                </div>
                <div class="flex items-center gap-2">
                  <span v-if="saveStatus[pair.id]" class="text-xs text-gray-400">{{ saveStatus[pair.id] }}</span>
                  <button @click="insertPairAfter(i)" class="text-xs text-gray-400 hover:text-blue-600">insert after</button>
                  <button v-if="i < pairs.length - 1" @click="mergePair(pair, i)" class="text-xs text-gray-400 hover:text-orange-600">merge</button>
                  <button @click="removePair(pair.id, i)" class="text-xs text-gray-400 hover:text-red-500">remove</button>
                </div>
              </div>
              <div class="mb-3 pl-3 border-l-2 border-gray-200">
                <PairEditor
                  :html="pair.source_html"
                  :readonly="false"
                  placeholder="Source text..."
                  class="text-gray-600"
                  @update="(html: string) => { pair.source_html = html; debouncedSave(pair.id, 'source_html', html) }"
                />
              </div>
              <div class="pl-3 border-l-2 border-blue-300">
                <PairEditor
                  :html="pair.target_html"
                  placeholder="Start translating..."
                  @update="(html: string) => { pair.target_html = html; debouncedSave(pair.id, 'target_html', html) }"
                />
              </div>
            </div>
          </div>
        </div>

        <div v-if="pairs.length === 0" class="flex-1 flex items-center justify-center text-gray-400">
          No paragraphs yet. Click "+ Paragraph" or import files to get started.
        </div>
      </div>

      <!-- Search panel (slide-out) -->
      <div v-if="showSearchPanel" class="w-80 border-l border-gray-200 bg-white flex flex-col shrink-0">
        <div class="flex items-center justify-between px-4 py-2 border-b border-gray-200">
          <span class="text-sm font-medium text-gray-700">Search</span>
          <button @click="showSearchPanel = false" class="text-gray-400 hover:text-gray-600 text-lg leading-none">&times;</button>
        </div>
        <div class="px-4 py-2">
          <input v-model="searchQuery" @input="onSearchInput" placeholder="Search text..."
            class="w-full border border-gray-300 rounded px-3 py-1.5 text-sm" autofocus />
        </div>
        <div class="flex-1 overflow-y-auto px-4 py-2 space-y-2">
          <div v-if="searchResults && searchResults.total === 0" class="text-sm text-gray-400">No results</div>
          <div v-if="searchResults" v-for="r in searchResults.results" :key="r.pair_id"
            class="border border-gray-100 rounded p-2 text-xs hover:bg-gray-50">
            <div class="text-gray-500 mb-1">#{{ r.position + 1 }} &middot; {{ r.project_title }}</div>
            <div v-if="r.source_snippet" class="text-gray-700 mb-1" v-html="r.source_snippet"></div>
            <div v-if="r.target_snippet" class="text-blue-700" v-html="r.target_snippet"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, onBeforeUnmount as onBeforeUnmountOpt } from 'vue'

const PairEditor = defineComponent({
  name: 'PairEditor',
  props: {
    html: { type: String, required: true },
    placeholder: { type: String, default: '' },
    readonly: { type: Boolean, default: false },
  },
  emits: ['update'],
  setup(props, { emit }) {
    const editor = useEditor({
      extensions: [
        StarterKit.configure({
          heading: false,
          codeBlock: false,
          code: false,
          bulletList: false,
          orderedList: false,
          blockquote: false,
        }),
        Underline,
        Placeholder.configure({ placeholder: props.placeholder }),
      ],
      content: props.html,
      editable: !props.readonly,
      onUpdate: ({ editor }) => {
        emit('update', editor.getHTML())
      },
    })

    onBeforeUnmountOpt(() => {
      editor.value?.destroy()
    })

    return { editor }
  },
  components: { EditorContent },
  template: '<EditorContent :editor="editor" />',
})

export { PairEditor }
</script>
