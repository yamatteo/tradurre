import { type Ref, watch, onMounted, onBeforeUnmount } from 'vue'

export function useScrollSync(
  colA: Ref<HTMLElement | undefined>,
  colB: Ref<HTMLElement | undefined>,
  enabled: Ref<boolean>,
) {
  let syncing = false

  function syncScroll(source: HTMLElement, target: HTMLElement) {
    if (syncing) return
    syncing = true

    // Find the visible pair element in the source column
    const sourceRect = source.getBoundingClientRect()
    const midY = sourceRect.top + sourceRect.height / 2

    const pairEls = source.querySelectorAll<HTMLElement>('[data-pair-index]')
    let activePair: HTMLElement | null = null
    for (const el of pairEls) {
      const r = el.getBoundingClientRect()
      if (r.top <= midY && r.bottom >= midY) {
        activePair = el
        break
      }
      // If we've scrolled past everything, use the last one
      if (r.bottom <= midY) activePair = el
    }

    if (activePair) {
      const index = activePair.dataset.pairIndex
      const targetPair = target.querySelector<HTMLElement>(
        `[data-pair-index="${index}"]`,
      )
      if (targetPair) {
        // Compute ratio within the active pair
        const sourceR = activePair.getBoundingClientRect()
        const ratio = (midY - sourceR.top) / Math.max(sourceR.height, 1)

        const targetR = targetPair.getBoundingClientRect()
        const targetMid = target.getBoundingClientRect().top + target.clientHeight / 2
        const desiredScrollTop =
          target.scrollTop + (targetR.top + ratio * targetR.height - targetMid)

        target.scrollTop = Math.max(0, desiredScrollTop)
      }
    }

    requestAnimationFrame(() => {
      syncing = false
    })
  }

  function onScrollA() {
    if (!enabled.value || !colA.value || !colB.value) return
    syncScroll(colA.value, colB.value)
  }

  function onScrollB() {
    if (!enabled.value || !colA.value || !colB.value) return
    syncScroll(colB.value, colA.value)
  }

  function attach() {
    colA.value?.addEventListener('scroll', onScrollA, { passive: true })
    colB.value?.addEventListener('scroll', onScrollB, { passive: true })
  }

  function detach() {
    colA.value?.removeEventListener('scroll', onScrollA)
    colB.value?.removeEventListener('scroll', onScrollB)
  }

  watch(enabled, (val) => {
    if (val) attach()
    else detach()
  })

  onMounted(() => {
    if (enabled.value) attach()
  })

  onBeforeUnmount(detach)
}
