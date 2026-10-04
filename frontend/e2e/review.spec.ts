import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// The pair of tests/test_books_api.py. Imported beads: B1 (Marie arriva. | Marie arrivò.) 1:1,
// B2 (Il pleuvait. | Paul partì.) 1:1, B3 (Paul partit. Il ne dit rien. | Non disse niente.) 2:1 below 0.5.
const SOURCE = 'Marie arriva.\n\nIl pleuvait.\n\nPaul partit. Il ne dit rien.'
const TARGET = 'Marie arrivò.\n\nPaul partì. Non disse niente.'

async function importBook(request: APIRequestContext, title: string) {
  const res = await request.post('/api/v2/books', {
    multipart: {
      source: { name: 'fr.txt', mimeType: 'text/plain', buffer: Buffer.from(SOURCE) },
      target: { name: 'it.txt', mimeType: 'text/plain', buffer: Buffer.from(TARGET) },
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

function row(page: Page, beadId: number) {
  return page.locator(`[data-testid="bead-row"][data-bead-id="${beadId}"]`)
}

async function open(page: Page, id: string) {
  await page.goto(`/book/${id}`)
  await expect(current(page)).toBeVisible()
}

test('a low-confidence bead is a problem, with a badge and a count', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Problems')
  const [b1, b2, b3] = book.beads
  expect(b3.confidence).toBeLessThan(0.5)
  await open(page, id)
  await expect(row(page, b3.id)).toHaveAttribute('data-problem', 'true')
  await expect(row(page, b3.id).getByTestId('problem-badge')).toHaveText(/^\s*2:1 · 0\.\d\d\s*$/)
  for (const b of [b1, b2]) {
    await expect(row(page, b.id)).toHaveAttribute('data-problem', 'false')
    await expect(row(page, b.id).getByTestId('problem-badge')).toHaveCount(0)
  }
  await expect(page.getByTestId('problem-count')).toHaveText('1 problem')
})

test('p and P jump to the problem bead and wrap around', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Problem keys')
  const [b1, , b3] = book.beads
  await open(page, id)
  await expect(current(page)).toHaveAttribute('data-bead-id', String(b1.id))
  await page.keyboard.press('p')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(b3.id))
  await page.keyboard.press('p')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(b3.id))
  await page.keyboard.press('ArrowUp')
  await page.keyboard.press('ArrowUp')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(b1.id))
  await page.keyboard.press('Shift+P')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(b3.id))
  await page.keyboard.press('Shift+P')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(b3.id))
  await page.keyboard.press('ArrowUp')
  await page.getByTestId('next-problem').click()
  await expect(current(page)).toHaveAttribute('data-bead-id', String(b3.id))
})

test('reviewing the problem bead clears it without changing the row height', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Problem reviewed')
  const b3 = book.beads[2]
  await open(page, id)
  await page.keyboard.press('p')
  const before = (await row(page, b3.id).boundingBox())!.height
  await page.keyboard.press('r')
  await expect(row(page, b3.id)).toHaveAttribute('data-reviewed', 'true')
  await expect(row(page, b3.id).getByTestId('problem-badge')).toHaveCount(0)
  await expect(page.getByTestId('problem-count')).toHaveText('0 problems')
  expect((await row(page, b3.id).boundingBox())!.height).toBe(before)
  await page.keyboard.press('p')
  await expect(page.getByTestId('status')).toHaveText('No problems left')
})

test('Highlight multi-segment counts beads with more than one segment on a side', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Problem multi')
  await open(page, id)
  await page.keyboard.press('p')
  await page.keyboard.press('r')
  await expect(page.getByTestId('problem-count')).toHaveText('0 problems')
  await page.keyboard.press('Control+z')
  await expect(page.getByTestId('problem-count')).toHaveText('1 problem')
  await page.keyboard.press('ArrowUp')
  await page.keyboard.press('ArrowUp')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(book.beads[0].id))
  await page.keyboard.press('m')  // B1 + B2: a 2:2 bead, manual/1.0
  await expect(page.getByTestId('bead-row')).toHaveCount(2)
  const merged = page.getByTestId('bead-row').first()
  await expect(merged).toHaveAttribute('data-problem', 'false')
  await expect(page.getByTestId('problem-count')).toHaveText('1 problem')
  await page.getByTestId('show-multi').check()
  await expect(page.getByTestId('problem-count')).toHaveText('2 problems')
  await expect(merged).toHaveAttribute('data-problem', 'true')
  await expect(merged.getByTestId('problem-badge')).toHaveText(/^\s*2:2 · 1\.00\s*$/)
})

function reviewed(page: Page) {
  return page.getByTestId('bead-row').evaluateAll((els) => els.map((el) => el.getAttribute('data-reviewed')))
}

function inRun(page: Page) {
  return page.getByTestId('bead-row').evaluateAll((els) => els.map((el) => el.getAttribute('data-in-run')))
}

test('Shift+↓ selects a run, r marks it in one undo step', async ({ page, request }) => {
  const { id } = await importBook(request, 'Run')
  await open(page, id)
  await page.keyboard.press('Shift+ArrowDown')
  await page.keyboard.press('Shift+ArrowDown')
  await expect.poll(() => inRun(page)).toEqual(['true', 'true', 'true'])
  await expect(page.getByTestId('status')).toHaveText('3 beads selected (1–3). R marks them all reviewed.')
  await page.keyboard.press('r')
  await expect.poll(() => reviewed(page)).toEqual(['true', 'true', 'true'])
  await expect.poll(() => inRun(page)).toEqual(['true', 'true', 'true'])
  await page.keyboard.press('Control+z')
  await expect.poll(() => reviewed(page)).toEqual(['false', 'false', 'false'])
  await expect.poll(() => inRun(page)).toEqual(['false', 'false', 'false'])
})

test('r on a run with mixed marks marks them all', async ({ page, request }) => {
  const { id } = await importBook(request, 'Run mixed')
  await open(page, id)
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('r')
  await expect.poll(() => reviewed(page)).toEqual(['false', 'true', 'false'])
  await page.keyboard.press('ArrowUp')
  await page.keyboard.press('Shift+ArrowDown')
  await page.keyboard.press('Shift+ArrowDown')
  await page.keyboard.press('r')
  await expect.poll(() => reviewed(page)).toEqual(['true', 'true', 'true'])
  await page.keyboard.press('r')
  await expect.poll(() => reviewed(page)).toEqual(['false', 'false', 'false'])
})

test('Shift+click selects up to a bead; a plain ↓ and Esc clear the run', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Run clear')
  await open(page, id)
  await row(page, book.beads[2].id).locator('[data-cell="target"]').click({ modifiers: ['Shift'] })
  await expect.poll(() => inRun(page)).toEqual(['true', 'true', 'true'])
  await expect(current(page)).toHaveAttribute('data-bead-id', String(book.beads[2].id))
  await page.keyboard.press('ArrowUp')
  await expect.poll(() => inRun(page)).toEqual(['false', 'false', 'false'])
  await page.keyboard.press('Shift+ArrowDown')
  await expect.poll(() => inRun(page)).toEqual(['false', 'true', 'true'])
  await page.keyboard.press('Escape')
  await expect.poll(() => inRun(page)).toEqual(['false', 'false', 'false'])
  await expect(current(page)).toHaveAttribute('data-bead-id', String(book.beads[2].id))
})

test('R marks everything up to here reviewed', async ({ page, request }) => {
  const { id } = await importBook(request, 'Up to here')
  await open(page, id)
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Shift+R')
  await expect.poll(() => reviewed(page)).toEqual(['true', 'true', 'false'])
  await expect(page.getByTestId('status')).toHaveText('Reviewed up to here (2 beads)')
  await page.keyboard.press('Shift+R')
  await expect(page.getByTestId('status')).toHaveText('Already reviewed up to here')
  await page.keyboard.press('ArrowDown')
  await page.getByTestId('reviewed-up-to-here').click()
  await expect.poll(() => reviewed(page)).toEqual(['true', 'true', 'true'])
  await expect(page.getByTestId('status')).toHaveText('Reviewed up to here (1 bead)')
})
