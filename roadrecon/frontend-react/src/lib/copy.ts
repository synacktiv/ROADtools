import { toast } from 'sonner'

export function copy(text: string, what = 'ID') {
  navigator.clipboard?.writeText(text).then(() => toast(`${what} copied`))
}
