import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// The timing tests: they measure the app, so nothing else may run against the shared e2e backend meanwhile. The
// `scale` project (playwright.config.ts) runs this file after every other test, and `serial` keeps its tests in one
// worker, one after another.
test.describe.configure({ mode: 'serial' })

async function importBook(request: APIRequestContext, title: string, source: string, target: string) {
  const res = await request.post('/api/v2/books', {
    multipart: {
      source: { name: 'fr.txt', mimeType: 'text/plain', buffer: Buffer.from(source) },
      target: { name: 'it.txt', mimeType: 'text/plain', buffer: Buffer.from(target) },
      title,
    },
  })
  expect(res.status()).toBe(201)
  const id: string = (await res.json()).id
  const book = await (await request.get(`/api/v2/books/${id}`)).json()
  return { id, book }
}

function current(page: Page) {
  return page.locator('[data-testid="bead-row"][data-current="true"]')
}

test('a 10,000-bead book loads and navigates within the limits', async ({ page, request }) => {
  test.setTimeout(120_000)
  const n = 10_000
  const source = Array.from({ length: n }, (_, k) => `Phrase numéro ${k}.`).join('\n\n')
  const target = Array.from({ length: n }, (_, k) => `Frase numero ${k}.`).join('\n\n')
  const { id, book } = await importBook(request, 'Big', source, target)
  expect(book.beads.length).toBe(n)

  const start = Date.now()
  await page.goto(`/book/${id}`)
  await expect(page.locator(`[data-bead-id="${book.beads[n - 1].id}"]`)).toBeAttached({ timeout: 60_000 })
  const load = Date.now() - start

  await expect(current(page)).toHaveAttribute('data-bead-id', String(book.beads[0].id))
  const navStart = Date.now()
  for (let k = 1; k <= 20; k++) {
    await page.keyboard.press('ArrowDown')
    await expect(current(page)).toHaveAttribute('data-bead-id', String(book.beads[k].id))
  }
  const nav = Date.now() - navStart

  console.log(`10,000-bead book: load ${load} ms, 20 ArrowDown ${nav} ms`)
  test.info().annotations.push({ type: 'timing', description: `load ${load} ms, 20 ArrowDown ${nav} ms` })
  expect(load).toBeLessThan(5_000)
  expect(nav).toBeLessThan(2_000)
})

test('r on a 10,000-bead book is fast', async ({ page, request }) => {
  test.setTimeout(120_000)
  const n = 10_000
  const source = Array.from({ length: n }, (_, k) => `Phrase numéro ${k}.`).join('\n\n')
  const target = Array.from({ length: n }, (_, k) => `Frase numero ${k}.`).join('\n\n')
  const { id, book } = await importBook(request, 'Big', source, target)
  await page.goto(`/book/${id}`)
  await expect(page.locator(`[data-bead-id="${book.beads[n - 1].id}"]`)).toBeAttached({ timeout: 60_000 })
  for (let k = 1; k <= 20; k++) await page.keyboard.press('ArrowDown')
  const row = page.locator(`[data-bead-id="${book.beads[20].id}"]`)
  await expect(row).toHaveAttribute('data-current', 'true')

  const start = Date.now()
  await page.keyboard.press('r')
  await expect(row).toHaveAttribute('data-reviewed', 'true')
  const elapsed = Date.now() - start

  console.log(`10,000-bead book: r to reviewed border ${elapsed} ms`)
  test.info().annotations.push({ type: 'timing', description: `r to reviewed border ${elapsed} ms` })
  expect(elapsed).toBeLessThan(1_500)
})

test('a 5,000-bead book: load, corrections and scrolling', async ({ page, request }) => {
  test.setTimeout(120_000)
  const n = 5_000
  const source = Array.from({ length: n }, (_, k) => `Phrase numéro ${k}.`).join('\n\n')
  const target = Array.from({ length: n }, (_, k) => `Frase numero ${k}.`).join('\n\n')
  const { id, book } = await importBook(request, 'Big 5k', source, target)
  expect(book.beads.length).toBe(n)
  const rows = page.getByTestId('bead-row')

  const start = Date.now()
  await page.goto(`/book/${id}`)
  await expect(page.locator(`[data-bead-id="${book.beads[n - 1].id}"]`)).toBeAttached({ timeout: 60_000 })
  const load = Date.now() - start

  for (let k = 1; k <= 20; k++) await page.keyboard.press('ArrowDown')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(book.beads[20].id))
  const nextSource = page.locator(`[data-bead-id="${book.beads[21].id}"] [data-cell="source"] [data-segment-id]`)
  await expect(nextSource).toHaveCount(1)

  /** Milliseconds from the key press to `done` resolving. */
  async function timed(key: string, done: () => Promise<void>) {
    const t = Date.now()
    await page.keyboard.press(key)
    await done()
    return Date.now() - t
  }
  const move = await timed('Alt+ArrowDown', () => expect(nextSource).toHaveCount(2))
  const undoMove = await timed('Control+z', () => expect(nextSource).toHaveCount(1))
  const merge = await timed('m', () => expect(rows).toHaveCount(n - 1))
  const undoMerge = await timed('Control+z', () => expect(rows).toHaveCount(n))
  // The first correction may pay a warm-up: a second move and undo tell it from the move's own cost.
  const moveAgain = await timed('Alt+ArrowDown', () => expect(nextSource).toHaveCount(2))
  const undoMoveAgain = await timed('Control+z', () => expect(nextSource).toHaveCount(1))

  await page.evaluate(() => {
    const w = window as unknown as { longTasks: number[] }
    w.longTasks = []
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) w.longTasks.push(entry.duration)
    }).observe({ type: 'longtask' })
  })
  await rows.nth(25).hover()
  for (let k = 0; k < 20; k++) {
    await page.mouse.wheel(0, 1500)
    await page.waitForTimeout(50)
  }
  await page.waitForTimeout(200)
  const longTasks: number[] = await page.evaluate(() => (window as unknown as { longTasks: number[] }).longTasks)
  const longest = Math.max(0, ...longTasks)

  const timing = `load ${load} ms, Alt+↓ ${move} ms, Ctrl+Z ${undoMove} ms, m ${merge} ms, Ctrl+Z ${undoMerge} ms, `
    + `Alt+↓ again ${moveAgain} ms, Ctrl+Z again ${undoMoveAgain} ms, `
    + `scroll: ${longTasks.length} long tasks, longest ${Math.round(longest)} ms`
  console.log(`5,000-bead book: ${timing}`)
  test.info().annotations.push({ type: 'timing', description: timing })
  expect(load).toBeLessThan(3_000)
  for (const t of [move, undoMove, merge, undoMerge, moveAgain, undoMoveAgain]) expect(t).toBeLessThan(500)
  expect(longest).toBeLessThan(100)
})
