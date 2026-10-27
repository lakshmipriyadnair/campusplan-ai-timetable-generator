const activities = [
  ['lecture', 'weekly_lecture_hours', 'weekly_lecture_sessions', 'lecture_session_minutes'],
  ['tutorial', 'weekly_tutorial_hours', 'weekly_tutorial_sessions', 'tutorial_session_minutes'],
  ['practical', 'weekly_practical_hours', 'weekly_practical_sessions', 'practical_session_minutes'],
]

export function buildS5Readiness(data, requestedYearId = '') {
  const departments = data.departments ?? []
  const semesters = data.semesters ?? []
  const academicYears = data['academic-years'] ?? []
  const cseDepartmentIds = new Set(departments.filter((row) => (row.code === 'CSE' || row.name === 'CSE')).map((row) => String(row.id)))
  const cseS5 = semesters.filter((row) => Number(row.semester_number) === 5 && cseDepartmentIds.has(String(row.department_id)))
  const years = academicYears.filter((year) => cseS5.some((semester) => String(semester.academic_year_id) === String(year.id)))
  const yearStillAvailable = years.some((year) => String(year.id) === String(requestedYearId))
  const yearId = yearStillAvailable
    ? String(requestedYearId)
    : String(years.find((year) => year.is_active)?.id ?? years[0]?.id ?? '')
  const selectedSemesters = cseS5.filter((row) => String(row.academic_year_id) === yearId)
  const semesterIds = new Set(selectedSemesters.map((row) => String(row.id)))
  const namedGroups = (data['student-groups'] ?? []).filter((row) => semesterIds.has(String(row.semester_id)) && ['S5-A', 'S5-B'].includes(row.group_name))
  const groups = namedGroups.filter((row) => Boolean(row.is_predefined))
  const requirements = (data['shared-subject-requirements'] ?? []).filter((row) => semesterIds.has(String(row.semester_id)))
  const legacyRecords = (data['semester-subjects'] ?? []).filter((row) => semesterIds.has(String(row.semester_id)))
  const assignmentLinks = data['section-teacher-assignments'] ?? []
  const messages = []

  if (!yearId) messages.push('No academic year containing a CSE S5 semester is configured.')
  if (selectedSemesters.length > 1) messages.push('Validation error: more than one CSE S5 semester is associated with this academic year. Resolve the duplicate configuration.')
  for (const name of ['S5-A', 'S5-B']) {
    const named = namedGroups.filter((row) => row.group_name === name)
    const protectedMatches = groups.filter((row) => row.group_name === name)
    if (named.length > 1) messages.push(`Validation error: ${name} is ambiguous in the selected CSE S5 academic year (${named.length} matching groups).`)
    else if (named.length === 1 && protectedMatches.length === 0) messages.push(`Validation error: ${name} exists but is not configured as a protected predefined group.`)
    else if (protectedMatches.length === 0) messages.push(`${name} is not configured for the selected academic year.`)
    else if (Number(protectedMatches[0].student_count) !== 72) messages.push(`Validation error: ${name} has ${protectedMatches[0].student_count} students; the confirmed count is 72.`)
  }
  if (yearId && requirements.length === 0) messages.push('No shared S5 subject requirements have been entered for this academic year.')
  if (legacyRecords.length) messages.push(`${legacyRecords.length} legacy per-group S5 subject record(s) exist in this academic year. Review them manually; they are not copied into shared requirements.`)

  for (const requirement of requirements) {
    const subject = (data.subjects ?? []).find((row) => String(row.id) === String(requirement.subject_id))
    const subjectCode = subject?.subject_code ?? 'A subject'
    for (const [activity, hoursKey, sessionsKey, durationKey] of activities) {
      const hours = requirement[hoursKey]
      const sessions = requirement[sessionsKey]
      const duration = requirement[durationKey]
      if (hours == null) messages.push(`${subjectCode}: weekly ${activity} hours are not confirmed.`)
      if (hours != null && Number(hours) === 0) {
        messages.push(`${subjectCode}: ${activity} is confirmed as a zero-hour activity.`)
        continue
      }
      if (sessions == null) messages.push(`${subjectCode}: weekly ${activity} session count is not confirmed.`)
      else if (hours != null && Number(hours) > 0 && Number(sessions) === 0) messages.push(`Validation error: ${subjectCode} has positive ${activity} hours but zero sessions.`)
      if (duration == null) messages.push(`${subjectCode}: ${activity} session duration is not confirmed.`)
    }
    for (const group of groups) {
      if (!assignmentLinks.some((link) => String(link.requirement_id) === String(requirement.id) && String(link.student_group_id) === String(group.id))) {
        messages.push(`${subjectCode} has no teacher assigned to ${group.group_name}.`)
      }
    }
  }

  return { years, yearId, selectedSemesters, namedGroups, groups, requirements, legacyRecords, messages }
}

export function getS5AssignmentOptions(data, academicYearId) {
  const scoped = buildS5Readiness(data, academicYearId)
  // A duplicate CSE S5 semester for one year is ambiguous, so show no choices
  // until the academic structure is corrected.
  if (scoped.selectedSemesters.length !== 1) return { requirements: [], groups: [], ambiguous: scoped.selectedSemesters.length > 1 }
  return { requirements: scoped.requirements, groups: scoped.groups, ambiguous: false }
}

export function getS5RequirementsForYear(data, academicYearId) {
  if (!academicYearId) return []
  const cseDepartmentIds = new Set((data.departments ?? []).filter((row) =>(row.code === 'CSE' || row.name === 'CSE')).map((row) => String(row.id)))
  const semesterIds = new Set((data.semesters ?? [])
    .filter((row) => Number(row.semester_number) === 5
      && String(row.academic_year_id) === String(academicYearId)
      && cseDepartmentIds.has(String(row.department_id)))
    .map((row) => String(row.id)))
  return (data['shared-subject-requirements'] ?? []).filter((row) => semesterIds.has(String(row.semester_id)))
}

export function hasLabCompatiblePeriod(periods) {
  const teaching = periods.filter((period) => period.block_type === 'teaching')
  return teaching.some((period) => Boolean(period.is_lab_compatible))
}

export function defaultCheckboxValue(row, fieldName) {
  return row ? Boolean(row[fieldName]) : false
}
