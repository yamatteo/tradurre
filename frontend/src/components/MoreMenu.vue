<script setup lang="ts">
// The second bar's "More" menu (A1): the rare commands, none with a key. Its own component reading the injected
// selection, so moving while it is open re-renders the menu and not the book view's bead list (PLAN.md, Stage 4
// render rule 1). The open state belongs to BookView.vue, for Esc and for closing the other popovers.
import { computed, inject } from 'vue'
import { booksApi } from '@/api/client'
import { selectionKey } from '@/selection'

defineProps<{ open: boolean; disabled: boolean }>()
const emit = defineEmits<{
  toggle: []
  bulk: [action: 'exclude' | 'include', to: 'start' | 'end']
  restore: []
  realign: []
}>()

const selection = inject(selectionKey)!
const hasBead = computed(() => selection.currentBeadId.value !== null)
/** Whether the current sentence has an original to restore (edited, and its original not empty). */
const canRestore = computed(() => {
  const bead = selection.book.value?.beads.find((b) => b.id === selection.currentBeadId.value)
  const segment = bead?.[selection.currentSide.value].find((s) => s.segment_id === selection.currentSegmentId.value)
  return !!segment?.original
})

const BULK = [
  { action: 'exclude', to: 'start', label: 'Exclude from the start up to here', testid: 'exclude-to-start' },
  { action: 'include', to: 'start', label: 'Include from the start up to here', testid: 'include-to-start' },
  { action: 'exclude', to: 'end', label: 'Exclude from here to the end', testid: 'exclude-to-end' },
  { action: 'include', to: 'end', label: 'Include from here to the end', testid: 'include-to-end' },
] as const

const EXPORTS = [
  { side: 'source', format: 'txt', label: 'Source text (.txt)' },
  { side: 'source', format: 'docx', label: 'Source text (.docx)' },
  { side: 'target', format: 'txt', label: 'Target text (.txt)' },
  { side: 'target', format: 'docx', label: 'Target text (.docx)' },
] as const
</script>

<template>
  <div class="shrink-0 relative">
    <button type="button" data-testid="more" :aria-expanded="open" title="More commands"
      :disabled="disabled" @click="emit('toggle')"
      class="h-7 px-2 flex items-center gap-1 rounded text-ink hover:bg-hover disabled:opacity-40 disabled:hover:bg-transparent disabled:cursor-not-allowed"
      :class="open ? 'bg-hover' : ''">
      More
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 3.5L5 6.5 8 3.5" /></svg>
    </button>
    <div v-if="open" data-testid="more-menu" role="menu"
      class="absolute left-0 top-full mt-1.5 z-30 w-[310px] py-1.5 bg-white border border-bar-rule rounded-md shadow-lg">
      <p class="px-3 pb-1 text-[10.5px] uppercase tracking-wider text-faint">Exclude or include in bulk</p>
      <button v-for="item in BULK" :key="item.testid" type="button" role="menuitem" :data-testid="item.testid"
        :disabled="!hasBead" @click="emit('bulk', item.action, item.to)"
        class="w-full h-[30px] px-3 flex items-center text-left text-ink hover:bg-hover disabled:opacity-40">
        {{ item.label }}
      </button>
      <p class="px-3 pt-2 pb-1 text-[10.5px] uppercase tracking-wider text-faint">Text</p>
      <button type="button" role="menuitem" data-testid="restore-original-more" :disabled="!canRestore"
        @click="emit('restore')"
        class="w-full h-[30px] px-3 flex items-center text-left text-ink hover:bg-hover disabled:opacity-40">
        Restore the original sentence
      </button>
      <p class="px-3 pt-2 pb-1 text-[10.5px] uppercase tracking-wider text-faint">Alignment</p>
      <button type="button" role="menuitem" data-testid="realign" :disabled="!hasBead" @click="emit('realign')"
        class="w-full h-[30px] px-3 flex items-center text-left text-ink hover:bg-hover disabled:opacity-40">
        Re-align the selection
      </button>
      <p class="px-3 pt-2 pb-1 text-[10.5px] uppercase tracking-wider text-faint">Export</p>
      <a v-for="item in EXPORTS" :key="`${item.side}-${item.format}`" role="menuitem"
        :data-testid="`export-${item.side}-${item.format}`" :href="booksApi.editionUrl(selection.book.value?.id ?? '', item.side, item.format)" download
        @click="emit('toggle')"
        class="w-full h-[30px] px-3 flex items-center text-left text-ink hover:bg-hover">
        {{ item.label }}
      </a>
      <a role="menuitem" data-testid="export-bundle" :href="booksApi.bundleUrl(selection.book.value?.id ?? '')" download
        @click="emit('toggle')"
        class="w-full h-[30px] px-3 flex items-center text-left text-ink hover:bg-hover">
        Project bundle (.zip)
      </a>
    </div>
  </div>
</template>
