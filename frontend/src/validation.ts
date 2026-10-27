export function validateEntry(kind: string, values: Record<string, string>): Record<string, string> {
  const errors: Record<string, string> = {}
  const required = (field: string, label: string) => {
    if (!values[field]?.trim()) errors[field] = `${label} is required.`
  }
  if (kind === 'faculty') {
    required('faculty_name', 'Faculty name')
    required('faculty_code', 'Faculty code')
    if (values.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email)) errors.email = 'Enter a valid email address.'
  }
  if (kind === 'rooms') {
    required('room_name', 'Room name')
    required('room_type', 'Room type')
    if (!/^\d+$/.test(values.capacity ?? '') || Number(values.capacity) < 1) errors.capacity = 'Capacity must be a positive whole number.'
  }
  if (kind === 'subjects') {
    required('subject_code', 'Subject code')
    required('subject_name', 'Subject name')
  }
  return errors
}
