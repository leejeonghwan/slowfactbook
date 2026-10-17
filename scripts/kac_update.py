#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국공항공사 공항별 월별 통계(운항·여객·화물)를 차트에 붙인다.

인천공항은 따로 공사가 있어 airport_update.py 가 맡는다. 이 스크립트는
김포·김해·제주 등 한국공항공사가 운영하는 14개 공항을 맡는다.

조회 화면이 쓰는 ajax 끝점을 그대로 부른다.
  POST https://www.airport.co.kr/www/ajaxf/frFlightStatsSvc/timeSeriesStats.do

내려오는 칸은 도착(I)/출발(O) 로 갈려 있어 더해 쓴다.
  운항(편) = OC
  여객(명) = FP 유임 + NP 무임 + TS 환승
  화물(톤) = (FF 화물 + BF 수하물 + MF 우편) / 1000     ← kg 로 온다
합계 식은 화면의 표(엑셀 내려받기)와 한 자리까지 맞춰 확인했다.

등록부는 data/kac_map.json. 열쇠는 차트 id.
  {"c2271": {"airport": "CJU", "col": "여객", "scale": 0.0001, "round": 1}}

겹치는 달이 어긋나면 그 차트는 건드리지 않는다.

  python3 scripts/kac_update.py            미리보기
  python3 scripts/kac_update.py --apply
"""
import argparse, datetime, json, os, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
URL = "https://www.airport.co.kr/www/ajaxf/frFlightStatsSvc/timeSeriesStats.do"
PAGE = "https://www.airport.co.kr/www/cms/frFlightStatsCon/timeSeriesStats.do?MENU_ID=1250"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

AIRPORTS = {"GMP": "김포", "PUS": "김해", "CJU": "제주", "CJJ": "청주",
            "TAE": "대구", "MWX": "무안", "YNY": "양양", "KWJ": "광주",
            "USN": "울산", "RSU": "여수", "KPO": "포항경주", "HIN": "사천",
            "WJU": "원주", "KUV": "군산"}
# 칸 이름 -> (더할 항목들, 나눌 값)
COLS = {"운항": (["OC"], 1), "여객": (["FP", "NP", "TS"], 1),
        "화물": (["FF", "BF", "MF"], 1000)}


def fetch(airport, y0, m0, y1, m1):
    """{"YYYY-MM": {"운항": .., "여객": .., "화물": ..}}"""
    body = urllib.parse.urlencode({
        "MENU_ID": "1250", "pageNo": "1", "YM_TYPE": "YYYYMM",
        "ST_YY": str(y0), "ST_MM": f"{m0:02d}",
        "EN_YY": str(y1), "EN_MM": f"{m1:02d}",
        "AIRPORT_CHK": airport})
    req = urllib.request.Request(URL, data=body.encode(), headers={
        "User-Agent": UA, "X-Requested-With": "XMLHttpRequest", "Referer": PAGE,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read().decode("utf-8"))
    out = {}
    for row in d.get("data") or []:
        k = f"{row['CO_YEAR']}-{int(row['CO_MONTH']):02d}"
        v = {}
        for name, (parts, div) in COLS.items():
            s = 0
            for p in parts:
                s += (row.get("S_" + p + "I") or 0) + (row.get("S_" + p + "O") or 0)
            v[name] = s / div
        out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", help="이 차트 id 만")
    a = ap.parse_args()

    mp = os.path.join(DATA, "kac_map.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if a.only:
        mapping = {k: v for k, v in mapping.items() if k == a.only}
    if not mapping:
        print("data/kac_map.json 이 비어 있습니다."); return 0

    now = datetime.datetime.now(KST)
    stamp = now.strftime("%Y-%m-%d %H:%M")
    cut = now.strftime("%Y-%m")

    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in _items if it.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}

    # 공항마다 한 번만 받는다.
    cache = {}
    plans, skips = [], []
    for cid, spec in mapping.items():
        it = items.get(cid)
        if not it:
            skips.append((cid, "차트를 찾지 못했습니다")); continue
        if len(it["series"]) != 1:
            skips.append((cid, f"계열이 {len(it['series'])}개입니다(1개만 지원)")); continue
        col = spec.get("col")
        if col not in COLS:
            skips.append((cid, f"col 이 {list(COLS)} 중에 없습니다")); continue
        air = spec.get("airport")
        if air not in AIRPORTS:
            skips.append((cid, f"공항 코드 {air} 를 모릅니다")); continue

        if air not in cache:
            try:
                cache[air] = fetch(air, spec.get("fromYear", 2006), 1,
                                   now.year, 12)
            except Exception as e:
                cache[air] = e
        got = cache[air]
        if isinstance(got, Exception):
            skips.append((cid, f"조회 실패: {got}")); continue

        sc = float(spec.get("scale", 1))
        rd = spec.get("round")
        src = {k: (round(v[col] * sc, rd) if rd is not None else v[col] * sc)
               for k, v in got.items() if v.get(col) is not None}
        if not src:
            skips.append((cid, "내려온 값이 없습니다")); continue

        labels = [str(x) for x in it["labels"]]
        mode = spec.get("mode", "append")
        tol = float(spec.get("tol", 0.6))

        if mode == "replace":
            keys = [k for k in sorted(src) if k != cut and src[k]]
            nl, ns = keys, [[src[k] for k in keys]]
            note = f"통째로 교체 ({len(keys)}개월, {keys[0]}~{keys[-1]})"
            if nl == labels and ns == it["series"]:
                skips.append((cid, "이미 최신")); continue
        else:
            bad, seen = [], 0
            for k, b0 in src.items():
                if k not in labels:
                    continue
                a0 = it["series"][0][labels.index(k)]
                if a0 is None:
                    continue
                seen += 1
                if abs(a0 - b0) > tol:
                    bad.append((k, a0, b0))
            if seen < 6:
                skips.append((cid, f"대조할 달이 부족합니다({seen}곳)")); continue
            if bad:
                skips.append((cid, f"겹치는 달 {len(bad)}곳 불일치 (예 {bad[0]})")); continue
            addk = [k for k in sorted(src) if k > labels[-1] and k != cut and src[k]]
            if not addk:
                skips.append((cid, "이미 최신")); continue
            nl = labels + addk
            ns = [list(it["series"][0]) + [src[k] for k in addk]]
            note = f"{len(addk)}개월 추가"

        plans.append({"id": cid, "title": it["title"], "labels": nl, "series": ns,
                      "from": labels[-1], "to": nl[-1], "note": note})

    print(f"등록 {len(mapping)}건 · 고칠 것 {len(plans)}건 · 건너뜀 {len(skips)}건\n")
    for p in plans:
        print(f"  + {p['title'][:24]:26s} {p['from']} -> {p['to']}  {p['note']}")
    for cid, why in skips:
        print(f"  - {cid}: {why}")

    if a.apply and plans:
        for p in plans:
            spec = mapping[p["id"]]
            o = ov.setdefault(p["id"], {})
            o["id"] = p["id"]
            o["labels"] = p["labels"]; o["series"] = p["series"]
            for k in ("title", "source", "sourceUrl", "unit"):
                if spec.get(k):
                    o[k] = spec[k]
            o["updated"] = stamp
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n-> data/overrides.json 에 {len(plans)}건 반영.")
    elif plans:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
