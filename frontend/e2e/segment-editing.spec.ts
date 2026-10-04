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

async function importBook(request: APIRequestContext, title: string, gap = true) {
  const res = await request.post('/api/v2/books', {
    multipart: {
      source: { name: 'fr.txt', mimeType: 'text/plain', buffer: Buffer.from(SOURCE) },
      target: { name: 'it.txt', mimeType: 'text/plain', buffer: Buffer.from(TARGET) },
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

function editor(page: Page) {
  return page.getByTestId('segment-editor')
}

test('Enter opens the editor and Enter saves', async ({ page, request }) => {
  const { id } = await importBook(request, 'Edit')
  await open(page, id)
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Enter')
  await expect(editor(page)).toBeFocused()
  await expect(editor(page)).toHaveValue('Marie arriva.')
  await page.keyboard.press('Backspace')
  await page.keyboard.type(' tard.')
  await page.keyboard.press('Enter')
  await expect(editor(page)).toHaveCount(0)
  await expect.poll(() => rows(page)).toEqual([
    ORIGINAL[0], [['Marie arriva tard.'], ['Marie arrivò.']], ...ORIGINAL.slice(2),
  ])
  await expect(page.locator('[data-current-segment="true"]')).toHaveText('Marie arriva tard.')
})

test('Escape cancels', async ({ page, request }) => {
  const { id } = await importBook(request, 'Cancel', false)  // as imported, so there is nothing to undo
  await open(page, id)
  await page.keyboard.press('Enter')
  await page.keyboard.type(' changed')
  await page.keyboard.press('Escape')
  await expect(editor(page)).toHaveCount(0)
  await expect.poll(() => rows(page)).toEqual([
    ...ORIGINAL.slice(0, 2),
    [['Il pleuvait.'], ['Paul partì.']],
    [['Paul partit.', 'Il ne dit rien.'], ['Non disse niente.']],
  ])
  await expect(page.getByTestId('undo')).toBeDisabled()
})

test('clicking another row saves', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Blur')
  await open(page, id)
  await page.keyboard.press('Enter')
  await page.keyboard.type(' I')
  await page.getByText('Il pleuvait.').click()
  await expect(editor(page)).toHaveCount(0)
  await expect.poll(() => rows(page)).toEqual([[['Chapitre un I'], ['Capitolo uno']], ...ORIGINAL.slice(1)])
  // The click still selected the other row.
  await expect(current(page)).toHaveAttribute('data-bead-id', String(book.beads[2].id))
})

test('Ctrl+Enter splits at the caret', async ({ page, request }) => {
  const { id } = await importBook(request, 'Split')
  await open(page, id)
  await page.keyboard.press('Enter')
  for (let k = 0; k < 3; k++) await page.keyboard.press('ArrowLeft')  // "Chapitre |un"
  await page.keyboard.press('Control+Enter')
  await expect.poll(() => rows(page)).toEqual([[['Chapitre', 'un'], ['Capitolo uno']], ...ORIGINAL.slice(1)])
  await expect(page.locator('[data-current-segment="true"]')).toHaveText('Chapitre')
  await page.keyboard.press('Control+z')
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
})

test('Ctrl+Enter after a change saves, then splits', async ({ page, request }) => {
  const { id } = await importBook(request, 'Edit and split')
  await open(page, id)
  await page.keyboard.press('Enter')
  await page.keyboard.type(' premier')
  for (let k = 0; k < 8; k++) await page.keyboard.press('ArrowLeft')  // "Chapitre un| premier"
  await page.keyboard.press('Control+Enter')
  await expect.poll(() => rows(page)).toEqual([[['Chapitre un', 'premier'], ['Capitolo uno']], ...ORIGINAL.slice(1)])
  await page.keyboard.press('Control+z')
  await expect.poll(() => rows(page)).toEqual([[['Chapitre un premier'], ['Capitolo uno']], ...ORIGINAL.slice(1)])
})

test('j joins with the next segment', async ({ page, request }) => {
  const { id } = await importBook(request, 'Join')
  await open(page, id)
  for (let k = 0; k < 3; k++) await page.keyboard.press('ArrowDown')  // D1
  await page.keyboard.press('j')
  await expect.poll(() => rows(page)).toEqual([
    ...ORIGINAL.slice(0, 3),
    [['Paul partit. Il ne dit rien.'], ['Paul partì.', 'Non disse niente.']],
  ])
  await expect(page.locator('[data-current-segment="true"]')).toHaveText('Paul partit. Il ne dit rien.')
})

test('an empty text shows the server message', async ({ page, request }) => {
  const { id } = await importBook(request, 'Empty')
  await open(page, id)
  await page.keyboard.press('Enter')
  await page.keyboard.press('Control+a')
  await page.keyboard.press('Delete')
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('status')).toHaveText("A segment can't be empty; join it with its neighbour instead")
  await expect(editor(page)).toHaveCount(0)
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
})

test('a double-click opens the editor', async ({ page, request }) => {
  const { id } = await importBook(request, 'Double-click')
  await open(page, id)
  await page.getByText('Marie arrivò.').dblclick()
  await expect(editor(page)).toBeFocused()
  await expect(editor(page)).toHaveValue('Marie arrivò.')
  await expect(current(page)).toHaveAttribute('data-side', 'target')
})
