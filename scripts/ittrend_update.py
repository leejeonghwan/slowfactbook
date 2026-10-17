#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""인터넷트렌드(InternetTrend) 검색엔진 점유율을 연도별로 받아 차트에 붙인다.

조회 페이지는 서버에서 표를 그려 내려보낸다. 그 표를 읽는다.
  https://internettrend.co.kr/reports/search-engine?from=YYYY-01-01&to=YYYY-12-31

점유율은 로거를 단 국내 웹사이트의 유입 구성비다. 시장 점유율이 아니다.
합이 100이 안 되는 것은 「기타·판별 불가」가 빠져 있기 때문이고,
"etc": true 를 적으면 100에서 뺀 나머지를 '기타' 계열로 붙인다.

등록부는 data/ittrend_map.json. 열쇠는 차트 id.
  {"c1190": {"engines": ["네이버", "구글", "다음", "줌"], "from": 2015}}

기본은 지난해까지다. 올해는 아직 끝나지 않아 넣지 않는다.

  python3 scripts/ittrend_update.py            미리보기
  python3 scripts/ittrend_update.py --apply
"""
import argparse, datetime, json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
URL = "https://internettrend.co.kr/reports/search-engine?from={y}-01-01&to={y}-12-31"
# 표의 한 줄: 엔진 이름과 바로 뒤에 오는 첫 퍼센트(= 기간 평균 점유율)
ROW = re.compile(r'<span class="">([A-Z]+)\(([^)]+)\)</span></span></td>'
                 r'<td[^>]*><span class="font-semibold">([\d.]+)%</span>')


def year(y):
    """{'네이버': 62.86, ...}"""
    req = urllib.request.Request(URL.format(y=y), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        h = r.read().decode("utf-8", "replace")
    out = {m.group(2): float(m.group(3)) for m in ROW.finditer(h)}
    if not out:
        raise RuntimeError(f"{y}년 표를 읽지 못했습니다(페이지 구조가 바뀌었을 수 있습니다)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", help="이 차트 id 만")
    a = ap.parse_args()

    mp = os.path.join(DATA, "ittrend_map.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if a.only:
        mapping = {k: v for k, v in mapping.items() if k == a.only}
    if not mapping:
        print("data/ittrend_map.json 이 비어 있습니다."); return 0

    now = datetime.datetime.now(KST)
    stamp = now.strftime("%Y-%m-%d %H:%M")

    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in _items if it.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}

    cache, plans, skips = {}, [], []
    for cid, spec in mapping.items():
        it = items.get(cid)
        if not it:
            skips.append((cid, "차트를 찾지 못했습니다")); continue
        y0 = int(spec.get("from", 2015))
        y1 = int(spec.get("to") or (now.year - 1))   # 올해는 아직 안 끝났다
        try:
            for y in range(y0, y1 + 1):
                if y not in cache:
                    cache[y] = year(y)
        except Exception as e:
            skips.append((cid, f"조회 실패: {e}")); continue

        eng = spec.get("engines") or ["네이버", "구글", "다음", "줌"]
        labels = [f"{y}년" for y in range(y0, y1 + 1)]
        series = [[cache[y].get(n) for y in range(y0, y1 + 1)] for n in eng]
        names = list(eng)
        if spec.get("etc"):
            # 표에 안 나온 몫. 「기타·판별 불가」를 합쳐 100을 채운다.
            series.append([round(100 - sum(v for v in cache[y].values()), 2)
                           for y in range(y0, y1 + 1)])
            names.append("기타")

        old = [str(x) for x in it["labels"]]
        if old == labels and it["series"] == series:
            skips.append((cid, "이미 최신")); continue
        plans.append({"id": cid, "title": it["title"], "labels": labels,
                      "series": series, "names": names,
                      "from": old[-1] if old else "-", "to": labels[-1]})

    print(f"등록 {len(mapping)}건 · 고칠 것 {len(plans)}건 · 건너뜀 {len(skips)}건\n")
    for p in plans:
        print(f"  + {p['title'][:26]:28s} {p['from']} -> {p['to']}  "
              f"({len(p['labels'])}개 연도, 계열 {len(p['series'])})")
    for cid, why in skips:
        print(f"  - {cid}: {why}")

    if a.apply and plans:
        for p in plans:
            spec = mapping[p["id"]]
            o = ov.setdefault(p["id"], {})
            o["id"] = p["id"]
            o["labels"] = p["labels"]; o["series"] = p["series"]
            o["seriesNames"] = p["names"]
            for k in ("title", "source", "sourceUrl", "unit", "vizType", "stacked"):
                if spec.get(k) is not None:
                    o[k] = spec[k]
            o["updated"] = stamp
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n-> data/overrides.json 에 {len(plans)}건 반영.")
    elif plans:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
