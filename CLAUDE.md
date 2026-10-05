# Rules

- **Features beyond the original ROADrecon show only when their data was collected.** A database gathered with the original roadrecon must open without errors and without any trace of the new feature: no sidebar entry, page, tab, card or column, rather than an empty one. The backend checks whether the data is there (the table exists and has rows), reports it to the frontend, and returns empty results rather than errors if a route is called anyway. The frontend hides everything that depends on it.

Context: [ROADMAP.md](ROADMAP.md) (conventions, phases), [CONTEXT.md](CONTEXT.md) (vocabulary), [docs/adr](docs/adr).
