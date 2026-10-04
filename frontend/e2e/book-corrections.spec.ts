import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Beads after import and `restoreGap`: A (Chapitre un | Capitolo uno), B (Marie arriva. | Marie arrivò.),
// C (Il pleuvait. | ), D (Paul partit. Il ne dit rien. | Paul partì. Non disse niente.) as two beads D1, D2.
const SOURCE = 'Chapitre un\n\nMarie arriva.\n\nIl pleuvait.\n\nPaul partit. Il ne dit rien.'
const TARGET = 'Capitolo uno\n\nMarie arrivò.\n\nPaul partì. Non disse niente.'

const ORIGINAL = [
  [['Chapitre un'], ['Capitolo uno']],
  [['Marie arriva.'], ['Marie arrivò.']],
  [['Il pleuvait.'], []],
  [['Paul partit.'], ['Paul partì.']],
  [['Il ne dit rien.'], ['Non disse niente.']],
]
const B_MERGED = [
  ORIGINAL[0],
  [['Marie arriva.', 'Il pleuvait.'], ['Marie arrivò.']],
  ORIGINAL[3],
  ORIGINAL[4],
]

async function importBook(
  request: APIRequestContext, title: string, source = SOURCE, target = TARGET,
  gap = source === SOURCE && target === TARGET,
) {
  const res = await request.post('/api/v2/books', {
    multipart: {
      source: { name: 'fr.txt', mimeType: 'text/plain', buffer: Buffer.from(source) },
      target: { name: 'it.txt', mimeType: 'text/plain', buffer: Buffer.from(target) },
      title,
    },
  })
  expect(res.status()).toBe(201)
  const id: string = (await res.json()).id
  if (gap) await restoreGap(request, id)
  const book = await (await request.get(`/api/v2/books/${id}`)).json()
  return { id, book }
}

/** The two corrections that turn the imported layout into the one above: on so little text the length aligner pairs
 * "Il pleuvait." with "Paul partì." and puts both remaining source sentences in the last bead. */
async function restoreGap(request: APIRequestContext, id: string) {
  let book = await (await request.get(`/api/v2/books/${id}`)).json()
  const moved = await request.post(`/api/v2/books/${id}/beads/${book.beads[2].id}/move`, {
    data: { side: 'target', to: 'next' },
  })
  expect(moved.status()).toBe(200)
  book = await moved.json()
  const last = book.beads[3]
  const split = await request.post(`/api/v2/books/${id}/beads/${last.id}/split`, {
    data: { source_at: last.source[1].segment_id, target_at: last.target[1].segment_id },
  })
  expect(split.status()).toBe(200)
}

function current(page: Page) {
  return page.locator('[data-testid="bead-row"][data-current="true"]')
}

/** Each bead row's segment texts, [source, target]. */
function rows(page: Page) {
  return page.getByTestId('bead-row').evaluateAll((els) =>
    els.map((row) =>
      ['source', 'target'].map((side) =>
        [...row.querySelectorAll(`[data-cell="${side}"] [data-segment-id]`)].map((s) => s.textContent),
      ),
    ),
  )
}

async function open(page: Page, id: string) {
  await page.goto(`/book/${id}`)
  await expect(current(page)).toBeVisible()
}

test('Alt+↓ and Alt+↑ move a segment to the next and previous bead', async ({ page, request }) => {
  const { id } = await importBook(request, 'Move')
  await open(page, id)
  await page.keyboard.press('ArrowDown')  // B, source
  await page.keyboard.press('Alt+ArrowDown')
  await expect.poll(() => rows(page)).toEqual([
    ORIGINAL[0],
    [[], ['Marie arrivò.']],
    [['Marie arriva.', 'Il pleuvait.'], []],
    ORIGINAL[3],
    ORIGINAL[4],
  ])
  await page.keyboard.press('ArrowDown')  // C
  await page.keyboard.press('Alt+ArrowUp')
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
})

test('m merges with the next bead and s splits it back', async ({ page, request }) => {
  const { id } = await importBook(request, 'Merge')
  await open(page, id)
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('m')
  await expect.poll(() => rows(page)).toEqual(B_MERGED)
  await page.keyboard.press('Tab')
  await expect(page.locator('[data-current-segment="true"]')).toHaveText('Il pleuvait.')
  await page.keyboard.press('s')
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
  // The current bead is the new one, still on the segment split at.
  await expect(current(page)).toHaveAttribute('data-bead-id', await page.getByTestId('bead-row').nth(2).getAttribute('data-bead-id') ?? '')
  await expect(page.locator('[data-current-segment="true"]')).toHaveText('Il pleuvait.')
})

test('r toggles the reviewed mark', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Reviewed')
  await open(page, id)
  const row = page.locator(`[data-bead-id="${book.beads[0].id}"]`)
  await page.keyboard.press('r')
  await expect(row).toHaveAttribute('data-reviewed', 'true')
  await expect(page.getByTestId('book-progress')).toHaveText('reviewed 1 / 5')
  await page.keyboard.press('r')
  await expect(row).toHaveAttribute('data-reviewed', 'false')
  await expect(page.getByTestId('book-progress')).toHaveText('reviewed 0 / 5')
})

test('x excludes a block and Include brings it back', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Exclude')
  await open(page, id)
  await page.getByText('Il pleuvait.').click()
  await page.keyboard.press('x')
  await expect(page.getByTestId('bead-row')).toHaveCount(4)
  // C is gone: the current bead is the one now at its index (D1).
  await expect(current(page)).toHaveAttribute('data-bead-id', String(book.beads[3].id))

  await page.getByTestId('show-excluded').check()
  // The checkbox has focus, and ↓ still moves the current bead.
  await page.keyboard.press('ArrowDown')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(book.beads[4].id))

  await page.getByTestId('include').click()
  await expect(page.getByTestId('excluded-row')).toHaveCount(0)
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
})

test('a refused correction shows the server message', async ({ page, request }) => {
  const { id } = await importBook(request, 'Refused')
  await open(page, id)
  for (let k = 0; k < 4; k++) await page.keyboard.press('ArrowDown')
  await page.keyboard.press('m')
  await expect(page.getByTestId('status')).toHaveText('There is no next bead to merge with')
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
})

test('undo and redo with the keyboard and the header', async ({ page, request }) => {
  // The import as it is (no `restoreGap`), so there is nothing to undo at first.
  const imported = [
    ORIGINAL[0],
    ORIGINAL[1],
    [['Il pleuvait.'], ['Paul partì.']],
    [['Paul partit.', 'Il ne dit rien.'], ['Non disse niente.']],
  ]
  const merged = [
    ORIGINAL[0],
    [['Marie arriva.', 'Il pleuvait.'], ['Marie arrivò.', 'Paul partì.']],
    imported[3],
  ]
  const { id } = await importBook(request, 'Undo', SOURCE, TARGET, false)
  await open(page, id)
  await expect.poll(() => rows(page)).toEqual(imported)
  await expect(page.getByTestId('undo')).toBeDisabled()
  await expect(page.getByTestId('redo')).toBeDisabled()
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('m')
  await expect.poll(() => rows(page)).toEqual(merged)
  await expect(page.getByTestId('undo')).toBeEnabled()

  await page.keyboard.press('Control+z')
  await expect.poll(() => rows(page)).toEqual(imported)
  await page.keyboard.press('Control+y')
  await expect.poll(() => rows(page)).toEqual(merged)
  await page.keyboard.press('Control+z')
  await expect.poll(() => rows(page)).toEqual(imported)
  await page.keyboard.press('Control+Shift+z')
  await expect.poll(() => rows(page)).toEqual(merged)
  await page.getByTestId('undo').click()
  await expect.poll(() => rows(page)).toEqual(imported)
})

test('a header button does the same as its key', async ({ page, request }) => {
  const { id } = await importBook(request, 'Button')
  await open(page, id)
  await page.getByText('Marie arriva.').click()
  await page.getByTestId('bead-actions').locator('[data-action="merge"]').click()
  await expect.poll(() => rows(page)).toEqual(B_MERGED)
})

test('selecting a row moves no other row', async ({ page, request }) => {
  const { id } = await importBook(request, 'Layout')
  await open(page, id)  // A is current
  const below = page.getByTestId('bead-row').nth(2)
  const before = (await below.boundingBox())!.y
  await page.getByText('Marie arriva.').click()  // B, the row above it
  await expect(page.getByTestId('bead-row').nth(1)).toHaveAttribute('data-current', 'true')
  expect((await below.boundingBox())!.y).toBe(before)
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
  await expect(row).toHaveClass(/border-green-500/)
  const elapsed = Date.now() - start

  console.log(`10,000-bead book: r to reviewed border ${elapsed} ms`)
  test.info().annotations.push({ type: 'timing', description: `r to reviewed border ${elapsed} ms` })
  expect(elapsed).toBeLessThan(1_500)
})
