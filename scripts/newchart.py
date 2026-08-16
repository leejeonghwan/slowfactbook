#!/usr/bin/env python3
"""
항목 이름 하나로 새 차트를 만든다. 키노트를 거치지 않는다.

  1) 찾기      python3 scripts/newchart.py "청년 실업률"
                 → KOSIS·ECOS에서 후보를 찾아 번호를 매겨 보여준다
  2) 미리보기   python3 scripts/newchart.py "청년 실업률" --pick 3
                 → 표 + 그래프 HTML, 키노트용 TSV 를 만든다
  3) 등록      python3 scripts/newchart.py "청년 실업률" --pick 3 --add --category 노동
                 → data/api_charts.json 에 넣는다. 이후 빌드마다 API에서 최신값을
                   새로 받으므로 사람이 갱신할 일이 없다.

키노트에서 만든 기존 1,658개(origin=keynote)와 여기서 만든 것(origin=api)은
서로 다른 트랙이다. 섞이지 않는다.

  KOSIS_API_KEY=... ECOS_API_KEY=... python3 scripts/newchart.py ...
"""
import os, sys, json, html, argparse, urllib.parse, urllib.request, time, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "latest", "새차트")
CACHE_DIR = os.path.join(ROOT, ".cache")
KOSIS_KEY = os.environ.get("KOSIS_API_KEY", "")
CHARTS = os.path.join(DATA, "api_charts.json")
FREQ_KO = {"Y": "연간", "Q": "분기", "M": "월간", "H": "반기", "A": "연간", "S": "반기", "D": "일간"}


# ── KOSIS ──────────────────────────────────────────────────
def kosis(url, tries=3):
    last = None
    for t in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(0.8 + t)
    raise RuntimeError(str(last)[:100])


def kosis_search(term):
    u = ("https://kosis.kr/openapi/statisticsSearch.do?method=getList"
         f"&apiKey={urllib.parse.quote(KOSIS_KEY)}&format=json&jsonVD=Y"
         f"&searchNm={urllib.parse.quote(term)}")
    d = kosis(u)
    return d if isinstance(d, list) else []


def kosis_meta(org, tbl):
    u = ("https://kosis.kr/openapi/statisticsData.do?method=getMeta"
         f"&apiKey={urllib.parse.quote(KOSIS_KEY)}&format=json&jsonVD=Y"
         f"&orgId={org}&tblId={tbl}&type=ITM")
    d = kosis(u)
    return d if isinstance(d, list) else []


def kosis_data(spec, p0="1960", p1="2030"):
    q = {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
         "orgId": spec["orgId"], "tblId": spec["tblId"], "itmId": spec["itmId"],
         "prdSe": spec["prdSe"], "startPrdDe": spec.get("startPrdDe", p0),
         "endPrdDe": spec.get("endPrdDe", p1)}
    for i in range(1, 5):
        if spec.get(f"objL{i}"):
            q[f"objL{i}"] = spec[f"objL{i}"]
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + "&".join(f"{k}={urllib.parse.quote(str(v), safe='+')}" for k, v in q.items()))
    d = kosis(u)
    if not isinstance(d, list):
        return [], ""
    out, unit = {}, ""
    for r in d:
        try:
            out[r["PRD_DE"]] = float(r["DT"])
            unit = unit or r.get("UNIT_NM", "")
        except (TypeError, ValueError, KeyError):
            continue
    return sorted(out.items()), unit


def find_kosis(term, limit=6):
    """제목으로 통계표를 찾고, 각 표의 첫 항목·첫 분류로 실제 데이터를 확인한다."""
    cands = []
    for c in kosis_search(term)[:8]:
        tbl, org = c.get("TBL_ID"), c.get("ORG_ID")
        if not tbl or tbl.startswith("INH_"):
            continue
        try:
            mi = kosis_meta(org, tbl)
        except Exception:
            continue
        itms = [r for r in mi if r.get("OBJ_ID") == "ITEM"]
        objs = {}
        for r in mi:
            if r.get("OBJ_ID") != "ITEM":
                objs.setdefault(r["OBJ_ID"], []).append((r["ITM_ID"], r["ITM_NM"]))
        if not itms:
            continue
        keys = list(objs)
        for im in itms[:3]:
            spec = {"provider": "kosis", "orgId": org, "tblId": tbl,
                    "itmId": im["ITM_ID"] + "+", "prdSe": "Y"}
            for i, k in enumerate(keys, 1):
                spec[f"objL{i}"] = objs[k][0][0] + "+"
            for prd in ("Y", "M", "Q"):
                spec["prdSe"] = prd
                spec["startPrdDe"], spec["endPrdDe"] = ("1960", "2030") if prd == "Y" else \
                    ("196001", "203012") if prd == "M" else ("196001", "203004")
                try:
                    ser, unit = kosis_data(spec)
                except Exception:
                    continue
                if len(ser) >= 5:
                    cands.append({
                        "provider": "kosis", "spec": dict(spec),
                        "source": c.get("STAT_NM") or c.get("TBL_NM"),
                        "table": c.get("TBL_NM"), "tblId": tbl,
                        "item": im["ITM_NM"],
                        "obj": objs[keys[0]][0][1] if keys else "",
                        "cycle": prd, "unit": unit,
                        "n": len(ser), "first": ser[0][0], "last": ser[-1][0],
                        "lastVal": ser[-1][1], "series": ser,
                        "url": f"https://kosis.kr/statHtml/statHtml.do?orgId={org}&tblId={tbl}",
                    })
                    break
            if len(cands) >= limit:
                break
        if len(cands) >= limit:
            break
    return cands


# ── ECOS ───────────────────────────────────────────────────
def find_ecos(term, limit=6):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    try:
        import ecos
    except Exception:
        return []
    ip = os.path.join(CACHE_DIR, "ecos_index.json")
    if not os.path.exists(ip) or not os.environ.get("ECOS_API_KEY"):
        return []
    index = json.load(open(ip, encoding="utf-8"))
    ranked = sorted(index, key=lambda e: -ecos.score_title(term, e["statName"], e["itemName"]))
    ranked = [e for e in ranked
              if ecos.score_title(term, e["statName"], e["itemName"]) >= 0.5][:limit * 3]
    out = []
    for e in ranked:
        cyc = e["cycle"] or "A"
        lo, hi = ecos.span(cyc, "1960", "2030")
        try:
            ser = ecos.search(e["statCode"], cyc, lo, hi, e["itemCode"])
        except Exception:
            continue
        if len(ser) < 5:
            continue
        out.append({
            "provider": "ecos",
            "spec": {"provider": "ecos", "statCode": e["statCode"], "itemCode": e["itemCode"],
                     "cycle": cyc, "start": lo, "end": hi},
            "source": "한국은행 ECOS", "table": e["statName"], "tblId": e["statCode"],
            "item": e["itemName"], "obj": "", "cycle": cyc, "unit": e.get("unit") or "",
            "n": len(ser), "first": ser[0][0], "last": ser[-1][0],
            "lastVal": ser[-1][1], "series": ser,
            "url": f"https://ecos.bok.or.kr/#/Short/{e['statCode']}",
        })
        if len(out) >= limit:
            break
    return out


# ── 출력 ───────────────────────────────────────────────────
def pp(t, cyc):
    t = str(t)
    if cyc in ("M",) and len(t) == 6:
        return f"{t[:4]}-{t[4:]}"
    if cyc == "Q":
        return (f"{t[:4]} {t[4:].lstrip('0Q') or '1'}Q") if len(t) > 4 else t
    if cyc == "D" and len(t) == 8:
        return f"{t[:4]}-{t[4:6]}-{t[6:]}"
    return t[:4]


def preview(c, title, scale=1.0):
    os.makedirs(OUT, exist_ok=True)
    slug = re.sub(r"[^\w가-힣]+", "_", title)[:40]
    ser = c["series"]
    labels = [pp(p, c["cycle"]) for p, _ in ser]
    vals = [round(v * scale, 6) for _, v in ser]

    with open(os.path.join(OUT, f"{slug}.tsv"), "w", encoding="utf-8-sig") as f:
        f.write(f"# {title}\n# 출처: {c['source']} ({c['tblId']}) {c['url']}\n")
        f.write(f"# {FREQ_KO.get(c['cycle'],'')} · 단위 {c['unit']}"
                + (f" · 표시배수 ×{scale:g}" if scale != 1 else "") + "\n")
        f.write("시점\t값\n")
        for l, v in zip(labels, vals):
            f.write(f"{l}\t{v}\n")

    trs = "".join(f"<tr><td>{l}</td><td class=n>{v:,}</td></tr>" for l, v in zip(labels, vals))
    p = os.path.join(OUT, f"{slug}.html")
    open(p, "w", encoding="utf-8").write(f"""<!DOCTYPE html><html lang=ko><meta charset=utf-8>
<title>{html.escape(title)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script><style>
body{{font:14px/1.6 system-ui,-apple-system,"Apple SD Gothic Neo",sans-serif;background:#f7f7f5;margin:0;color:#1a1a1a}}
.w{{max-width:880px;margin:0 auto;padding:28px 20px 60px}}
h1{{font-size:22px;margin:0 0 4px}} .src{{color:#666;font-size:12.5px;margin-bottom:18px}}
.card{{background:#fff;border:1px solid #e5e5e2;border-radius:12px;padding:18px;margin-bottom:14px}}
table{{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}}
th,td{{padding:5px 8px;border-bottom:1px solid #f1f1ef;text-align:left}}
td.n{{text-align:right}} th{{color:#666;font-size:11.5px;background:#f4f4f2}}
.scroll{{max-height:420px;overflow:auto}} a{{color:#2f5e8e}}
.tip{{color:#666;font-size:12.5px;margin-top:8px}}
</style><div class=w>
<h1>{html.escape(title)}</h1>
<div class=src>{html.escape(c['source'])} · {html.escape(str(c['table']))} <a href="{c['url']}" target=_blank>{c['tblId']}</a>
 · {FREQ_KO.get(c['cycle'],'')} · 단위 {html.escape(c['unit'] or '')}
 {'· 표시배수 ×%g' % scale if scale != 1 else ''} · {labels[0]}~{labels[-1]} ({len(ser)}개)</div>
<div class=card><canvas id=c height=110></canvas></div>
<div class=card><div class=scroll><table><thead><tr><th>시점</th><th>값</th></tr></thead><tbody>{trs}</tbody></table></div>
<p class=tip>표를 그대로 드래그해 키노트·넘버스에 붙여넣으면 됩니다. 같은 폴더의 <b>{slug}.tsv</b>도 같은 내용입니다.</p></div>
<script>
new Chart(document.getElementById('c'), {{type:'line',
 data:{{labels:{json.dumps(labels, ensure_ascii=False)},
        datasets:[{{label:{json.dumps(title, ensure_ascii=False)},data:{json.dumps(vals)},
        borderColor:'#2f5e8e',backgroundColor:'rgba(47,94,142,.08)',borderWidth:2,
        pointRadius:0,tension:.15,fill:true}}]}},
 options:{{responsive:true,plugins:{{legend:{{display:false}}}},
   scales:{{x:{{ticks:{{maxTicksLimit:12,color:'#999'}},grid:{{display:false}}}},
            y:{{ticks:{{color:'#999'}},grid:{{color:'#eee'}}}}}}}}}});
</script></div></html>""")
    return p, os.path.join(OUT, f"{slug}.tsv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("term", help="찾을 항목 이름")
    ap.add_argument("--pick", type=int, help="후보 번호")
    ap.add_argument("--title", help="차트 제목 (기본: 검색어)")
    ap.add_argument("--category", default="새 데이터")
    ap.add_argument("--scale", type=float, default=1.0, help="표시 단위 배수 (예: 0.0001 = 만 단위)")
    ap.add_argument("--add", action="store_true", help="api_charts.json 에 등록")
    ap.add_argument("--source", choices=["kosis", "ecos", "both"], default="both")
    a = ap.parse_args()

    cands = []
    if a.source in ("kosis", "both") and KOSIS_KEY:
        cands += find_kosis(a.term)
    if a.source in ("ecos", "both"):
        cands += find_ecos(a.term)
    if not cands:
        print(f"'{a.term}' 후보를 찾지 못했습니다. 통계 용어에 가깝게 다시 써 보세요.")
        return 1

    if not a.pick:
        print(f"\n'{a.term}' 후보 {len(cands)}건\n")
        for i, c in enumerate(cands, 1):
            print(f"[{i}] {c['source']} · {str(c['table'])[:38]}")
            print(f"    {c['item']}{(' / ' + c['obj']) if c['obj'] else ''}  "
                  f"[{FREQ_KO.get(c['cycle'],'')}] {pp(c['first'],c['cycle'])}~{pp(c['last'],c['cycle'])} "
                  f"({c['n']}개) 최근값 {c['lastVal']:,} {c['unit']}")
        print(f"\n마음에 드는 번호로:  python3 scripts/newchart.py \"{a.term}\" --pick 1")
        return 0

    c = cands[a.pick - 1]
    title = a.title or a.term
    hp, tp = preview(c, title, a.scale)
    print(f"미리보기 → {hp}")
    print(f"TSV      → {tp}")
    print(f"출처     : {c['source']} · {c['table']} ({c['tblId']})")
    print(f"구간     : {pp(c['first'],c['cycle'])}~{pp(c['last'],c['cycle'])} "
          f"[{FREQ_KO.get(c['cycle'],'')}] 최근값 {c['lastVal']:,} {c['unit']}")

    if a.add:
        reg = json.load(open(CHARTS, encoding="utf-8")) if os.path.exists(CHARTS) else {}
        key = f"api-{len(reg)+1:04d}"
        reg[key] = {"title": title, "category": a.category, "origin": "api",
                    "scale": a.scale, "unit": c["unit"], "cycle": c["cycle"],
                    "source": c["source"], "sourceUrl": c["url"],
                    "table": c["table"], "tblId": c["tblId"], "item": c["item"],
                    **c["spec"]}
        json.dump(reg, open(CHARTS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"등록     : {key} → data/api_charts.json  (현재 {len(reg)}건)")
        print("다음 빌드부터 사이트에 나오고, 빌드할 때마다 최신값을 새로 받습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
