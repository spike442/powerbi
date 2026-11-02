# KPI Reconciliation Dashboards — handover

Power BI report with 3 pages on the ClickHouse table `Hera_SA.KPI_REC_ALL`, for a finance team.
The owner is a BI developer. They build and test in **Power BI Desktop (French UI)** on a Windows work PC.
They talk to you from this Linux machine and send **phone photos** of their work screen.

## Status (2026-11-02)
| Item | State |
|---|---|
| PBIP (`pbip/project/`) | Done, all 3 pages. Opened and refreshed fine in Desktop (it read the earlier embedded query, before the view existed). |
| View `Hera_SA.POWER_BI_DASHBOARD_KPI_VIEW` | **Blocked.** The SELECT runs, but `CREATE … ON CLUSTER` fails (see Open issues). Latest attempt v2.1.2 is untested by the user. |
| Production `.pbix` | Not built yet. Manual build in RS Desktop, guided by `pbip/BUILD_PBIX.md`. |
| Deployment | Not ours. The owner hands the `.pbix` to the Report Server admin (no deploy licence). |

## Open issues (start here)
1. **The view fails to create on INT.** DBeaver shows `Code: 47 … <Unreadable error message> (transport error: 404)`. With the `CREATE` line removed, the SELECT runs.
   - v2.1.2 replaced `IN (SELECT … FROM cte)` with an `INNER JOIN`. That construct is the suspect under `ON CLUSTER`, but this is not confirmed.
   - Next diagnostics, if it still fails:
     - (a) Run without `ON CLUSTER hera_cluster_1S_2R`. If that works, the problem is on the cluster side.
     - (b) Check that both replicas have the 8 new columns:
       `SELECT hostName(), count() FROM clusterAllReplicas('hera_cluster_1S_2R', system.columns) WHERE database='Hera_SA' AND table='KPI_REC_ALL' AND match(name,'^(NB|AMT)_Y(PV|CASH)_BREAK_BGM_ECO_EUR_(ABOVE|BELOW)$') GROUP BY 1` → 8 per node.
     - (c) Read the real error message from `clusterAllReplicas('hera_cluster_1S_2R', system.query_log)`: type `Exception*`, query ILIKE `'%POWER_BI_DASHBOARD_KPI_VIEW%'`.
2. **The PV/Cash `_ABOVE` column types look swapped** in the owner's column sheet: `NB_*_ABOVE` is float, `AMT_*_ABOVE` is int.
   - The view casts every unpivoted value to Float64, so it works either way. Without the cast, ClickHouse fails because of the mixed tuple types (reproduced locally).
   - If the amounts really are int, decimals are lost upstream. Suggest fixing the table.
3. The owner's repo file is named `POWER_BI_DASHOARD_KPI_VIEW.sql` (B missing). The view name uses the correct spelling; they were told to rename the file.
4. An older view `Hera_SA.V_KPI_REC_DASHBOARD` may exist on INT and can be dropped.
5. Photos `IMG_5216/5217.HEIC` and `.idea/` sit in the root. They are not pushed and the owner may delete them. An earlier `rm` was blocked by the permission check.

## The spec (from the owner's colleague; original photos deleted)
Filters on (a) and (c):
- Reconciliation: PNL/Carry, summed when both are selected.
- Entity.
- Product = `CAT_NAME`.
- PNL Component: PNL/PV/Cash, single select, default PNL.
- Threshold: Above/Below, single select, default Above.

Pages:
- **(a) Closing Progress**
  - Chart 1: number of breaks per closing day, current vs previous closing (line chart, x = `closing_day`, legend = closing).
  - Chart 2: residual amount per closing day for **Above and Below**, each in its own chart. The Threshold slicer must not filter them (interaction = None).
  - Tooltips: snapshot date and delta vs previous at the same closing day.
- **(b) Snapshot Detail**
  - Date picker limited to the current month, up to today. If empty, the latest snapshot is used.
  - Count and amount per band: `1K - 100K`, `100K - 300K`, `300K - 500K`, `500K - 1M`, `> 1M`.
  - Bands exist **only for PNL** and are not split by threshold, so this page has no Component/Threshold slicers. The subtitle says "PNL".
- **(c) Yearly Trend**
  - Latest snapshot of each closing in the current closing's year. One bar per closing: count and net amount.
  - "Year" = the year of the **current closing**. In Jan 2027 they are still closing 202612, so 2026 is shown.

## Data facts (KPI_REC_ALL)
- One row set per `REC_ID`, `PERIOD` (closing, e.g. `202609SA`), `CMN_RECORD_DATE` (daily snapshot) and `VERSION` (keep the max).
- Further dimensions: `ENT_ACC` (entity) and `CAT_NAME` (empty string → `(No category)`).
- KPIs are **stock** snapshots and must never be summed across days. The DAX measures are semi-additive (last date in context).
- Wide columns: `NB_/AMT_Y{PNL,PV,CASH}_BREAK_BGM_ECO_EUR[_ABOVE|_BELOW]`.
  - The bands `_LE_100K/_LE_300K/_LE_500K/_LE_1M/_GT_1M` exist for YPNL only.
  - The suffix-less columns are totals (= Above + Below) and are not used.
- Bands start at 1K: breaks below 1K are in no band. Totals include "NO BREAK" lines by design. Amounts are signed sums.
- NaN values were seen in `AMT_*` (handled with `isFinite`).
- `reconciliation` is derived from `REC_ID`: contains CARRY → `Carry`, contains FRZ → `PNL`, else the REC_ID itself.
- The previous closing's break count drops after about day 24. This is real data, not a bug.

## Architecture
```
KPI_REC_ALL ──(view: dedupe VERSION, unpivot, rank closings, flags)──► POWER_BI_DASHBOARD_KPI_VIEW
   ──ODBC dsn=HERA_CH, explicit column list──► FactBreaks (single import table) ──► 12 DAX measures ──► 3 pages
```

**View output columns:**
- `period`, `record_date`
- `closing_rank`: 1 = current, 2 = previous, from `dense_rank` on `substring(period,1,6)`
- `closing_order`: UInt32 YYYYMM, the sort key for `closing_month`
- `closing`: e.g. "Current (202609SA)"; `closing_scope`
- `closing_month`: e.g. "Sep 2026"
- `year_trend_snapshot` Y/N
- `closing_day`: day 1 = the closing's first snapshot
- `rec_id`, `reconciliation`, `entity`, `product`, `component`, `threshold`, `band`, `band_order`
- `breakdown`: Threshold | Band
- `current_month_snapshot` Y/N
- `nb_breaks`, `amt_breaks`

The view reads periods from last year onwards and keeps `closing_rank <= 2` plus the year-trend rows. `today()` is evaluated at each refresh, so a daily scheduled refresh is required.

**Hidden page filters** (`isHiddenInViewMode`):
- (a): `breakdown=Threshold`, `closing_scope ∈ {Current, Previous}`
- (b): `breakdown=Band`, `current_month_snapshot=Y`
- (c): `breakdown=Threshold`, `year_trend_snapshot=Y`

## Repo layout & workflow
```
CLAUDE.md                    this file
pbip/build_pbip.py           generator: python3 pbip/build_pbip.py → wipes and rebuilds pbip/project/
pbip/src/03_FactBreaks.pq    Power Query (M), embedded into the TMDL partition
pbip/src/04_measures.dax     measures; a measure starts with "Name =" right after a blank line (VAR lines are not new measures)
pbip/src/CY25SU12.json       base theme (from microsoft/fabric-samples), copied into the report
pbip/src/POWER_BI_DASHBOARD_KPI_VIEW.sql   view DDL — owner wants it with NO comments, clean aligned blocks
pbip/BUILD_PBIX.md           step-by-step RS Desktop build + admin hand-off note
pbip/project/                generated PBIP (TMDL + PBIR); never hand-edit, change the generator/src and regenerate
```

**Making a change:**
1. Edit `src/*` or `build_pbip.py`.
2. Regenerate.
3. Validate (see below).
4. Update `BUILD_PBIX.md` if the manual build steps change.
5. Commit, tag, push.

**PBIR/TMDL details used:**
- Schemas: report 1.2.0, page 1.4.0, visualContainer 1.5.0, definitionProperties 2.0.0, pages/version metadata 1.0.0.
- TMDL: compatibilityLevel 1567.
- Model: auto date/time off (`__PBI_TimeIntelligenceEnabled = 0`). lineageTags are uuid5 values, so regeneration is stable.
- Sort-by: `closing`→`closing_rank`, `band`→`band_order`, `closing_month`→`closing_order`.

**Validation:**
- PBIR JSON: validate with Python `jsonschema` against each file's `$schema` URL (remote `$ref`s), skipping `StaticResources/`. Previously 30 files, 0 errors.
- The validator venv was in a scratchpad that has since been wiped. Recreate it with `python3 -m venv` and `pip install jsonschema`.
- View: `clickhouse local` (v26.8) is installed at `/usr/local/bin/clickhouse`.
  - Build a mock `Hera_SA.KPI_REC_ALL` and run the DDL without `ON CLUSTER`, on both `--enable_analyzer=0` and `1`.
  - Run it with `</dev/null`, otherwise it hangs reading stdin.
  - There is no network access to the owner's ClickHouse.

**Git:**
- Remote `git@github.com:spike442/powerbi.git`, branch `main`.
- `CLAUDE.md`, `pbip/build_pbip.py` and `pbip/src/CY25SU12.json` are pushed (whitelisted), so a clone can regenerate the project.
- Push **only** what is needed. The whitelist lives in `.git/info/exclude` (local, not committed): `/*` is ignored, then the needed paths are re-included. A new file must be re-included there or git won't see it.
- The owner can't clone. After each push, create a tag; they download `https://github.com/spike442/powerbi/archive/refs/tags/vX.Y.Z.zip`. Latest tag: **v2.2.0**.
- No `gh` CLI and no token, so no formal GitHub Releases.

## Production target (Report Server)
- Power BI Report Server **May 2026** (1.26.9682.1442). It accepts only a `.pbix` saved by **Power BI Desktop optimized for Report Server, May 2026**.
- A PBIP, or a `.pbix` from regular Desktop, cannot be deployed. So the PBIP is the reference design, and the `.pbix` is rebuilt by hand using `BUILD_PBIX.md`.
- The ODBC System DSN `HERA_CH` already exists on the server under the same name. The DSN is hard-coded in the M (no parameter).
- The admin handles credentials, scheduled refresh (daily, after the KPI snapshot load) and access (Browser role).

## Working with the owner
- Replies in **English**. Give Desktop menu names in French in brackets (Accueil → Transformer les données, …).
- Design: **minimal**. Default theme, no KPI cards or decoration, markers off. They rejected "styled" and "modern" redesigns and asked to revert to the plain look.
- They drop phone photos (`IMG_*.HEIC`) into the repo root. Convert to read them: `convert X.HEIC -resize 2000x2000 out.jpg`, writing to the scratchpad.
- Be explicit when something is assumed vs verified. Example: the PV/Cash column names were first guessed from the PNL pattern, the owner asked "where did you get them", and the photo then confirmed them.
- Never write a file in place with `open(f,'w').write(f(open(f).read()))`. This once truncated a file. Read first, then write.
