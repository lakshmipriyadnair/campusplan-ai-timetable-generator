import test from 'node:test'
import assert from 'node:assert/strict'
import { buildS5Readiness, defaultCheckboxValue, getS5AssignmentOptions, hasLabCompatiblePeriod } from './s5Readiness.mjs'

function s5Data() {
  return {
    departments: [{ id: 1, code: 'CSE' }, { id: 2, code: 'ECE' }],
    'academic-years': [{ id: 10, name: '2026-27', is_active: true }, { id: 11, name: '2025-26', is_active: false }],
    semesters: [
      { id: 100, department_id: 1, academic_year_id: 10, semester_number: 5 },
      { id: 101, department_id: 2, academic_year_id: 10, semester_number: 5 },
      { id: 102, department_id: 1, academic_year_id: 11, semester_number: 5 },
    ],
    'student-groups': [
      { id: 1000, semester_id: 100, group_name: 'S5-A', student_count: 72, is_predefined: true },
      { id: 1001, semester_id: 100, group_name: 'S5-B', student_count: 72, is_predefined: true },
      { id: 1002, semester_id: 101, group_name: 'S5-A', student_count: 10, is_predefined: true },
      { id: 1003, semester_id: 102, group_name: 'S5-A', student_count: 72, is_predefined: true },
    ],
    subjects: [{ id: 7, subject_code: 'TEST' }],
    'shared-subject-requirements': [{
      id: 1, semester_id: 100, subject_id: 7,
      weekly_lecture_hours: 3, weekly_lecture_sessions: null, lecture_session_minutes: null,
      weekly_tutorial_hours: null, weekly_tutorial_sessions: null, tutorial_session_minutes: null,
      weekly_practical_hours: 0, weekly_practical_sessions: 0, practical_session_minutes: null,
    },
    { id: 2, semester_id: 101, subject_id: 7 },
    { id: 3, semester_id: 102, subject_id: 7 }],
    'section-teacher-assignments': [],
    'semester-subjects': [],
  }
}

test('a new period is unconfirmed, not lab-compatible, until selected', () => {
  assert.equal(defaultCheckboxValue(null, 'is_lab_compatible'), false)
  assert.equal(hasLabCompatiblePeriod([{ block_type: 'teaching', is_lab_compatible: false }]), false)
  assert.equal(hasLabCompatiblePeriod([{ block_type: 'teaching', is_lab_compatible: true }]), true)
})

test('S5 readiness distinguishes unconfirmed hours, counts, durations, and confirmed zero hours', () => {
  const result = buildS5Readiness(s5Data())
  assert.ok(result.messages.some((message) => message.includes('lecture session count is not confirmed')))
  assert.ok(result.messages.some((message) => message.includes('lecture session duration is not confirmed')))
  assert.ok(result.messages.some((message) => message.includes('weekly tutorial hours are not confirmed')))
  assert.ok(result.messages.some((message) => message.includes('practical is confirmed as a zero-hour activity')))
  assert.ok(!result.messages.some((message) => message.includes('practical session duration is not confirmed')))
})

test('S5 readiness only matches the selected CSE semester and academic year, and flags ambiguity', () => {
  const data = s5Data()
  const current = buildS5Readiness(data, '10')
  assert.deepEqual(current.groups.map((group) => group.id), [1000, 1001])
  assert.deepEqual(current.requirements.map((requirement) => requirement.id), [1])
  assert.equal(current.messages.some((message) => message.includes('S5-A is ambiguous')), false)

  data.semesters.push({ id: 103, department_id: 1, academic_year_id: 10, semester_number: 5 })
  data['student-groups'].push({ id: 1004, semester_id: 103, group_name: 'S5-A', student_count: 72, is_predefined: true })
  const ambiguous = buildS5Readiness(data, '10')
  assert.ok(ambiguous.messages.some((message) => message.includes('more than one CSE S5 semester')))
  assert.ok(ambiguous.messages.some((message) => message.includes('S5-A is ambiguous')))
})

test('teacher assignment choices contain only protected groups and requirements for the selected CSE S5 year', () => {
  const data = s5Data()
  const current = getS5AssignmentOptions(data, '10')
  assert.deepEqual(current.requirements.map((row) => row.id), [1])
  assert.deepEqual(current.groups.map((row) => row.id), [1000, 1001])
  assert.equal(current.ambiguous, false)

  data.semesters.push({ id: 104, department_id: 1, academic_year_id: 10, semester_number: 5 })
  const ambiguous = getS5AssignmentOptions(data, '10')
  assert.deepEqual(ambiguous.requirements, [])
  assert.deepEqual(ambiguous.groups, [])
  assert.equal(ambiguous.ambiguous, true)
})
