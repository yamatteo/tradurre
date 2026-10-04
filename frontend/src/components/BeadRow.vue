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
const inRun = computed(() => selection.inRun[props.bead.id] === true)

const emit = defineEmits<{
  select: [beadId: number, side: Side, segmentId: number | null, extend: boolean]
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
  <!-- A1's grid: gutter mark | source | target | meta. Every state changes colours only, never the row's height. -->
  <div :data-bead-id="bead.id" :data-current="current" :data-side="current ? currentSide : undefined"
    :data-reviewed="bead.reviewed" :data-problem="problem" :data-in-run="inRun" data-testid="bead-row"
    class="relative grid grid-cols-[40px_minmax(0,1fr)_minmax(0,1fr)_96px] border-b border-row-rule scroll-mt-7"
    :class="[current ? 'outline-[1.5px] outline-accent -outline-offset-[1.5px]' : '', inRun ? 'bg-run' : '']">
    <!-- The 3 px left border is always there, only recoloured for a run: paint-only (render rule 2). -->
    <div class="flex justify-center pt-[11px] border-l-[3px]" :class="inRun ? 'border-accent' : 'border-transparent'">
      <svg v-if="bead.reviewed" aria-label="Reviewed" role="img" width="14" height="14" viewBox="0 0 14 14"
        class="text-reviewed" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
        stroke-linejoin="round"><path d="M2.5 7.5l3 3 6-7" /></svg>
      <svg v-else-if="problem" aria-label="Problem" role="img" width="12" height="12" viewBox="0 0 12 12"
        class="text-problem-mark mt-px" fill="currentColor"><path d="M6 0.5L11.5 6 6 11.5 0.5 6z" /></svg>
    </div>
    <div v-for="cell in cells" :key="cell.side" :data-cell="cell.side"
      class="cursor-text px-4 pt-[7px] pb-2 font-text text-[15px] leading-[1.45] text-ink"
      :class="[
        cell.side === 'target' ? 'border-l border-row-rule' : '',
        current && currentSide === cell.side ? 'bg-current-side' : '',
      ]"
      @click="emit('select', bead.id, cell.side, null, $event.shiftKey)">
      <span v-if="cell.blocks.length === 0" class="font-ui text-[12.5px] italic text-absent">Not in this edition</span>
      <div v-for="block in cell.blocks" :key="block.blockId" :data-block-kind="block.kind"
        :class="block.kind === 'heading' ? 'font-semibold' : ''">
        <template v-for="(seg, i) in block.segments" :key="seg.segment_id">
          <span v-if="i > 0" aria-hidden="true" class="inline-block w-px h-[0.9em] mx-2 align-[-0.1em] bg-separator" />
          <textarea v-if="editingSegmentId === seg.segment_id" :ref="mountEditor" :value="seg.text" rows="1"
            data-testid="segment-editor"
            class="block w-full resize-none overflow-hidden border border-accent rounded px-1 bg-white font-text text-[15px] leading-[1.45] font-normal"
            @input="grow($event.target as HTMLTextAreaElement)" @click.stop
            @keydown="onEditorKey($event, seg.segment_id)" @blur="onEditorBlur($event, seg.segment_id)" />
          <!-- The bottom border is always there, only recoloured: so selecting a segment repaints it without a layout
               (an inline gaining a background or a border is laid out again, and that walks all 10,000 rows). -->
          <span v-else :data-segment-id="seg.segment_id" :data-current-segment="currentSegmentId === seg.segment_id"
            class="border-b-2"
            :class="currentSegmentId === seg.segment_id ? 'bg-current-segment border-accent' : 'border-transparent'"
            @click.stop="emit('select', bead.id, cell.side, seg.segment_id, $event.shiftKey)"
            @dblclick.stop="emit('edit', seg.segment_id)">{{ seg.text }}</span>
        </template>
      </div>
    </div>
    <!-- Always rendered (so it never shifts anything), transparent unless current or a problem. -->
    <div :data-testid="problem ? 'problem-badge' : undefined"
      class="pt-[10px] pr-3 text-right font-code text-[11px] whitespace-nowrap"
      :class="problem ? 'text-problem font-medium' : current ? 'text-muted' : 'text-transparent'">
      {{ bead.source.length }}:{{ bead.target.length }} · {{ bead.confidence.toFixed(2) }}
    </div>
  </div>
</template>
