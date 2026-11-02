"""Generate the KPI Closing Progress Power BI Project (PBIP: TMDL model + PBIR report).

Usage:  python3 build_pbip.py

Data    : ClickHouse view Hera_SA.POWER_BI_DASHBOARD_KPI_VIEW (src/POWER_BI_DASHBOARD_KPI_VIEW.sql), ODBC DSN HERA_CH
Inputs  : src/03_FactBreaks.pq, src/04_measures.dax, src/CY25SU12.json
Output  : project/KPI_Closing_Progress.pbip + .Report/ + .SemanticModel/  -> open the .pbip in Power BI Desktop

Pages   : Closing Progress (a), Snapshot Detail (b), Yearly Trend (c)
"""
import json
import re
import shutil
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
NAME = "KPI_Closing_Progress"
TABLE = "FactBreaks"
NS = uuid.UUID("6f1c2a52-8d0e-4b8e-9a51-0c3b7f0d2a11")

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
THEME = "CY25SU12"


def tag(key):
    """Stable lineageTag so regenerating doesn't churn the model."""
    return str(uuid.uuid5(NS, key))


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(content, str):
        content = json.dumps(content, indent=2, ensure_ascii=False) + "\n"
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------- semantic model

COLUMNS = [  # name, TMDL dataType, formatString
    ("period", "string", None),
    ("record_date", "dateTime", "dd/mm/yyyy"),
    ("closing_rank", "int64", "0"),
    ("closing_order", "int64", "0"),
    ("closing", "string", None),
    ("closing_scope", "string", None),
    ("closing_month", "string", None),
    ("year_trend_snapshot", "string", None),
    ("closing_day", "int64", "0"),
    ("reconciliation", "string", None),
    ("entity", "string", None),
    ("product", "string", None),
    ("component", "string", None),
    ("threshold", "string", None),
    ("band", "string", None),
    ("band_order", "int64", "0"),
    ("breakdown", "string", None),
    ("current_month_snapshot", "string", None),
    ("nb_breaks", "int64", "#,0"),
    ("amt_breaks", "double", "#,0"),
]

SORT_BY = {"closing": "closing_rank", "band": "band_order", "closing_month": "closing_order"}

MEASURE_FORMATS = {
    "Snapshot Date": "dd/mm/yyyy",
    "Current Closing Day": "0",
    "Snapshot Subtitle": None,
    "Year Subtitle": None,
}


def read_measures():
    """Parse 04_measures.dax: a measure is 'Name =' right after a blank line, body runs to the next blank."""
    measures, current, prev_blank = [], None, True
    for line in (SRC / "04_measures.dax").read_text(encoding="utf-8").splitlines():
        if line.startswith("//"):
            continue
        m = re.match(r"^(\S.*?) =\s*(.*)$", line)
        if m and prev_blank:
            current = [m.group(1), [m.group(2)] if m.group(2) else []]
            measures.append(current)
        elif current is not None and line.strip():
            current[1].append(line)
        prev_blank = not line.strip()
    return [(n, "\n".join(body).strip("\n")) for n, body in measures]


def read_m_query():
    pq = SRC / "03_FactBreaks.pq"
    lines = [l for l in pq.read_text(encoding="utf-8").splitlines() if not l.startswith("//")]
    return "\n".join(lines).strip("\n")


def indent(text, tabs):
    pad = "\t" * tabs
    return "\n".join(pad + l if l.strip() else "" for l in text.splitlines())


def q(name):
    return f"'{name}'" if re.search(r"[^A-Za-z0-9_]", name) else name


def build_model(root):
    sm = root / f"{NAME}.SemanticModel"
    write(sm / "definition.pbism", {
        "$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.0",
        "settings": {},
    })
    write(sm / "definition" / "database.tmdl", "database\n\tcompatibilityLevel: 1567\n")
    write(sm / "definition" / "model.tmdl", (
        "model Model\n"
        "\tculture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: en-US\n"
        "\tdataAccessOptions\n"
        "\t\tlegacyRedirects\n"
        "\t\treturnErrorValuesAsNull\n"
        "\n"
        f'annotation PBI_QueryOrder = ["{TABLE}"]\n'
        "\n"
        "annotation __PBI_TimeIntelligenceEnabled = 0\n"
        "\n"
        f"ref table {TABLE}\n"
    ))

    out = [f"table {TABLE}", f"\tlineageTag: {tag('table')}", ""]
    for name, body in read_measures():
        out.append(f"\tmeasure {q(name)} =")
        out.append(indent(body, 3))
        fmt = MEASURE_FORMATS.get(name, "#,0")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out.append(f"\t\tlineageTag: {tag('measure:' + name)}")
        out.append("")
    for name, dtype, fmt in COLUMNS:
        out.append(f"\tcolumn {name}")
        out.append(f"\t\tdataType: {dtype}")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out.append(f"\t\tlineageTag: {tag('column:' + name)}")
        out.append("\t\tsummarizeBy: none")
        out.append(f"\t\tsourceColumn: {name}")
        if name in SORT_BY:
            out.append(f"\t\tsortByColumn: {SORT_BY[name]}")
        out.append("")
        out.append("\t\tannotation SummarizationSetBy = User")
        out.append("")
    out.append(f"\tpartition {TABLE} = m")
    out.append("\t\tmode: import")
    out.append("\t\tsource =")
    out.append(indent(read_m_query(), 4))
    out.append("")
    out.append("\tannotation PBI_ResultType = Table")
    write(sm / "definition" / "tables" / f"{TABLE}.tmdl", "\n".join(out) + "\n")


# ---------------------------------------------------------------- report helpers

def col(prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": TABLE}}, "Property": prop}}


def meas(prop):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": TABLE}}, "Property": prop}}


def proj(field, display=None):
    kind = "Column" if "Column" in field else "Measure"
    prop = field[kind]["Property"]
    p = {"field": field, "queryRef": f"{TABLE}.{prop}", "nativeQueryRef": prop}
    if display:
        p["displayName"] = display
    return p


def lit(value):
    return {"expr": {"Literal": {"Value": value}}}


def in_filter(prop, values):
    return {
        "Version": 2,
        "From": [{"Name": "f", "Entity": TABLE, "Type": 0}],
        "Where": [{"Condition": {"In": {
            "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "f"}}, "Property": prop}}],
            "Values": [[{"Literal": {"Value": f"'{v}'"}}] for v in values],
        }}}],
    }


def solid(color):
    return {"solid": {"color": {"expr": color} if isinstance(color, dict) else lit(f"'{color}'")}}


def text_value(text):
    """A literal string, or a measure (dict from meas()) evaluated at runtime."""
    return {"expr": text} if isinstance(text, dict) else lit(f"'{text}'")


def title(text, subtitle=None, subtitle_color=None):
    objs = {"title": [{"properties": {"show": lit("true"), "text": text_value(text)}}]}
    if subtitle:
        props = {"show": lit("true"), "text": text_value(subtitle)}
        if subtitle_color:
            props["fontColor"] = solid(subtitle_color)
        objs["subTitle"] = [{"properties": props}]
    return objs


def container(name, x, y, w, h, z, visual, filters=None):
    v = {
        "$schema": f"{SCHEMA}/item/report/definition/visualContainer/1.5.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z},
        "visual": visual,
    }
    if filters:
        v["filterConfig"] = {"filters": filters}
    return v


def slicer(name, column, label, x, y, w, h, z, single=False, default=None):
    objects = {
        "data": [{"properties": {"mode": lit("'Dropdown'")}}],
        "selection": [{"properties": (
            {"singleSelect": lit("true")} if single
            else {"singleSelect": lit("false"), "selectAllCheckboxEnabled": lit("true")}
        )}],
    }
    if default:
        objects["general"] = [{"properties": {"filter": {"filter": in_filter(column, [default])}}}]
    return container(name, x, y, w, h, z, {
        "visualType": "slicer",
        "query": {"queryState": {"Values": {"projections": [proj(col(column), label)]}}},
        "objects": objects,
        "drillFilterOtherVisuals": True,
    })


def line_chart(name, measure, label, tooltips, x, y, w, h, z, threshold=None, subtitle=None):
    day = col("closing_day")
    filters = None
    if threshold:
        filters = [{
            "name": f"{name}_threshold",
            "field": col("threshold"),
            "type": "Categorical",
            "filter": in_filter("threshold", [threshold]),
        }]
    return container(name, x, y, w, h, z, {
        "visualType": "lineChart",
        "query": {
            "queryState": {
                "Category": {"projections": [proj(day, "Closing day")]},
                "Series": {"projections": [proj(col("closing"), "Closing")]},
                "Y": {"projections": [proj(meas(measure))]},
                "Tooltips": {"projections": [proj(meas(t)) for t in tooltips]},
            },
            "sortDefinition": {"sort": [{"field": day, "direction": "Ascending"}], "isDefaultSort": True},
        },
        "objects": {
            "categoryAxis": [{"properties": {
                "axisType": lit("'Scalar'"),
                "showAxisTitle": lit("true"),
                "titleText": lit("'Closing day'"),
            }}],
            "lineStyles": [{"properties": {"showMarker": lit("false")}}],
            "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}],
        },
        "visualContainerObjects": title(label, subtitle),
        "drillFilterOtherVisuals": True,
    }, filters)


def page_filter(name, column, *values):
    """Technical page filter, hidden from report readers."""
    return {"name": name, "field": col(column), "type": "Categorical",
            "filter": in_filter(column, list(values)), "isHiddenInViewMode": True}


def column_chart(name, measure, label, x, y, w, h, z, subtitle=None, category="band", category_name="Amount band"):
    band = col(category)
    return container(name, x, y, w, h, z, {
        "visualType": "clusteredColumnChart",
        "query": {
            "queryState": {
                "Category": {"projections": [proj(band, category_name)]},
                "Y": {"projections": [proj(meas(measure))]},
            },
            "sortDefinition": {"sort": [{"field": band, "direction": "Ascending"}], "isDefaultSort": True},
        },
        "objects": {
            "labels": [{"properties": {"show": lit("true")}}],
            "categoryAxis": [{"properties": {"showAxisTitle": lit("false")}}],
        },
        "visualContainerObjects": title(label, subtitle),
        "drillFilterOtherVisuals": True,
    })


# ---------------------------------------------------------------- report

def build_report(root):
    rp = root / f"{NAME}.Report"
    write(rp / "definition.pbir", {
        "$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}},
    })
    d = rp / "definition"
    write(d / "version.json", {
        "$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })
    write(d / "report.json", {
        "$schema": f"{SCHEMA}/item/report/definition/report/1.2.0/schema.json",
        "themeCollection": {"baseTheme": {"name": THEME, "reportVersionAtImport": "5.61", "type": "SharedResources"}},
        "layoutOptimization": "None",
        "resourcePackages": [{
            "name": "SharedResources",
            "type": "SharedResources",
            "items": [{"name": THEME, "path": f"BaseThemes/{THEME}.json", "type": "BaseTheme"}],
        }],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True},
    })
    themes = rp / "StaticResources" / "SharedResources" / "BaseThemes"
    themes.mkdir(parents=True, exist_ok=True)
    shutil.copy(SRC / f"{THEME}.json", themes / f"{THEME}.json")

    page = "closingProgress"
    write(d / "pages" / "pages.json", {
        "$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [page, "snapshotDetail", "yearlyTrend"],
        "activePageName": page,
    })

    # 1280 x 720, 16px gutters: filters row, chart 1, chart 2 (Above | Below)
    W, G, GAP = 1280, 16, 16
    visuals = []
    sw = (W - 2 * G - 4 * GAP) / 5
    for i, (nm, c, lbl, single, default) in enumerate([
        ("slicerRec", "reconciliation", "Reconciliation", False, None),
        ("slicerEntity", "entity", "Entity", False, None),
        ("slicerProduct", "product", "Product", False, None),
        ("slicerComponent", "component", "PNL Component", True, "PNL"),
        ("slicerThreshold", "threshold", "Threshold", True, "Above"),
    ]):
        visuals.append(slicer(nm, c, lbl, round(G + i * (sw + GAP)), 8, round(sw), 72, 2000 + i, single, default))
    visuals.append(line_chart(
        "chartBreaks", "Breaks #", "Number of breaks per closing day",
        ["Snapshot Date", "Breaks # vs Previous"], G, 92, W - 2 * G, 300, 3000))
    half = (W - 2 * G - GAP) / 2
    for i, thr in enumerate(["Above", "Below"]):
        visuals.append(line_chart(
            f"chartAmt{thr}", "Residual Amount (EUR)", f"Residual amount per closing day – {thr}",
            ["Snapshot Date", "Residual Amount vs Previous"],
            round(G + i * (half + GAP)), 404, round(half), 308, 3001 + i, threshold=thr))

    write(d / "pages" / page / "page.json", {
        "$schema": f"{SCHEMA}/item/report/definition/page/1.4.0/schema.json",
        "name": page,
        "displayName": "Closing Progress",
        "displayOption": "FitToPage",
        "height": 720,
        "width": W,
        "filterConfig": {"filters": [
            page_filter("pageA_breakdown", "breakdown", "Threshold"),
            page_filter("pageA_closings", "closing_scope", "Current", "Previous"),
        ]},
        # chart 2 = threshold "All": the threshold slicer must not filter it
        "visualInteractions": [
            {"source": "slicerThreshold", "target": t, "type": "NoFilter"}
            for t in ("chartAmtAbove", "chartAmtBelow")
        ],
    })
    for v in visuals:
        write(d / "pages" / page / "visuals" / v["name"] / "visual.json", v)

    build_snapshot_page(d, W, G, GAP)
    build_yearly_page(d, W, G, GAP)


def build_snapshot_page(d, W, G, GAP):
    """Dashboard (b): current closing, one snapshot date, breaks per amount band.
    Bands exist only for PNL and are not split by threshold, so no Component/Threshold slicers."""
    page = "snapshotDetail"
    visuals = []
    sw = (W - 2 * G - 3 * GAP) / 4
    for i, (nm, c, lbl, single) in enumerate([
        ("slicerDateB", "record_date", "Snapshot date (latest if empty)", True),
        ("slicerRecB", "reconciliation", "Reconciliation", False),
        ("slicerEntityB", "entity", "Entity", False),
        ("slicerProductB", "product", "Product", False),
    ]):
        visuals.append(slicer(nm, c, lbl, round(G + i * (sw + GAP)), 8, round(sw), 72, 2000 + i, single))
    half = (W - 2 * G - GAP) / 2
    for i, (nm, m, lbl) in enumerate([
        ("chartBandCount", "Breaks #", "Number of breaks per amount band"),
        ("chartBandAmount", "Residual Amount (EUR)", "Residual amount per amount band (EUR)"),
    ]):
        visuals.append(column_chart(nm, m, lbl, round(G + i * (half + GAP)), 92, round(half), 620, 3000 + i,
                                    subtitle=meas("Snapshot Subtitle")))
    write(d / "pages" / page / "page.json", {
        "$schema": f"{SCHEMA}/item/report/definition/page/1.4.0/schema.json",
        "name": page,
        "displayName": "Snapshot Detail",
        "displayOption": "FitToPage",
        "height": 720,
        "width": W,
        "filterConfig": {"filters": [
            page_filter("pageB_breakdown", "breakdown", "Band"),
            page_filter("pageB_currentMonth", "current_month_snapshot", "Y"),
        ]},
    })
    for v in visuals:
        write(d / "pages" / page / "visuals" / v["name"] / "visual.json", v)


def build_yearly_page(d, W, G, GAP):
    """Dashboard (c): one bar per closing of the current closing's year, latest snapshot of each."""
    page = "yearlyTrend"
    visuals = []
    sw = (W - 2 * G - 4 * GAP) / 5
    for i, (nm, c, lbl, single, default) in enumerate([
        ("slicerRecC", "reconciliation", "Reconciliation", False, None),
        ("slicerEntityC", "entity", "Entity", False, None),
        ("slicerProductC", "product", "Product", False, None),
        ("slicerComponentC", "component", "PNL Component", True, "PNL"),
        ("slicerThresholdC", "threshold", "Threshold", True, "Above"),
    ]):
        visuals.append(slicer(nm, c, lbl, round(G + i * (sw + GAP)), 8, round(sw), 72, 2000 + i, single, default))
    half = (W - 2 * G - GAP) / 2
    for i, (nm, m, lbl) in enumerate([
        ("chartYearCount", "Breaks #", "Number of breaks per closing"),
        ("chartYearAmount", "Residual Amount (EUR)", "Net residual amount per closing (EUR)"),
    ]):
        visuals.append(column_chart(nm, m, lbl, round(G + i * (half + GAP)), 92, round(half), 620, 3000 + i,
                                    subtitle=meas("Year Subtitle"),
                                    category="closing_month", category_name="Closing"))
    write(d / "pages" / page / "page.json", {
        "$schema": f"{SCHEMA}/item/report/definition/page/1.4.0/schema.json",
        "name": page,
        "displayName": "Yearly Trend",
        "displayOption": "FitToPage",
        "height": 720,
        "width": W,
        "filterConfig": {"filters": [
            page_filter("pageC_breakdown", "breakdown", "Threshold"),
            page_filter("pageC_yearTrend", "year_trend_snapshot", "Y"),
        ]},
    })
    for v in visuals:
        write(d / "pages" / page / "visuals" / v["name"] / "visual.json", v)


def main():
    out = HERE / "project"
    if out.exists():
        shutil.rmtree(out)
    build_model(out)
    build_report(out)
    write(out / f"{NAME}.pbip", {
        "$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })
    write(out / ".gitignore", "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
    print(f"generated {out}")


if __name__ == "__main__":
    main()

