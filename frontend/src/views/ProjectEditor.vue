<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Placeholder from '@tiptap/extension-placeholder'
import { api, type Project, type Pair, type SearchResponse } from '@/api/client'

const props = defineProps<{ id: string }>()

const project = ref<Project | null>(null)
const pairs = ref<Pair[]>([])
const viewMode = ref<'sentence' | 'paragraph' | 'section'>('sentence')
const layoutMode = ref<'side-by-side' | 'interleaved'>('side-by-side')
const saveStatus = ref<Record<string, string>>({})

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

// --- Grouping for paragraph/section views ---

interface PairGroup {
  key: string
  section: number
  paragraph: number
  pairs: Pair[]
  sourceHtml: string
  targetHtml: string
}

const paragraphGroups = computed<PairGroup[]>(() => {
  const groups: Map<string, PairGroup> = new Map()
  for (const pair of pairs.value) {
    const key = `${pair.section}-${pair.paragraph}`
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        section: pair.section,
        paragraph: pair.paragraph,
        pairs: [],
        sourceHtml: '',
        targetHtml: '',
      })
    }
    const g = groups.get(key)!
    g.pairs.push(pair)
  }
  for (const g of groups.values()) {
    g.sourceHtml = g.pairs.map(p => p.source_html).join('')
    g.targetHtml = g.pairs.map(p => p.target_html).join('')
  }
  return Array.from(groups.values()).sort((a, b) =>
    a.section !== b.section ? a.section - b.section : a.paragraph - b.paragraph
  )
})

const sectionGroups = computed<PairGroup[]>(() => {
  const groups: Map<number, PairGroup> = new Map()
  for (const pair of pairs.value) {
    if (!groups.has(pair.section)) {
      groups.set(pair.section, {
        key: `sec-${pair.section}`,
        section: pair.section,
        paragraph: 0,
        pairs: [],
        sourceHtml: '',
        targetHtml: '',
      })
    }
    const g = groups.get(pair.section)!
    g.pairs.push(pair)
  }
  for (const g of groups.values()) {
    g.sourceHtml = g.pairs.map(p => p.source_html).join('')
    g.targetHtml = g.pairs.map(p => p.target_html).join('')
  }
  return Array.from(groups.values()).sort((a, b) => a.section - b.section)
})

// --- Debounced save for sentence-level editing ---
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

// --- Resplit for paragraph/section level editing ---
const resplitTimers: Record<string, ReturnType<typeof setTimeout>> = {}

function debouncedResplit(group: PairGroup, targetHtml: string) {
  const key = group.key
  saveStatus.value[key] = 'saving...'
  clearTimeout(resplitTimers[key])
  resplitTimers[key] = setTimeout(async () => {
    try {
      const pairIds = group.pairs.map(p => p.id)
      const result = await api.resplit(pairIds, targetHtml)
      // Replace the group's pairs in the main pairs array
      const firstIdx = pairs.value.findIndex(p => p.id === group.pairs[0].id)
      if (firstIdx >= 0) {
        pairs.value.splice(firstIdx, group.pairs.length, ...result.pairs)
      }
      saveStatus.value[key] = 'saved'
      setTimeout(() => {
        if (saveStatus.value[key] === 'saved') saveStatus.value[key] = ''
      }, 2000)
    } catch (e) {
      saveStatus.value[key] = 'error'
    }
  }, 1500)
}

// --- Pair operations (sentence level) ---

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

// --- Section/paragraph boundaries for sentence view ---
function isSectionBoundary(i: number): boolean {
  return i > 0 && pairs.value[i].section !== pairs.value[i - 1].section
}

function isParagraphBoundary(i: number): boolean {
  return i > 0
    && !isSectionBoundary(i)
    && pairs.value[i].paragraph !== pairs.value[i - 1].paragraph
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
      <!-- View mode toggle -->
      <div class="flex gap-1 bg-gray-100 rounded-lg p-0.5">
        <button @click="viewMode = 'section'"
          :class="viewMode === 'section' ? 'bg-white shadow-sm' : ''"
          class="px-3 py-1 text-sm rounded-md">
          Section
        </button>
        <button @click="viewMode = 'paragraph'"
          :class="viewMode === 'paragraph' ? 'bg-white shadow-sm' : ''"
          class="px-3 py-1 text-sm rounded-md">
          Paragraph
        </button>
        <button @click="viewMode = 'sentence'"
          :class="viewMode === 'sentence' ? 'bg-white shadow-sm' : ''"
          class="px-3 py-1 text-sm rounded-md">
          Sentence
        </button>
      </div>
      <!-- Layout toggle (sentence mode only) -->
      <div v-if="viewMode === 'sentence'" class="flex gap-1 bg-gray-100 rounded-lg p-0.5">
        <button @click="layoutMode = 'side-by-side'"
          :class="layoutMode === 'side-by-side' ? 'bg-white shadow-sm' : ''"
          class="px-3 py-1 text-sm rounded-md">
          Side by side
        </button>
        <button @click="layoutMode = 'interleaved'"
          :class="layoutMode === 'interleaved' ? 'bg-white shadow-sm' : ''"
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
      <button v-if="viewMode === 'sentence'" @click="addPair" class="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700">
        + Sentence
      </button>
    </div>

    <!-- Main content area with optional search panel -->
    <div class="flex-1 flex overflow-hidden">
      <!-- Editor area -->
      <div class="flex-1 flex flex-col overflow-hidden">

        <!-- ========================= SENTENCE VIEW ========================= -->
        <template v-if="viewMode === 'sentence'">

          <!-- Side-by-side layout -->
          <template v-if="layoutMode === 'side-by-side'">
            <!-- Column headers -->
            <div class="flex shrink-0 border-b border-gray-200">
              <div class="w-1/2 px-4 py-1 bg-gray-50 border-r border-gray-200">
                <span class="text-xs text-gray-400 uppercase tracking-wider">Source</span>
              </div>
              <div class="w-1/2 px-4 py-1 bg-white">
                <span class="text-xs text-gray-400 uppercase tracking-wider">Translation</span>
              </div>
            </div>
            <div class="flex-1 overflow-y-auto">
              <template v-for="(pair, i) in pairs" :key="pair.id">
                <!-- Section divider -->
                <div v-if="isSectionBoundary(i)"
                  class="bg-blue-50 border-y border-blue-200 py-1 px-4 text-xs text-blue-600 font-medium">
                  Section {{ pair.section + 1 }}
                </div>
                <!-- Paragraph divider -->
                <div v-else-if="isParagraphBoundary(i)"
                  class="border-t-2 border-gray-300">
                </div>
                <!-- Pair row -->
                <div class="flex border-b border-gray-100" :data-pair-index="i">
                  <!-- Source cell -->
                  <div class="w-1/2 p-4 bg-gray-50 border-r border-gray-200">
                    <PairEditor
                      :html="pair.source_html"
                      :readonly="false"
                      placeholder="Source text..."
                      @update="(html: string) => { pair.source_html = html; debouncedSave(pair.id, 'source_html', html) }"
                    />
                  </div>
                  <!-- Target cell -->
                  <div class="w-1/2 p-4 bg-white">
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
              </template>
            </div>
          </template>

          <!-- Interleaved layout -->
          <template v-else>
            <div class="flex-1 overflow-y-auto p-6">
              <div class="max-w-3xl mx-auto space-y-6">
                <template v-for="(pair, i) in pairs" :key="pair.id">
                  <!-- Section divider -->
                  <div v-if="isSectionBoundary(i)"
                    class="bg-blue-50 border border-blue-200 rounded py-1 px-4 text-xs text-blue-600 font-medium">
                    Section {{ pair.section + 1 }}
                  </div>
                  <!-- Paragraph divider -->
                  <div v-else-if="isParagraphBoundary(i)"
                    class="border-t-2 border-gray-300 -mx-2">
                  </div>
                  <!-- Card -->
                  <div class="bg-white rounded-lg border border-gray-200 p-4">
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
                </template>
              </div>
            </div>
          </template>

        </template>

        <!-- ===================== PARAGRAPH / SECTION VIEW ===================== -->
        <template v-else>
          <!-- Column headers -->
          <div class="flex shrink-0 border-b border-gray-200">
            <div class="w-1/2 px-4 py-1 bg-gray-50 border-r border-gray-200">
              <span class="text-xs text-gray-400 uppercase tracking-wider">Source (read-only)</span>
            </div>
            <div class="w-1/2 px-4 py-1 bg-white">
              <span class="text-xs text-gray-400 uppercase tracking-wider">Translation</span>
            </div>
          </div>
          <div class="flex-1 overflow-y-auto">
            <template v-for="(group, gi) in (viewMode === 'paragraph' ? paragraphGroups : sectionGroups)" :key="group.key">
              <!-- Section divider in paragraph view -->
              <div v-if="viewMode === 'paragraph' && gi > 0 && group.section !== (viewMode === 'paragraph' ? paragraphGroups : sectionGroups)[gi - 1].section"
                class="bg-blue-50 border-y border-blue-200 py-1 px-4 text-xs text-blue-600 font-medium">
                Section {{ group.section + 1 }}
              </div>
              <div class="flex border-b border-gray-200" :data-group-key="group.key">
                <!-- Source cell (read-only) -->
                <div class="w-1/2 p-4 bg-gray-50 border-r border-gray-200">
                  <div class="prose prose-sm max-w-none text-gray-600" v-html="group.sourceHtml"></div>
                </div>
                <!-- Target cell (editable, triggers resplit on save) -->
                <div class="w-1/2 p-4 bg-white">
                  <div class="flex items-start gap-2">
                    <div class="flex-1">
                      <PairEditor
                        :html="group.targetHtml"
                        placeholder="Start translating..."
                        @update="(html: string) => debouncedResplit(group, html)"
                      />
                    </div>
                    <div class="flex flex-col gap-1 shrink-0 mt-1">
                      <span v-if="saveStatus[group.key]" class="text-xs text-gray-400 whitespace-nowrap">
                        {{ saveStatus[group.key] }}
                      </span>
                      <span class="text-xs text-gray-300">{{ group.pairs.length }} sent.</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </template>

        <div v-if="pairs.length === 0" class="flex-1 flex items-center justify-center text-gray-400">
          No sentences yet. Click "+ Sentence" or import files to get started.
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
import { defineComponent, h, onBeforeUnmount as onBeforeUnmountOpt } from 'vue'

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

    return () => h(EditorContent, { editor: editor.value })
  },
})

export { PairEditor }
</script>
