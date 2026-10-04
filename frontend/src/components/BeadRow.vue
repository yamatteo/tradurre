<script setup lang="ts">
// One bead as a row (source left, target right). The selection is injected, not passed as props, and each row
// derives its own share of it in computeds: moving the selection re-renders the two rows whose share changed, and
// not the parent's 10,000-row list (PLAN.md, "Segment editing", scale tripwire).
import { computed, inject, watch } from 'vue'
import type { BookBead, BookSegment, Side } from '@/api/client'
import { selectionKey } from '@/selection'
import { isProblem } from '@/review'

const props = defineProps<{ bead: BookBead; multi: boolean }>()

const selection = inject(selectionKey)!
const current = computed(() => selection.currentRow[props.bead.id] === true)
const currentSide = computed<Side | null>(() => (current.value ? selection.currentSide.value : null))
const currentSegmentId = computed(() => (current.value ? selection.currentSegmentId.value : null))
const editingSegmentId = computed(() => (current.value ? selection.editingSegmentId.value : null))
const problem = computed(() => isProblem(props.bead, props.multi))

const emit = defineEmits<{
  select: [beadId: number, side: Side, segmentId: number | null]
  edit: [segmentId: number]
  save: [segmentId: number, text: string]
  cancel: []
  split: [segmentId: number, text: string, offset: number]
}>()

// The editor's outcome is decided once: by Enter, Escape, Ctrl+Enter, or else by its blur (which saves).
let finished = false
watch(editingSegmentId, (id) => {
  if (id !== null) finished = false  // only on opening: closing must not re-arm the blur of the closing editor
})

function grow(el: HTMLTextAreaElement) {
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

function mountEditor(el: unknown) {
  if (!(el instanceof HTMLTextAreaElement) || document.activeElement === el) return
  grow(el)
  el.focus()
  el.setSelectionRange(el.value.length, el.value.length)
}

function onEditorKey(event: KeyboardEvent, segmentId: number) {
  const el = event.target as HTMLTextAreaElement
  if (event.key === 'Escape') {
    event.preventDefault()
    finished = true
    emit('cancel')
  } else if (event.key === 'Enter' && event.ctrlKey) {
    event.preventDefault()
    finished = true
    emit('split', segmentId, el.value, el.selectionStart)
  } else if (event.key === 'Enter' && !event.shiftKey && !event.altKey && !event.metaKey) {
    event.preventDefault()
    finished = true
    emit('save', segmentId, el.value)
  }
}

function onEditorBlur(event: FocusEvent, segmentId: number) {
  if (finished) return
  finished = true
  emit('save', segmentId, (event.target as HTMLTextAreaElement).value)
}

interface CellBlock {
  blockId: number
  kind: string
  segments: BookSegment[]
}

/** The cell's segments grouped by block: each block starts on a new line. */
function blocks(segments: BookSegment[]): CellBlock[] {
  const out: CellBlock[] = []
  for (const seg of segments) {
    const last = out[out.length - 1]
    if (last && last.blockId === seg.block_id) last.segments.push(seg)
    else out.push({ blockId: seg.block_id, kind: seg.block_kind, segments: [seg] })
  }
  return out
}

const cells = computed(() =>
  (['source', 'target'] as const).map((side) => ({ side, blocks: blocks(props.bead[side]) })),
)
</script>

<template>
  <div :data-bead-id="bead.id" :data-current="current" :data-side="current ? currentSide : undefined"
    :data-reviewed="bead.reviewed" :data-problem="problem" data-testid="bead-row"
    class="relative grid grid-cols-2 gap-4 px-4 py-2 text-sm border-l-4"
    :class="[bead.reviewed ? 'border-green-500' : problem ? 'border-amber-400' : 'border-transparent', current ? 'outline outline-2 outline-blue-400 -outline-offset-2' : '']">
    <div v-for="cell in cells" :key="cell.side" :data-cell="cell.side"
      class="rounded px-1 cursor-text min-h-[1.5em]"
      :class="[
        cell.blocks.length === 0 ? 'bg-gray-100' : '',
        current && currentSide === cell.side ? 'bg-blue-50' : '',
      ]"
      @click="emit('select', bead.id, cell.side, null)">
      <div v-for="block in cell.blocks" :key="block.blockId" :data-block-kind="block.kind"
        :class="block.kind === 'heading' ? 'font-bold' : ''">
        <template v-for="(seg, i) in block.segments" :key="seg.segment_id">
          <span v-if="i > 0">{{ ' ' }}</span>
          <textarea v-if="editingSegmentId === seg.segment_id" :ref="mountEditor" :value="seg.text" rows="1"
            data-testid="segment-editor"
            class="block w-full resize-none overflow-hidden border border-blue-400 rounded px-1 font-normal"
            @input="grow($event.target as HTMLTextAreaElement)" @click.stop
            @keydown="onEditorKey($event, seg.segment_id)" @blur="onEditorBlur($event, seg.segment_id)" />
          <span v-else :data-segment-id="seg.segment_id" :data-current-segment="currentSegmentId === seg.segment_id"
            :class="currentSegmentId === seg.segment_id ? 'underline decoration-blue-500 decoration-2' : ''"
            @click.stop="emit('select', bead.id, cell.side, seg.segment_id)"
            @dblclick.stop="emit('edit', seg.segment_id)">{{ seg.text }}</span>
        </template>
      </div>
    </div>
    <!-- Absolutely positioned: reviewing a bead removes the badge without changing the row's height. -->
    <span v-if="problem" data-testid="problem-badge"
      class="absolute top-0 right-1 text-xs text-amber-700 pointer-events-none">
      {{ bead.source.length }}:{{ bead.target.length }} · {{ bead.confidence.toFixed(2) }}
    </span>
  </div>
</template>
