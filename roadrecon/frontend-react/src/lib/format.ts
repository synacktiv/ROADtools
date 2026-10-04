const dateFmt = new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: '2-digit' })
const dateTimeFmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export function fmtDate(v: string | null | undefined, withTime = false) {
  if (!v) return null
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? v : (withTime ? dateTimeFmt : dateFmt).format(d)
}

export const fmtNumber = (n: number) => n.toLocaleString()

export function plural(n: number, one: string, many = `${one}s`) {
  return `${fmtNumber(n)} ${n === 1 ? one : many}`
}
