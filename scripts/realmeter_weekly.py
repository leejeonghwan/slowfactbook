#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""리얼미터 주간통계표 → 대통령 지지율과 정당 지지율 주간 시계열.

  python3 scripts/realmeter_weekly.py            # 미리보기
  python3 scripts/realmeter_weekly.py --apply

rebuild_realmeter.py 는 아카이브를 통째로 받아 시계열을 복원하는 일회성 도구였다.
이 스크립트는 그 캐시(.cache/poll/realmeter_weeks.json)를 그대로 쓰면서,
새로 올라온 주간통계표만 받아 차트 뒤에 붙인다.

등록부는 data/realmeter_weekly.json. lastWeek 는 차트에 이미 담긴 마지막 주다.
새 주를 붙이기 전에 그 주의 원자료와 차트의 마지막 값이 맞는지 본다.
어긋나면 붙이지 않고 멈춘다 — 양식이 바뀌었을 때 조용히 틀린 값이 들어가는
것이 가장 나쁘기 때문이다.

계열은 등록부의 "fields" 로 고른다.
  approve      대통령 국정수행 긍정률
  disapprove   대통령 국정수행 부정률
  민주당 / 국민의힘   정당 지지도
"""
import argparse, datetime, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, ".cache", "poll")
STORE = os.path.join(CACHE, "realmeter_weeks.json")
LIST = os.path.join(CACHE, "realmeter_list.json")
sys.path.insert(0, HERE)
import generate_site as g
import rebuild_realmeter as rm

KST = datetime.timezone(datetime.timedelta(hours=9))


def value(row, field):
    if field in ("approve", "disapprove"):
        return row.get(field)
    p = row.get("party") or {}
    return p.get(field)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-scan", action="store_true", help="목록을 다시 훑지 않는다")
    ap.add_argument("--maxpage", type=int, default=3)
    a = ap.parse_args()

    if not a.no_scan:
        rm.scan(a.maxpage)
    left = rm.fetch(20)
    if left:
        print(f"아직 못 받은 통계표가 {left}개 있습니다. 다시 돌리면 이어받습니다.")

    store = rm.load(STORE, {})
    rows = {}
    for v in store.values():
        if v.get("week") and v.get("approve") is not None:
            rows[tuple(v["week"])] = v
    if not rows:
        print("원자료가 없습니다."); return 1
    order = sorted(rows)
    print(f"원자료 {len(order)}주: {order[0]} ~ {order[-1]}")

    mp = os.path.join(DATA, "realmeter_weekly.json")
    mapping = json.load(open(mp, encoding="utf-8"))
    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in items if it.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    changed = False
    for cid, spec in mapping.items():
        it = items.get(cid)
        if not it:
            print(f"  - {cid}: 차트를 찾지 못했습니다"); continue
        title = it.get("title") or cid
        fields = spec["fields"]
        if len(fields) != len(it["series"]):
            print(f"  - {cid} {title}: 등록 계열 {len(fields)}개 != 차트 계열 {len(it['series'])}개")
            continue
        last = tuple(spec["lastWeek"])
        if last not in rows:
            print(f"  - {cid} {title}: 마지막 주 {last} 의 원자료가 없어 대조할 수 없습니다")
            continue

        want = [value(rows[last], f) for f in fields]
        have = [s[-1] for s in it["series"]]
        if any(w is None for w in want) or want != have:
            print(f"  - {cid} {title}: {last} 대조 어긋남 차트 {have} vs 원문 {want} — 손대지 않습니다")
            continue

        new = [w for w in order if w > last]
        if not new:
            print(f"  · {cid} {title}: 이미 최신 ({last[0]}년 {last[1]}월 {last[2]}주, {len(it['labels'])}점)")
            continue

        labels = [str(x) for x in it["labels"]]
        series = [list(s) for s in it["series"]]
        added = []
        for w in new:
            vals = [value(rows[w], f) for f in fields]
            if any(v is None for v in vals):
                print(f"  - {cid} {title}: {w} 에 빠진 값이 있어 여기서 멈춥니다"); break
            labels.append(f"{w[0]}-{w[1]:02d}")
            for i, v in enumerate(vals):
                series[i].append(v)
            added.append((w, vals))
            last = w
        if not added:
            continue
        for w, vals in added:
            print(f"  + {cid} {title}: {w[0]}년 {w[1]}월 {w[2]}주 {vals}")
        if a.apply:
            o = ov.setdefault(cid, {}); o["id"] = cid
            o["labels"] = labels; o["series"] = series; o["updated"] = stamp
            spec["lastWeek"] = list(last)
            changed = True

    if a.apply and changed:
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        open(ovp, "a", encoding="utf-8").write("\n")
        json.dump(mapping, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        open(mp, "a", encoding="utf-8").write("\n")
        print("-> data/overrides.json 에 반영했습니다.")
    elif not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
