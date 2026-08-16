#!/usr/bin/env python3
"""
매핑된 차트의 최신 원본 데이터를 받아 ① 키노트용 TSV ② 버전 대장 ③ 카탈로그를 만든다.

  data/api_map*.json ──▶ KOSIS API ──┬─▶ latest/tsv/<id>_<제목>.tsv   키노트·넘버스 붙여넣기용
                                     ├─▶ data/versions.json           차트별 버전 대장
                                     └─▶ latest/index.html            갱신 필요 차트 카탈로그

버전 대장(versions.json)이 '교통정리'의 핵심이다. 차트 하나에 시점이 셋 있다.

  chartLast   지금 차트가 담고 있는 마지막 시점   (data/full.json = 키노트에서 뽑은 것)
  apiLast     KOSIS 원본의 마지막 시점
  keynoteSync 키노트에 이미 반영했는지 (사람이 표시)

  chartLast == apiLast              → 최신 (current)
  chartLast <  apiLast              → 갱신 필요 (stale)
  chartLast >  apiLast              → 차트가 앞섬 (ahead) — 추계·전망이 섞인 경우

TSV는 매칭 때 복원한 실제 시점(2003-01 …)으로 쓴다. 연도만 반복되던 x축이 여기서 바로잡힌다.

  KOSIS_API_KEY=... python3 scripts/export_latest.py
  KOSIS_API_KEY=... python3 scripts/export_latest.py --only-stale
"""
import os, sys, json, time, html, argparse, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "latest")
TSV = os.path.join(OUT, "tsv")
KEY = os.environ.get("KOSIS_API_KEY", "")
FREQ = {"Y": "연간", "Q": "분기", "M": "월간", "H": "반기"}


def fetch(spec):
    if spec.get("provider") == "ecos":
        return fetch_ecos(spec)
    q = {"method": "getList", "apiKey": KEY, "format": "json", "jsonVD": "Y",
         "orgId": spec.get("orgId", "101"), "tblId": spec["tblId"],
         "itmId": spec.get("itmId", "T1+"), "prdSe": spec.get("prdSe", "Y"),
         "startPrdDe": str(spec["startPrdDe"]), "endPrdDe": str(spec["endPrdDe"])}
    for i in range(1, 5):
        if spec.get(f"objL{i}"):
            q[f"objL{i}"] = spec[f"objL{i}"]
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + "&".join(f"{k}={urllib.parse.quote(str(v), safe='+')}" for k, v in q.items()))
    last = None
    for t in range(4):
        try:
            with urllib.request.urlopen(u, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
            if isinstance(d, list):
                return d
            raise RuntimeError(str(d)[:120])
        except Exception as e:
            last = e
            time.sleep(1 + t)
    raise RuntimeError(str(last)[:120])


def fetch_ecos(spec):
    """ECOS 응답을 KOSIS 형태({PRD_DE, DT})로 맞춰 돌려준다."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import ecos
    ser = ecos.search(spec["statCode"], spec["cycle"], spec["start"], spec["end"],
                      spec.get("itemCode"))
    return [{"PRD_DE": p, "DT": v} for p, v in ser]


def pretty(p, prdSe):
    """202503 → 2025-03,  20251 → 2025 1Q,  2025 → 2025"""
    p = str(p)
    if prdSe == "M" and len(p) == 6:
        return f"{p[:4]}-{p[4:]}"
    if prdSe == "Q":
        return f"{p[:4]} {int(p[4:] or 1)}Q" if len(p) > 4 else p
    if prdSe == "H" and len(p) > 4:
        return f"{p[:4]} {'상반기' if p[4:] in ('01','1') else '하반기'}"
    return p[:4]


def safe(s):
    return "".join(c if c.isalnum() or c in " _-()·" else "_" for c in s)[:52].strip()


def cmp_period(a, b):
    """시점 문자열 비교 (같은 주기 가정). -1/0/1"""
    if a is None or b is None:
        return 0
    a, b = str(a), str(b)
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    return (a > b) - (a < b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-stale", action="store_true", help="갱신 필요한 차트만 TSV로 뽑는다")
    a = ap.parse_args()
    os.makedirs(TSV, exist_ok=True)

    mapping = {}
    for f in ("api_map.json", "api_map_auto.json", "ecos_map.json"):
        p = os.path.join(DATA, f)
        if os.path.exists(p):
            mapping.update(json.load(open(p, encoding="utf-8")))
    if not mapping:
        print("매핑이 없습니다. scripts/match_fast.py 를 먼저 돌리세요.")
        return 1

    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import generate_site as g
    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    by = {it["slide"]: it for it in items}

    vp = os.path.join(DATA, "versions.json")
    ver = json.load(open(vp, encoding="utf-8")) if os.path.exists(vp) else {}

    rows = []
    for slide, spec in sorted(mapping.items(), key=lambda kv: kv[1].get("category", "")):
        it = by.get(slide)
        if not it:
            continue
        prdSe = spec.get("prdSe") or {"A": "Y", "S": "H", "Q": "Q", "M": "M"}.get(spec.get("cycle"), "Y")
        try:
            raw = fetch(spec)
        except Exception as e:
            rows.append({"slide": slide, "id": it["id"], "title": it["title"],
                         "cat": it["category"], "err": str(e)[:80]})
            print(f"  ✗ {it['id']} {it['title'][:24]}: {str(e)[:60]}")
            continue
        d = {}
        for r in raw:
            try:
                d[r["PRD_DE"]] = float(r["DT"])
            except (TypeError, ValueError, KeyError):
                continue
        ser = sorted(d.items())
        if not ser:
            continue

        # 차트가 담고 있는 마지막 시점 — 매칭 때 복원한 시점이 있으면 그것을 쓴다
        rec = spec.get("_recoveredPeriods")
        chart_last = rec[-1] if rec else (spec.get("_periodRange") or [None, None])[-1]
        if not chart_last:
            chart_last = str(it["labels"][-1])[:4]
        api_last = ser[-1][0]
        c = cmp_period(chart_last, api_last)
        state = "current" if c == 0 else ("stale" if c < 0 else "ahead")

        prev = ver.get(slide, {})
        ver[slide] = {"id": it["id"], "title": it["title"], "category": it["category"],
                      "tblId": spec.get("tblId") or spec.get("statCode"),
                      "provider": spec.get("provider", "kosis"),
                      "statNm": spec.get("_statNm") or spec.get("_tblNm"),
                      "prdSe": prdSe, "scale": spec.get("scale", 1),
                      "chartLast": chart_last, "apiLast": api_last, "state": state,
                      "keynoteSync": prev.get("keynoteSync", False),
                      "keynoteSyncedAt": prev.get("keynoteSyncedAt"),
                      "matchScore": spec.get("_matchScore")}

        if not a.only_stale or state == "stale":
            sc = spec.get("scale", 1) or 1
            fn = f"{it['id']}_{safe(it['title'])}.tsv"
            with open(os.path.join(TSV, fn), "w", encoding="utf-8-sig") as fh:
                fh.write(f"# {it['title']}\n")
                fh.write(f"# 출처: {spec.get('_statNm') or ''} "
                         f"({spec.get('tblId') or spec.get('statCode')}) {spec.get('sourceUrl','')}\n")
                fh.write(f"# 주기: {FREQ.get(prdSe, prdSe)} · 차트 단위 = 원자료 × {sc:g}\n")
                fh.write("시점\t원자료\t차트단위\n")
                for p, v in ser:
                    fh.write(f"{pretty(p, prdSe)}\t{v}\t{round(v * sc, 6)}\n")
            ver[slide]["tsv"] = fn
        rows.append({"slide": slide, **ver[slide], "n": len(ser)})
        mark = {"current": "·", "stale": "●", "ahead": "▲"}[state]
        print(f"  {mark} {it['id']:6s} {it['title'][:24]:26s} 차트 {chart_last} → API {api_last} "
              f"[{FREQ.get(prdSe,'')}]")

    json.dump(ver, open(vp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    ok = [r for r in rows if "err" not in r]
    stale = [r for r in ok if r["state"] == "stale"]
    ahead = [r for r in ok if r["state"] == "ahead"]
    body = ""
    for r in sorted(ok, key=lambda x: (x["state"] != "stale", x["category"])):
        cls = {"stale": "st", "ahead": "ah", "current": ""}[r["state"]]
        lab = {"stale": "갱신 필요", "ahead": "차트가 앞섬", "current": "최신"}[r["state"]]
        tsv = f"<a href='tsv/{r['tsv']}' download>TSV</a>" if r.get("tsv") else ""
        sc = r.get("scale", 1)
        body += (f"<tr class='{cls}'><td>{r['id']}</td><td>{html.escape(r['category'])}</td>"
                 f"<td>{html.escape(r['title'])}</td><td>{FREQ.get(r['prdSe'],'')}</td>"
                 f"<td class=n>{r['chartLast']}</td><td class=n>{r['apiLast']}</td>"
                 f"<td><span class='b {cls}'>{lab}</span></td>"
                 f"<td class=n>{'' if sc == 1 else f'×{sc:g}'}</td>"
                 f"<td><span class=m>{html.escape(str(r.get('statNm') or ''))}</span><br>"
                 f"{r['tblId']} <span class=m>{r.get('provider','')}</span></td>"
                 f"<td>{tsv}</td></tr>")
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(f"""<!DOCTYPE html>
<html lang=ko><meta charset=utf-8><title>슬로우팩트북 · 데이터 버전 대장</title><style>
body{{font:14px/1.55 system-ui,-apple-system,"Apple SD Gothic Neo",sans-serif;background:#fafafa;color:#1a1a1a;margin:0}}
.w{{max-width:1200px;margin:0 auto;padding:26px 20px 60px}}
h1{{font-size:21px;margin:0 0 4px}} p.s{{color:#666;font-size:13px;margin:0 0 18px;max-width:760px}}
.k{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}}
.k div{{background:#fff;border:1px solid #e6e6e6;border-radius:10px;padding:11px 15px}}
.k b{{display:block;font-size:21px}} .k span{{font-size:12px;color:#666}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e6e6e6;border-radius:10px;overflow:hidden}}
th{{text-align:left;font-size:12px;color:#555;background:#f4f4f2;padding:8px 9px;border-bottom:1px solid #e6e6e6}}
td{{padding:7px 9px;border-bottom:1px solid #f1f1ef;font-size:13px;vertical-align:top}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}} .m{{color:#999;font-size:11px}} a{{color:#2f5e8e}}
tr.st{{background:#fff8f0}} tr.ah{{background:#f4f7fb}}
.b{{font-size:11px;padding:2px 7px;border-radius:99px;background:#eee;color:#555;white-space:nowrap}}
.b.st{{background:#fdecd8;color:#a1520f}} .b.ah{{background:#e4edf8;color:#2f5e8e}}
</style><div class=w>
<h1>데이터 버전 대장</h1>
<p class=s>차트가 담고 있는 마지막 시점과 KOSIS 원본의 마지막 시점을 나란히 놓았습니다.
<b>갱신 필요</b>인 것만 TSV를 받아 키노트에 반영하면 됩니다. TSV에는 원자료 값과 차트 단위로 환산한 값이 함께 들어 있습니다.
<b>차트가 앞섬</b>은 추계·전망이 섞인 차트라 정상입니다.</p>
<div class=k>
 <div><b>{len(ok)}</b><span>매핑된 차트</span></div>
 <div><b>{len(stale)}</b><span>갱신 필요</span></div>
 <div><b>{len(ahead)}</b><span>차트가 앞섬(추계)</span></div>
 <div><b>{len(rows)-len(ok)}</b><span>수집 실패</span></div>
</div>
<table><thead><tr><th>ID</th><th>카테고리</th><th>제목</th><th>주기</th><th>차트 최신</th><th>API 최신</th>
<th>상태</th><th>단위배수</th><th>통계표</th><th>받기</th></tr></thead><tbody>{body}</tbody></table>
</div></html>""")
    print(f"\n매핑 {len(ok)} · 갱신 필요 {len(stale)} · 차트가 앞섬 {len(ahead)} · 실패 {len(rows)-len(ok)}")
    print(f"→ {OUT}/index.html   (버전 대장)")
    print(f"→ {TSV}/            (키노트용 TSV)")
    print(f"→ {DATA}/versions.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
