# Build the production .pbix (Power BI Desktop for Report Server)

The Report Server only accepts a `.pbix` saved by **Power BI Desktop optimized for Report Server, May 2026**.
The `project/` PBIP is the reference design: open it in regular Power BI Desktop next to RS Desktop and copy what you see.
Files to paste from: `src/03_FactBreaks.pq`, `src/04_measures.dax`. French menu names in brackets.

## 0. Before you start
- [ ] The view exists on the target ClickHouse: run `src/05_view_kpi_rec_dashboard.sql` (ON CLUSTER) on INT, then PROD.
- [ ] Check: `SELECT breakdown, component, threshold, count() FROM Hera_SA.V_KPI_REC_DASHBOARD GROUP BY 1, 2, 3 ORDER BY 1, 2, 3`
      → Threshold rows for PNL / PV / Cash × Above / Below, Band rows for PNL.
- [ ] RS Desktop: Help → About (Aide → À propos) says **May 2026**. File → New.
- [ ] File → Options → Current file → Data load (Fichier actuel → Chargement des données): untick
      **Auto date/time** (Date/heure automatique).

## 1. Data (10 min)
1. Home → Transform data (Accueil → Transformer les données).
2. New Source → Blank Query (Nouvelle source → Requête vide) → Advanced Editor (Éditeur avancé):
   delete everything, paste `src/03_FactBreaks.pq` (the `//` lines can stay).
3. Rename the query **`FactBreaks`**. Approve the native query prompt if asked.
4. Preview: **20 columns**, `record_date` is a date. Close & Apply (Fermer et appliquer).

## 2. Model (5 min)
Data view (Vue Données), select the column → Column tools → Sort by column (Outils de colonne → Trier par colonne):

| Column | Sort by |
|---|---|
| `closing` | `closing_rank` |
| `band` | `band_order` |
| `closing_month` | `closing_order` |

Summarization (Résumé) → **Don't summarize** on `closing_rank`, `closing_order`, `closing_day`, `band_order`, `nb_breaks`, `amt_breaks`.
Format `record_date` as `dd/mm/yyyy`.

## 3. Measures (15 min)
Select table `FactBreaks` → Home → New measure (Nouvelle mesure). Paste each block of `src/04_measures.dax`
(from the `Name =` line to the blank line), **in this order**, then set the format:

| # | Measure | Format |
|---|---|---|
| 1 | Breaks # | `#,0` |
| 2 | Residual Amount (EUR) | `#,0` |
| 3 | Snapshot Date | `dd/mm/yyyy` |
| 4 | Current Closing Day | `0` |
| 5 | Breaks # Current | `#,0` |
| 6 | Breaks # Previous | `#,0` |
| 7 | Breaks # vs Previous | `#,0` |
| 8 | Residual Amount Current | `#,0` |
| 9 | Residual Amount Previous | `#,0` |
| 10 | Residual Amount vs Previous | `#,0` |
| 11 | Snapshot Subtitle | text |
| 12 | Year Subtitle | text |

## 4. Page "Closing Progress" (20 min)
Canvas 1280 × 720 (Format page → Paramètres du canevas).

**Page filters**, then hide each one with the eye icon (Masquer en mode lecture):
`breakdown` = Threshold · `closing_scope` = Current, Previous.

**Slicers** (top row, style **Dropdown** / Liste déroulante; rename the field in the well to set the header):

| Header | Field | Selection | Saved state |
|---|---|---|---|
| Reconciliation | `reconciliation` | Multi + Select all | all |
| Entity | `entity` | Multi + Select all | all |
| Product | `product` | Multi + Select all | all |
| PNL Component | `component` | Single select (Sélection unique) | **PNL** |
| Threshold | `threshold` | Single select | **Above** |

**Line chart, full width** – "Number of breaks per closing day":
X `closing_day` (type **Continuous**, title "Closing day") · Y `Breaks #` · Legend `closing` ·
Tooltips `Snapshot Date`, `Breaks # vs Previous` · markers off · legend top.

**Two line charts below, side by side** – "Residual amount per closing day – Above" / "– Below":
same as above but Y `Residual Amount (EUR)`, Tooltips `Snapshot Date`, `Residual Amount vs Previous`,
and a **visual filter** (Filtres de ce visuel) `threshold` = Above (left) / Below (right).

**Interactions:** select the Threshold slicer → Format → Edit interactions (Modifier les interactions)
→ **None** (⊘) on both amount charts.

## 5. Page "Snapshot Detail" (10 min)
New page, 1280 × 720. Hidden page filters: `breakdown` = Band · `current_month_snapshot` = Y.

Slicers (Dropdown): "Snapshot date (latest if empty)" `record_date` single select, **left empty** ·
Reconciliation · Entity · Product (multi + select all).

Two clustered column charts (Histogramme groupé), side by side, X `band`, axis sorted by `band` ascending, data labels on:
- "Number of breaks per amount band" – Y `Breaks #`
- "Residual amount per amount band (EUR)" – Y `Residual Amount (EUR)`
- Subtitle on → **fx** → Field value (Valeur du champ) → `Snapshot Subtitle`.

## 6. Page "Yearly Trend" (10 min)
New page, 1280 × 720. Hidden page filters: `breakdown` = Threshold · `year_trend_snapshot` = Y.

Slicers: copy the 5 from page 1 (Ctrl+C / Ctrl+V, **Don't sync** / Ne pas synchroniser); keep PNL and Above.

Two clustered column charts, X `closing_month` sorted ascending, data labels on:
- "Number of breaks per closing" – Y `Breaks #`
- "Net residual amount per closing (EUR)" – Y `Residual Amount (EUR)`
- Subtitle **fx** → `Year Subtitle`.

## 7. Check and save (10 min)
- [ ] Refresh; same numbers as the PBIP in regular Desktop, page by page.
- [ ] Page 1 legend: only Current and Previous. Page 2 dates: current month only. Page 3: one bar per closing of the year.
- [ ] Component PV / Cash shows data on pages 1 and 3.
- [ ] Reset slicers to the saved state above (date empty), go to page 1, save **`KPI_Closing_Progress.pbix`**.

If subtitles / fx are missing in RS Desktop, skip them (information only).

## 8. Hand-off note for the Report Server admin
> **KPI_Closing_Progress.pbix** – Power BI Desktop for Report Server May 2026.
> - Data source: ODBC `dsn=HERA_CH` (System DSN, 64-bit), ClickHouse view `Hera_SA.V_KPI_REC_DASHBOARD` (already created).
> - After upload: Manage → Data sources → set the credentials, Test connection, then refresh once.
> - Scheduled refresh: **daily, after the KPI snapshot load** (the "current month" and "current closing" are computed at refresh).
> - Access: Browser role for the readers.
