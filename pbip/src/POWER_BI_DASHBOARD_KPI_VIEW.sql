CREATE OR REPLACE VIEW Hera_SA.POWER_BI_DASHBOARD_KPI_VIEW ON CLUSTER hera_cluster_1S_2R AS
WITH latest_version AS (
    SELECT REC_ID, PERIOD, CMN_RECORD_DATE, max(VERSION) AS VERSION
    FROM Hera_SA.KPI_REC_ALL
    WHERE PERIOD >= toString(toYear(today()) - 1)
    GROUP BY REC_ID, PERIOD, CMN_RECORD_DATE
),
snapshots AS (
    SELECT k.*
    FROM Hera_SA.KPI_REC_ALL AS k
    INNER JOIN latest_version AS l
        ON  k.REC_ID = l.REC_ID
        AND k.PERIOD = l.PERIOD
        AND k.CMN_RECORD_DATE = l.CMN_RECORD_DATE
        AND k.VERSION = l.VERSION
    WHERE k.PERIOD >= toString(toYear(today()) - 1)
),
unpivoted AS (
    SELECT
        PERIOD                                         AS period,
        CMN_RECORD_DATE                                AS record_date,
        REC_ID                                         AS rec_id,
        ENT_ACC                                        AS entity,
        if(empty(CAT_NAME), '(No category)', CAT_NAME) AS product,
        tupleElement(m, 1)                             AS component,
        tupleElement(m, 2)                             AS threshold,
        tupleElement(m, 3)                             AS band,
        tupleElement(m, 4)                             AS band_order,
        tupleElement(m, 5)                             AS nb,
        tupleElement(m, 6)                             AS amt
    FROM snapshots
    ARRAY JOIN [
        ('PNL',  'Above', 'All',         0, toFloat64(NB_YPNL_BREAK_BGM_ECO_EUR_ABOVE),   toFloat64(AMT_YPNL_BREAK_BGM_ECO_EUR_ABOVE)),
        ('PNL',  'Below', 'All',         0, toFloat64(NB_YPNL_BREAK_BGM_ECO_EUR_BELOW),   toFloat64(AMT_YPNL_BREAK_BGM_ECO_EUR_BELOW)),
        ('PV',   'Above', 'All',         0, toFloat64(NB_YPV_BREAK_BGM_ECO_EUR_ABOVE),    toFloat64(AMT_YPV_BREAK_BGM_ECO_EUR_ABOVE)),
        ('PV',   'Below', 'All',         0, toFloat64(NB_YPV_BREAK_BGM_ECO_EUR_BELOW),    toFloat64(AMT_YPV_BREAK_BGM_ECO_EUR_BELOW)),
        ('Cash', 'Above', 'All',         0, toFloat64(NB_YCASH_BREAK_BGM_ECO_EUR_ABOVE),  toFloat64(AMT_YCASH_BREAK_BGM_ECO_EUR_ABOVE)),
        ('Cash', 'Below', 'All',         0, toFloat64(NB_YCASH_BREAK_BGM_ECO_EUR_BELOW),  toFloat64(AMT_YCASH_BREAK_BGM_ECO_EUR_BELOW)),
        ('PNL',  'All',   '1K - 100K',   1, toFloat64(NB_YPNL_BREAK_BGM_ECO_EUR_LE_100K), toFloat64(AMT_YPNL_BREAK_BGM_ECO_EUR_LE_100K)),
        ('PNL',  'All',   '100K - 300K', 2, toFloat64(NB_YPNL_BREAK_BGM_ECO_EUR_LE_300K), toFloat64(AMT_YPNL_BREAK_BGM_ECO_EUR_LE_300K)),
        ('PNL',  'All',   '300K - 500K', 3, toFloat64(NB_YPNL_BREAK_BGM_ECO_EUR_LE_500K), toFloat64(AMT_YPNL_BREAK_BGM_ECO_EUR_LE_500K)),
        ('PNL',  'All',   '500K - 1M',   4, toFloat64(NB_YPNL_BREAK_BGM_ECO_EUR_LE_1M),   toFloat64(AMT_YPNL_BREAK_BGM_ECO_EUR_LE_1M)),
        ('PNL',  'All',   '> 1M',        5, toFloat64(NB_YPNL_BREAK_BGM_ECO_EUR_GT_1M),   toFloat64(AMT_YPNL_BREAK_BGM_ECO_EUR_GT_1M))
    ] AS m
),
aggregated AS (
    SELECT
        period, record_date, rec_id, entity, product, component, threshold, band, band_order,
        toInt64(sum(nb))                            AS nb_breaks,
        toFloat64(sum(if(isFinite(amt), amt, 0)))   AS amt_breaks
    FROM unpivoted
    GROUP BY period, record_date, rec_id, entity, product, component, threshold, band, band_order
),
ranked AS (
    SELECT
        aggregated.*,
        dense_rank() OVER (ORDER BY substring(period, 1, 6) DESC)                       AS closing_rank,
        dateDiff('day', min(record_date) OVER (PARTITION BY period), record_date) + 1   AS closing_day,
        max(record_date) OVER (PARTITION BY period)                                     AS last_snapshot_date,
        substring(period, 1, 4) = max(substring(period, 1, 4)) OVER ()                  AS in_closing_year
    FROM aggregated
)
SELECT
    period,
    record_date,
    closing_rank,
    toUInt32(substring(period, 1, 6))                                                   AS closing_order,
    multiIf(closing_rank = 1, 'Current', closing_rank = 2, 'Previous', 'Older') || ' (' || period || ')' AS closing,
    multiIf(closing_rank = 1, 'Current', closing_rank = 2, 'Previous', 'Older')         AS closing_scope,
    arrayElement(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
                 toUInt8(substring(period, 5, 2))) || ' ' || substring(period, 1, 4)    AS closing_month,
    if(in_closing_year AND record_date = last_snapshot_date, 'Y', 'N')                  AS year_trend_snapshot,
    closing_day,
    rec_id,
    multiIf(positionCaseInsensitive(rec_id, 'CARRY') > 0, 'Carry',
            positionCaseInsensitive(rec_id, 'FRZ') > 0, 'PNL',
            rec_id)                                                                     AS reconciliation,
    entity,
    product,
    component,
    threshold,
    band,
    band_order,
    if(band_order = 0, 'Threshold', 'Band')                                             AS breakdown,
    if(closing_rank = 1
       AND toStartOfMonth(record_date) = toStartOfMonth(today())
       AND record_date <= today(), 'Y', 'N')                                            AS current_month_snapshot,
    nb_breaks,
    amt_breaks
FROM ranked
WHERE closing_rank <= 2
   OR (in_closing_year AND record_date = last_snapshot_date);
