import { test, expect } from '@playwright/test'

const API = '/api/v1'

test.describe('Scroll sync in side-by-side mode', () => {
  let projectId: string

  test.beforeAll(async ({ request }) => {
    // Create a temporary project via the API
    const res = await request.post(`${API}/projects`, {
      data: {
        title: 'E2E Scroll Sync Test',
        source_lang: 'en',
        target_lang: 'it',
      },
    })
    const project = await res.json()
    projectId = project.id

    // Add enough pairs so the content overflows the viewport
    const longText =
      '<p>' + 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. '.repeat(10) + '</p>'
    for (let i = 0; i < 30; i++) {
      await request.post(`${API}/projects/${projectId}/pairs`, {
        data: {
          source_html: longText,
          target_html: longText,
          source_text: 'filler',
          target_text: 'filler',
        },
      })
    }
  })

  test.afterAll(async ({ request }) => {
    if (projectId) {
      await request.delete(`${API}/projects/${projectId}`)
    }
  })

  test('scrolling keeps source and target pairs vertically aligned', async ({ page }) => {
    await page.goto(`/project/${projectId}`)

    // Wait for pairs to render
    await page.waitForSelector('[data-pair-index="10"]', { timeout: 10_000 })

    // Find all scrollable columns (overflow-y-auto elements)
    const scrollables = page.locator('.overflow-y-auto')
    const count = await scrollables.count()

    // In the current broken layout there are 2 independent scrollable columns.
    // In the fixed layout there will be 1 scrollable container with rows.
    // Either way, scroll the first scrollable element.
    const scrollContainer = scrollables.first()

    // Verify the content overflows (is scrollable)
    const isScrollable = await scrollContainer.evaluate(
      (el) => el.scrollHeight > el.clientHeight,
    )
    expect(isScrollable).toBe(true)

    // Scroll down by 800px
    await scrollContainer.evaluate((el) => {
      el.scrollTop = 800
      el.dispatchEvent(new Event('scroll'))
    })
    await page.waitForTimeout(300)

    // Find a pair element that is currently visible near the center of the viewport
    // and verify that both its source and target cells are at the same vertical position.
    //
    // Strategy: pick pair index 15 (should be somewhere in the middle of the content).
    // Get the bounding rects of the source and target content for that pair.
    const alignment = await page.evaluate(() => {
      const pairs = document.querySelectorAll('[data-pair-index="15"]')
      if (pairs.length === 0) return null

      if (pairs.length === 1) {
        // Row-based layout: source and target are children of the same row.
        // The pair is aligned by construction — test passes.
        const row = pairs[0] as HTMLElement
        const cells = row.children
        if (cells.length < 2) return null
        const sourceRect = cells[0]!.getBoundingClientRect()
        const targetRect = cells[1]!.getBoundingClientRect()
        return {
          sourceTop: sourceRect.top,
          targetTop: targetRect.top,
          layout: 'row',
        }
      }

      // Two-column layout: there are two elements with data-pair-index="15",
      // one in each column.
      const sourceRect = pairs[0]!.getBoundingClientRect()
      const targetRect = pairs[1]!.getBoundingClientRect()
      return {
        sourceTop: sourceRect.top,
        targetTop: targetRect.top,
        layout: 'two-column',
      }
    })

    expect(alignment).not.toBeNull()

    // The source and target for the same pair should be at the same vertical position.
    // Allow up to 5px tolerance for sub-pixel rendering differences.
    const diff = Math.abs(alignment!.sourceTop - alignment!.targetTop)
    expect(diff).toBeLessThanOrEqual(5)
  })
})
