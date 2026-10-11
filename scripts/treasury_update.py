#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""미국 재무부 일별 국채 수익률을 월평균으로 접어 이어붙인다.

FRED 의 DGS10·DGS30 이 쓰는 원자료가 바로 이것이고, FRED 의 fredgraph.csv 는
이 PC 의 망에서 막혀 있어 원천인 재무부에서 직접 받는다(키 불필요).
  https://home.treasury.gov/.../daily-treasury-rates.csv/<연도>/all?type=daily_treasury_yield_curve

등록부는 data/treasury_map.json. 열쇠는 차트 id.
  {"c2093": {"series": [{"name": "", "col": "30 Yr"}]}}

겹치는 달의 월평균이 어긋나면 그 차트는 건드리지 않는다.
"""
import argparse, csv, datetime, io, json, os, re, sys, urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
BASE = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
        "daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve"
        "&field_tdr_date_value={y}&page&_format=csv")


def fetch_year(y):
    req = urllib.request.Request(BASE.format(y=y), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = list(csv.DictReader(io.StringIO(r.read().decode("utf-8", "replace"))))
    acc = defaultdict(lambda: defaultdict(list))
    for r in rows:
        mm, dd, yy = r["Date"].split("/")
        for col, v in r.items():
            if col == "Date" or not v or not v.strip():
                continue
            try:
                acc[f"{yy}-{mm}"][col].append(float(v))
            except ValueError:
                pass
    return {k: {c: round(sum(v) / len(v), 2) for c, v in d.items()} for k, d in acc.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--years", type=int, default=2, help="받아올 최근 연도 수")
    a = ap.parse_args()
    if not a.apply:
        a.dry_run = True

    mp = os.path.join(DATA, "treasury_map.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if not mapping:
        print("data/treasury_map.json 이 비어 있습니다."); return 0

    now = datetime.datetime.now(KST)
    monthly = {}
    for y in range(now.year - a.years + 1, now.year + 1):
        try:
            monthly.update(fetch_year(y))
        except Exception as e:
            print(f"  {y}년 조회 실패: {e}")
    if not monthly:
        print("받아온 자료가 없습니다."); return 1
    cut = now.strftime("%Y-%m")            # 이번 달은 아직 안 끝났다

    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in _items if it.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    stamp = now.strftime("%Y-%m-%d %H:%M")

    plans, skips = [], []
    for cid, spec in mapping.items():
        it = items.get(cid)
        if not it:
            skips.append((cid, "차트를 찾지 못했습니다")); continue
        labels = [str(x) for x in it["labels"]]
        if not re.fullmatch(r"\d{4}-\d{2}", labels[-1]):
            skips.append((cid, f"라벨이 월 꼴이 아닙니다: {labels[-1]}")); continue
        cols = [s["col"] for s in spec["series"]]
        if len(cols) != len(it["series"]):
            skips.append((cid, f"등록 계열 {len(cols)}개 ≠ 차트 계열 {len(it['series'])}개")); continue
        bad, seen = [], 0
        for k, d in monthly.items():
            if k not in labels:
                continue
            i = labels.index(k)
            for si, c in enumerate(cols):
                a0, b0 = it["series"][si][i], d.get(c)
                if a0 is None or b0 is None:
                    continue
                seen += 1
                if abs(a0 - b0) > 0.051:
                    bad.append((k, c, a0, b0))
        if seen < 2:
            skips.append((cid, "대조할 달이 부족합니다")); continue
        if bad:
            skips.append((cid, f"겹치는 구간 {len(bad)}곳 불일치 (예 {bad[0]})")); continue
        addk = [k for k in sorted(monthly) if k > labels[-1] and k != cut]
        addk = [k for k in addk if all(monthly[k].get(c) is not None for c in cols)]
        if not addk:
            skips.append((cid, "이미 최신")); continue
        nl = labels + addk
        ns = [list(s) + [monthly[k][c] for k in addk] for s, c in zip(it["series"], cols)]
        plans.append({"id": cid, "title": it["title"], "labels": nl, "series": ns,
                      "n": len(addk), "from": labels[-1], "to": nl[-1]})

    print(f"등록 {len(mapping)}건 · 이어붙일 것 {len(plans)}건 · 건너뜀 {len(skips)}건\n")
    for p in plans:
        print(f"  + {p['title'][:30]:32s} {p['from']} → {p['to']}  ({p['n']}개월 추가)")
    for cid, why in skips:
        print(f"  - {cid}: {why}")

    if a.apply and plans:
        for p in plans:
            o = ov.setdefault(p["id"], {})
            o["labels"] = p["labels"]; o["series"] = p["series"]; o["updated"] = stamp
            # 자동 갱신에 쓴 참조 주소를 차트에 남긴다 (차트 페이지의 '출처 링크' 버튼).
            u = (mapping.get(p["id"]) or {}).get("sourceUrl")
            if u:
                o["sourceUrl"] = u
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n→ data/overrides.json 에 {len(plans)}건 반영.")
    elif plans:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
