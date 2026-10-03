<script setup lang="ts">
// One bead as a row (source left, target right). Only the current row gets non-null selection props, so moving
// the selection re-renders two rows, not the whole book (PLAN.md, "Reading and navigation", Scale).
import { computed } from 'vue'
import type { BookBead, BookSegment, Side } from '@/api/client'

const props = defineProps<{
  bead: BookBead
  current: boolean
  currentSide: Side | null
  currentSegmentId: number | null
}>()

const emit = defineEmits<{ select: [beadId: number, side: Side, segmentId: number | null] }>()

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
    :data-reviewed="bead.reviewed" data-testid="bead-row"
    class="grid grid-cols-2 gap-4 px-4 py-2 text-sm border-l-4"
    :class="[bead.reviewed ? 'border-green-500' : 'border-transparent', current ? 'outline outline-2 outline-blue-400 -outline-offset-2' : '']">
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
          <span :data-segment-id="seg.segment_id" :data-current-segment="currentSegmentId === seg.segment_id"
            :class="currentSegmentId === seg.segment_id ? 'underline decoration-blue-500 decoration-2' : ''"
            @click.stop="emit('select', bead.id, cell.side, seg.segment_id)">{{ seg.text }}</span>
        </template>
      </div>
    </div>
  </div>
</template>
