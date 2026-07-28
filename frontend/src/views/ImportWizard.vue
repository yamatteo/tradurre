<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { api, type ImportUnit } from '@/api/client'

const router = useRouter()
const step = ref(1)
const error = ref('')
const loading = ref(false)

// Step 1: Upload
const mode = ref<'files' | 'artifact'>('files')
const title = ref('')
const sourceLang = ref('')
const targetLang = ref('')
const sourceFileInput = ref<HTMLInputElement>()
const targetFileInput = ref<HTMLInputElement>()
const artifactFileInput = ref<HTMLInputElement>()
const artifactWarnings = ref<string[]>([])
const artifactStats = ref<Record<string, unknown> | null>(null)

// Step 2: Sections
const sourceSections = ref<ImportUnit[]>([])
const targetSections = ref<ImportUnit[]>([])

// Step 3: Paragraphs
const sourceParagraphs = ref<ImportUnit[]>([])
const targetParagraphs = ref<ImportUnit[]>([])

// Step 4: Sentences
const sourceSentences = ref<ImportUnit[]>([])
const targetSentences = ref<ImportUnit[]>([])

// --- Step 1 → 2: Upload files, get section-level alignment ---
async function previewSections() {
  const sf = sourceFileInput.value?.files?.[0]
  const tf = targetFileInput.value?.files?.[0]
  if (!sf || !tf) { error.value = 'Please select both files.'; return }
  if (!title.value.trim()) { error.value = 'Please enter a title.'; return }
  if (!sourceLang.value.trim() || !targetLang.value.trim()) { error.value = 'Please enter both languages.'; return }

  error.value = ''
  loading.value = true
  try {
    const data = await api.importSections(sf, tf)
    sourceSections.value = data.source_sections
    targetSections.value = data.target_sections
    step.value = 2
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// --- Alternate step 1: load a pre-aligned artifact, skip straight to sentence review ---
async function loadArtifact() {
  const af = artifactFileInput.value?.files?.[0]
  if (!af) { error.value = 'Please select an artifact file.'; return }

  error.value = ''
  loading.value = true
  try {
    const data = await api.importArtifact(af)
    title.value = data.title
    sourceLang.value = data.source_lang
    targetLang.value = data.target_lang
    sourceSentences.value = data.source_sentences
    targetSentences.value = data.target_sentences
    artifactWarnings.value = data.warnings
    artifactStats.value = data.stats
    step.value = 4
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// --- Step 2 → 3: Confirm sections, get paragraph-level alignment ---
async function previewParagraphs() {
  error.value = ''
  loading.value = true
  try {
    const maxLen = Math.max(sourceSections.value.length, targetSections.value.length)
    const sections = []
    for (let i = 0; i < maxLen; i++) {
      const src = sourceSections.value[i]
      const tgt = targetSections.value[i]
      sections.push({
        source_text: src?.text || '',
        target_text: tgt?.text || '',
      })
    }
    const data = await api.importParagraphs(sections)
    sourceParagraphs.value = data.source_paragraphs
    targetParagraphs.value = data.target_paragraphs
    step.value = 3
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// --- Step 3 → 4: Confirm paragraphs, get sentence-level alignment ---
async function previewSentences() {
  error.value = ''
  loading.value = true
  try {
    const maxLen = Math.max(sourceParagraphs.value.length, targetParagraphs.value.length)
    const paragraphs = []
    for (let i = 0; i < maxLen; i++) {
      const src = sourceParagraphs.value[i]
      const tgt = targetParagraphs.value[i]
      paragraphs.push({
        source_text: src?.text || '',
        target_text: tgt?.text || '',
        section: src?.section ?? tgt?.section ?? 0,
        paragraph: src?.index ?? tgt?.index ?? i,
      })
    }
    const data = await api.importSentences(paragraphs)
    sourceSentences.value = data.source_sentences
    targetSentences.value = data.target_sentences
    step.value = 4
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// --- Step 4: Confirm and create project ---
async function confirm() {
  loading.value = true
  error.value = ''
  try {
    const maxLen = Math.max(sourceSentences.value.length, targetSentences.value.length)
    const pairs = []
    for (let i = 0; i < maxLen; i++) {
      const src = sourceSentences.value[i] || { html: '<p></p>', text: '', section: 0, paragraph: 0 }
      const tgt = targetSentences.value[i] || { html: '<p></p>', text: '', section: 0, paragraph: 0 }
      pairs.push({
        source_html: src.html,
        target_html: tgt.html,
        source_text: src.text,
        target_text: tgt.text,
        section: src.section,
        paragraph: src.paragraph,
      })
    }
    const project = await api.importConfirm({
      title: title.value,
      source_lang: sourceLang.value,
      target_lang: targetLang.value,
      pairs,
    })
    router.push(`/project/${project.id}`)
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// --- Alignment adjustment controls ---
function insertBlank(side: 'source' | 'target', arr: { value: ImportUnit[] }, index: number) {
  arr.value.splice(index, 0, { html: '<p></p>', text: '', index: 0, section: 0, paragraph: 0 })
}

function removeRow(side: 'source' | 'target', arr: { value: ImportUnit[] }, index: number) {
  arr.value.splice(index, 1)
}

// Current step's data
const currentSourceArr = computed(() => {
  if (step.value === 2) return sourceSections
  if (step.value === 3) return sourceParagraphs
  return sourceSentences
})
const currentTargetArr = computed(() => {
  if (step.value === 2) return targetSections
  if (step.value === 3) return targetParagraphs
  return targetSentences
})
const currentMaxRows = computed(() =>
  Math.max(currentSourceArr.value.value.length, currentTargetArr.value.value.length)
)

const stepLabel = computed(() => {
  if (step.value === 2) return 'sections'
  if (step.value === 3) return 'paragraphs'
  return 'sentences'
})

function lowConfidenceClass(unit: ImportUnit | undefined) {
  return unit && unit.confidence !== undefined && unit.confidence < 0.5 ? 'bg-amber-50' : ''
}
</script>

<template>
  <div class="max-w-5xl mx-auto p-6">
    <h1 class="text-xl font-semibold mb-4">Import Files</h1>

    <!-- Progress -->
    <div class="flex gap-2 mb-6 text-sm">
      <span :class="step >= 1 ? 'text-blue-600 font-medium' : 'text-gray-400'">1. Upload</span>
      <span class="text-gray-300">/</span>
      <span :class="step >= 2 ? 'text-blue-600 font-medium' : 'text-gray-400'">2. Sections</span>
      <span class="text-gray-300">/</span>
      <span :class="step >= 3 ? 'text-blue-600 font-medium' : 'text-gray-400'">3. Paragraphs</span>
      <span class="text-gray-300">/</span>
      <span :class="step >= 4 ? 'text-blue-600 font-medium' : 'text-gray-400'">4. Sentences</span>
    </div>

    <div v-if="error" class="bg-red-50 text-red-700 p-3 rounded mb-4 text-sm">{{ error }}</div>

    <!-- Step 1: Upload -->
    <div v-if="step === 1" class="space-y-4">
      <div class="flex gap-2 text-sm">
        <button @click="mode = 'files'"
          :class="mode === 'files' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600'"
          class="px-3 py-1.5 rounded">From text files</button>
        <button @click="mode = 'artifact'"
          :class="mode === 'artifact' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600'"
          class="px-3 py-1.5 rounded">From aligned artifact (.json)</button>
      </div>

      <template v-if="mode === 'files'">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Project title</label>
          <input v-model="title" class="w-full border border-gray-300 rounded px-3 py-2 text-sm" placeholder="e.g. Don Quixote Ch.1" />
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Source language</label>
            <input v-model="sourceLang" class="w-full border border-gray-300 rounded px-3 py-2 text-sm" placeholder="e.g. Spanish" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Target language</label>
            <input v-model="targetLang" class="w-full border border-gray-300 rounded px-3 py-2 text-sm" placeholder="e.g. English" />
          </div>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Source file (.docx, .txt or .pdf)</label>
            <input ref="sourceFileInput" type="file" accept=".docx,.txt,.pdf" class="text-sm" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Target file (.docx, .txt or .pdf)</label>
            <input ref="targetFileInput" type="file" accept=".docx,.txt,.pdf" class="text-sm" />
          </div>
        </div>
        <button @click="previewSections" :disabled="loading"
          class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm">
          {{ loading ? 'Processing...' : 'Preview' }}
        </button>
      </template>

      <template v-else>
        <p class="text-sm text-gray-500">
          Upload a pre-aligned artifact produced by the external alignment pipeline
          (e.g. a Colab run). Title, languages and alignment are prefilled from the
          file, and you'll land directly on the sentence review step.
        </p>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Artifact file (.json)</label>
          <input ref="artifactFileInput" type="file" accept=".json" class="text-sm" />
        </div>
        <button @click="loadArtifact" :disabled="loading"
          class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm">
          {{ loading ? 'Loading...' : 'Load Artifact' }}
        </button>
      </template>
    </div>

    <!-- Steps 2-4: Alignment preview (sections / paragraphs / sentences) -->
    <div v-if="step >= 2">
      <div v-if="artifactWarnings.length || artifactStats" class="bg-amber-50 text-amber-800 p-3 rounded mb-4 text-xs space-y-1">
        <div v-for="(w, i) in artifactWarnings" :key="i">{{ w }}</div>
        <div v-if="artifactStats">Pipeline stats: {{ JSON.stringify(artifactStats) }}</div>
        <div class="flex items-center gap-1 pt-1">
          <span class="inline-block w-3 h-3 bg-amber-100 border border-amber-200"></span>
          <span>= low-confidence pairing, worth double-checking</span>
        </div>
      </div>
      <div class="flex items-center justify-between mb-4">
        <div class="text-sm text-gray-500">
          {{ currentSourceArr.value.length }} source / {{ currentTargetArr.value.length }} target {{ stepLabel }}
        </div>
        <div class="flex gap-2">
          <button @click="step = step - 1" class="px-3 py-1.5 border border-gray-300 rounded text-sm hover:bg-gray-50">Back</button>
          <button v-if="step === 2" @click="previewParagraphs" :disabled="loading"
            class="px-4 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm">
            {{ loading ? 'Processing...' : 'Confirm Sections' }}
          </button>
          <button v-else-if="step === 3" @click="previewSentences" :disabled="loading"
            class="px-4 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm">
            {{ loading ? 'Processing...' : 'Confirm Paragraphs' }}
          </button>
          <button v-else @click="confirm" :disabled="loading"
            class="px-4 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 text-sm">
            {{ loading ? 'Creating...' : 'Confirm Import' }}
          </button>
        </div>
      </div>

      <div class="border border-gray-200 rounded-lg overflow-hidden">
        <div class="grid grid-cols-2 bg-gray-100 border-b border-gray-200 px-4 py-2 text-xs text-gray-500 uppercase tracking-wider">
          <div>Source</div>
          <div>Target</div>
        </div>
        <div class="max-h-[60vh] overflow-y-auto divide-y divide-gray-100">
          <div v-for="i in currentMaxRows" :key="i" class="grid grid-cols-2 divide-x divide-gray-100">
            <!-- Source side -->
            <div class="p-3 text-sm" :class="currentSourceArr.value[i - 1] ? lowConfidenceClass(currentSourceArr.value[i - 1]) : 'bg-gray-50'">
              <div v-if="currentSourceArr.value[i - 1]" class="flex gap-2">
                <div class="flex-1 prose prose-sm max-w-none" v-html="currentSourceArr.value[i - 1]!.html"></div>
                <div class="flex flex-col gap-1 shrink-0">
                  <button @click="insertBlank('source', currentSourceArr.value, i - 1)" class="text-xs text-gray-400 hover:text-blue-600" title="Insert blank above">+</button>
                  <button @click="removeRow('source', currentSourceArr.value, i - 1)" class="text-xs text-gray-400 hover:text-red-500" title="Remove">x</button>
                </div>
              </div>
              <span v-else class="text-gray-300 italic">empty</span>
            </div>
            <!-- Target side -->
            <div class="p-3 text-sm" :class="currentTargetArr.value[i - 1] ? lowConfidenceClass(currentTargetArr.value[i - 1]) : 'bg-gray-50'">
              <div v-if="currentTargetArr.value[i - 1]" class="flex gap-2">
                <div class="flex-1 prose prose-sm max-w-none" v-html="currentTargetArr.value[i - 1]!.html"></div>
                <div class="flex flex-col gap-1 shrink-0">
                  <button @click="insertBlank('target', currentTargetArr.value, i - 1)" class="text-xs text-gray-400 hover:text-blue-600" title="Insert blank above">+</button>
                  <button @click="removeRow('target', currentTargetArr.value, i - 1)" class="text-xs text-gray-400 hover:text-red-500" title="Remove">x</button>
                </div>
              </div>
              <span v-else class="text-gray-300 italic">empty</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
