export function loadCollections<T>(api: (path: string) => Promise<T>, collections: string[]): Promise<Record<string, T>>
export function saveRecord(options: {
  persist: () => Promise<unknown>
  reload: () => Promise<unknown>
  reset: () => void
  onSaved: () => void
}): Promise<unknown>
