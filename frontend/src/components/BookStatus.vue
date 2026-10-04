<script setup lang="ts">
// The bottom bar's status message, injected (PLAN.md, Stage 4 render rule).
import { inject } from 'vue'
import { statusKey } from '@/selection'

const status = inject(statusKey)!
</script>

<template>
  <p data-testid="status" class="absolute left-4 right-[380px] inset-y-0 leading-[25px] truncate [contain:strict]">{{ status }}</p>
</template>
