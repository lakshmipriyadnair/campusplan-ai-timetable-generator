import test from 'node:test'
import assert from 'node:assert/strict'
import { COLLEGE_TIME_CONFIG, getSessionGridPosition, isContinuousLaboratory } from './timetable.ts'

test('one shared teaching-period and weekday configuration is used', () => {
  assert.deepEqual(COLLEGE_TIME_CONFIG.teachingPeriods, [1, 2, 3, 4, 5, 6, 7, 8])
  assert.equal(COLLEGE_TIME_CONFIG.lunchAfterPeriod, 4)
  assert.deepEqual(COLLEGE_TIME_CONFIG.weekdays, ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'])
})

test('a two-period laboratory is one continuous grid block', () => {
  const lab = { weekday: 'Monday', startPeriod: 2, durationPeriods: 2, kind: 'laboratory', subject: 'Real configured subject' }
  assert.deepEqual(getSessionGridPosition(lab), { column: 2, span: 2 })
  assert.equal(isContinuousLaboratory(lab), true)
})

test('grid positioning accounts for lunch and rejects blocks across it', () => {
  assert.deepEqual(getSessionGridPosition({ startPeriod: 5, durationPeriods: 1 }), { column: 6, span: 1 })
  assert.equal(getSessionGridPosition({ startPeriod: 4, durationPeriods: 2 }), null)
  assert.ok(!('Z' in COLLEGE_TIME_CONFIG))
})
