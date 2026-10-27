export type S5Readiness = {
  years: Record<string, unknown>[]
  yearId: string
  selectedSemesters: Record<string, unknown>[]
  namedGroups: Record<string, unknown>[]
  groups: Record<string, unknown>[]
  requirements: Record<string, unknown>[]
  legacyRecords: Record<string, unknown>[]
  messages: string[]
}

export function buildS5Readiness(data: Record<string, any>, requestedYearId?: string): S5Readiness
export function getS5AssignmentOptions(data: Record<string, any>, academicYearId: string): { requirements: Record<string, any>[]; groups: Record<string, any>[]; ambiguous: boolean }
export function getS5RequirementsForYear(data: Record<string, any>, academicYearId: string): Record<string, any>[]
export function hasLabCompatiblePeriod(periods: Record<string, any>[]): boolean
export function defaultCheckboxValue(row: Record<string, any> | null, fieldName: string): boolean
