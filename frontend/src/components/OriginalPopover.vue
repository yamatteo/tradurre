<script setup lang="ts">
// The current sentence's original extracted text (SPEC §2: "can always compare or revert"; A2 of the design), shown
// whole: no highlighting of what changed. Its open state is injected, so opening it doesn't re-render the bead list
// (PLAN.md, Stage 4 render rule 1).
import { computed, inject, nextTick, ref, watch } from 'vue'
import type { Book } from '@/api/client'
import { originalKey, selectionKey } from '@/selection'

const props = defineProps<{ book: Book }>()
const emit = defineEmits<{ restore: []; close: [] }>()

const selection = inject(selectionKey)!
const show = inject(originalKey)!

const segment = computed(() => {
  if (!show.value) return null
  const bead = props.book.beads.find((b) => b.id === selection.currentBeadId.value)
  return bead?.[selection.currentSide.value].find((s) => s.segment_id === selection.currentSegmentId.value) ?? null
})
const original = computed(() => segment.value?.original ?? null)

const el = ref<HTMLElement | null>(null)
const position = ref({ top: 0, left: 0 })

/** Under the sentence's span, or above it if it would leave the viewport; kept inside the window's width. */
async function place() {
  if (original.value === null || !segment.value) return
  await nextTick()
  const span = document.querySelector(`[data-segment-id="${segment.value.segment_id}"]`)
  if (!span || !el.value) return
  const rect = span.getBoundingClientRect()
  const height = el.value.offsetHeight
  const below = rect.bottom + 6
  const top = below + height > window.innerHeight ? Math.max(rect.top - 6 - height, 8) : below
  const left = Math.min(Math.max(rect.left, 8), window.innerWidth - 360 - 8)
  position.value = { top, left }
}

watch([original, () => segment.value?.segment_id], place, { immediate: true })
</script>

<template>
  <div v-if="original !== null" ref="el" data-testid="original-popover" role="dialog" aria-label="Original sentence"
    class="fixed z-30 w-[360px] bg-white border border-bar-rule rounded-md shadow-lg font-ui text-[12.5px]"
    :style="{ top: `${position.top}px`, left: `${position.left}px` }">
    <div class="flex items-center justify-between pl-3 pr-1.5 h-8">
      <span class="text-[10.5px] uppercase tracking-wider text-faint">Original</span>
      <button type="button" aria-label="Close" title="Close (Esc)" @click="emit('close')"
        class="w-6 h-6 flex items-center justify-center rounded text-muted hover:bg-hover">
        <svg width="10" height="10" viewBox="0 0 10 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true">
          <path d="M1 1l8 8M9 1l-8 8" />
        </svg>
      </button>
    </div>
    <p v-if="original" data-testid="original-text" class="px-3 font-text text-[15px] leading-[1.45] text-ink">{{ original }}</p>
    <p v-else data-testid="original-text" class="px-3 italic text-muted">The original of this part is empty: it was split after an edit.</p>
    <div class="flex justify-end p-2">
      <button type="button" data-testid="restore-original" :disabled="!original" @click="emit('restore')"
        class="h-7 px-2 rounded text-ink hover:bg-hover disabled:opacity-40 disabled:hover:bg-transparent disabled:cursor-not-allowed">
        Restore original
      </button>
    </div>
  </div>
</template>
