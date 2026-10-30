#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국과 미국의 기준금리(c2310).

  python3 scripts/policy_rates.py            # 미리보기
  python3 scripts/policy_rates.py --apply

한국은 한국은행 ECOS 기준금리(722Y001 0101000), 미국은 세인트루이스 연은
FRED 실효 연방기금금리(FEDFUNDS) 월평균이다.

ecos_update.py 는 FRED 를 못 받고 fred_update.py 는 ECOS 를 못 받는다.
소스가 둘이라 여기에 따로 둔다.

겹치는 달을 전수 대조해 하나라도 어긋나면 손대지 않는다.
"""
import argparse, datetime, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g
import fred_update as fr

CID = "c2310"
KST = datetime.timezone(datetime.timedelta(hours=9))
TOL = 0.011


def korea():
    key = os.environ["ECOS_API_KEY"]
    u = (f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/5000/"
         f"722Y001/M/199901/209912/0101000")
    r = json.load(urllib.request.urlopen(u, timeout=120))
    rows = r.get("StatisticSearch", {}).get("row")
    if not rows:
        raise RuntimeError(f"ECOS: {json.dumps(r, ensure_ascii=False)[:160]}")
    return {f"{x['TIME'][:4]}-{x['TIME'][4:6]}": round(float(x["DATA_VALUE"]), 2) for x in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    kr = korea()
    us = fr.bucket(fr.fetch_rows("FEDFUNDS"), "month", "mean", 0, 2)
    start = min(kr)
    months = [m for m in sorted(set(kr) | set(us)) if m >= start]
    series = [[kr.get(m) for m in months], [us.get(m) for m in months]]
    print(f"원자료 {len(months)}개월: {months[0]} ~ {months[-1]}")

    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    it = {x["id"]: x for x in items if x.get("id")}.get(CID)
    if not it:
        print(f"{CID} 차트를 찾지 못했습니다."); return 1
    if len(it["series"]) != 2:
        print("차트 계열이 둘이 아닙니다 — 손대지 않습니다"); return 1

    old = {str(l): [s[i] for s in it["series"]]
           for i, l in enumerate(str(x) for x in it["labels"])}
    bad, seen = [], 0
    for i, m in enumerate(months):
        if m not in old:
            continue
        seen += 1
        for si in (0, 1):
            x, y = old[m][si], series[si][i]
            if x is not None and y is not None and abs(x - y) > TOL:
                bad.append((m, si, x, y))
    if bad:
        print(f"겹치는 {len(bad)}곳 어긋남 (예 {bad[:3]}) — 손대지 않습니다"); return 1
    print(f"겹치는 {seen}개월 대조 — 일치")

    new = [m for m in months if m not in old]
    if not new:
        print(f"· 이미 최신 ({months[-1]}, {len(months)}점)"); return 0
    for m in new:
        i = months.index(m)
        print(f"+ {m}  한국 {series[0][i]}  미국 {series[1][i]}")
    if not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)"); return 0

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    o = ov.setdefault(CID, {}); o["id"] = CID
    o["labels"] = months; o["series"] = series
    o["updated"] = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(ovp, "a", encoding="utf-8").write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
