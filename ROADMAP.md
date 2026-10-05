# ROADrecon GUI next — roadmap

New ROADrecon GUI: FastAPI backend + React/shadcn frontend, reading the existing `roadrecon.db` unchanged.
Branch: `gui-next`. Vocabulary: [CONTEXT.md](CONTEXT.md). Decisions: [docs/adr](docs/adr).

## How to run (from `roadrecon/`, nothing installed on the host)

```sh
podman compose run --rm py python roadrecon/tests/gendb.py -o roadrecon/.dev/roadrecon.db   # synthetic DB
podman compose up                              # prod: built GUI + API on http://127.0.0.1:5000 (ROADRECON_DB overrides the DB)
podman compose up api web                      # dev: api (--reload) + Vite on http://127.0.0.1:5173
podman compose up legacy                       # old Flask GUI on the same DB, http://127.0.0.1:5001
VITE_MOCK=1 podman compose up web              # frontend on mock data only
podman compose run --rm py pytest roadrecon/tests -q
podman compose run --rm node npm run build
```

Worktree agents: `podman compose -p rr-<worktree> run --rm py|node ...` (no published ports, isolated project).

If `podman compose` fails with `pasta failed` / `unable to upgrade to tcp`, the host network setup is broken. Tests and builds need no network: `podman run --rm --network none -v $PWD:/src:z -w /src localhost/roadrecon-dev-py pytest roadrecon/tests -q`. For screenshots, run api, vite and Playwright in one `podman pod create --network none` pod; they share localhost.

## Conventions (summary)

- Every list returns `Page[T] = {items, total, page, page_size}`; params `page`, `page_size` (≤500), `q`, `sort`, `order` + typed filters.
- Relation tabs reuse the target type's list endpoint with a relation filter (`/api/users?memberOf=<group>&transitive=true`).
- Every reference to an object is an `ObjectRef {id, type, displayName, sub?}` and renders as an `ObjectLink`.
- Indexes are additive (`CREATE INDEX IF NOT EXISTS`), never schema changes. `--read-only` touches nothing.
- Routes are plain `def`; no `create=True` on `database.init` (it drops all tables).
- Features beyond the original ROADrecon show only when their data was collected: with a DB from the original roadrecon, no sidebar entry, page, tab or card, and no errors ([CLAUDE.md](CLAUDE.md)).

---

## Phase 0 — Setup
- [x] Branch `gui-next` from master `f72a752`
- [x] `.gitignore` negation for `roadrecon/frontend-react/*.json`
- [x] `.claude/` in `.git/info/exclude`, `worktree.baseRef: head`
- [x] `CONTEXT.md` glossary, ADR 0001 (live CA scope), ADR 0002 (indexes after load)
- [x] `roadrecon/compose.yaml` + `roadrecon/Containerfile`, dev image built
- [x] `ROADMAP.md`

## Phase 1 — Component inventory
- [x] Needed components mapped to shadcn (appendix A)
- [x] Design plan via `frontend-design` skill (tokens: colour, type, layout, principles) — appendix B (revised to glass)

## Phase 2 — Frontend mockup
- [x] Scaffold `roadrecon/frontend-react` (Vite 8, React 19, TS 5.9, Tailwind v4, shadcn radix-nova, @fontsource)
- [x] Shell: inset sidebar, breadcrumb, ⌘K command palette, theme switch
- [x] Custom components (appendix A, "custom")
- [x] Hand-written draft types `src/api/types.ts` + typed fixtures + mock `fetch` (`VITE_MOCK=1`)
- [x] All list pages on mock data
- [x] All object pages and tabs on mock data
- [x] Policies list + detail (PolicyFlow) + in-scope users + named locations
- [x] Screenshot review / self-critique pass (Playwright, both themes) — redesigned to the glass direction
- [x] Bigger UI (16 px base), Tabler icons, two-pane object pages, visual indicators, advanced filter builder
- [x] Per-page enhancement pass with the Taste skills (redesign / taste / minimalist), one agent per page (wave 1)
- [x] Shared:
  - real ROADrecon logo and favicon, bigger navbar;
  - object page header shows each fact once;
  - Raw tab with a collapsible, colourised JSON tree;
  - table cell copy, CSV/JSON export (page or all rows), a Columns menu (hide or add, remembered per list);
  - column-header menus (sort, search or pick values, hide) tied to the filter chips;
  - expandable rows.
- [x] Wave 2 per page: no duplicated info, markers next to names, `meta.filter` on columns, extra hidden columns, new spec fields, expandable Conditional Access rows
- [x] World map component for named locations (`components/world-map.tsx`, `@svg-maps/world` CC BY 4.0, credited on the map): per-location map as the side card, overview map above the list
- [ ] **User review of the mockup**
- [x] `roadrecon/tests/gendb.py` synthetic DB generator (parallel worktree), validated with `roadrecon plugin policies` (300 users in 0.9 s, 50k in 9 s)

## Phase 3 — API spec
- [x] `api/db.py` (engine, pragmas, `ensure_indexes`, read-only), `api/app.py`, `api/__main__.py`
- [x] `api/common.py` (paginate, filters, ObjectRef resolver, CTEs, MFA summary, privileged lists) + `tests/test_common.py`
- [x] Pydantic models (`api/models.py`) + router stubs for every route below (`api/routers/<slice>.py`, 501 until implemented)
- [x] Cross-slice hooks stubbed in the owning module: `users.page_users`, `roles.count_roles` / `count_scoped_roles`, `policies.count_affecting`, `governance.count_*` (counts return 0 until the slice lands)
- [x] `openapi.json` exported, `schema.d.ts` generated, frontend switched to generated types (tsc clean)
- [x] Tag `spec-v1` (plus `tests/conftest.py` fixtures and `tests/test_app.py`, which fails if `openapi.json` drifts from the models)

## Phase 4 — Route implementation (fan-out, worktrees)

| Slice | Routes | Pages | Backend | Frontend | Tests |
|---|---|---|---|---|---|
| S1 users | `/api/users` (incl. MFA filters), `/api/users/{id}`, `/api/owners` | users, user page, mfa | [x] | [x] | [x] |
| S2 groups | `/api/groups`, `/api/groups/{id}` | groups, group page | [x] | [x] | [x] |
| S3 devices + AUs | `/api/devices[/{id}]`, `/api/administrative-units[/{id}]` | devices, AUs | [x] | [x] | [x] |
| S4 SPs + apps | `/api/service-principals[/{id}]`, `/api/applications[/{id}]` | SPs, apps | [x] | [x] | [x] |
| S5 policies | `/api/policies[/{id}]`, `/api/policies/{id}/users`, `/api/policies/affecting/{type}/{id}`, `/api/named-locations[/{id}]` | policies, named locations, Policies tab | [x] | [x] | [x] |
| S6 roles | `/api/roles[/{id}]`, `/api/role-assignments` | roles, role page, Roles tabs | [x] | [x] | [x] |
| S7 grants | `/api/app-role-assignments`, `/api/oauth2-grants` | app roles, OAuth2 grants, grant tabs | [x] | [x] | [x] |
| S8 governance | `/api/azure-role-assignments`, `/api/pim-assignments`, `/api/groups/{id}/pim`, `/api/access-package-policies` | Azure / PIM / access package tabs | [x] | [x] | [x] |
| S9 meta | `/api/stats`, `/api/tenant`, `/api/search` | dashboard, ⌘K, settings | [x] | [x] | [x] |

Batch 1: S5, S1, S2, S3, S4. Batch 2: S6, S7, S8, S9. Code review after each batch.

Backend status (2026-10-04): every route implemented in its worktree, merged into `gui-next`; both batch reviews applied; 201 tests (`pytest roadrecon/tests`).
- End-to-end smoke: all 29 pages render against the real API (gendb DB, Vite proxy, Playwright) with no HTTP or page errors.
- Per-page frontend follow-ups (2026-10-05):
  - [x] the app page reads publisher, owner tenant, status and assignment from `ApplicationDetail`, without fetching the SP;
  - [x] `LocationPolicies` uses `NamedLocationRow.policies` + `excludedBy`, with no request per row;
  - [x] `grants.tsx` and `apps.tsx` use the server's `isPrivileged` / `privilegedScopes` (the regex copies are gone);
  - [x] the governance tables set `meta.sort` (the backend accepts `role`, `kind`, `resourceType`, `packageName`).
- Dashboard directory settings:
  - [x] long CamelCase setting names (`BannedPasswordCheckOnPremisesMode` in Password Rule Settings, `Group.Unified`) overlapped the value; they now wrap between words;
  - [x] rework the "Password Rule Settings" section (lockout numbers, banned-password flags and chips; mock only, gendb has no directory settings).
- Spec changes after `spec-v1`:
  - `RoleDetail.holders` is a list of `{kind, principalType, scope, count}` (the role page tallied 1000 assignments, over the 500 cap);
  - `NamedLocationRow.excludedBy`: ids of the policies that exclude the location.
- SQLite-only SQL, marked `ponytail:`: `json_array_length` (SP / app credential counts) and `json_each` / `json_extract` (app role value filter). Needs `CAST(... AS json)` variants for Postgres.
- Open questions for a real tenant:
  - do deny access-package policies block a package that an allow policy grants? (Today they are only hidden.)
  - does Entra store user actions as `Acrs: urn:user:*`? (Handled both ways.)

## Phase 5 — Integration and parity

Performance and compatibility
- [x] 50k-user synthetic DB: list, relation and in-scope endpoints < 300 ms (`.dev/perf.py`: worst is a policy's in-scope users at about 240 ms; `role-assignments?expandGroups` across all roles is about 350 ms, but the UI only uses it with `roleId`)
- [x] DB without PIM/IG/AZ tables returns empty results, not errors (`minimal_client` tests, plus single missing PIM tables)
- [x] `--read-only` on a read-only file works (`test_read_only_engine`)
- [x] Side-by-side with the Flask GUI on the same DB (`legacy` compose service, Angular built on node 16)

Parity with the old GUI — lists
- [x] Users (name, UPN, enabled, mail, department, last password change, job title, mobile, source, type, MFA)
- [x] Groups (name, description, type, source, mail, public, role assignable, dynamic)
- [x] Devices (name, manufacturer, enabled, model, OS, version, trust type, compliant, managed, rooted)
- [x] Service principals (name, type, publisher, Microsoft app, passwords, keys, roles, OAuth2 permissions, custom owner)
- [x] Applications (name, multitenant, homepage, public client, implicit flow, passwords, keys, roles, permissions, custom owner)
- [x] Administrative units (name, description, membership rule)
- [x] Application roles (principal, type, application, role, description)
- [x] OAuth2 permissions (consent type, principal, client, resource, scope, expiry)
- [x] MFA (name, UPN, enabled, per-user MFA, methods count, FIDO, app, phone, method icons)
- [x] Directory roles (per role: principal, scope, active/eligible, type, UPN, source, status, MFA)

Parity — object pages
- [x] User: overview, groups, roles, owned devices/SPs/apps/groups, PIM (direct + via groups), access packages, Azure roles, policies, raw
- [x] Group: overview, parents, roles, owners (users + SPs), members (users, groups, SPs, devices), PIM roles, PIM rights (direct only, like the old GUI), Azure roles, raw
- [x] Device: overview, owners, BitLocker keys, raw
- [x] Administrative unit: overview, members (users, groups, devices), raw
- [x] Service principal: overview, owners, roles, groups, app roles given / received, defined permissions, Azure roles, metadata, raw
- [x] Application: overview, owners, defined permissions, metadata, raw, link to service principal

Parity — other
- [x] Dashboard: stats, directory settings, tenant information + domains, authorization policy
- [x] Settings page removed at the user's request (2026-10-04). Where each setting went:
  - theme: toggle in the header;
  - page size: the table footer;
  - MFA columns: the Columns menu;
  - Entra admin center links: always shown;
  - blue-team badge colours: dropped (red-team colours are the default);
  - paging: always server-side.

New features
- [x] Policies list + detail with every GUID resolved to a link
- [x] Users in scope of a policy (paginated, include/exclude)
- [x] Policies tab on user, group, role, service principal, application (with "via")
- [x] Named locations list + detail with the policies using them
- [x] Owner service principals shown (old GUI only showed owner users)
- [x] Every object mention is a link (incl. scopes, grants, policy conditions)
- [x] ⌘K global search, dark mode
- [x] Directory roles list (`RoleRow.syncedCount`; expanded rows read `/api/role-assignments?expandGroups`, so assigned groups with no members only show on the role page):
  - privileged roles first;
  - expandable rows that show the users assigned the role;
  - a column with how many holders are not cloud only (synced from on-premises).
- [x] Animations on the dashboard and on page loading (relaxes design principle 5, "motion only answers an action"; honour `prefers-reduced-motion`)
- [x] SQL query page (`/api/sql`, `/api/sql/schema`, 11 built-in queries served by the backend; 1000 rows, 10 s, ATTACH denied):
  - direct SQL against the database, with autosuggest (tables, columns) and built-in queries to choose from;
  - results in a `DataTable`, with one-click CSV export;
  - run on a separate read-only connection (`PRAGMA query_only`), with a row cap and a timeout.
- [x] Resizable table columns (drag the column header edge in `DataTable`).
- [x] Named locations map: trusted countries in green (already handled; mock and gendb had no trusted country location, now they do).
- [x] Service principals list: a URLs column (reply URLs, homepage, logout URL), hidden by default, with a `url` filter; logout URL also on the SP page.

## Phase 6 — Switch
- [x] Default prod target: `podman compose up` builds the frontend and serves it from the FastAPI app on one port (`python -m roadtools.roadrecon.api`), no Vite
- [x] `roadrecon gui` / `roadrecon-gui` → `roadtools.roadrecon.api.__main__` (keep `-d`, `--host`, `--port`)
- [x] `gather` calls `ensure_indexes` before policyanalysis
- [x] `roadrecon/setup.py`: add fastapi + uvicorn, drop flask / marshmallow deps, `sqlalchemy>=2`
- [x] Vite `outDir` → `roadtools/roadrecon/dist_gui` (keep `.gitkeep`)
- [x] `azure-pipelines.yml` builds `frontend-react`
- [ ] Delete `server.py`, `roadrecon/frontend/`, mock fetch; rewrite `tests/test_guiserver.py` (after the user review; `xlsexport` no longer imports `server.py`); move the README logo off `roadrecon/frontend/src/assets/rt_transparent.svg`
- [x] Run `roadrecon/tests` in `azure-pipelines.yml` (httpx added; one pytest call over `tests/` and `roadrecon/tests/`)
- [x] README: the new GUI (`roadrecon gui` options, what it shows, `/docs`) and the `frontend-react` dev setup

## Phase 7 — Device compliance settings (new collection)
The original collector does not gather Intune compliance data. Collect it, then show it on a new page.
- ~~Collector~~ — **out of scope** (2026-10-05): Intune is only on MS Graph, and collectors use only the APIs of the original roadrecon (rule in CLAUDE.md). `compliancegather` was written then removed. Without a collector, the tables below stay empty on real DBs (only gendb fills them), so the page and the device tab never show.
- [x] Tables in `roadlib/metadef/database.py` (`DeviceManagementSettings`, `DeviceCompliancePolicys`, `DeviceCompliancePolicyAssignments`), added, never altered. A DB without them gives empty results, not errors, and the API reports that compliance data is absent (see the conventions).
- [x] API: `/api/device-compliance` (settings + policy list, `Page[T]`) and `/api/device-compliance/{id}` (settings by platform, assignments as `ObjectRef` to groups or all users / all devices, actions for non-compliance). Add to openapi.json and `schema.d.ts`, with tests on gendb data.
- [x] gendb: settings and a few policies per platform.
- [x] Frontend: a "Device compliance" page in the sidebar, shown only when compliance data was collected. Tenant settings card on top (a no-policy device marked compliant shows as `regulatory`), then a `DataTable` of policies (platform, assigned groups, grace period). The detail page has a two-pane layout and a Raw tab.
- [x] Device page: a Compliance tab with the policies that target the device through its groups or its owners' groups (`/api/device-compliance?deviceId=`, with "via" and Applies / Excluded; exclusion wins; All users counts any owned device, flagged approximate since licences are not collected).

## Phase 8 — Authentication strengths
Today the policies show authentication strength ids as unresolved references (only the three built-in ids are known, in the old `policies` plugin).
- ~~Collector~~ — out of scope: AAD Graph has no strength definitions (not in the metadef; the test tenant dump of 2026-10-05 only has policyTypes 2, 5, 8, 10, 18, 19, 24), and MS Graph is out of scope (CLAUDE.md).
- [x] API: built-in strength ids (`…0002/3/4`) resolve from a constant with their allowed combinations (`PolicyDetail.authenticationStrengths`); custom ids stay unresolved ("Custom authentication strength").
- [x] MFA requirement: `PolicyRow.requiresMfa` / `mfaApproximate` + a `requiresMfa` filter. A grant entry met only by MFA and/or strengths requires MFA; built-in strengths count; a custom strength counts but is flagged approximate (combinations not collected); "MFA or compliant device" does not.
- [x] Frontend: policy flow lists a built-in strength's combinations, or notes a custom one; the user page's risk signals card says whether an enabled policy in scope requires MFA.
- Reference: https://learn.microsoft.com/en-us/entra/identity/authentication/concept-authentication-strengths

## UI bugs
- [x] Long badge content overlaps the row: on the Conditional access page, an unfolded policy whose Users, Resources or platform ("Any platform") group/badge holds very long content runs over the whole line. Wrap it onto new lines. Fix the other places with the same badge/group pattern too. Fixed in the shared `KeywordChip`, `IconText`, `PolicyRef` and wrapping `ObjectLink` (`min-w-0` + `break-words`); the shadcn `Badge` itself stays one-line for short status chips.
- [ ] Narrow viewport (about 820 px): the header search button and theme toggle overflow, so the whole page scrolls sideways; an unfolded table row wraps at the table width, not the visible width.

## Done from "Later" (2026-10-05)
- Shared router helpers in `api/common.py` (`flag`, `count_rows`, `count_of`, `gm_user` / `gm_group`); openapi.json unchanged.
- `mfa_` column-id prefix dropped (saved MFA column choices reset once).
- One `StatusMark` in `components/badges.tsx` for disabled, no MFA, not compliant, risky; disabled is `IconBan` everywhere.
- Code split: routes lazy-loaded, world map in its own chunk (named-location pages only). Initial JS 2.1 MB → 558 kB (655 → 180 kB gzip).
- `RoleDetail.policyCount` and the count on the role page's Policies tab.
- `xlsexport` MFA sheet: missing `strongAuthenticationDetail` keys are treated as absent (`tests/test_xlsexport.py`, skipped without openpyxl).
- The raw tab's collapsible JSON tree was already done in Phase 2.

## Known approximations (shown as such in the UI)
- Guest and external user types: inferred from `userType`.
- App bundles (`Office365`, `MicrosoftAdminPortals`) are not expanded to their apps.
- Device filter rules and service principal filter rules are shown, not evaluated.
- Scope through eligible roles is flagged as eligible-only.

## Later (deliberately skipped)
- FTS5 trigram search if `LIKE '%q%'` gets slow on very large tenants (>500k users)
- Column-compat shim for dumps made by very old roadlib versions
- policyanalysis fixes (Postgres `on_conflict`, roles via groups, duplicates, `ALLUSERS` in exclude)
- Postgres compose service + test run
- Playwright smoke test
- Azure resource / subscription pages
- Teams / chat resource-specific consent settings on the dashboard consent card.

---

## Appendix A — Component inventory

Existing shadcn registry components, used as is:

| Need | shadcn component |
|---|---|
| App navigation, mobile navigation | `sidebar` (includes `sheet`) |
| Location in the app | `breadcrumb` |
| Global search (⌘K) | `command`, `kbd`, `dialog` |
| Tables | `table` + TanStack Table |
| Table toolbar | `input-group` (search), `button`, `button-group` (pager), `dropdown-menu` (columns), `select` (filters, page size), `switch` (toggle filters), `spinner` (refetch) |
| Object page | `tabs` (segmented), `card`, `separator`, `scroll-area`, `badge`, `toggle-group` (sub-views) |
| Overview page | `card` (stat cards, sections), `item` |
| Previews and hints | `hover-card`, `tooltip` |
| Loading and empty states | `skeleton`, `empty` |
| Feedback (copy id) | `sonner` |
| Settings | `field`, `switch`, `select` |
| Raw JSON, policy sections | `collapsible` |

Not used: `pagination` (link-based; the table footer needs buttons + page size), `chart` (no charts in scope), `form` (no forms).

Custom components (no shadcn equivalent):

| Component | Why custom | Built from |
|---|---|---|
| `ObjectLink` | Type glyph + name + hover preview, used for every reference | `hover-card`, router `Link` |
| `TypeGlyph` | One consistent mark per object type | inline SVG |
| `DataTable` | Server-side paging/sort/search with state in the URL; also used for every relation tab | `table`, TanStack Table, toolbar components |
| `ObjectPage` | Header (glyph, name, badges, copyable id, portal link) + tabs with counts, tab in the URL | `tabs`, `badge`, `button` |
| `PropertyList` | Label/value grid with formatters (bool, date, GUID, lists) | plain markup |
| `JsonView` | Raw tab | `pre` + copy button |
| `MfaMethods` | Method icons with the default method marked | `tooltip`, lucide icons |
| `CredentialList` | Password/key credentials with expiry state | `table`, `badge` |
| `PolicyFlow` | Who → target resources → conditions → grant/session, include/exclude chips | `ObjectLink`, `badge` |
| `PolicyMatchList` | Policies concerning an object, with side and "via" chain | `ObjectLink`, `badge` |
| `StateBadge` | Policy state, enabled/disabled, active/eligible, approval (blue team aware) | `badge` |
| `AzureScope` | Port of `utils.parseAzureScope` | plain markup |

## Appendix B — Design plan (frontend-design)

**Brief.** Modern, glassy and minimal, inspired by a dark shadcn dashboard shot: an inset content panel floating over a vivid blurred gradient, translucent surfaces, hairline borders, segmented tabs, stat cards, and colour used only for meaning. The audience is pentesters and blue teamers going through a tenant dump. Its job: get from object to object fast, and see what applies to an object and what excludes it.

The first direction (road-signage palette with Overpass) was replaced on 2026-10-04, at the user's request, by the glass direction below. Two parts of it carry information and were kept: the object-type glyphs and the policy route.

**Colour.** UI chrome is greyscale only. Hue is reserved for meaning.

| Token | Dark | Light | Use |
|---|---|---|---|
| `background` | `#09090b` | `#f4f4f5` | page; the glass panel sits on it |
| `card` | white 3.5 % | white 62 % | translucent surfaces (`.glass`: blur 16 px plus a top highlight) |
| `border` | white 9 % | black 8 % | hairlines |
| `muted-foreground` | `#a1a1aa` | `#71717a` | secondary text |
| `guide` | `#4ade80` | `#15803d` | applies, enabled, active |
| `warning` | `#fbbf24` | `#b45309` | report-only, eligible, approximate |
| `regulatory` | `#f87171` | `#dc2626` | block, excluded, disabled, no MFA |
| backdrop | teal `#14b8a6`, indigo `#6366f1`, magenta `#db2777`, red `#ef4444` | same | fixed, blurred 80 px, 30 % opacity in dark and 35 % in light |

**Type.**
- Geist Variable for all text and Geist Mono for GUIDs, IP ranges and JSON, bundled via @fontsource so the app works offline.
- Base size 16 px (the user asked for a bigger UI). Scale: 14 / 16 (body) / 18 / 20 / 24 / 30.
- Weights: 400, 500 and 600.
- Sentence case everywhere.

**Icons.** Tabler Icons (`@tabler/icons-react`, picked by the user from shadcn.io/icons; stroke 1.75). shadcn's `iconLibrary` is set to `tabler`, so the shadcn internals use Tabler too.

One icon per object type, carried by every reference:

| Object | Icon |
|---|---|
| user | `IconUser` |
| group | `IconUsersGroup` |
| device | `IconDeviceLaptop` |
| service principal | `IconRobot` |
| application | `IconAppWindow` |
| administrative unit | `IconHierarchy2` |
| directory role | `IconCrown` |
| policy | `IconShieldLock` |
| named location | `IconMapPin` |
| unresolved reference | `IconHelpCircle` |

The logo is `IconRoad`.

**Layout.**
- shadcn `sidebar` uses the `inset` variant. The content panel is translucent with `backdrop-blur` and a 1 px ring.
- The header holds the sidebar trigger, the breadcrumb, a ⌘K search and the theme toggle. Dark is the default theme.
- Lists are a toolbar plus a table inside a glass frame (rounded-xl).
- Object pages follow the frontend-ng detail view: a header, then two panes.
  - Left: a sticky glass properties panel (stacked label / value, visual values) and an optional `aside` card.
  - Right: segmented `tabs` with counts for the relations.
  - The raw object opens in a shadcn `sheet`.
- Visual indication is preferred over text: `Flag` (with risky colouring), `StatusDot`, `SourceIcon`, method icons, meters.
- The overview page has 4 stat `card`s, a Conditional Access state bar, a role assignment bar list, then tenant settings.

**Principles.**
1. shadcn components first. Custom code only where shadcn has nothing: glyphs, `PolicyFlow`, property rows, data table glue.
2. Every object mention is an `ObjectLink` with a hover preview.
3. Colour means something or it is not used.
4. One expressive element: the policy route (a dashed amber line for report-only, grey for disabled, a no-entry stop for block).
5. Motion only answers an action.

## Appendix C — Spec changes made during the mockup

- Dropped `/api/mfa`. The MFA view is `/api/users` with the `mfa`, `perUserMfa` and `excludeMailboxOnly` filters, which reuses `UserRow`.
- Added `/api/owners?ownerOf=`: owners of any object, users and service principals in one list (the old GUI hid SP owners).
- `PolicyMatch` is now one entry per policy: `effect` (exclusion wins), plus `included[]` and `excluded[]` reasons, each with `condition`, a `via` chain, `approximate` and `eligibleOnly`.
- **Advanced filtering on every list.**
  - Every `PageQuery` accepts a repeatable `filter=field:op:value` and `match=all|any`.
  - Operators: `contains notContains eq ne startsWith endsWith empty notEmpty in notIn gt lt`. `in` / `notIn` take a comma list of URI-encoded items.
  - New route `GET /api/filters/{resource}` returns `FilterField[]` (`key`, `label`, `type` text|enum|bool|date|number, and `options` for enums, up to 200 distinct values from the dump).
  - Resources: users, groups, devices, administrative-units, service-principals, applications, roles, role-assignments, app-role-assignments, oauth2-grants, policies, named-locations.
  - Backend: one shared helper maps each resource's whitelisted fields to columns or expressions. Unknown fields or operators give a 422.
  - The field catalogues to mirror are in `mock.ts` `FIELDS`.
- The single-select quick filters were replaced by the filter builder. Relation switches (transitive, expand groups) stay as plain query params.
- `GroupQuery.memberOfAu` was added for AU member groups.
- **Fields added on 2026-10-04**, all from real roadrecon.db columns or computed server-side:
  - `UserDetail.onPremisesSecurityIdentifier`;
  - `GroupDetail.securityIdentifier` (`cloudSecurityIdentifier`) and `GroupDetail.onPremisesSecurityIdentifier`;
  - `DeviceDetail.owners: ObjectRef[]`;
  - `RoleRow.isPrivileged` (fixed set of tier-0 template IDs);
  - `Tenant.authorizationPolicy.userConsentPolicy | guestRole | guestInvitesFrom`: enums decoded from `permissionGrantPolicyIdsAssignedToDefaultUserRole`, `guestUserRoleId` and `allowInvitesFrom`.
- `FilterResource` adds `azure-role-assignments`, `pim-assignments` and `access-package-policies`.
- **Spec requests from the agents, for Phase 3:**
  - holder counts by principal type and scope on `RoleDetail` (today the page fetches up to 1000 assignments);
  - policy refs on `NamedLocationRow` (avoids one detail request per row);
  - publisher, owner tenant, enabled and assignment required on `ApplicationDetail` (copied from the linked service principal);
  - a privilege tier per permission (replaces name patterns in the UI);
  - export is client-side today: a streaming `format=csv` on list routes if dumps exceed 50 000 rows. `PolicyUserQuery` extends `UserQuery`, so the in-scope users table has the same filters as the users list.
- **Done in Phase 3 (spec-v1):**
  - `RoleDetail.holders`: assignment counts by principal type and by scope;
  - `NamedLocationRow.policies: ObjectRef[]`; the detail's `PolicyMatch[]` is renamed `policyMatches`;
  - `ApplicationDetail.publisherName | appOwnerTenantId | accountEnabled | appRoleAssignmentRequired` (from the linked SP);
  - `isPrivileged` on `AppRoleDefinition`, `PermissionScopeDefinition`, required permissions and `AppRoleAssignmentRow`, plus `OAuth2GrantRow.privilegedScopes` (server-side name pattern, `common.is_privileged_permission`);
  - role ids are template ids everywhere;
  - streaming CSV skipped until a dump needs it.
