<script setup lang="ts">
// The bottom bar's position, `Turn i of n · Side · sentence k of m` (`Bead` at sentence level). Its own component, reading the injected
// selection: if `BookView.vue`'s template read it, every move would re-render the whole bead list (Stage 2 scale rule).
import { computed, inject } from 'vue'
import { unitNoun } from '@/levels'
import { selectionKey } from '@/selection'

const selection = inject(selectionKey)!
const index = computed(() => new Map(selection.units.value.map((u, i) => [u.id, i])))
const text = computed(() => {
  const unit = selection.currentUnit.value
  const i = unit ? index.value.get(unit.id) : undefined
  if (!unit || i === undefined) return ''
  const side = selection.currentSide.value
  const segments = unit[side]
  const k = segments.findIndex((s) => s.segment_id === selection.currentSegmentId.value)
  const label = side === 'source' ? 'Source' : 'Target'
  const noun = unitNoun(selection.level.value)
  return `${noun[0]!.toUpperCase()}${noun.slice(1)} ${i + 1} of ${selection.units.value.length} · ${label} · sentence ${k < 0 ? '–' : k + 1} of ${segments.length}`
})
</script>

<template>
  <p data-testid="position" class="absolute right-4 inset-y-0 w-[360px] leading-[25px] text-right font-code text-[11px] [contain:strict]">{{ text }}</p>
</template>
