export type Row = Record<string, unknown> & { id: number }

export const API_BASE = import.meta.env?.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, options)
  } catch {
    throw new Error('Cannot reach the backend. Start FastAPI and try again.')
  }
  if (!response.ok) {
    let message = `Request failed (${response.status}).`
    try {
      const body = await response.json() as { detail?: unknown }
      if (typeof body.detail === 'string') message = body.detail
      else if (body.detail && typeof body.detail === 'object') {
        const detail = body.detail as { message?: string; errors?: { row: number; column: string; message: string }[] }
        message = detail.message ?? JSON.stringify(body.detail)
        if (detail.errors?.length) message += ` ${detail.errors.map((e) => `Row ${e.row}, ${e.column}: ${e.message}`).join('; ')}`
      } else if (Array.isArray(body.detail)) {
        message = body.detail.map((e: { loc?: unknown[]; msg?: string }) => `${e.loc?.slice(-1)[0] ?? 'Field'}: ${e.msg ?? 'invalid'}`).join('; ')
      }
    } catch { /* Keep the readable status message. */ }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function send(path: string, method: string, body: Record<string, unknown>) {
  return api<Row>(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
}
