#!/usr/bin/env python3
"""
Slow Factbook build pipeline.

  source/*.key | *.pptx  ->  data/*.json  ->  site/index.html

Run from repo root:
  python3 scripts/build.py

- .key files are parsed with extract_keynote.py (keynote-parser)
- .pptx files are parsed with extract_pptx.py (python-pptx)
- Category for each file is read from categories.json (keyed by filename stem);
  if absent, the cleaned filename is used.
- A build report (counts + failed/ image-only slides) is written to
  data/_report.json so you can see what needs a manual/vision pass.

Naming convention for source files:  NN_카테고리.key   e.g.  02_노동.key
The leading "NN_" is stripped for display; categories.json maps it to the
canonical category label.
"""
import os, sys, re, json, glob, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source")
DATA = os.path.join(ROOT, "data")
SITE = os.path.join(ROOT, "site")
SCRIPTS = os.path.join(ROOT, "scripts")

def load_categories():
    p = os.path.join(ROOT, "categories.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}

def stem(path):
    return os.path.splitext(os.path.basename(path))[0]

def display_name(s):
    return re.sub(r"^\d+[_\-\s]*", "", s)

def main():
    os.makedirs(DATA, exist_ok=True)
    os.makedirs(SITE, exist_ok=True)
    catmap = load_categories()
    report = {"files": [], "total_charts": 0, "needs_attention": []}

    sources = sorted(glob.glob(os.path.join(SRC, "*.key")) +
                     glob.glob(os.path.join(SRC, "*.pptx")))
    if not sources:
        print("No source files in source/. Drop *.key or *.pptx there.")

    for src in sources:
        s = stem(src)
        category = catmap.get(s) or catmap.get(display_name(s)) or display_name(s)
        out = os.path.join(DATA, s + ".json")
        ext = os.path.splitext(src)[1].lower()
        script = "extract_keynote.py" if ext == ".key" else "extract_pptx.py"
        print(f"\n== {os.path.basename(src)}  ->  {category}")
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), src, out],
                           capture_output=True, text=True)
        print(r.stdout.strip() or r.stderr.strip()[-300:])
        if not os.path.exists(out):
            report["needs_attention"].append({"file": os.path.basename(src), "error": "extract failed"})
            continue
        doc = json.load(open(out, encoding="utf-8"))
        doc["category"] = category
        json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        charts = doc.get("_charts", 0)
        report["total_charts"] += charts
        failed = doc.get("_failed", []) or doc.get("_image_only", [])
        report["files"].append({"file": os.path.basename(src), "category": category,
                                "charts": charts, "failed_or_image": len(failed)})
        if failed:
            report["needs_attention"].append({"file": os.path.basename(src), "items": failed})

    # build site from everything in data/
    sys.path.insert(0, SCRIPTS)
    import generate_site
    items = generate_site.build(DATA, os.path.join(SITE, "index.html"))
    report["site_items"] = len(items)
    json.dump(report, open(os.path.join(DATA, "_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nDONE. charts={report['total_charts']} site_items={len(items)} "
          f"needs_attention={len(report['needs_attention'])}")
    print("See data/_report.json for slides needing a manual/vision pass.")

if __name__ == "__main__":
    main()
