#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""미국 노동통계국(BLS) 공개 API 로 물가 차트를 이어붙인다.

API 키가 없어도 되는 v1 을 쓴다(하루 요청 수 제한이 있어 등록은 소수로 유지한다).
  https://api.bls.gov/publicAPI/v1/timeseries/data/<계열코드>

등록부는 data/bls_map.json. 열쇠는 차트 id.
  {"c0882": {"series": "CUUR0000SA0", "mode": "yoy", "round": 1}}
  mode 가 yoy 면 받은 지수를 전년 동월 대비 상승률(%)로 환산한다. level 이면 지수 그대로.

겹치는 달의 값이 하나라도 어긋나면 그 차트는 건드리지 않는다.
"""
import argparse, datetime, json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"


def fetch(code, y0, y1):
    url = (f"https://api.bls.gov/publicAPI/v1/timeseries/data/{code}"
           f"?startyear={y0}&endyear={y1}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        doc = json.load(r)
    if doc.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(str(doc.get("message"))[:120])
    out = {}
    for s in doc.get("Results", {}).get("series", []):
        for x in s.get("data", []):
            p = x.get("period", "")
            if not p.startswith("M") or p == "M13":
                continue
            v = str(x.get("value", "")).replace(",", "").strip()
            if not re.fullmatch(r"-?\d+(\.\d+)?", v):
                continue            # 발표가 건너뛴 달은 '-' 로 온다
            out[f'{x["year"]}-{p[1:]}'] = float(v)
    return out


def to_yoy(idx, nd):
    out = {}
    for k, v in idx.items():
        y, m = k.split("-")
        p = f"{int(y)-1}-{m}"
        if p in idx and idx[p]:
            out[k] = round((v / idx[p] - 1) * 100, nd)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.apply:
        a.dry_run = True

    mp = os.path.join(DATA, "bls_map.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if not mapping:
        print("data/bls_map.json 이 비어 있습니다."); return 0

    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in _items if it.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    year = datetime.datetime.now(KST).year

    plans, skips = [], []
    for cid, spec in mapping.items():
        it = items.get(cid)
        if not it:
            skips.append((cid, "차트를 찾지 못했습니다")); continue
        labels = [str(x) for x in it["labels"]]
        if not re.fullmatch(r"\d{4}-\d{2}", labels[-1]):
            skips.append((cid, f"라벨이 월 꼴이 아닙니다: {labels[-1]}")); continue
        nd = int(spec.get("round", 1))
        y0 = int(labels[-1][:4]) - 2          # 대조 겹침 + yoy 계산용 전년치
        try:
            idx = fetch(spec["series"], y0, year)
        except Exception as e:
            skips.append((cid, f"조회 실패: {e}")); continue
        vals = to_yoy(idx, nd) if spec.get("mode", "yoy") == "yoy" else \
               {k: round(v, nd) for k, v in idx.items()}
        cur = it["series"][0]
        bad = [(k, cur[labels.index(k)], vals[k]) for k in vals
               if k in labels and cur[labels.index(k)] is not None
               and abs(cur[labels.index(k)] - vals[k]) > 0.051]
        seen = sum(1 for k in vals if k in labels)
        if seen < 1:
            skips.append((cid, "겹치는 달이 없습니다 — 계열이 맞는지 확인하세요")); continue
        if bad:
            skips.append((cid, f"겹치는 구간 {len(bad)}곳 불일치 (예 {bad[0]})")); continue
        addk = [k for k in sorted(vals) if k > labels[-1]]
        if not addk:
            skips.append((cid, "이미 최신")); continue
        plans.append({"id": cid, "title": it["title"],
                      "labels": labels + addk, "series": [list(cur) + [vals[k] for k in addk]],
                      "n": len(addk), "from": labels[-1], "to": addk[-1]})

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
