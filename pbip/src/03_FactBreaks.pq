// =====================================================================
// FactBreaks — Power Query (M), reads the ClickHouse view (05_view_kpi_rec_dashboard.sql)
// RS Desktop: Home > Transform data > New Source > Blank Query > Advanced Editor > paste
// DSN HERA_CH must exist (same name on your PC and on the Report Server)
// =====================================================================
let
    Source = Odbc.Query("dsn=HERA_CH",
        "SELECT period, record_date, closing_rank, closing_order, closing, closing_scope, closing_month, year_trend_snapshot, closing_day, reconciliation, entity, product, component, threshold, band, band_order, breakdown, current_month_snapshot, nb_breaks, amt_breaks FROM Hera_SA.V_KPI_REC_DASHBOARD"),
    Typed = Table.TransformColumnTypes(Source, {
        {"period", type text},
        {"record_date", type date},
        {"closing_rank", Int64.Type},
        {"closing_order", Int64.Type},
        {"closing", type text},
        {"closing_scope", type text},
        {"closing_month", type text},
        {"year_trend_snapshot", type text},
        {"closing_day", Int64.Type},
        {"reconciliation", type text},
        {"entity", type text},
        {"product", type text},
        {"component", type text},
        {"threshold", type text},
        {"band", type text},
        {"band_order", Int64.Type},
        {"breakdown", type text},
        {"current_month_snapshot", type text},
        {"nb_breaks", Int64.Type},
        {"amt_breaks", type number}
    })
in
    Typed
