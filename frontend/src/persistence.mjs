/** Fetch every collection as one snapshot; callers must not publish partial results. */
export async function loadCollections(api, collections) {
  const values = await Promise.all(collections.map((name) => api(`/${name}`)))
  return Object.fromEntries(collections.map((name, index) => [name, values[index]]))
}

/** Reset a form only after the server confirms the save transaction. */
export async function saveRecord({ persist, reload, reset, onSaved }) {
  await persist()
  reset()
  onSaved()
  return reload()
}
