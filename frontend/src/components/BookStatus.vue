<script setup lang="ts">
// The bottom bar's status message, or the selected run's summary while there is one and no message; both injected
// (PLAN.md, Stage 4 render rule). The latest wins: `BookView.vue` clears the message when the run changes.
import { computed, inject } from 'vue'
import { selectionKey, statusKey } from '@/selection'

const status = inject(statusKey)!
const selection = inject(selectionKey)!
const text = computed(() => {
  const run = selection.runBounds.value
  if (!run || status.value) return status.value
  // The same rule as `r` (and the button in BeadActions.vue): mark all if any is unreviewed, else clear all.
  const marks = selection.book.value?.beads.slice(run.first - 1, run.last).some((b) => !b.reviewed) ?? true
  return `${run.size} beads selected (${run.first}–${run.last}). R ${marks ? 'marks them all reviewed' : 'clears them all'}.`
})
</script>

<template>
  <p data-testid="status" class="absolute left-4 right-[380px] inset-y-0 leading-[25px] truncate [contain:strict]">{{ text }}</p>
</template>
