import test from 'node:test'
import assert from 'node:assert/strict'
import { api, API_BASE } from './api.ts'

test('frontend API uses the local FastAPI base by default', () => {
  assert.equal(API_BASE, 'http://127.0.0.1:8000/api/v1')
})

test('API 404 responses keep the backend detail instead of becoming empty data', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'Not Found' }), {
    status: 404,
    headers: { 'Content-Type': 'application/json' },
  })
  try {
    await assert.rejects(api('/faculty-scheduling-profiles'), /Not Found/)
  } finally {
    globalThis.fetch = originalFetch
  }
})
