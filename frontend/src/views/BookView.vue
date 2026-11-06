<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, shallowReactive, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { booksApi, type Book, type BookBead, type BookSegment, type BookExcludedBlock, type BookRun, type Side } from '@/api/client'
import BeadActions, { type Correction } from '@/components/BeadActions.vue'
import BeadRow from '@/components/BeadRow.vue'
import BookPosition from '@/components/BookPosition.vue'
import BookStatus from '@/components/BookStatus.vue'
import KeysPanel from '@/components/KeysPanel.vue'
import MoreMenu from '@/components/MoreMenu.vue'
import OriginalPopover from '@/components/OriginalPopover.vue'
import { SHORTCUTS, type KeyedId } from '@/keys'
import { buildUnits, isBlank, isSpeech, LEVELS, LEVEL_LABELS, RANK, unitNoun, type Level, type Unit } from '@/levels'
import { originalKey, selectionKey, statusKey } from '@/selection'
import { isProblem } from '@/review'

const props = defineProps<{ id: string }>()
const route = useRoute()

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

// The level of the rows (SPEC §3.3 "Level"): the book always opens at turns.
const level = ref<Level>('turn')
const currentBeadId = ref<number | null>(null)
const currentSide = ref<Side>('source')
const currentSegmentId = ref<number | null>(null)
const editingSegmentId = ref<number | null>(null)
provide(statusKey, status)
watch(currentSegmentId, () => (showOriginal.value = false))

// The units at the level, rebuilt when the book or the level changes; a unit made of the same bead objects as before
// is the same object, so only changed rows re-render (see `reconcile`).
let lastUnits = new Map<number, Unit>()
const units = computed<Unit[]>(() => {
  const built = book.value ? buildUnits(book.value.beads, level.value, lastUnits) : []
  lastUnits = new Map(built.map((u) => [u.id, u]))
  return built
})
const unitIndex = computed(() => new Map(units.value.map((u, i) => [u.id, i])))
/** Bead id → index of the unit holding it. */
const beadUnitIndex = computed(() => {
  const map = new Map<number, number>()
  units.value.forEach((u, i) => u.beads.forEach((b) => map.set(b.id, i)))
  return map
})
const beadIndex = computed(() => new Map(book.value?.beads.map((b, i) => [b.id, i]) ?? []))
const currentBead = computed<BookBead | null>(() => {
  const i = currentBeadId.value === null ? undefined : beadIndex.value.get(currentBeadId.value)
  return i === undefined ? null : book.value!.beads[i]!
})
const currentUnit = computed<Unit | null>(() => {
  const i = currentBeadId.value === null ? undefined : beadUnitIndex.value.get(currentBeadId.value)
  return i === undefined ? null : units.value[i]!
})
const currentUnitId = computed(() => currentUnit.value?.id ?? null)
const currentRow = shallowReactive<Record<number, true>>({})
watch(currentUnitId, (id, old) => {
  if (old !== null && old !== undefined) delete currentRow[old]
  if (id !== null) currentRow[id] = true
}, { flush: 'sync' })

const reviewedCount = computed(() => units.value.filter((u) => u.reviewed).length)
const problemCount = computed(() => units.value.filter((u) => isProblem(u, showMulti.value)).length)
const noun = computed(() => unitNoun(level.value))

// The selected run (SPEC §3.3 "Reviewed marks"): the units from the anchor to the current unit, both included. A run
// exists when the anchor is set and differs from the current unit. `inRun` is updated by difference, like
// `currentRow`, so a Shift+arrow wakes only the rows whose membership changed (Stage 2 scale rule).
const runAnchorId = ref<number | null>(null)
const inRun = shallowReactive<Record<number, true>>({})
const runRange = computed<[number, number] | null>(() => {
  if (runAnchorId.value === null || currentUnitId.value === null || runAnchorId.value === currentUnitId.value) return null
  const a = unitIndex.value.get(runAnchorId.value)
  const c = unitIndex.value.get(currentUnitId.value)
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
  const ids = new Set(range ? units.value.slice(range[0], range[1] + 1).map((u) => u.id) : [])
  for (const key of Object.keys(inRun)) if (!ids.has(Number(key))) delete inRun[Number(key)]
  for (const id of ids) if (!inRun[id]) inRun[id] = true
}, { flush: 'sync' })

// The sentence cut with Ctrl+X (SPEC §3.3), waiting for a Ctrl+V in the neighbouring bead. `cutRow` (unit id →
// segment id) is updated by difference, like `currentRow`: a cut wakes only its own row.
const cut = shallowRef<{ beadId: number; side: Side; segmentId: number } | null>(null)
const cutRow = shallowReactive<Record<number, number>>({})
const cutKey = computed(() => {
  const c = cut.value
  const i = c ? beadUnitIndex.value.get(c.beadId) : undefined
  return c && i !== undefined ? `${units.value[i]!.id}:${c.segmentId}` : null
})
watch(cutKey, (key, old) => {
  if (old) delete cutRow[Number(old.split(':')[0])]
  if (key) cutRow[Number(key.split(':')[0])] = Number(key.split(':')[1])
}, { flush: 'sync' })
provide(selectionKey, { currentRow, currentBeadId, currentUnit, currentSide, currentSegmentId, editingSegmentId, inRun, runBounds, cutRow, book, units, level })

function runUnits(): Unit[] {
  const range = runRange.value
  return range ? units.value.slice(range[0], range[1] + 1) : []
}

function clearRun() {
  runAnchorId.value = null
}

type Item = { type: 'unit'; unit: Unit } | { type: 'excluded'; block: BookExcludedBlock }

/** Rows in display order: units, and with "Show excluded" each excluded block right after the unit holding its bead. */
const items = computed<Item[]>(() => {
  if (!book.value) return []
  const rows: Item[] = units.value.map((unit) => ({ type: 'unit', unit }))
  if (!showExcluded.value) return rows
  const after = new Map<number | null, BookExcludedBlock[]>()
  for (const block of book.value.excluded) {
    const key = block.after_bead_id === null ? null : (units.value[beadUnitIndex.value.get(block.after_bead_id) ?? -1]?.id ?? null)
    const list = after.get(key) ?? []
    list.push(block)
    after.set(key, list)
  }
  const out: Item[] = (after.get(null) ?? []).map((block) => ({ type: 'excluded', block }))
  for (const item of rows) {
    out.push(item)
    if (item.type === 'unit') {
      for (const block of after.get(item.unit.id) ?? []) out.push({ type: 'excluded', block })
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

/** Select a unit, side and segment (default: the side's first segment of the unit); the current bead becomes the one
 * holding that segment. `extend` (Shift) grows the run from its anchor; any other change of unit clears it. */
function select(unitId: number, side: Side, segmentId: number | null, extend = false) {
  const unit = units.value[unitIndex.value.get(unitId) ?? -1]
  if (!unit) return
  if (extend) {
    if (runAnchorId.value === null) runAnchorId.value = currentUnitId.value
  } else if (unitId !== currentUnitId.value) {
    clearRun()
  }
  const segment = (segmentId === null ? unit[side][0] : unit[side].find((s) => s.segment_id === segmentId)) ?? null
  currentBeadId.value = beadOfSegment(unit, side, segment?.segment_id ?? null)
  currentSide.value = side
  currentSegmentId.value = segment?.segment_id ?? null
  nextTick(() => {
    document.querySelector(`[data-testid="bead-row"][data-bead-id="${unitId}"]`)?.scrollIntoView({ block: 'nearest' })
  })
}

/** The unit's bead holding the segment, else its first bead. */
function beadOfSegment(unit: Unit, side: Side, segmentId: number | null): number {
  return (unit.beads.find((b) => b[side].some((s) => s.segment_id === segmentId)) ?? unit.beads[0]!).id
}

function moveBead(delta: number, extend = false) {
  if (!units.value.length) return
  const i = currentUnitId.value === null ? -1 : unitIndex.value.get(currentUnitId.value)!
  const next = Math.min(Math.max(i + delta, 0), units.value.length - 1)
  select(units.value[next]!.id, currentSide.value, null, extend)
}

/** Tab / Shift+Tab: the next or previous segment of the side in the unit, crossing its beads. */
function moveSegment(delta: number) {
  const unit = currentUnit.value
  if (!unit) return
  const segments = unit[currentSide.value]
  const i = segments.findIndex((s) => s.segment_id === currentSegmentId.value)
  const next = segments[i + delta]
  if (next) {
    currentBeadId.value = beadOfSegment(unit, currentSide.value, next.segment_id)
    currentSegmentId.value = next.segment_id
  }
}

function nextUnreviewed() {
  if (!units.value.length) return
  const start = currentUnitId.value === null ? -1 : unitIndex.value.get(currentUnitId.value)!
  for (let k = 1; k <= units.value.length; k++) {
    const unit = units.value[(start + k) % units.value.length]!
    if (!unit.reviewed) {
      select(unit.id, currentSide.value, null)
      return
    }
  }
  say(`Every ${noun.value} is reviewed`)
}

/** Jump to the next (delta 1) or previous (delta -1) problem unit, wrapping around like `n`. */
function nextProblem(delta: 1 | -1) {
  const all = units.value
  if (!all.length) return
  const start = currentUnitId.value === null ? (delta > 0 ? -1 : 0) : unitIndex.value.get(currentUnitId.value)!
  for (let k = 1; k <= all.length; k++) {
    const unit = all[(((start + delta * k) % all.length) + all.length) % all.length]!
    if (isProblem(unit, showMulti.value)) {
      select(unit.id, currentSide.value, null)
      return
    }
  }
  say('No problems left')
}

/** `L`, or the control in the top bar: the rows become units of another level. The current bead stays (and so its
 * unit); the run and the cut go. */
function setLevel(next: Level) {
  if (next === level.value) return
  clearRun()
  cut.value = null
  level.value = next
  const id = currentUnitId.value
  if (id !== null) {
    nextTick(() => {
      document.querySelector(`[data-testid="bead-row"][data-bead-id="${id}"]`)?.scrollIntoView({ block: 'nearest' })
    })
  }
}

function cycleLevel() {
  setLevel(LEVELS[(LEVELS.indexOf(level.value) + 1) % LEVELS.length]!)
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
 * Send one correction and show its result. The current bead (and so its unit) stays if it still exists, else the
 * unit now at the old unit's index (clamped); `selectIndex`, a bead index, overrides that (after a split). Errors go to the status line. A successful
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
    const oldIndex = currentUnitId.value === null ? 0 : (unitIndex.value.get(currentUnitId.value) ?? 0)
    const side = currentSide.value
    const segmentId = currentSegmentId.value
    book.value = reconcile(old, next)
    const beads = book.value.beads
    keepCut(beads)
    if (!beads.length) {
      currentBeadId.value = null
      return true
    }
    let index: number
    if (selectIndex !== undefined) index = beadUnitIndex.value.get(beads[Math.min(Math.max(selectIndex, 0), beads.length - 1)]!.id)!
    else index = beadUnitIndex.value.get(currentBeadId.value ?? -1) ?? Math.min(oldIndex, units.value.length - 1)
    const unit = units.value[index]!
    const keep = unit[side].some((s) => s.segment_id === segmentId)
    select(unit.id, side, keep ? segmentId : null)
    return true
  } catch (e) {
    say((e as Error).message)
    return false
  } finally {
    busy.value = false
  }
}

function currentSegment() {
  return currentUnit.value?.[currentSide.value].find((s) => s.segment_id === currentSegmentId.value) ?? null
}

/** Whether each source block is a speech paragraph, as the backend decides it (see `isSpeech`); for the split rule. */
const speechByBlock = computed(() => {
  const map = new Map<number, boolean>()
  for (const bead of book.value?.beads ?? []) {
    for (const s of bead.source) if (!map.has(s.block_id) && !isBlank(s.text)) map.set(s.block_id, isSpeech(s.text))
  }
  return map
})

/** The bead at a unit's edge that a move acts on: the first for 'previous', the last for 'next'; null (and says why)
 * when it has no segment on the side, at a coarser level (at sentences the backend decides, as ever). */
function edgeBead(unit: Unit, side: Side, edge: 'previous' | 'next'): BookBead | null {
  const bead = edge === 'previous' ? unit.beads[0]! : unit.beads[unit.beads.length - 1]!
  if (unit.level !== 'sentence' && !bead[side].length) {
    const which = edge === 'previous' ? 'first' : 'last'
    say(`The ${noun.value}'s ${which} bead has no ${side === 'source' ? 'source' : 'target'} sentence: switch to sentences (L)`)
    return null
  }
  return bead
}

/** `S` at a coarser level: the bead and source segment to split at, or null (and says why). Only where a bead crosses
 * a break of the level: before the segment, in the same bead, a paragraph break (another block) or, at turns, a
 * non-speech block. */
function coarseSplitPoint(): { bead: BookBead; segment: BookSegment } | null {
  const bead = currentBead.value
  const segment = currentSegment()
  const refuse = () => {
    say(`A ${noun.value} can be split only at a source break that a bead crosses: switch to sentences (L) to split here`)
    return null
  }
  if (!bead || !segment || currentSide.value !== 'source') return refuse()
  const i = bead.source.indexOf(segment)
  if (i < 1) return refuse()
  const before = bead.source[i - 1]!
  const paragraphBreak = before.block_id !== segment.block_id
  const breaks = paragraphBreak || (level.value === 'turn' && !speechByBlock.value.get(segment.block_id))
  return breaks ? { bead, segment } : refuse()
}

function runCorrection(action: Correction) {
  const unit = currentUnit.value
  if (!unit) return
  const side = currentSide.value
  switch (action) {
    case 'move-previous': {
      const bead = edgeBead(unit, side, 'previous')
      return bead && correct((id) => booksApi.move(id, bead.id, side, 'previous'))
    }
    case 'move-next': {
      const bead = edgeBead(unit, side, 'next')
      return bead && correct((id) => booksApi.move(id, bead.id, side, 'next'))
    }
    case 'merge': {
      const bead = unit.beads[unit.beads.length - 1]!
      return correct((id) => booksApi.mergeNext(id, bead.id))
    }
    case 'split': {
      let bead: BookBead
      let at: number | null
      if (unit.level === 'sentence') {
        if (!currentBead.value) return
        bead = currentBead.value
        at = currentSegmentId.value
      } else {
        const point = coarseSplitPoint()
        if (!point) return
        bead = point.bead
        at = point.segment.segment_id
      }
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
      const run = runUnits()
      const lv = level.value
      if (!run.length) return correct((id) => booksApi.setReviewed(id, unit.beads.map((b) => b.id), !unit.reviewed, lv))
      // A run: mark all if any is unreviewed, else clear all; one request, one undo.
      const flag = run.some((u) => !u.reviewed)
      return correct((id) => booksApi.setReviewed(id, run.flatMap((u) => u.beads.map((b) => b.id)), flag, lv), undefined, true)
    }
    case 'up-to-here':
      return reviewUpToHere()
    case 'exclude': {
      const segment = currentSegment()
      if (!segment) return say(`The ${noun.value} has no ${side} segment`)
      return correct((id) => booksApi.excludeBlock(id, segment.block_id))
    }
  }
}

/** `Shift+R`: mark every unit from the first to the current one reviewed at the level; the run, if any, is kept. */
async function reviewUpToHere() {
  const unit = currentUnit.value
  if (!unit) return
  const lv = level.value
  const todo = units.value.slice(0, unitIndex.value.get(unit.id)! + 1).filter((u) => !u.reviewed)
  if (!todo.length) return say('Already reviewed up to here')
  const ids = todo.flatMap((u) => u.beads.filter((b) => (b.review_level === null ? 0 : RANK[b.review_level]) < RANK[lv]).map((b) => b.id))
  if (await correct((id) => booksApi.setReviewed(id, ids, true, lv), undefined, true)) {
    say(`Reviewed up to here (${todo.length} ${unitNoun(lv, todo.length)})`)
  }
}

function startEditing(segmentId: number | null = currentSegmentId.value) {
  if (segmentId === null || busy.value) return
  editingSegmentId.value = segmentId
}

/** Opened by a double-click: select the segment first (its bead and side are the current ones). */
function editSegment(segmentId: number) {
  if (currentUnit.value) select(currentUnit.value.id, currentSide.value, segmentId)
  startEditing(segmentId)
}

function segmentText(segmentId: number): string | undefined {
  for (const side of ['source', 'target'] as const) {
    const seg = currentUnit.value?.[side].find((s) => s.segment_id === segmentId)
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

/** Ctrl+X: mark the current sentence as cut (nothing changes yet), if it is at an edge of its unit; Ctrl+V moves it. */
function cutSentence() {
  const segment = currentSegment()
  const unit = currentUnit.value
  if (!segment || !unit) return
  const side = currentSide.value
  const first = unit.beads[0]!
  const last = unit.beads[unit.beads.length - 1]!
  const bead = segment === first[side][0] ? first : segment === last[side][last[side].length - 1] ? last : null
  if (!bead) {
    return say(`Only the first or last sentence of a ${noun.value} can move to a neighbouring ${noun.value}`)
  }
  cut.value = { beadId: bead.id, side, segmentId: segment.segment_id }
  navigator.clipboard.writeText(segment.text).catch(() => {})  // the cut itself doesn't need the clipboard
  say(`Sentence cut: go to the previous or next ${noun.value} and press Ctrl+V (Esc cancels)`)
}

/** Ctrl+V: the cut sentence moves across the bead boundary between its bead and the current unit's edge bead there,
 * if the current unit lies right beside it (SPEC §3.3). */
async function pasteSentence() {
  const c = cut.value
  const unit = currentUnit.value
  if (!c) return say('Nothing cut')
  if (!unit) return
  const from = beadIndex.value.get(c.beadId)
  const first = beadIndex.value.get(unit.beads[0]!.id)
  const last = beadIndex.value.get(unit.beads[unit.beads.length - 1]!.id)
  const segments = from === undefined ? [] : book.value!.beads[from]![c.side]
  let to: 'previous' | 'next' | null = null
  if (from !== undefined && last === from - 1 && segments[0]?.segment_id === c.segmentId) to = 'previous'
  else if (from !== undefined && first === from + 1 && segments[segments.length - 1]?.segment_id === c.segmentId) to = 'next'
  if (!to) return say(`A sentence can only move to the edge of the neighbouring ${noun.value}: the text order never changes`)
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
  'source-side': () => currentUnit.value && select(currentUnit.value.id, 'source', null),
  'target-side': () => currentUnit.value && select(currentUnit.value.id, 'target', null),
  'next-sentence': (event) => moveSegment(event.shiftKey ? -1 : 1),
  'next-problem': () => nextProblem(1),
  'previous-problem': () => nextProblem(-1),
  'next-unreviewed': nextUnreviewed,
  level: cycleLevel,
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

/** "Re-align the selection" (SPEC §3.3): the beads of the selected run, or of the current unit without one; the new beads start
 * unreviewed, the run is cleared and the first new bead becomes current. */
async function realign() {
  showMore.value = false
  const bead = currentBead.value
  if (!bead || !book.value) return
  const run = runUnits()
  const stretch = (run.length ? run : [currentUnit.value!]).flatMap((u) => u.beads)
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
    // `?bead=<id>` (from a search result) opens the book at that bead, centred.
    const wanted = route.query.bead === undefined ? undefined : Number(route.query.bead)
    const found = wanted === undefined ? undefined : beadUnitIndex.value.get(wanted)
    const first = units.value[found ?? 0]
    if (first) select(first.id, 'source', null)
    if (found !== undefined) {
      nextTick(() => {
        document.querySelector(`[data-testid="bead-row"][data-bead-id="${first!.id}"]`)?.scrollIntoView({ block: 'center' })
      })
    } else if (wanted !== undefined) {
      say('That bead no longer exists: the book changed since the search')
    }
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
        <div data-testid="level" role="group" aria-label="Level" title="Sentences / turns / paragraphs (L)"
          class="shrink-0 flex items-center gap-0.5">
          <button v-for="l in LEVELS" :key="l" type="button" :data-level="l" :aria-pressed="level === l" @click="setLevel(l)"
            class="h-7 px-2 rounded text-ink hover:bg-hover" :class="level === l ? 'bg-hover font-semibold' : ''">
            {{ LEVEL_LABELS[l] }}
          </button>
        </div>
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
          <span data-testid="book-progress">Reviewed {{ reviewedCount }} / {{ units.length }}</span>
          <span class="w-[84px] h-1 rounded-full bg-bar-rule overflow-hidden">
            <span class="block h-full bg-progress" :style="{ width: `${units.length ? (100 * reviewedCount) / units.length : 0}%` }" />
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
        <router-link :to="`/search?book=${book.id}`" data-testid="search-link"
          class="shrink-0 h-7 px-2 flex items-center rounded text-ink hover:bg-hover">Search</router-link>
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
          <template v-for="item in items" :key="item.type === 'unit' ? `b${item.unit.id}` : `x${item.block.block_id}`">
            <BeadRow v-if="item.type === 'unit'" :unit="item.unit" :multi="showMulti"
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
        <BookPosition />
      </div>
      <KeysPanel v-if="showKeys" @close="showKeys = false" />
      <OriginalPopover :book="book" @restore="restoreOriginal" @close="showOriginal = false" />
    </template>
  </div>
</template>
