/** Lightweight preview integrity checks; the backend remains authoritative. */
export function validatePreviewAlternative(sessions) {
  const problems = []
  const resources = new Map()
  for (const session of sessions) {
    const periods = session.period_numbers ?? []
    if (!periods.length) problems.push(`${session.subject_code} ${session.group_name}: session has no teaching period.`)
    if (periods.some((period, index) => index > 0 && period !== periods[index - 1] + 1)) {
      problems.push(`${session.subject_code} ${session.group_name}: periods are not consecutive.`)
    }
    if (session.required_room_type === 'laboratory' && (periods.length !== 2 || periods[1] !== periods[0] + 1)) {
      problems.push(`${session.subject_code} ${session.group_name}: laboratory must use two consecutive periods.`)
    }
    if (session.room_type !== session.required_room_type) problems.push(`${session.subject_code} ${session.group_name}: selected room type is incompatible.`)
    if (Number(session.room_capacity) < Number(session.student_count)) problems.push(`${session.subject_code} ${session.group_name}: room capacity is too small.`)
    const roomEquipment = new Set((session.room_equipment ?? []).map((name) => String(name).trim().toLocaleLowerCase()))
    for (const needed of session.required_equipment ?? []) {
      if (!roomEquipment.has(String(needed).trim().toLocaleLowerCase())) problems.push(`${session.subject_code} ${session.group_name}: required equipment is missing.`)
    }
    const start = minutes(session.start_time)
    const end = minutes(session.end_time)
    if (start === null || end === null || end - start !== Number(session.duration_minutes)) {
      problems.push(`${session.subject_code} ${session.group_name}: time range does not match the required duration.`)
    }
    for (const period of periods) {
      for (const [kind, id] of [['group', session.group_id], ['teacher', session.teacher_id], ['room', session.room_id]]) {
        const key = `${kind}:${id}:${session.weekday}:${period}`
        if (resources.has(key)) problems.push(`${kind} conflict in ${session.group_name} at period ${period}.`)
        resources.set(key, true)
      }
    }
  }
  return [...new Set(problems)]
}

export function validateGenerationResult(result) {
  if (result.status !== 'success') return result
  const problems = []
  const signatures = new Set()
  if (result.valid_count !== result.alternatives.length) problems.push('The returned valid count does not match the preview alternatives.')
  for (const alternative of result.alternatives) {
    problems.push(...validatePreviewAlternative(alternative.sessions ?? []).map((message) => `Alternative ${alternative.alternative_number}: ${message}`))
    const signature = (alternative.sessions ?? []).map((session) => [session.group_id, session.subject_code, session.activity_type, session.session_index, session.weekday, (session.period_numbers ?? []).join(','), session.room_id, session.teacher_id].join(':')).sort().join('|')
    if (signatures.has(signature)) problems.push('The solver returned duplicate alternatives.')
    signatures.add(signature)
  }
  if (!problems.length) return result
  return { ...result, status: 'invalid', valid_count: 0, alternatives: [], diagnostics: [...(result.diagnostics ?? []), ...new Set(problems)] }
}

function minutes(value) {
  if (typeof value !== 'string' || !/^\d{2}:\d{2}$/.test(value)) return null
  const [hours, mins] = value.split(':').map(Number)
  return hours * 60 + mins
}
