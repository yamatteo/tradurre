<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, shallowReactive, shallowRef, watch } from 'vue'
import { booksApi, type Book, type BookBead, type BookExcludedBlock, type BookRun, type Side } from '@/api/client'
import BeadActions, { type Correction } from '@/components/BeadActions.vue'
import BeadRow from '@/components/BeadRow.vue'
import BookPosition from '@/components/BookPosition.vue'
import BookStatus from '@/components/BookStatus.vue'
import KeysPanel from '@/components/KeysPanel.vue'
import MoreMenu from '@/components/MoreMenu.vue'
import OriginalPopover from '@/components/OriginalPopover.vue'
import { SHORTCUTS, type KeyedId } from '@/keys'
import { originalKey, selectionKey, statusKey } from '@/selection'
import { isProblem } from '@/review'

const props = defineProps<{ id: string }>()

// shallowRef: the book is replaced whole, never mutated (PLAN.md, "Reading and navigation", Scale).
const book = shallowRef<Book | null>(null)
const error = ref('')
const status = ref('')
const showExcluded = ref(false)
// "Highlight multi-segment": beads with more than one segment on a side count as problems too.
const showMulti = ref(false)
// The latest import run (SPEC §3.1.5): fetched once on mount; corrections don't change it.
const importRun = shallowRef<BookRun | null>(null)
const showImportLog = ref(false)
const showKeys = ref(false)
// The "More" menu of the second bar (A1): the rare bulk commands. Changes on clicks only (render rule 1 allows it).
const showMore = ref(false)
const moreMenu = ref<InstanceType<typeof MoreMenu> | null>(null)
const importLog = ref<HTMLElement | null>(null)
const list = ref<HTMLElement | null>(null)
// The original-sentence popover (key `o`): read by OriginalPopover.vue only, never by this template (render rule 1).
const showOriginal = ref(false)
provide(originalKey, showOriginal)
const busy = ref(false)

const currentBeadId = ref<number | null>(null)
const currentSide = ref<Side>('source')
const currentSegmentId = ref<number | null>(null)
const editingSegmentId = ref<number | null>(null)
const currentRow = shallowReactive<Record<number, true>>({})
watch(currentBeadId, (id, old) => {
  if (old !== null && old !== undefined) delete currentRow[old]
  if (id !== null) currentRow[id] = true
}, { flush: 'sync' })
provide(statusKey, status)
watch(currentSegmentId, () => (showOriginal.value = false))

const reviewedCount = computed(() => book.value?.beads.filter((b) => b.reviewed).length ?? 0)
const problemCount = computed(() => book.value?.beads.filter((b) => isProblem(b, showMulti.value)).length ?? 0)
const beadIndex = computed(() => new Map(book.value?.beads.map((b, i) => [b.id, i]) ?? []))
const currentBead = computed<BookBead | null>(() => {
  const i = currentBeadId.value === null ? undefined : beadIndex.value.get(currentBeadId.value)
  return i === undefined ? null : book.value!.beads[i]!
})

// The selected run (SPEC §3.3 "Reviewed marks"): the beads from the anchor to the current bead, both included. A run
// exists when the anchor is set and differs from the current bead. `inRun` is updated by difference, like
// `currentRow`, so a Shift+arrow wakes only the rows whose membership changed (Stage 2 scale rule).
const runAnchorId = ref<number | null>(null)
const inRun = shallowReactive<Record<number, true>>({})
const runRange = computed<[number, number] | null>(() => {
  if (runAnchorId.value === null || currentBeadId.value === null || runAnchorId.value === currentBeadId.value) return null
  const a = beadIndex.value.get(runAnchorId.value)
  const c = beadIndex.value.get(currentBeadId.value)
  if (a === undefined || c === undefined) return null
  return [Math.min(a, c), Math.max(a, c)]
})
const runBounds = computed(() => {
  const range = runRange.value
  return range && { first: range[0] + 1, last: range[1] + 1, size: range[1] - range[0] + 1 }
})
watch(runRange, (range, old) => {
  // A new run, or a run grown or shrunk, replaces the message with its summary (BookStatus.vue).
  if (range?.[0] !== old?.[0] || range?.[1] !== old?.[1]) status.value = ''
  const ids = new Set(range ? book.value!.beads.slice(range[0], range[1] + 1).map((b) => b.id) : [])
  for (const key of Object.keys(inRun)) if (!ids.has(Number(key))) delete inRun[Number(key)]
  for (const id of ids) if (!inRun[id]) inRun[id] = true
}, { flush: 'sync' })

// The sentence cut with Ctrl+X (SPEC §3.3), waiting for a Ctrl+V in the neighbouring bead. `cutRow` (bead id →
// segment id) is updated by difference, like `currentRow`: a cut wakes only its own row.
const cut = shallowRef<{ beadId: number; side: Side; segmentId: number } | null>(null)
const cutRow = shallowReactive<Record<number, number>>({})
watch(cut, (c, old) => {
  if (old) delete cutRow[old.beadId]
  if (c) cutRow[c.beadId] = c.segmentId
}, { flush: 'sync' })
provide(selectionKey, { currentRow, currentBeadId, currentSide, currentSegmentId, editingSegmentId, inRun, runBounds, cutRow, book })

function runBeads(): BookBead[] {
  const range = runRange.value
  return range ? book.value!.beads.slice(range[0], range[1] + 1) : []
}

function clearRun() {
  runAnchorId.value = null
}

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

/** Select a bead, side and segment. `extend` (Shift) grows the run from its anchor; any other change of bead clears it. */
function select(beadId: number, side: Side, segmentId: number | null, extend = false) {
  if (extend) {
    if (runAnchorId.value === null) runAnchorId.value = currentBeadId.value
  } else if (beadId !== currentBeadId.value) {
    clearRun()
  }
  currentBeadId.value = beadId
  currentSide.value = side
  const bead = book.value!.beads[beadIndex.value.get(beadId)!]!
  currentSegmentId.value = segmentId ?? firstSegment(bead, side)
  nextTick(() => {
    document.querySelector(`[data-testid="bead-row"][data-bead-id="${beadId}"]`)?.scrollIntoView({ block: 'nearest' })
  })
}

function moveBead(delta: number, extend = false) {
  const beads = book.value?.beads
  if (!beads?.length) return
  const i = currentBeadId.value === null ? -1 : beadIndex.value.get(currentBeadId.value)!
  const next = Math.min(Math.max(i + delta, 0), beads.length - 1)
  select(beads[next]!.id, currentSide.value, null, extend)
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

/** Jump to the next (delta 1) or previous (delta -1) problem bead, wrapping around like `n`. */
function nextProblem(delta: 1 | -1) {
  const beads = book.value?.beads
  if (!beads?.length) return
  const start = currentBeadId.value === null ? (delta > 0 ? -1 : 0) : beadIndex.value.get(currentBeadId.value)!
  for (let k = 1; k <= beads.length; k++) {
    const bead = beads[(((start + delta * k) % beads.length) + beads.length) % beads.length]!
    if (isProblem(bead, showMulti.value)) {
      select(bead.id, currentSide.value, null)
      return
    }
  }
  say('No problems left')
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
 * old index (clamped); `selectIndex` overrides that (after a split). Errors go to the status line. A successful
 * correction clears the selected run, except the review marks for the run (`keepRun`), and keeps the cut sentence
 * only while it is still the first or last of its side in a bead; a refused one changes nothing, so it keeps both.
 * Resolves to whether it succeeded.
 */
async function correct(request: (id: string) => Promise<Book>, selectIndex?: number, keepRun = false): Promise<boolean> {
  if (busy.value || !book.value) return false
  busy.value = true
  const old = book.value
  try {
    const next = await request(old.id)
    if (!keepRun) clearRun()
    // The selection is read now, not before the request: the translator may have moved meanwhile.
    const oldIndex = currentBeadId.value === null ? 0 : (beadIndex.value.get(currentBeadId.value) ?? 0)
    const side = currentSide.value
    const segmentId = currentSegmentId.value
    book.value = reconcile(old, next)
    const beads = book.value.beads
    keepCut(beads)
    if (!beads.length) {
      currentBeadId.value = null
      return true
    }
    let i = selectIndex ?? beadIndex.value.get(currentBeadId.value ?? -1) ?? oldIndex
    i = Math.min(Math.max(i, 0), beads.length - 1)
    const bead = beads[i]!
    const keep = bead[side].some((s) => s.segment_id === segmentId)
    select(bead.id, side, keep ? segmentId : null)
    return true
  } catch (e) {
    say((e as Error).message)
    return false
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
    case 'edit':
      return startEditing()
    case 'join':
      return joinNext()
    case 'reviewed': {
      const run = runBeads()
      if (!run.length) return correct((id) => booksApi.setReviewed(id, [bead.id], !bead.reviewed))
      // A run: mark all if any is unreviewed, else clear all; one request, one undo.
      const flag = run.some((b) => !b.reviewed)
      return correct((id) => booksApi.setReviewed(id, run.map((b) => b.id), flag), undefined, true)
    }
    case 'up-to-here':
      return reviewUpToHere()
    case 'exclude': {
      const segment = currentSegment()
      if (!segment) return say(`The bead has no ${side} segment`)
      return correct((id) => booksApi.excludeBlock(id, segment.block_id))
    }
  }
}

/** `R`: mark every bead from the first to the current one reviewed; the run, if any, is kept. */
async function reviewUpToHere() {
  const bead = currentBead.value
  if (!bead) return
  const ids = book.value!.beads.slice(0, beadIndex.value.get(bead.id)! + 1).filter((b) => !b.reviewed).map((b) => b.id)
  if (!ids.length) return say('Already reviewed up to here')
  if (await correct((id) => booksApi.setReviewed(id, ids, true), undefined, true)) {
    say(`Reviewed up to here (${ids.length} bead${ids.length === 1 ? '' : 's'})`)
  }
}

function startEditing(segmentId: number | null = currentSegmentId.value) {
  if (segmentId === null || busy.value) return
  editingSegmentId.value = segmentId
}

/** Opened by a double-click: select the segment first (its bead and side are the current ones). */
function editSegment(segmentId: number) {
  if (currentBead.value) select(currentBead.value.id, currentSide.value, segmentId)
  startEditing(segmentId)
}

function segmentText(segmentId: number): string | undefined {
  for (const side of ['source', 'target'] as const) {
    const seg = currentBead.value?.[side].find((s) => s.segment_id === segmentId)
    if (seg) return seg.text
  }
}

function saveEdit(segmentId: number, value: string) {
  editingSegmentId.value = null
  const text = value.replace(/\n/g, ' ')
  if (text === segmentText(segmentId)) return
  correct((id) => booksApi.editSegment(id, segmentId, text))
}

function cancelEdit() {
  editingSegmentId.value = null
}

/** Ctrl+Enter: save the text if changed, then split at the caret (two operations, two undo steps). */
function splitEdit(segmentId: number, value: string, offset: number) {
  editingSegmentId.value = null
  const text = value.replace(/\n/g, ' ')
  const changed = text !== segmentText(segmentId)
  correct(async (id) => {
    if (changed) await booksApi.editSegment(id, segmentId, text)
    try {
      return await booksApi.splitSegment(id, segmentId, offset)
    } catch (e) {
      if (!changed) throw e
      say((e as Error).message)  // the edit was saved: show it anyway
      return booksApi.getBook(id)
    }
  })
}

function joinNext() {
  const segmentId = currentSegmentId.value
  if (segmentId !== null) correct((id) => booksApi.joinNext(id, segmentId))
}

/** After a correction the cut follows its sentence, if that is still at an edge of its bead; else it is dropped. */
function keepCut(beads: BookBead[]) {
  const c = cut.value
  if (!c) return
  const bead = beads.find((b) => b[c.side].some((s) => s.segment_id === c.segmentId))
  const segments = bead?.[c.side] ?? []
  if (!bead || (segments[0]!.segment_id !== c.segmentId && segments[segments.length - 1]!.segment_id !== c.segmentId)) {
    cut.value = null
  } else if (bead.id !== c.beadId) {
    cut.value = { ...c, beadId: bead.id }
  }
}

/** Ctrl+C outside the sentence editor: the current sentence goes to the clipboard. */
async function copySentence() {
  const segment = currentSegment()
  if (!segment) return
  try {
    await navigator.clipboard.writeText(segment.text)
    say('Sentence copied')
  } catch (e) {
    say(`Could not copy: ${(e as Error).message}`)
  }
}

/** Ctrl+X: mark the current sentence as cut (nothing changes yet), if it is at an edge of its bead; Ctrl+V moves it. */
function cutSentence() {
  const bead = currentBead.value
  const segment = currentSegment()
  if (!bead || !segment) return
  const side = currentSide.value
  const segments = bead[side]
  if (segment !== segments[0] && segment !== segments[segments.length - 1]) {
    return say('Only the first or last sentence of a bead can move to a neighbouring bead')
  }
  cut.value = { beadId: bead.id, side, segmentId: segment.segment_id }
  navigator.clipboard.writeText(segment.text).catch(() => {})  // the cut itself doesn't need the clipboard
  say('Sentence cut: go to the previous or next bead and press Ctrl+V (Esc cancels)')
}

/** Ctrl+V: the cut sentence moves to the adjacent edge of the current bead, if that is its neighbour (SPEC §3.3). */
async function pasteSentence() {
  const c = cut.value
  if (!c) return say('Nothing cut')
  const from = beadIndex.value.get(c.beadId)
  const here = currentBeadId.value === null ? undefined : beadIndex.value.get(currentBeadId.value)
  const segments = from === undefined ? [] : book.value!.beads[from]![c.side]
  let to: 'previous' | 'next' | null = null
  if (from !== undefined && here === from - 1 && segments[0]?.segment_id === c.segmentId) to = 'previous'
  else if (from !== undefined && here === from + 1 && segments[segments.length - 1]?.segment_id === c.segmentId) to = 'next'
  if (!to) return say('A sentence can only move to the edge of the neighbouring bead: the text order never changes')
  const direction = to
  if (await correct((id) => booksApi.move(id, c.beadId, c.side, direction))) {
    cut.value = null  // the moved sentence is at an edge of its new bead: `keepCut` alone would keep it
    say('Sentence moved (Ctrl+Z to undo)')
  }
}

function isTextEntry(target: HTMLElement | null): boolean {
  if (!target) return false
  if (target.isContentEditable || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT') return true
  return target.tagName === 'INPUT' && !['checkbox', 'radio', 'button'].includes((target as HTMLInputElement).type)
}

// The plain-key handlers, one per keyed entry of SHORTCUTS (keys.ts): the compiler refuses a missing or extra one.
const handlers: Record<KeyedId, (event: KeyboardEvent) => void> = {
  'previous-bead': () => moveBead(-1),
  'next-bead': () => moveBead(1),
  'source-side': () => currentBead.value && select(currentBead.value.id, 'source', null),
  'target-side': () => currentBead.value && select(currentBead.value.id, 'target', null),
  'next-sentence': (event) => moveSegment(event.shiftKey ? -1 : 1),
  'next-problem': () => nextProblem(1),
  'previous-problem': () => nextProblem(-1),
  'next-unreviewed': nextUnreviewed,
  'show-keys': () => (showKeys.value = true),
  reviewed: () => runCorrection('reviewed'),
  'reviewed-up-to-here': () => runCorrection('up-to-here'),
  merge: () => runCorrection('merge'),
  split: () => runCorrection('split'),
  exclude: () => runCorrection('exclude'),
  'show-original': toggleOriginal,
  edit: () => startEditing(),
  join: joinNext,
}
const actions = new Map<string, (event: KeyboardEvent) => void>()
for (const s of SHORTCUTS) if ('key' in s) actions.set(s.key, handlers[s.id])

function onKey(event: KeyboardEvent) {
  if (isTextEntry(event.target as HTMLElement | null)) return
  if (showKeys.value) {
    // The panel is modal: only Esc, which closes it.
    if (event.key === 'Escape') showKeys.value = false
    event.preventDefault()
    return
  }
  if (event.key === 'Escape' && showImportLog.value) {
    event.preventDefault()
    showImportLog.value = false
    return
  }
  if (event.key === 'Escape' && showMore.value) {
    event.preventDefault()
    showMore.value = false
    return
  }
  if (event.key === 'Escape' && showOriginal.value) {
    event.preventDefault()
    showOriginal.value = false
    return
  }
  if (event.key === 'Escape' && cut.value) {
    event.preventDefault()
    cut.value = null
    return
  }
  if (event.key === 'Escape' && runRange.value) {
    event.preventDefault()
    clearRun()
    return
  }
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
  if (event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey && (key === 'c' || key === 'x' || key === 'v')) {
    // Text selected outside the bead list (e.g. in the import log) is copied by the browser, as usual.
    const selected = document.getSelection()
    if (key !== 'v' && selected && !selected.isCollapsed && !list.value?.contains(selected.anchorNode)) return
    event.preventDefault()
    if (key === 'c') copySentence()
    else if (key === 'x') cutSentence()
    else pasteSentence()
    return
  }
  if (event.ctrlKey || event.metaKey || event.altKey) return
  if (event.shiftKey && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
    event.preventDefault()
    moveBead(event.key === 'ArrowUp' ? -1 : 1, true)
    return
  }
  // A letter's case comes from Shift alone, never from Caps Lock: with Caps Lock on, `r` must not become `R`.
  const letter = event.key.length === 1 && event.key.toLowerCase() !== event.key.toUpperCase()
  const action = actions.get(letter ? (event.shiftKey ? event.key.toUpperCase() : key) : event.key)
  if (!action) return
  event.preventDefault()
  action(event)
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

/** A "More" item (SPEC §3.3): exclude or include every block of the current side up to here or from here on. */
async function bulk(action: 'exclude' | 'include', to: 'start' | 'end') {
  showMore.value = false
  const bead = currentBead.value
  if (!bead || !book.value) return
  const side = currentSide.value
  const before = book.value.excluded.length
  const request = action === 'exclude' ? booksApi.excludeRange : booksApi.includeRange
  if (await correct((id) => request(id, bead.id, side, to))) {
    const n = Math.abs(book.value.excluded.length - before)
    const blocks = `${n} block${n === 1 ? '' : 's'}`
    say(action === 'exclude' ? `Excluded ${blocks} (Ctrl+Z to undo)` : `Included ${blocks}`)
  }
}

function toggleMore() {
  showMore.value = !showMore.value
  if (showMore.value) showImportLog.value = showOriginal.value = false
}

function toggleImportLog() {
  showImportLog.value = !showImportLog.value
  if (showImportLog.value) showMore.value = showOriginal.value = false
}

/** `o`: show or hide the current sentence's original, if it is edited. */
function toggleOriginal() {
  if (showOriginal.value) {
    showOriginal.value = false
    return
  }
  const segment = currentSegment()
  if (!segment) return
  if (segment.original === null) return say('This sentence is not edited')
  showOriginal.value = true
  showMore.value = showImportLog.value = false
}

async function restoreOriginal() {
  showOriginal.value = showMore.value = false
  const segment = currentSegment()
  if (!segment?.original) return
  if (await correct((id) => booksApi.restoreOriginal(id, segment.segment_id))) say('Original restored (Ctrl+Z to undo)')
}

/** "Re-align the selection" (SPEC §3.3): the selected run, or the current bead without one; the new beads start
 * unreviewed, the run is cleared and the first new bead becomes current. */
async function realign() {
  showMore.value = false
  const bead = currentBead.value
  if (!bead || !book.value) return
  const run = runBeads()
  const stretch = run.length ? run : [bead]
  const n = stretch.length
  const before = book.value.beads.length
  const first = beadIndex.value.get(stretch[0]!.id)!
  if (await correct((id) => booksApi.realign(id, stretch[0]!.id, stretch[n - 1]!.id), first)) {
    const m = n + book.value.beads.length - before
    say(`Re-aligned ${n} bead${n === 1 ? '' : 's'} into ${m} (Ctrl+Z to undo)`)
  }
}

/** A click outside the "More" menu or the import log closes it. */
function onWindowMouseDown(event: MouseEvent) {
  if (showMore.value && !(moreMenu.value?.$el as HTMLElement | undefined)?.contains(event.target as Node)) showMore.value = false
  if (showImportLog.value && !importLog.value?.contains(event.target as Node)) showImportLog.value = false
}

onMounted(async () => {
  window.addEventListener('keydown', onKey)
  window.addEventListener('mousedown', onWindowMouseDown)
  try {
    book.value = await booksApi.getBook(props.id)
    const first = book.value.beads[0]
    if (first) select(first.id, 'source', null)
  } catch (e) {
    error.value = (e as Error).message
    return
  }
  try {
    importRun.value = (await booksApi.getRuns(props.id)).find((run) => run.kind === 'import') ?? null
  } catch (e) {
    say(`Import log: ${(e as Error).message}`)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('mousedown', onWindowMouseDown)
  window.clearTimeout(statusTimer)
})
</script>

<template>
  <div class="h-screen flex flex-col bg-ground font-ui text-ink">
    <p v-if="error" class="p-6 text-red-600">{{ error }}</p>
    <template v-else-if="book">
      <!-- Top bar (A1). -->
      <div data-testid="top-bar" class="shrink-0 h-10 flex items-center gap-3 px-4 border-b border-bar-rule text-[12.5px]">
        <router-link to="/" class="shrink-0 text-muted hover:text-ink">&larr; Library</router-link>
        <span class="shrink-0 w-px h-4 bg-bar-rule" />
        <h1 class="min-w-0 truncate text-[13.5px] font-semibold" data-testid="book-title">{{ book.title }}</h1>
        <span class="flex-1" />
        <label class="shrink-0 flex items-center gap-1.5 cursor-pointer text-muted">
          <input v-model="showExcluded" type="checkbox" data-testid="show-excluded" class="accent-accent" />
          Show excluded
        </label>
        <label class="shrink-0 flex items-center gap-1.5 cursor-pointer text-muted">
          <input v-model="showMulti" type="checkbox" data-testid="show-multi" class="accent-accent" />
          Highlight multi-segment
        </label>
        <span class="shrink-0 w-px h-4 bg-bar-rule" />
        <div class="shrink-0 flex items-center gap-2 text-muted">
          <span data-testid="book-progress">Reviewed {{ reviewedCount }} / {{ book.beads.length }}</span>
          <span class="w-[84px] h-1 rounded-full bg-bar-rule overflow-hidden">
            <span class="block h-full bg-progress" :style="{ width: `${book.beads.length ? (100 * reviewedCount) / book.beads.length : 0}%` }" />
          </span>
        </div>
        <span class="shrink-0 w-px h-4 bg-bar-rule" />
        <div v-if="importRun" ref="importLog" class="shrink-0 relative">
          <button type="button" data-testid="import-log" :aria-expanded="showImportLog"
            :title="importRun.warnings.length ? `Import log: ${importRun.warnings.length} warning${importRun.warnings.length === 1 ? '' : 's'}` : 'Import log'"
            @click="toggleImportLog"
            class="h-7 px-2 flex items-center gap-1.5 rounded text-ink hover:bg-hover"
            :class="showImportLog ? 'bg-hover' : ''">
            <svg v-if="importRun.warnings.length" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor"
              stroke-width="1.4" stroke-linejoin="round" class="text-problem-mark" aria-hidden="true">
              <path d="M7 1.5L13 12H1z" /><path d="M7 5.5v3M7 10v.2" stroke-linecap="round" />
            </svg>
            Import log
            <span v-if="importRun.warnings.length" class="px-1.5 rounded-full bg-pill text-pill-ink font-code text-[10.5px] font-medium">{{ importRun.warnings.length }}</span>
          </button>
          <div v-if="showImportLog" data-testid="import-log-panel"
            class="absolute right-0 top-full mt-1.5 z-30 w-[390px] max-h-[60vh] overflow-auto bg-white border border-bar-rule rounded-md shadow-lg">
            <div class="flex items-center justify-between px-3 h-9 border-b border-row-rule">
              <span class="font-semibold">Import log</span>
              <button type="button" aria-label="Close" title="Close (Esc)" @click="showImportLog = false"
                class="w-6 h-6 flex items-center justify-center rounded text-muted hover:bg-hover">
                <svg width="10" height="10" viewBox="0 0 10 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true">
                  <path d="M1 1l8 8M9 1l-8 8" />
                </svg>
              </button>
            </div>
            <div class="p-3">
              <p class="mb-1.5 text-[10.5px] uppercase tracking-wider text-faint">Warnings · {{ importRun.warnings.length }}</p>
              <ul v-if="importRun.warnings.length" class="mb-3 space-y-1">
                <li v-for="(w, i) in importRun.warnings" :key="i" data-testid="import-warning" class="text-problem">
                  {{ w.side ? `${w.side}: ` : '' }}{{ w.message }}
                </li>
              </ul>
              <p class="text-muted">Imported {{ new Date(importRun.created_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) }} with Tradurre {{ importRun.app_version }}</p>
              <pre data-testid="import-stats" class="mt-1.5 p-2 bg-ground rounded font-code text-[11px] overflow-auto">{{ JSON.stringify(importRun.stats, null, 2) }}</pre>
            </div>
          </div>
        </div>
        <button type="button" data-testid="keys" title="Keyboard shortcuts (H)" @click="showKeys = true"
          class="shrink-0 h-7 px-2 flex items-center gap-1.5 rounded text-ink hover:bg-hover">
          Keys <kbd>H</kbd>
        </button>
      </div>

      <!-- Second bar (A1): navigation | review | corrections | history. -->
      <div data-testid="second-bar" class="shrink-0 h-[38px] flex items-center gap-2 px-3 bg-bar border-b border-bar-rule text-[12.5px]">
        <div class="shrink-0 flex items-center gap-0.5">
          <button type="button" aria-label="Previous problem" title="Previous problem (Shift+P)" @click="nextProblem(-1)"
            class="w-7 h-7 flex items-center justify-center rounded text-ink hover:bg-hover">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7.5 2.5L4 6l3.5 3.5" /></svg>
          </button>
          <span data-testid="problem-count" class="px-1 tabular-nums">{{ problemCount }} problem{{ problemCount === 1 ? '' : 's' }}</span>
          <button type="button" data-testid="next-problem" aria-label="Next problem" title="Next problem (P)" @click="nextProblem(1)"
            class="w-7 h-7 flex items-center justify-center rounded text-ink hover:bg-hover">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 2.5L8 6 4.5 9.5" /></svg>
          </button>
          <button type="button" title="Next unreviewed (N)" @click="nextUnreviewed"
            class="h-7 px-2 flex items-center gap-1.5 rounded text-ink hover:bg-hover">
            Next unreviewed <kbd>N</kbd>
          </button>
        </div>
        <span class="shrink-0 w-px h-5 bg-bar-rule" />
        <BeadActions class="shrink-0" group="review" :book="book" :disabled="busy || editingSegmentId !== null" @correct="runCorrection" />
        <span class="shrink-0 w-px h-5 bg-bar-rule" />
        <BeadActions class="shrink-0" group="corrections" :book="book" :disabled="busy || editingSegmentId !== null" @correct="runCorrection" />
        <MoreMenu ref="moreMenu" :open="showMore" :disabled="busy || editingSegmentId !== null" @toggle="toggleMore"
          @bulk="bulk" @restore="restoreOriginal" @realign="realign" />
        <span class="flex-1" />
        <button type="button" data-testid="undo" aria-label="Undo" title="Undo (Ctrl+Z)" :disabled="!book.can_undo || busy || editingSegmentId !== null" @click="undo"
          class="shrink-0 w-7 h-7 flex items-center justify-center rounded text-ink hover:bg-hover disabled:opacity-40 disabled:hover:bg-transparent disabled:cursor-not-allowed">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 2.5L2 5l2.5 2.5" /><path d="M2 5h6.5a3.5 3.5 0 010 7H6" /></svg>
        </button>
        <button type="button" data-testid="redo" aria-label="Redo" title="Redo (Ctrl+Y)" :disabled="!book.can_redo || busy || editingSegmentId !== null" @click="redo"
          class="shrink-0 w-7 h-7 flex items-center justify-center rounded text-ink hover:bg-hover disabled:opacity-40 disabled:hover:bg-transparent disabled:cursor-not-allowed">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9.5 2.5L12 5 9.5 7.5" /><path d="M12 5H5.5a3.5 3.5 0 000 7H8" /></svg>
        </button>
      </div>

      <!-- The bead list is the only scrolling element. -->
      <!-- A scroll closes the original popover, which is placed once and would float away (a write, not a read). -->
      <div ref="list" class="flex-1 min-h-0 overflow-auto bg-list" @scroll="showOriginal = false">
        <div class="max-w-[1560px] mx-auto">
          <div class="sticky top-0 z-10 h-7 grid grid-cols-[40px_minmax(0,1fr)_minmax(0,1fr)_96px] items-center bg-list border-b border-bar-rule text-[10.5px] uppercase tracking-wider text-faint">
            <span />
            <span class="px-4">Source · {{ book.source_lang.toUpperCase() }}</span>
            <span class="px-4">Target · {{ book.target_lang.toUpperCase() }}</span>
            <span />
          </div>
          <template v-for="item in items" :key="item.type === 'bead' ? `b${item.bead.id}` : `x${item.block.block_id}`">
            <BeadRow v-if="item.type === 'bead'" :bead="item.bead" :multi="showMulti"
              @select="select" @edit="editSegment" @save="saveEdit" @cancel="cancelEdit"
              @split="splitEdit" />
            <!-- One row per excluded block and side (user, 2026-10-04): never paired across sides. -->
            <div v-else :data-excluded-block-id="item.block.block_id" data-testid="excluded-row"
              class="grid grid-cols-[40px_minmax(0,1fr)_minmax(0,1fr)_96px] border-b border-row-rule bg-excluded text-[13px] text-muted">
              <span />
              <div v-for="side in (['source', 'target'] as const)" :key="side" class="px-4 pt-[7px] pb-2"
                :class="side === 'target' ? 'border-l border-row-rule' : ''">
                <template v-if="side === item.block.side">
                  <span class="mr-2 text-[10.5px] uppercase tracking-wider text-faint">
                    {{ item.block.kind.replace('_', ' ') }}
                  </span>
                  {{ item.block.segments.map((s) => s.text).join(' ') }}
                </template>
              </div>
              <div class="pt-[6px] pr-3 text-right">
                <button type="button" data-testid="include" @click="include(item.block.block_id)"
                  class="px-1.5 py-0.5 text-xs border border-outline rounded bg-white text-ink hover:bg-hover">
                  Include
                </button>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- Both texts sit in fixed, size-contained boxes: their changes are laid out alone, not with the bead list. -->
      <div class="shrink-0 relative h-[26px] border-t border-bar-rule text-[12px] text-muted">
        <BookStatus />
        <BookPosition :book="book" />
      </div>
      <KeysPanel v-if="showKeys" @close="showKeys = false" />
      <OriginalPopover :book="book" @restore="restoreOriginal" @close="showOriginal = false" />
    </template>
  </div>
</template>
