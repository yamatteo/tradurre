import { test, expect } from '@playwright/test'

test('importing a txt pair creates a book', async ({ request }) => {
  const res = await request.post('/api/v2/books', {
    multipart: {
      source: { name: 'contrefeu.txt', mimeType: 'text/plain', buffer: Buffer.from('Marie arriva. Paul partit.') },
      target: { name: 'sacro.txt', mimeType: 'text/plain', buffer: Buffer.from('Marie arrivò. Paul partì.') },
    },
  })
  expect(res.status()).toBe(201)
  const book = await res.json()

  const books = await (await request.get('/api/v2/books')).json()
  expect(books).toContainEqual(expect.objectContaining({ id: book.id, title: 'contrefeu', bead_count: 2 }))
})

const SOURCE = 'Marie arriva.\n\nIl pleuvait.\n\nPaul partit.'
const TARGET = 'Marie arrivò.\n\nPaul partì.'

function txt(name: string, text: string) {
  return { name, mimeType: 'text/plain', buffer: Buffer.from(text) }
}

test('importing through the form opens the book, which the project list then opens', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Import a book (txt/docx/pdf)' }).click()
  await expect(page).toHaveURL(/\/book\/import$/)

  const importButton = page.getByRole('button', { name: 'Import' })
  await expect(importButton).toBeDisabled()
  await page.getByLabel('Original (French)').setInputFiles(txt('Bosco del form.txt', SOURCE))
  await expect(page.getByLabel('Title')).toHaveValue('Bosco del form')
  await expect(page.getByLabel('Source')).toHaveValue('fr')
  await expect(page.getByLabel('Target')).toHaveValue('it')
  await page.getByLabel('Translation (Italian)').setInputFiles(txt('bosco.txt', TARGET))
  await importButton.click()

  await expect(page).toHaveURL(/\/book\/[0-9a-f-]+$/)
  const bookId = page.url().split('/').pop()!
  await expect(page.getByTestId('book-title')).toHaveText('Bosco del form')
  await expect(page.getByTestId('bead-row')).toHaveCount(2)
  await expect(page.getByTestId('book-progress')).toHaveText('reviewed 0 / 2')

  await page.goto('/')
  const card = page.locator(`[data-project-id="${bookId}"]`)
  await expect(card).toContainText('2 beads, 0 reviewed')
  await card.click()
  await expect(page).toHaveURL(new RegExp(`/book/${bookId}$`))
  await expect(page.getByTestId('bead-row')).toHaveCount(2)
})

test('importing an unreadable PDF shows the server message', async ({ page }) => {
  await page.goto('/book/import')
  await page.getByLabel('Original (French)').setInputFiles({
    name: 'livre.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4'),
  })
  await page.getByLabel('Translation (Italian)').setInputFiles(txt('libro.txt', TARGET))
  await page.getByRole('button', { name: 'Import' }).click()
  await expect(page.getByTestId('import-error')).toHaveText('The file is not a readable PDF')
  await expect(page).toHaveURL(/\/book\/import$/)
})

test('import warnings are shown before opening the book', async ({ page }) => {
  await page.goto('/book/import')
  await page.getByLabel('Original (French)').setInputFiles(txt('ete.txt', SOURCE))
  await page.getByLabel('Translation (Italian)').setInputFiles({
    name: 'estate.txt', mimeType: 'text/plain', buffer: Buffer.from('Marie arrivò.', 'latin1'),
  })
  await page.getByRole('button', { name: 'Import' }).click()
  await expect(page.getByTestId('import-warnings')).toContainText('target: The text file is not valid UTF-8')
  await page.getByRole('button', { name: 'Continue' }).click()
  await expect(page).toHaveURL(/\/book\/[0-9a-f-]+$/)
  await expect(page.getByTestId('book-title')).toHaveText('ete')
})

test('the book view keeps the import log with its warnings and stats', async ({ page, request }) => {
  const res = await request.post('/api/v2/books', {
    multipart: {
      source: { name: 'log.txt', mimeType: 'text/plain', buffer: Buffer.from('Marie arriva.\n\nPaul partit.') },
      target: { name: 'registro.txt', mimeType: 'text/plain', buffer: Buffer.from('Marie arrivò.\n\nPaul partì.', 'latin1') },
    },
  })
  expect(res.status()).toBe(201)
  const id: string = (await res.json()).id
  await page.goto(`/book/${id}`)

  const button = page.getByTestId('import-log')
  await expect(button).toHaveText('Import log (1 warning)')
  await expect(page.getByTestId('import-log-panel')).toHaveCount(0)
  await button.click()
  await expect(page.getByTestId('import-warning')).toHaveText(['target: The text file is not valid UTF-8; it was read as Latin-1.'])
  await expect(page.getByTestId('import-stats')).toContainText('"beads": 2')

  const rows = page.getByTestId('bead-row')
  await expect(rows.nth(0)).toHaveAttribute('data-current', 'true')
  await page.keyboard.press('ArrowDown')
  await expect(rows.nth(1)).toHaveAttribute('data-current', 'true')
})
