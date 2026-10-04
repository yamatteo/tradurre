<script setup lang="ts">
// The bottom bar's position, `Bead i of n · Side · sentence k of m`. Its own component, reading the injected
// selection: if `BookView.vue`'s template read it, every move would re-render the whole bead list (Stage 2 scale rule).
import { computed, inject } from 'vue'
import type { Book } from '@/api/client'
import { selectionKey } from '@/selection'

const props = defineProps<{ book: Book }>()

const selection = inject(selectionKey)!
const index = computed(() => new Map(props.book.beads.map((b, i) => [b.id, i])))
const text = computed(() => {
  const id = selection.currentBeadId.value
  const i = id === null ? undefined : index.value.get(id)
  if (i === undefined) return ''
  const side = selection.currentSide.value
  const segments = props.book.beads[i]![side]
  const k = segments.findIndex((s) => s.segment_id === selection.currentSegmentId.value)
  const label = side === 'source' ? 'Source' : 'Target'
  return `Bead ${i + 1} of ${props.book.beads.length} · ${label} · sentence ${k < 0 ? '–' : k + 1} of ${segments.length}`
})
</script>

<template>
  <p data-testid="position" class="absolute right-4 inset-y-0 w-[360px] leading-[25px] text-right font-code text-[11px] [contain:strict]">{{ text }}</p>
</template>
