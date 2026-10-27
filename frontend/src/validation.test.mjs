import test from 'node:test'
import assert from 'node:assert/strict'
import { validateEntry } from './validation.ts'

test('faculty form requires a name and code and validates email', () => {
  assert.deepEqual(validateEntry('faculty', { faculty_name: '', faculty_code: '', email: 'not-an-email' }), {
    faculty_name: 'Faculty name is required.',
    faculty_code: 'Faculty code is required.',
    email: 'Enter a valid email address.',
  })
  assert.deepEqual(validateEntry('faculty', { faculty_name: 'A Teacher', faculty_code: 'T01', email: 'teacher@example.edu' }), {})
})

test('room form requires a name, type, and positive whole-number capacity', () => {
  assert.deepEqual(validateEntry('rooms', { room_name: '', room_type: '', capacity: '0' }), {
    room_name: 'Room name is required.',
    room_type: 'Room type is required.',
    capacity: 'Capacity must be a positive whole number.',
  })
  assert.deepEqual(validateEntry('rooms', { room_name: 'Lab 1', room_type: 'laboratory', capacity: '30' }), {})
})

test('subject form requires a code and name', () => {
  assert.deepEqual(validateEntry('subjects', { subject_code: '', subject_name: '' }), {
    subject_code: 'Subject code is required.',
    subject_name: 'Subject name is required.',
  })
})
