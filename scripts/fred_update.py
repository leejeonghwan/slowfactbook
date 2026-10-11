#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""세인트루이스 연은 FRED 월별 시계열을 이어붙인다.

fredgraph.csv 는 키가 필요 없다.
  https://fred.stlouisfed.org/graph/fredgraph.csv?id=<시리즈 id>

등록부는 data/fred_map.json. 열쇠는 차트 id, 계열 순서는 차트와 같아야 한다.
  {"c0543": {"series": [{"id": "SAHMCURRENT"}],
             "sourceUrl": "https://fred.stlouisfed.org/series/SAHMCURRENT"}}

일별·주별 시리즈는 월평균으로 접는다("fold": "mean", 기본) 또는 그 달의
마지막 값을 쓴다("fold": "last"). 월별 시리즈는 그대로 들어온다.

겹치는 달이 어긋나면 그 차트는 건드리지 않는다. 표가 바뀐 게 아니라 다른
시리즈를 붙이려 한 것일 수 있어서다.
"""
import argparse, csv, datetime, io, json, os, re, subprocess, sys, urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"


def fetch(sid, fold="mean"):
    """{"YYYY-MM": 값} 으로 돌려준다. 결측(".")은 버린다."""
    # urllib 로는 FRED 가 응답을 끝내 주지 않는다(이 망에서 계속 타임아웃).
    # curl 은 멀쩡히 받아 오므로 그쪽에 맡긴다.
    body = subprocess.run(
        ["curl", "-sS", "--compressed", "--max-time", "60", "-A", UA,
         CSV.format(sid=sid)],
        capture_output=True, text=True, timeout=90).stdout
    rows = list(csv.reader(io.StringIO(body)))
    if not rows or len(rows[0]) < 2:
        raise RuntimeError(f"{sid}: 내려온 표가 비었습니다")
    acc = defaultdict(list)
    for d, v in ((r[0], r[1]) for r in rows[1:] if len(r) >= 2):
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d.strip())
        if not m:
            continue
        try:
            x = float(v)
        except ValueError:
            continue                      # FRED 는 결측을 "." 으로 적는다
        acc[f"{m.group(1)}-{m.group(2)}"].append((d.strip(), x))
    out = {}
    for k, vs in acc.items():
        if fold == "last":
            out[k] = sorted(vs)[-1][1]
        else:
            xs = [x for _, x in vs]
            out[k] = round(sum(xs) / len(xs), 4) if len(xs) > 1 else xs[0]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="이 차트 id 만")
    a = ap.parse_args()
    if not a.apply:
        a.dry_run = True

    mp = os.path.join(DATA, "fred_map.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if a.only:
        mapping = {k: v for k, v in mapping.items() if k == a.only}
    if not mapping:
        print("data/fred_map.json 이 비어 있습니다."); return 0

    now = datetime.datetime.now(KST)
    cut = now.strftime("%Y-%m")            # 이번 달은 아직 안 끝났다

    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in _items if it.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    stamp = now.strftime("%Y-%m-%d %H:%M")

    cache = {}
    plans, skips = [], []
    for cid, spec in mapping.items():
        it = items.get(cid)
        if not it:
            skips.append((cid, "차트를 찾지 못했습니다")); continue
        labels = [str(x) for x in it["labels"]]
        if not re.fullmatch(r"\d{4}-\d{2}", labels[-1]):
            skips.append((cid, f"라벨이 월 꼴이 아닙니다: {labels[-1]}")); continue
        sers = spec.get("series") or []
        if len(sers) != len(it["series"]):
            skips.append((cid, f"등록 계열 {len(sers)}개 != 차트 계열 {len(it['series'])}개")); continue
        tol = float(spec.get("tol", 0.011))

        got, err = [], None
        for s in sers:
            key = (s["id"], s.get("fold", spec.get("fold", "mean")))
            if key not in cache:
                try:
                    cache[key] = fetch(*key)
                except Exception as e:
                    err = f"{s['id']} 조회 실패: {e}"; break
            got.append(cache[key])
        if err:
            skips.append((cid, err)); continue

        # 겹치는 달 대조. 어긋나면 손대지 않는다.
        bad, seen = [], 0
        for si, d in enumerate(got):
            for k, b0 in d.items():
                if k not in labels:
                    continue
                i = labels.index(k)
                a0 = it["series"][si][i]
                if a0 is None:
                    continue
                seen += 1
                if abs(a0 - b0) > tol:
                    bad.append((k, sers[si]["id"], a0, b0))
        if seen < 6:
            skips.append((cid, f"대조할 달이 부족합니다({seen}곳)")); continue

        # "mode": "replace" — 차트 전체를 FRED 현재 빈티지로 다시 깐다. 실업률처럼
        # 계절조정이 뒤로 고쳐지는 지표는 옛 슬라이드 값이 조금씩 어긋나는데,
        # 뒤만 이어붙이면 한 차트 안에 두 빈티지가 섞인다.
        # 그래도 '다른 시리즈를 붙이려 한 것'은 걸러야 하므로, 겹치는 구간이
        # 대체로 맞는지(어긋남이 drift 이내인지)는 확인한다.
        if spec.get("mode") == "replace":
            drift = float(spec.get("drift", 0.3))
            far = [b for b in bad if abs(b[2] - b[3]) > drift]
            if far or len(bad) > seen * 0.5:
                skips.append((cid, f"다른 시리즈로 보입니다 (어긋남 {len(bad)}/{seen}곳"
                                   + (f", 예 {far[0]}" if far else "") + ")")); continue
            ks = sorted(set(got[0]) & set.intersection(*[set(d) for d in got]))
            ks = [k for k in ks if k != cut]
            if not ks:
                skips.append((cid, "받아온 달이 없습니다")); continue
            ns = [[d[k] for k in ks] for d in got]
            if ks == labels and all(ns[i] == it["series"][i] for i in range(len(ns))):
                skips.append((cid, "이미 최신")); continue
            plans.append({"id": cid, "title": it["title"], "labels": ks, "series": ns,
                          "n": len(ks), "from": labels[-1], "to": ks[-1],
                          "note": f"전체 교체 {len(bad)}곳 수정"})
            continue

        if bad:
            skips.append((cid, f"겹치는 구간 {len(bad)}곳 불일치 (예 {bad[0]})")); continue

        addk = [k for k in sorted(got[0]) if k > labels[-1] and k != cut]
        addk = [k for k in addk if all(d.get(k) is not None for d in got)]
        if not addk:
            skips.append((cid, "이미 최신")); continue
        nl = labels + addk
        ns = [list(s) + [d[k] for k in addk] for s, d in zip(it["series"], got)]
        plans.append({"id": cid, "title": it["title"], "labels": nl, "series": ns,
                      "n": len(addk), "from": labels[-1], "to": nl[-1]})

    print(f"등록 {len(mapping)}건 · 이어붙일 것 {len(plans)}건 · 건너뜀 {len(skips)}건\n")
    for p in plans:
        print(f"  + {p['title'][:30]:32s} {p['from']} -> {p['to']}  "
              + (p.get("note") or f"({p['n']}개월 추가)"))
    for cid, why in skips:
        print(f"  - {cid}: {why}")

    if a.apply and plans:
        for p in plans:
            o = ov.setdefault(p["id"], {})
            o["id"] = p["id"]
            o["labels"] = p["labels"]; o["series"] = p["series"]; o["updated"] = stamp
            u = (mapping.get(p["id"]) or {}).get("sourceUrl")
            if u:
                o["sourceUrl"] = u
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n-> data/overrides.json 에 {len(plans)}건 반영.")
    elif plans:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
