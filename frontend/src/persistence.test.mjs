import test from 'node:test'
import assert from 'node:assert/strict'
import { loadCollections, saveRecord } from './persistence.mjs'

test('collection loading rejects instead of returning a partial snapshot', async () => {
  const api = async (path) => {
    if (path === '/rooms') throw new Error('Backend unavailable')
    return []
  }
  await assert.rejects(loadCollections(api, ['faculty', 'rooms']), /Backend unavailable/)
})

test('failed save keeps entered form values and does not show success or reload', async () => {
  const called = []
  await assert.rejects(saveRecord({
    persist: async () => { called.push('persist'); throw new Error('save failed') },
    reload: async () => { called.push('reload') },
    reset: () => called.push('reset'),
    onSaved: () => called.push('success'),
  }), /save failed/)
  assert.deepEqual(called, ['persist'])
})

test('confirmed save resets the form, reports success, then reloads records', async () => {
  const called = []
  const result = await saveRecord({
    persist: async () => { called.push('persist') },
    reload: async () => { called.push('reload'); return true },
    reset: () => called.push('reset'),
    onSaved: () => called.push('success'),
  })
  assert.equal(result, true)
  assert.deepEqual(called, ['persist', 'reset', 'success', 'reload'])
})
