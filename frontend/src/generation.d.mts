export function validatePreviewAlternative(sessions: Array<Record<string, any>>): string[]
export function validateGenerationResult<T extends { status: string; valid_count: number; alternatives: Array<{ alternative_number: number; sessions: Array<Record<string, any>> }>; diagnostics: string[] }>(result: T): T | (T & { status: 'invalid'; valid_count: 0; alternatives: []; diagnostics: string[] })
