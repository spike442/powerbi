-- =====================================================================
-- Hera_SA.V_KPI_REC_DASHBOARD — single source for the 3 Power BI dashboards
--   (a) Closing Progress   : breakdown = 'Threshold', closing_scope IN ('Current','Previous')
--   (b) Snapshot Detail    : breakdown = 'Band', current_month_snapshot = 'Y'
--   (c) Yearly Trend       : breakdown = 'Threshold', year_trend_snapshot = 'Y'
-- FULL version (PNL + PV + Cash): run only once the 8 YPV/YCASH _ABOVE/_BELOW columns exist.
-- Power BI query: SELECT * FROM Hera_SA.V_KPI_REC_DASHBOARD
-- today() is evaluated at query time, i.e. at each Power BI refresh.
-- =====================================================================
CREATE OR REPLACE VIEW Hera_SA.V_KPI_REC_DASHBOARD ON CLUSTER hera_cluster_1S_2R AS
WITH latest AS (
    -- safety net: one snapshot per (REC_ID, PERIOD, day) = highest VERSION
    SELECT REC_ID, PERIOD, CMN_RECORD_DATE, max(VERSION) AS VERSION
    FROM Hera_SA.KPI_REC_ALL
    GROUP BY REC_ID, PERIOD, CMN_RECORD_DATE
),
unpivoted AS (
    -- unpivot the wide NB_/AMT_ columns into (component, threshold, band, nb, amt)
    SELECT
        k.PERIOD                AS period,
        k.CMN_RECORD_DATE       AS record_date,
        k.REC_ID                AS rec_id,
        k.ENT_ACC               AS entity,
        if(empty(k.CAT_NAME), '(No category)', k.CAT_NAME) AS product,  -- CAT_NAME is '' when not category-based
        tupleElement(m, 1)      AS component,
        tupleElement(m, 2)      AS threshold,
        tupleElement(m, 3)      AS band,
        tupleElement(m, 4)      AS band_order,
        tupleElement(m, 5)      AS nb,
        tupleElement(m, 6)      AS amt
    FROM Hera_SA.KPI_REC_ALL AS k
    ARRAY JOIN [
        ('PNL',  'Above', 'All', 0, NB_YPNL_BREAK_BGM_ECO_EUR_ABOVE,  AMT_YPNL_BREAK_BGM_ECO_EUR_ABOVE),
        ('PNL',  'Below', 'All', 0, NB_YPNL_BREAK_BGM_ECO_EUR_BELOW,  AMT_YPNL_BREAK_BGM_ECO_EUR_BELOW),
        ('PV',   'Above', 'All', 0, NB_YPV_BREAK_BGM_ECO_EUR_ABOVE,   AMT_YPV_BREAK_BGM_ECO_EUR_ABOVE),
        ('PV',   'Below', 'All', 0, NB_YPV_BREAK_BGM_ECO_EUR_BELOW,   AMT_YPV_BREAK_BGM_ECO_EUR_BELOW),
        ('Cash', 'Above', 'All', 0, NB_YCASH_BREAK_BGM_ECO_EUR_ABOVE, AMT_YCASH_BREAK_BGM_ECO_EUR_ABOVE),
        ('Cash', 'Below', 'All', 0, NB_YCASH_BREAK_BGM_ECO_EUR_BELOW, AMT_YCASH_BREAK_BGM_ECO_EUR_BELOW),
        -- amount bands (PNL only in the table, not split by threshold)
        ('PNL',  'All',   '1K - 100K',   1, NB_YPNL_BREAK_BGM_ECO_EUR_LE_100K, AMT_YPNL_BREAK_BGM_ECO_EUR_LE_100K),
        ('PNL',  'All',   '100K - 300K', 2, NB_YPNL_BREAK_BGM_ECO_EUR_LE_300K, AMT_YPNL_BREAK_BGM_ECO_EUR_LE_300K),
        ('PNL',  'All',   '300K - 500K', 3, NB_YPNL_BREAK_BGM_ECO_EUR_LE_500K, AMT_YPNL_BREAK_BGM_ECO_EUR_LE_500K),
        ('PNL',  'All',   '500K - 1M',   4, NB_YPNL_BREAK_BGM_ECO_EUR_LE_1M,   AMT_YPNL_BREAK_BGM_ECO_EUR_LE_1M),
        ('PNL',  'All',   '> 1M',        5, NB_YPNL_BREAK_BGM_ECO_EUR_GT_1M,   AMT_YPNL_BREAK_BGM_ECO_EUR_GT_1M)
    ] AS m
    WHERE (k.REC_ID, k.PERIOD, k.CMN_RECORD_DATE, k.VERSION) IN (SELECT REC_ID, PERIOD, CMN_RECORD_DATE, VERSION FROM latest)
),
agg AS (
    SELECT period, record_date, rec_id, entity, product, component, threshold, band, band_order,
           toInt64(sum(nb))    AS nb_breaks,
           toFloat64(sum(if(isFinite(amt), amt, 0))) AS amt_breaks   -- NaN seen in AMT_* (INT, 202609SA carry)
    FROM unpivoted
    GROUP BY period, record_date, rec_id, entity, product, component, threshold, band, band_order
),
ranked AS (
    SELECT
        agg.*,
        -- 202609SA -> 1 (current), 202608SA -> 2 (previous), ...
        dense_rank() OVER (ORDER BY substring(period, 1, 6) DESC)                AS closing_rank,
        -- day 1 = first snapshot of that closing; aligns current vs previous
        dateDiff('day', min(record_date) OVER (PARTITION BY period), record_date) + 1 AS closing_day,
        -- dashboard (c): latest snapshot of each closing ...
        max(record_date) OVER (PARTITION BY period)                              AS last_snapshot_date,
        -- ... for the closings of the CURRENT CLOSING's year (Jan 2027 still shows 2026 while closing 202612)
        substring(period, 1, 4) = max(substring(period, 1, 4)) OVER ()           AS in_closing_year
    FROM agg
)
SELECT
    period,
    record_date,
    closing_rank,
    multiIf(closing_rank = 1, 'Current', closing_rank = 2, 'Previous', 'Older')
        || ' (' || period || ')'                                                AS closing,
    multiIf(closing_rank = 1, 'Current', closing_rank = 2, 'Previous', 'Older') AS closing_scope,
    arrayElement(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
                 toUInt8(substring(period, 5, 2))) || ' ' || substring(period, 1, 4) AS closing_month,
    if(in_closing_year AND record_date = last_snapshot_date, 'Y', 'N')          AS year_trend_snapshot,
    closing_day,
    rec_id,
    -- friendly label; any other / future REC_ID shows as itself
    multiIf(positionCaseInsensitive(rec_id, 'CARRY') > 0, 'Carry',
            positionCaseInsensitive(rec_id, 'FRZ') > 0,   'PNL',
            rec_id)                                                             AS reconciliation,
    entity,
    product,
    component,
    threshold,
    band,
    band_order,
    -- dashboard (a) uses the Above/Below rows, dashboard (b) the amount-band rows
    if(band_order = 0, 'Threshold', 'Band')                                     AS breakdown,
    -- dashboard (b) date picker: current closing, current month, up to today
    if(closing_rank = 1 AND toStartOfMonth(record_date) = toStartOfMonth(today())
       AND record_date <= today(), 'Y', 'N')                                    AS current_month_snapshot,
    nb_breaks,
    amt_breaks
FROM ranked
WHERE closing_rank <= 2                                         -- (a), (b): current + previous, all days
   OR (in_closing_year AND record_date = last_snapshot_date)     -- (c): latest snapshot of each closing of the year;
