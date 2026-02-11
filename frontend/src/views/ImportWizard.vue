<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type ImportParagraph } from '@/api/client'

const router = useRouter()
const step = ref(1)
const error = ref('')
const loading = ref(false)

// Step 1
const title = ref('')
const sourceLang = ref('')
const targetLang = ref('')
const sourceFileInput = ref<HTMLInputElement>()
const targetFileInput = ref<HTMLInputElement>()

// Step 2
const sourceParagraphs = ref<ImportParagraph[]>([])
const targetParagraphs = ref<ImportParagraph[]>([])

async function preview() {
  const sf = sourceFileInput.value?.files?.[0]
  const tf = targetFileInput.value?.files?.[0]
  if (!sf || !tf) { error.value = 'Please select both files.'; return }
  if (!title.value.trim()) { error.value = 'Please enter a title.'; return }
  if (!sourceLang.value.trim() || !targetLang.value.trim()) { error.value = 'Please enter both languages.'; return }

  error.value = ''
  loading.value = true
  try {
    const data = await api.importPreview(sf, tf)
    sourceParagraphs.value = data.source_paragraphs
    targetParagraphs.value = data.target_paragraphs
    step.value = 2
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function insertBlank(side: 'source' | 'target', index: number) {
  const arr = side === 'source' ? sourceParagraphs : targetParagraphs
  arr.value.splice(index, 0, { html: '<p></p>', text: '' })
}

function removeRow(side: 'source' | 'target', index: number) {
  const arr = side === 'source' ? sourceParagraphs : targetParagraphs
  arr.value.splice(index, 1)
}

const maxRows = () => Math.max(sourceParagraphs.value.length, targetParagraphs.value.length)

async function confirm() {
  loading.value = true
  error.value = ''
  try {
    const pairs = []
    for (let i = 0; i < maxRows(); i++) {
      const src = sourceParagraphs.value[i] || { html: '<p></p>', text: '' }
      const tgt = targetParagraphs.value[i] || { html: '<p></p>', text: '' }
      pairs.push({
        source_html: src.html,
        target_html: tgt.html,
        source_text: src.text,
        target_text: tgt.text,
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
</script>

<template>
  <div class="max-w-5xl mx-auto p-6">
    <h1 class="text-xl font-semibold mb-4">Import Files</h1>

    <!-- Progress -->
    <div class="flex gap-2 mb-6 text-sm">
      <span :class="step >= 1 ? 'text-blue-600 font-medium' : 'text-gray-400'">1. Upload</span>
      <span class="text-gray-300">/</span>
      <span :class="step >= 2 ? 'text-blue-600 font-medium' : 'text-gray-400'">2. Align</span>
    </div>

    <div v-if="error" class="bg-red-50 text-red-700 p-3 rounded mb-4 text-sm">{{ error }}</div>

    <!-- Step 1: Upload -->
    <div v-if="step === 1" class="space-y-4">
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
          <label class="block text-sm font-medium text-gray-700 mb-1">Source file (.docx or .txt)</label>
          <input ref="sourceFileInput" type="file" accept=".docx,.txt" class="text-sm" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Target file (.docx or .txt)</label>
          <input ref="targetFileInput" type="file" accept=".docx,.txt" class="text-sm" />
        </div>
      </div>
      <button @click="preview" :disabled="loading"
        class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm">
        {{ loading ? 'Processing...' : 'Preview' }}
      </button>
    </div>

    <!-- Step 2: Align -->
    <div v-if="step === 2">
      <div class="flex items-center justify-between mb-4">
        <div class="text-sm text-gray-500">
          {{ sourceParagraphs.length }} source / {{ targetParagraphs.length }} target paragraphs
        </div>
        <div class="flex gap-2">
          <button @click="step = 1" class="px-3 py-1.5 border border-gray-300 rounded text-sm hover:bg-gray-50">Back</button>
          <button @click="confirm" :disabled="loading"
            class="px-4 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm">
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
          <div v-for="i in maxRows()" :key="i" class="grid grid-cols-2 divide-x divide-gray-100">
            <!-- Source side -->
            <div class="p-3 text-sm" :class="sourceParagraphs[i - 1] ? '' : 'bg-gray-50'">
              <div v-if="sourceParagraphs[i - 1]" class="flex gap-2">
                <div class="flex-1 prose prose-sm max-w-none" v-html="sourceParagraphs[i - 1]!.html"></div>
                <div class="flex flex-col gap-1 shrink-0">
                  <button @click="insertBlank('source', i - 1)" class="text-xs text-gray-400 hover:text-blue-600" title="Insert blank above">+</button>
                  <button @click="removeRow('source', i - 1)" class="text-xs text-gray-400 hover:text-red-500" title="Remove">x</button>
                </div>
              </div>
              <span v-else class="text-gray-300 italic">empty</span>
            </div>
            <!-- Target side -->
            <div class="p-3 text-sm" :class="targetParagraphs[i - 1] ? '' : 'bg-gray-50'">
              <div v-if="targetParagraphs[i - 1]" class="flex gap-2">
                <div class="flex-1 prose prose-sm max-w-none" v-html="targetParagraphs[i - 1]!.html"></div>
                <div class="flex flex-col gap-1 shrink-0">
                  <button @click="insertBlank('target', i - 1)" class="text-xs text-gray-400 hover:text-blue-600" title="Insert blank above">+</button>
                  <button @click="removeRow('target', i - 1)" class="text-xs text-gray-400 hover:text-red-500" title="Remove">x</button>
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
