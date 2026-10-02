/** A byte count for a person: `512 B`, `12 KB`, `1.5 MB`. Binary units, as the 50 MB limit is 50 MiB. */
export function formatBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  const text = unit === 0 || value >= 10 ? Math.round(value).toString() : value.toFixed(1)
  return `${text} ${units[unit]}`
}
