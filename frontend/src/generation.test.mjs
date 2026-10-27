import test from 'node:test'
import assert from 'node:assert/strict'
import { validateGenerationResult, validatePreviewAlternative } from './generation.mjs'

function session(overrides = {}) {
  return {
    group_id: 1, group_name: 'S5-A', subject_code: 'TEST101', activity_type: 'lecture', session_index: 1,
    teacher_id: 1, room_id: 1, weekday: 0, period_numbers: [1], start_time: '08:00', end_time: '09:00', duration_minutes: 60,
    room_type: 'classroom', required_room_type: 'classroom', room_capacity: 75, student_count: 72,
    room_equipment: [], required_equipment: [], ...overrides,
  }
}

test('preview checker rejects simultaneous group, shared-teacher, and room use across sections', () => {
  const a = session()
  const b = session({ group_id: 2, group_name: 'S5-B', subject_code: 'TEST102' })
  const issues = validatePreviewAlternative([a, b]).join(' ')
  assert.match(issues, /teacher conflict/i)
  assert.match(issues, /room conflict/i)
  const groupConflict = validatePreviewAlternative([a, session({ subject_code: 'TEST103' })]).join(' ')
  assert.match(groupConflict, /group conflict/i)
})

test('preview checker rejects incompatible room capacity and equipment', () => {
  const issues = validatePreviewAlternative([session({ room_capacity: 70, required_equipment: ['GPU'], room_equipment: [] })]).join(' ')
  assert.match(issues, /capacity is too small/i)
  assert.match(issues, /equipment is missing/i)
})

test('laboratory preview requires exactly two consecutive periods', () => {
  assert.match(validatePreviewAlternative([session({ required_room_type: 'laboratory', room_type: 'laboratory', period_numbers: [1] })]).join(' '), /two consecutive periods/i)
  assert.match(validatePreviewAlternative([session({ required_room_type: 'laboratory', room_type: 'laboratory', period_numbers: [1, 3], start_time: '08:00', end_time: '10:00', duration_minutes: 120 })]).join(' '), /not consecutive/i)
  assert.deepEqual(validatePreviewAlternative([session({ required_room_type: 'laboratory', room_type: 'laboratory', period_numbers: [1, 2], end_time: '10:00', duration_minutes: 120 })]), [])
})

test('incomplete and infeasible outcomes preserve diagnostics without exposing alternatives', () => {
  for (const status of ['incomplete', 'infeasible']) {
    const result = { status, valid_count: 0, alternatives: [], diagnostics: ['missing confirmed data'] }
    assert.equal(validateGenerationResult(result), result)
  }
})

test('success requires valid, genuinely distinct alternatives', () => {
  const first = { alternative_number: 1, sessions: [session()] }
  const second = { alternative_number: 2, sessions: [session({ period_numbers: [2], start_time: '09:00', end_time: '10:00' })] }
  const valid = { status: 'success', valid_count: 2, alternatives: [first, second], diagnostics: [] }
  assert.equal(validateGenerationResult(valid), valid)
  const duplicate = { ...valid, alternatives: [first, { ...second, sessions: [session()] }] }
  const rejected = validateGenerationResult(duplicate)
  assert.equal(rejected.status, 'invalid')
  assert.equal(rejected.valid_count, 0)
})
