import { writeFileSync } from 'node:fs'
import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Served by the FastAPI app (roadtools.roadrecon.api) and shipped in the Python package.
const outDir = path.resolve(import.meta.dirname, '../roadtools/roadrecon/dist_gui')

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // emptyOutDir also deletes the .gitkeep files that keep dist_gui in git
    { name: 'gitkeep', apply: 'build', closeBundle: () => ['', '/assets'].forEach((d) => writeFileSync(`${outDir}${d}/.gitkeep`, '')) },
  ],
  build: { outDir, emptyOutDir: true },
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  server: {
    proxy: { '/api': process.env.API_URL ?? 'http://127.0.0.1:8000' },
  },
})
