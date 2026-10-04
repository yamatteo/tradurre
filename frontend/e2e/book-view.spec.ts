import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Beads after import and `restoreGap`: A (Chapitre un | Capitolo uno), B (Marie arriva. | Marie arrivò.),
// C (Il pleuvait. | ), D (Paul partit. Il ne dit rien. | Paul partì. Non disse niente.) as two beads D1, D2.
const SOURCE = 'Chapitre un\n\nMarie arriva.\n\nIl pleuvait.\n\nPaul partit. Il ne dit rien.'
const TARGET = 'Capitolo uno\n\nMarie arrivò.\n\nPaul partì. Non disse niente.'

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

test('arrows, tab and clicks move the current bead, side and segment', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Navigation')
  const ids: number[] = book.beads.map((b: { id: number }) => b.id)
  await page.goto(`/book/${id}`)

  await expect(current(page)).toHaveAttribute('data-bead-id', String(ids[0]))
  await expect(current(page)).toHaveAttribute('data-side', 'source')
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('ArrowDown')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(ids[2]))
  await page.keyboard.press('ArrowRight')
  await expect(current(page)).toHaveAttribute('data-side', 'target')
  await page.keyboard.press('ArrowUp')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(ids[1]))
  await expect(current(page)).toHaveAttribute('data-side', 'target')
  await expect(page.locator('[data-current-segment="true"]')).toHaveText('Marie arrivò.')
  await page.keyboard.press('ArrowUp')
  await page.keyboard.press('ArrowUp')  // stays on the first bead
  await expect(current(page)).toHaveAttribute('data-bead-id', String(ids[0]))

  // Clicking a segment selects its bead, side and segment.
  await page.getByText('Il pleuvait.').click()
  await expect(current(page)).toHaveAttribute('data-bead-id', String(ids[2]))
  await expect(current(page)).toHaveAttribute('data-side', 'source')
  // The one-sided bead's empty target cell is grey.
  await expect(current(page).locator('[data-cell="target"]')).toHaveClass(/bg-gray-100/)
})

test('a heading block renders bold', async ({ page, request }) => {
  // txt import has no headings (only docx does), so the first block is turned into one in the response.
  const { id, book } = await importBook(request, 'Heading')
  await page.route(`**/api/v2/books/${id}`, async (route) => {
    const body = await (await route.fetch()).json()
    for (const side of ['source', 'target']) body.beads[0][side][0].block_kind = 'heading'
    await route.fulfill({ json: body })
  })
  await page.goto(`/book/${id}`)
  const first = page.locator(`[data-bead-id="${book.beads[0].id}"]`)
  await expect(first.locator('[data-block-kind="heading"]')).toHaveCount(2)
  await expect(first.locator('[data-block-kind="heading"]').first()).toHaveClass(/font-bold/)
  await expect(page.locator(`[data-bead-id="${book.beads[1].id}"] [data-block-kind="paragraph"]`).first())
    .not.toHaveClass(/font-bold/)
})

test('tab moves between segments of a cell', async ({ page, request }) => {
  // Two sentences in one bead: the targets merge them.
  const { id } = await importBook(request, 'Tab', 'Marie arriva. Paul partit.', 'Marie arrivò e Paul partì.')
  await page.goto(`/book/${id}`)
  const beads = await (await request.get(`/api/v2/books/${id}`)).json()
  // Merge the first two beads so the source cell has two segments.
  await request.post(`/api/v2/books/${id}/beads/${beads.beads[0].id}/merge-next`)
  await page.reload()
  const seg = page.locator('[data-current-segment="true"]')
  await expect(seg).toHaveText('Marie arriva.')
  await page.keyboard.press('Tab')
  await expect(seg).toHaveText('Paul partit.')
  await page.keyboard.press('Tab')  // stays on the last
  await expect(seg).toHaveText('Paul partit.')
  await page.keyboard.press('Shift+Tab')
  await expect(seg).toHaveText('Marie arriva.')
})

test('n jumps to the next unreviewed bead', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Unreviewed')
  const ids: number[] = book.beads.map((b: { id: number }) => b.id)
  await request.post(`/api/v2/books/${id}/reviewed`, { data: { bead_ids: [ids[1]], reviewed: true } })
  await page.goto(`/book/${id}`)
  await expect(page.locator(`[data-bead-id="${ids[1]}"]`)).toHaveAttribute('data-reviewed', 'true')
  await expect(page.locator(`[data-bead-id="${ids[1]}"]`)).toHaveClass(/border-green-500/)
  await page.keyboard.press('n')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(ids[2]))  // skipped the reviewed one

  await request.post(`/api/v2/books/${id}/reviewed`, { data: { bead_ids: ids, reviewed: true } })
  await page.reload()
  await expect(current(page)).toHaveAttribute('data-bead-id', String(ids[0]))
  await page.keyboard.press('n')
  await expect(page.getByTestId('status')).toHaveText('Every bead is reviewed')
})

test('show excluded reveals an excluded block in place', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Excluded')
  const ids: number[] = book.beads.map((b: { id: number }) => b.id)
  const block = book.beads[2].source[0].block_id  // "Il pleuvait."
  await request.post(`/api/v2/books/${id}/blocks/${block}/exclude`)
  await page.goto(`/book/${id}`)
  await expect(page.getByTestId('bead-row')).toHaveCount(ids.length - 1)
  await expect(page.getByTestId('excluded-row')).toHaveCount(0)

  await page.getByTestId('show-excluded').check()
  const row = page.getByTestId('excluded-row')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('Il pleuvait.')
  // Right after bead B's row.
  const previous = row.locator('xpath=preceding-sibling::*[1]')
  await expect(previous).toHaveAttribute('data-bead-id', String(ids[1]))
})

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
