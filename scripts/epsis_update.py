#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전력통계정보시스템(EPSIS) 발전원별 입찰량·거래량.

  입찰량 https://epsis.kpx.or.kr/epsisnew/selectEkmaBddBftChart.do?menuId=040401
  거래량 https://epsis.kpx.or.kr/epsisnew/selectEkmaPtdBftChart.do?menuId=040501

두 페이지 모두 차트 데이터를 ajax 로 내려준다. 먼저 페이지를 열어 세션 쿠키를
받고(안 받으면 빈 배열이 온다), selDate=month 로 POST 하면 2002년 1월부터
최근 달까지가 한 번에 온다. 값은 Number("…") 로 감싸여 오므로 벗겨서 읽는다.

  Value  원자력   Value2 유연탄   Value3 무연탄   Value4 유류
  Value5 LNG      Value6 양수     Value7 신재생   (석탄 = 유연탄+무연탄)

등록부는 data/epsis_map.json. 열쇠는 차트 id.
  {"feed": "bid"|"ptd"|"both", "freq": "month"|"year",
   "year": 2024,                 # freq=month 일 때 그 해 열두 달
                                 # freq=allmonth 면 2002년 1월부터 전 구간
   "series": ["원자력","석탄","LNG"],   # 한 자료에서 여러 연료
   "fuel": "석탄",                # feed=both 일 때 한 연료의 입찰량·거래량
   "unit": "GWh"|"TWh"}

겹치는 구간이 어긋나면 그 차트는 건드리지 않는다.

  python3 scripts/epsis_update.py --dry-run
  python3 scripts/epsis_update.py --apply
"""
import argparse, datetime, json, os, re, sys, urllib.parse, urllib.request, http.cookiejar

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
FEEDS = {
    "bid": ("https://epsis.kpx.or.kr/epsisnew/selectEkmaBddBftChart.do?menuId=040401",
            "https://epsis.kpx.or.kr/epsisnew/selectEkmaBddBftChart.ajax", "입찰량"),
    "ptd": ("https://epsis.kpx.or.kr/epsisnew/selectEkmaPtdBftChart.do?menuId=040501",
            "https://epsis.kpx.or.kr/epsisnew/selectEkmaPtdBftChart.ajax", "거래량"),
}
FUEL = {"원자력": ("Value",), "유연탄": ("Value2",), "무연탄": ("Value3",),
        "석탄": ("Value2", "Value3"), "유류": ("Value4",), "LNG": ("Value5",),
        "양수": ("Value6",), "신재생": ("Value7",)}
TOL = 1.0          # GWh. 반올림 차이만 허용한다


def fetch(feed):
    """{'2024-01': {'원자력': 14417.4, ...}} — 2002년 1월부터 최근 달까지."""
    page, ajax, _ = FEEDS[feed]
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", UA)]
    op.open(page, timeout=60).read()          # 세션 쿠키부터 받는다
    req = urllib.request.Request(
        ajax, data=urllib.parse.urlencode({"selDate": "month", "selRegion": "1"}).encode(),
        headers={"User-Agent": UA, "Referer": page, "X-Requested-With": "XMLHttpRequest"})
    body = op.open(req, timeout=60).read().decode("utf-8", "replace")
    body = re.sub(r'Number\("([^"]*)"\)', r'"\1"', body)
    out = {}
    for m in re.finditer(r"chartData\.push\((\{.*?\})\)\s*;", body, re.S):
        try:
            d = json.loads(re.sub(r"\s+", " ", m.group(1)))
        except Exception:
            continue
        mm = re.fullmatch(r"(\d{4})/(\d{2})/\d{2}", str(d.get("Date", "")))
        if not mm:
            continue
        raw = {k: float(v) for k, v in d.items() if k != "Date" and v not in ("", None)}
        out[f"{mm.group(1)}-{mm.group(2)}"] = {
            f: sum(raw.get(k, 0.0) for k in ks) for f, ks in FUEL.items()}
    if not out:
        raise RuntimeError(f"{feed}: 차트 데이터가 비어 있습니다 — 페이지 구조가 바뀐 듯합니다")
    return out


def to_year(monthly, fuel, scale):
    """열두 달이 다 찬 해만 연간으로 묶는다(진행 중인 해는 빼야 선이 꺾인다)."""
    by = {}
    for k, v in monthly.items():
        by.setdefault(k[:4], []).append(v[fuel])
    return {y: round(sum(vs) / scale, 4) for y, vs in sorted(by.items()) if len(vs) == 12}


def build(spec, feeds):
    """등록부 한 줄 → (labels, series, names)."""
    unit = spec.get("unit", "GWh")
    scale = 1000.0 if unit == "TWh" else 1.0
    if spec["feed"] == "both":
        f = spec["fuel"]
        a, b = to_year(feeds["bid"], f, scale), to_year(feeds["ptd"], f, scale)
        ys = [y for y in sorted(a) if y in b]
        return ys, [[a[y] for y in ys], [b[y] for y in ys]], ["입찰량", "거래량"]
    src = feeds[spec["feed"]]
    names = spec["series"]
    if spec["freq"] == "allmonth":
        ks = sorted(src)
        return ks, [[round(src[k][f] / scale, 4) for k in ks] for f in names], names
    if spec["freq"] == "year":
        cols = {f: to_year(src, f, scale) for f in names}
        ys = sorted(set.intersection(*[set(c) for c in cols.values()]))
        return ys, [[cols[f][y] for y in ys] for f in names], names
    y = str(spec["year"])
    ks = [f"{y}-{m:02d}" for m in range(1, 13)]
    if not all(k in src for k in ks):
        return None, None, None
    return [f"{m:02d}" for m in range(1, 13)], \
           [[round(src[k][f] / scale, 4) for k in ks] for f in names], names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.apply:
        a.dry_run = True

    mp = os.path.join(DATA, "epsis_map.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if not mapping:
        print("data/epsis_map.json 이 비어 있습니다.")
        return 0

    feeds = {}
    for f in sorted({s["feed"] for s in mapping.values()} | ({"bid", "ptd"} if any(
            s["feed"] == "both" for s in mapping.values()) else set())):
        if f == "both":
            continue
        feeds[f] = fetch(f)
        print(f"  {FEEDS[f][2]}: {len(feeds[f])}개월 "
              f"{min(feeds[f])} ~ {max(feeds[f])}")

    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in _items if it.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    plans, skips = [], []
    for cid, spec in mapping.items():
        it = items.get(cid)
        if not it:
            skips.append((cid, "차트를 찾지 못했습니다")); continue
        labs, ser, names = build(spec, feeds)
        if labs is None:
            skips.append((cid, f"{spec.get('year')}년 열두 달이 다 차지 않았습니다")); continue
        cur = {str(L): [s[i] for s in it["series"]] for i, L in enumerate(it["labels"])}
        bad = []
        for i, L in enumerate(labs):
            if str(L) in cur:
                old = cur[str(L)]
                for k in range(min(len(old), len(ser))):
                    if old[k] is not None and abs(old[k] - ser[k][i]) > TOL:
                        bad.append((L, names[k], old[k], ser[k][i]))
        over = [L for L in labs if str(L) in cur]
        if bad:
            skips.append((cid, f"겹치는 {len(over)}개 중 {len(bad)}곳 불일치 {bad[:3]}")); continue
        same = (list(it["labels"]) == [str(x) for x in labs]
                and all(a0 == b0 for s0, s1 in zip(it["series"], ser)
                        for a0, b0 in zip(s0, s1)))
        if same:
            skips.append((cid, "이미 최신")); continue
        plans.append({"id": cid, "title": it["title"], "labels": [str(x) for x in labs],
                      "series": ser, "names": names, "spec": spec,
                      "from": str(labs[0]), "to": str(labs[-1]), "n": len(labs),
                      "over": len(over)})

    print(f"\n등록 {len(mapping)}건 · 고칠 것 {len(plans)}건 · 건너뜀 {len(skips)}건\n")
    for p in plans:
        print(f"  + {p['title'][:30]:32s} {p['from']} → {p['to']}  ({p['n']}점, 겹침 {p['over']} 일치)")
    for cid, why in skips:
        print(f"  - {cid}: {why}")

    if a.apply and plans:
        for p in plans:
            o = ov.setdefault(p["id"], {})
            o.update({"id": p["id"], "labels": p["labels"], "series": p["series"],
                      "seriesNames": p["names"], "unit": p["spec"].get("unit", "GWh"),
                      "sourceUrl": FEEDS[p["spec"]["feed"]][0] if p["spec"]["feed"] != "both"
                                   else FEEDS["bid"][0] + " " + FEEDS["ptd"][0],
                      "updated": stamp})
            o.pop("revised", None)
            o.setdefault("source", "전력통계정보시스템. 단위: " + p["spec"].get("unit", "GWh") + ".")
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n→ data/overrides.json 에 {len(plans)}건 반영. 다음: python3 scripts/build.py")
    elif plans:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
