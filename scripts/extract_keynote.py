#!/usr/bin/env python3
"""
Keynote -> structured JSON extractor (Slow Factbook).

Usage:
  python3 extract_keynote.py input.key output.json

Requires: keynote-parser, pyyaml
  pip install keynote-parser pyyaml --break-system-packages

Pulls, for every slide: title text, source/unit line, and the native
Keynote chart (type + series names + category labels + numeric grid).
Slides whose .iwa fails to deserialize are reported in "_failed" for
a vision-based fallback pass.
"""
import sys, os, re, json, glob, tempfile, subprocess

CHART_TYPE_MAP = {
    "lineChartType2D": "line",
    "columnChartType2D": "column",
    "barChartType2D": "bar",
    "stackedBarChartType2D": "stacked_bar",     # vertical stacked columns
    "stackedColumnChartType2D": "stacked_bar",
    "pieChartType2D": "pie",
    "twoAxisChartType2D": "two_axis",
    "areaChartType2D": "area",
    "scatterChartType2D": "scatter",
}

def find_nodes(node, pred, out):
    if isinstance(node, dict):
        if pred(node): out.append(node)
        for v in node.values(): find_nodes(v, pred, out)
    elif isinstance(node, list):
        for v in node: find_nodes(v, pred, out)

def collect_key(node, key, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key: out.append(v)
            collect_key(v, key, out)
    elif isinstance(node, list):
        for v in node: collect_key(v, key, out)

def cell_value(cell):
    if isinstance(cell, dict) and "numericValue" in cell:
        return cell["numericValue"]
    return None

def parse_chart(ch):
    g = ch.get("grid", {}) or {}
    cols = g.get("columnName") or []
    rows = g.get("rowName") or []
    grid = g.get("gridRow") or []
    # matrix[row][col]
    series = [[] for _ in cols] if cols else [[]]
    for r in grid:
        vals = r.get("value") if isinstance(r, dict) else None
        vals = vals or []
        for j in range(len(series)):
            series[j].append(cell_value(vals[j]) if j < len(vals) else None)
    return {
        "chartType_raw": ch.get("chartType"),
        "vizType": CHART_TYPE_MAP.get(ch.get("chartType"), ch.get("chartType")),
        "seriesNames": [c if c not in ("", "Untitled 1") else None for c in cols],
        "labels": rows,
        "series": series,
    }

def clean_text(s):
    return re.sub(r"\s+", " ", s.replace("￼", "")).strip()

def extract_slide_texts(doc):
    runs = []
    collect_key(doc, "text", runs)
    flat = []
    for r in runs:
        if isinstance(r, list):
            for s in r:
                if isinstance(s, str): flat.append(clean_text(s))
        elif isinstance(r, str):
            flat.append(clean_text(r))
    flat = [s for s in flat if s]
    return flat

UNIT_RE = re.compile(r"단위|출처|통계청|국가데이터처|노동부|고용노동부|조사|기준|OECD|, 20\d\d")
URL_RE = re.compile(r"https?://\S+")

def pick_meta(texts):
    title = texts[0] if texts else ""
    source = ""
    url = ""
    for t in texts[1:]:
        if URL_RE.search(t) and not url:
            url = URL_RE.search(t).group(0)
        elif UNIT_RE.search(t) and not source:
            source = t
    return title, source, url

def main(inp, outp):
    workdir = tempfile.mkdtemp()
    unpack = os.path.join(workdir, "unpacked")
    res = subprocess.run(["keynote-parser", "unpack", inp, "--output", unpack],
                         capture_output=True, text=True)
    failed = re.findall(r"Failed to process file (\S+)", res.stderr + res.stdout)

    import yaml
    idx = os.path.join(unpack, "Index")
    items = []
    for f in sorted(glob.glob(os.path.join(idx, "Slide-*.yaml"))):
        docs = list(yaml.safe_load_all(open(f, encoding="utf-8")))
        charts = []
        for d in docs:
            find_nodes(d, lambda n: "chartType" in n and "grid" in n, charts)
        texts = []
        for d in docs:
            texts += extract_slide_texts(d)
        title, source, url = pick_meta(texts)
        slide_id = os.path.basename(f).replace(".iwa.yaml", "")
        if not charts:
            items.append({"slide": slide_id, "title": title, "source": source,
                          "sourceUrl": url, "vizType": None, "note": "no native chart"})
            continue
        for ci, ch in enumerate(charts):
            parsed = parse_chart(ch)
            items.append({
                "slide": slide_id,
                "title": title + (f" ({ci+1})" if len(charts) > 1 else ""),
                "source": source, "sourceUrl": url,
                **parsed,
            })
    out = {"_source_file": os.path.basename(inp),
           "_slides": len(set(i["slide"] for i in items)),
           "_charts": sum(1 for i in items if i.get("vizType")),
           "_failed": failed, "items": items}
    json.dump(out, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"slides={out['_slides']} charts={out['_charts']} failed={len(failed)} -> {outp}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
