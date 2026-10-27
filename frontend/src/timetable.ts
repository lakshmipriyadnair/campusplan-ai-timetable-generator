/** One shared college-day layout used by every semester timetable view. */
export const COLLEGE_TIME_CONFIG = {
  teachingPeriods: [1, 2, 3, 4, 5, 6, 7, 8],
  lunchAfterPeriod: 4,
  weekdays: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
} as const

export type TimetableSession = {
  weekday: string
  startPeriod: number
  durationPeriods: number
  kind: 'lecture' | 'laboratory' | 'tutorial'
  subject: string
  faculty?: string
  room?: string
}

/** Maps the teaching-period number to a visual grid column (including lunch). */
export function getSessionGridPosition(session: Pick<TimetableSession, 'startPeriod' | 'durationPeriods'>) {
  const { startPeriod, durationPeriods } = session
  const lastPeriod = startPeriod + durationPeriods - 1
  if (startPeriod < 1 || durationPeriods < 1 || lastPeriod > COLLEGE_TIME_CONFIG.teachingPeriods.length) return null
  // A multi-period block cannot be continuous when it would cross the lunch break.
  if (startPeriod <= COLLEGE_TIME_CONFIG.lunchAfterPeriod && lastPeriod > COLLEGE_TIME_CONFIG.lunchAfterPeriod) return null
  const lunchColumnOffset = startPeriod > COLLEGE_TIME_CONFIG.lunchAfterPeriod ? 1 : 0
  return { column: startPeriod + lunchColumnOffset, span: durationPeriods }
}

export function isContinuousLaboratory(session: TimetableSession) {
  return session.kind === 'laboratory' && session.durationPeriods === 2
}
