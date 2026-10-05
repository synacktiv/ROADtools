// The GUI is used offline: fail the build if the bundle pulls anything from the network.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const bad = []
const walk = (dir) => {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name)
    if (e.isDirectory()) walk(p)
    else if (/\.(html|css)$/.test(e.name) && /url\(\s*['"]?https?:|<(link|script)[^>]+https?:/.test(readFileSync(p, 'utf8'))) bad.push(p)
  }
}
walk('../roadtools/roadrecon/dist_gui')
if (bad.length) {
  console.error('External resources referenced in:', bad.join(', '))
  process.exit(1)
}
