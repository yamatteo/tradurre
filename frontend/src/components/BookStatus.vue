<script setup lang="ts">
// The bottom bar's status message, or the selected run's summary while there is one; both injected (PLAN.md,
// Stage 4 render rule).
import { computed, inject } from 'vue'
import { selectionKey, statusKey } from '@/selection'

const status = inject(statusKey)!
const selection = inject(selectionKey)!
const text = computed(() => {
  const run = selection.runBounds.value
  return run ? `${run.size} beads selected (${run.first}–${run.last}). R marks them all reviewed.` : status.value
})
</script>

<template>
  <p data-testid="status" class="absolute left-4 right-[380px] inset-y-0 leading-[25px] truncate [contain:strict]">{{ text }}</p>
</template>
