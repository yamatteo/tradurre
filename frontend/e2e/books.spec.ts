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
