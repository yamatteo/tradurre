<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { booksApi, type Book, type BookBead, type BookExcludedBlock, type Side } from '@/api/client'
import BeadRow, { type Correction } from '@/components/BeadRow.vue'

const props = defineProps<{ id: string }>()

// shallowRef: the book is replaced whole, never mutated (PLAN.md, "Reading and navigation", Scale).
const book = shallowRef<Book | null>(null)
const error = ref('')
const status = ref('')
const showExcluded = ref(false)
const busy = ref(false)

const currentBeadId = ref<number | null>(null)
const currentSide = ref<Side>('source')
const currentSegmentId = ref<number | null>(null)

const reviewedCount = computed(() => book.value?.beads.filter((b) => b.reviewed).length ?? 0)
const beadIndex = computed(() => new Map(book.value?.beads.map((b, i) => [b.id, i]) ?? []))
const currentBead = computed<BookBead | null>(() => {
  const i = currentBeadId.value === null ? undefined : beadIndex.value.get(currentBeadId.value)
  return i === undefined ? null : book.value!.beads[i]!
})

type Item = { type: 'bead'; bead: BookBead } | { type: 'excluded'; block: BookExcludedBlock }

/** Rows in display order: beads, and with "Show excluded" each excluded block right after its bead. */
const items = computed<Item[]>(() => {
  if (!book.value) return []
  const beads: Item[] = book.value.beads.map((bead) => ({ type: 'bead', bead }))
  if (!showExcluded.value) return beads
  const after = new Map<number | null, BookExcludedBlock[]>()
  for (const block of book.value.excluded) {
    const list = after.get(block.after_bead_id) ?? []
    list.push(block)
    after.set(block.after_bead_id, list)
  }
  const out: Item[] = (after.get(null) ?? []).map((block) => ({ type: 'excluded', block }))
  for (const item of beads) {
    out.push(item)
    if (item.type === 'bead') {
      for (const block of after.get(item.bead.id) ?? []) out.push({ type: 'excluded', block })
    }
  }
  return out
})

let statusTimer: number | undefined
function say(message: string) {
  status.value = message
  window.clearTimeout(statusTimer)
  statusTimer = window.setTimeout(() => (status.value = ''), 5000)
}

function firstSegment(bead: BookBead, side: Side): number | null {
  return bead[side][0]?.segment_id ?? null
}

function select(beadId: number, side: Side, segmentId: number | null) {
  currentBeadId.value = beadId
  currentSide.value = side
  const bead = book.value!.beads[beadIndex.value.get(beadId)!]!
  currentSegmentId.value = segmentId ?? firstSegment(bead, side)
  nextTick(() => {
    document.querySelector(`[data-testid="bead-row"][data-bead-id="${beadId}"]`)?.scrollIntoView({ block: 'nearest' })
  })
}

function moveBead(delta: number) {
  const beads = book.value?.beads
  if (!beads?.length) return
  const i = currentBeadId.value === null ? -1 : beadIndex.value.get(currentBeadId.value)!
  const next = Math.min(Math.max(i + delta, 0), beads.length - 1)
  select(beads[next]!.id, currentSide.value, null)
}

function moveSegment(delta: number) {
  const bead = currentBead.value
  if (!bead) return
  const segments = bead[currentSide.value]
  const i = segments.findIndex((s) => s.segment_id === currentSegmentId.value)
  const next = segments[i + delta]
  if (next) currentSegmentId.value = next.segment_id
}

function nextUnreviewed() {
  const beads = book.value?.beads
  if (!beads?.length) return
  const start = currentBeadId.value === null ? -1 : beadIndex.value.get(currentBeadId.value)!
  for (let k = 1; k <= beads.length; k++) {
    const bead = beads[(start + k) % beads.length]!
    if (!bead.reviewed) {
      select(bead.id, currentSide.value, null)
      return
    }
  }
  say('Every bead is reviewed')
}

/** Reuse the old objects for unchanged beads and excluded blocks, so only changed rows re-render. */
function reconcile(old: Book, next: Book): Book {
  const oldBeads = new Map(old.beads.map((b) => [b.id, b]))
  const oldExcluded = new Map(old.excluded.map((x) => [x.block_id, x]))
  const same = <T>(a: T | undefined, b: T): T => (a !== undefined && JSON.stringify(a) === JSON.stringify(b) ? a : b)
  return {
    ...next,
    beads: next.beads.map((b) => same(oldBeads.get(b.id), b)),
    excluded: next.excluded.map((x) => same(oldExcluded.get(x.block_id), x)),
  }
}

/**
 * Send one correction and show its result. The current bead stays if it still exists, else the bead now at its
 * old index (clamped); `selectIndex` overrides that (after a split). Errors go to the status line.
 */
async function correct(request: (id: string) => Promise<Book>, selectIndex?: number) {
  if (busy.value || !book.value) return
  busy.value = true
  const oldIndex = currentBeadId.value === null ? 0 : (beadIndex.value.get(currentBeadId.value) ?? 0)
  const side = currentSide.value
  const segmentId = currentSegmentId.value
  try {
    book.value = reconcile(book.value, await request(book.value.id))
    const beads = book.value.beads
    if (!beads.length) {
      currentBeadId.value = null
      return
    }
    let i = selectIndex ?? beadIndex.value.get(currentBeadId.value ?? -1) ?? oldIndex
    i = Math.min(Math.max(i, 0), beads.length - 1)
    const bead = beads[i]!
    const keep = bead[side].some((s) => s.segment_id === segmentId)
    select(bead.id, side, keep ? segmentId : null)
  } catch (e) {
    say((e as Error).message)
  } finally {
    busy.value = false
  }
}

function currentSegment() {
  return currentBead.value?.[currentSide.value].find((s) => s.segment_id === currentSegmentId.value) ?? null
}

function runCorrection(action: Correction) {
  const bead = currentBead.value
  if (!bead) return
  const side = currentSide.value
  switch (action) {
    case 'move-previous':
      return correct((id) => booksApi.move(id, bead.id, side, 'previous'))
    case 'move-next':
      return correct((id) => booksApi.move(id, bead.id, side, 'next'))
    case 'merge':
      return correct((id) => booksApi.mergeNext(id, bead.id))
    case 'split': {
      const at = currentSegmentId.value
      const index = beadIndex.value.get(bead.id)!
      return correct(
        (id) => booksApi.splitBead(id, bead.id, side === 'source' ? at : null, side === 'target' ? at : null),
        index + 1,
      )
    }
    case 'reviewed':
      return correct((id) => booksApi.setReviewed(id, [bead.id], !bead.reviewed))
    case 'exclude': {
      const segment = currentSegment()
      if (!segment) return say(`The bead has no ${side} segment`)
      return correct((id) => booksApi.excludeBlock(id, segment.block_id))
    }
  }
}

function isTextEntry(target: HTMLElement | null): boolean {
  if (!target) return false
  if (target.isContentEditable || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT') return true
  return target.tagName === 'INPUT' && !['checkbox', 'radio', 'button'].includes((target as HTMLInputElement).type)
}

function onKey(event: KeyboardEvent) {
  if (isTextEntry(event.target as HTMLElement | null)) return
  const key = event.key.toLowerCase()
  if (event.altKey && !event.ctrlKey && !event.metaKey && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
    event.preventDefault()
    runCorrection(event.key === 'ArrowUp' ? 'move-previous' : 'move-next')
    return
  }
  if (event.ctrlKey && !event.altKey && !event.metaKey && (key === 'z' || key === 'y')) {
    event.preventDefault()
    if (key === 'z' && !event.shiftKey) undo()
    else redo()
    return
  }
  if (event.ctrlKey || event.metaKey || event.altKey) return
  const actions: Record<string, () => void> = {
    ArrowDown: () => moveBead(1),
    ArrowUp: () => moveBead(-1),
    ArrowLeft: () => currentBead.value && select(currentBead.value.id, 'source', null),
    ArrowRight: () => currentBead.value && select(currentBead.value.id, 'target', null),
    Tab: () => moveSegment(event.shiftKey ? -1 : 1),
    n: nextUnreviewed,
    m: () => runCorrection('merge'),
    s: () => runCorrection('split'),
    r: () => runCorrection('reviewed'),
    x: () => runCorrection('exclude'),
  }
  const action = actions[event.key]
  if (!action) return
  event.preventDefault()
  action()
}

function undo() {
  correct((id) => booksApi.undo(id))
}

function redo() {
  correct((id) => booksApi.redo(id))
}

function include(blockId: number) {
  correct((id) => booksApi.includeBlock(id, blockId))
}

onMounted(async () => {
  window.addEventListener('keydown', onKey)
  try {
    book.value = await booksApi.getBook(props.id)
    const first = book.value.beads[0]
    if (first) select(first.id, 'source', null)
  } catch (e) {
    error.value = (e as Error).message
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  window.clearTimeout(statusTimer)
})
</script>

<template>
  <div class="max-w-6xl mx-auto p-6">
    <p v-if="error" class="text-red-600">{{ error }}</p>
    <template v-else-if="book">
      <div class="sticky top-0 z-10 bg-gray-50 pb-2 mb-2">
        <div class="flex items-center justify-between gap-4">
          <div class="flex items-center gap-3">
            <router-link to="/" class="text-gray-400 hover:text-gray-600">&larr;</router-link>
            <h1 class="text-xl font-bold text-gray-900" data-testid="book-title">{{ book.title }}</h1>
          </div>
          <div class="flex items-center gap-4 text-sm text-gray-600">
            <button type="button" data-testid="undo" title="Ctrl+Z" :disabled="!book.can_undo || busy" @click="undo"
              class="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed">
              Undo
            </button>
            <button type="button" data-testid="redo" title="Ctrl+Y" :disabled="!book.can_redo || busy" @click="redo"
              class="px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed">
              Redo
            </button>
            <label class="flex items-center gap-1 cursor-pointer">
              <input v-model="showExcluded" type="checkbox" data-testid="show-excluded" />
              Show excluded
            </label>
            <p data-testid="book-progress">reviewed {{ reviewedCount }} / {{ book.beads.length }}</p>
          </div>
        </div>
        <p class="text-sm text-amber-700 min-h-[1.25rem]" data-testid="status">{{ status }}</p>
      </div>

      <div class="bg-white border border-gray-200 rounded-lg divide-y divide-gray-100">
        <template v-for="item in items" :key="item.type === 'bead' ? `b${item.bead.id}` : `x${item.block.block_id}`">
          <BeadRow v-if="item.type === 'bead'" :bead="item.bead" :current="item.bead.id === currentBeadId"
            :current-side="item.bead.id === currentBeadId ? currentSide : null"
            :current-segment-id="item.bead.id === currentBeadId ? currentSegmentId : null"
            @select="select" @correct="runCorrection" />
          <div v-else :data-excluded-block-id="item.block.block_id" data-testid="excluded-row"
            class="grid grid-cols-2 gap-4 px-4 py-2 text-sm border-l-4 border-transparent text-gray-400 italic">
            <div v-for="side in (['source', 'target'] as const)" :key="side">
              <template v-if="side === item.block.side">
                <span class="not-italic text-xs uppercase tracking-wide bg-gray-100 rounded px-1 mr-1">
                  {{ item.block.kind.replace('_', ' ') }}
                </span>
                {{ item.block.segments.map((s) => s.text).join(' ') }}
                <button type="button" data-testid="include" @click="include(item.block.block_id)"
                  class="not-italic ml-2 px-1.5 py-0.5 text-xs border border-gray-300 rounded bg-white text-gray-600 hover:bg-gray-100">
                  Include
                </button>
              </template>
            </div>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>
