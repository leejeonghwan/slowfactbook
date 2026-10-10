#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""증감 그래프(양수 계열 + 음수 계열)의 계열 이름을 '증가'·'감소'로 채운다.

키노트에서 증감을 색으로 가르려고 양수와 음수를 두 계열로 쪼개 그린 차트가 많은데,
그 과정에서 계열 이름이 값(-6.82080141)이나 추출 흔적(Untitled 1)으로 들어가 있다.
범례가 뜻을 잃어 버리므로, 아래 조건을 모두 만족할 때만 이름을 채운다.

  1. 계열이 정확히 둘
  2. 한쪽은 값이 모두 0 이상, 다른 쪽은 모두 0 이하
  3. 두 계열이 같은 시점에서 동시에 값을 갖지 않는다(쪼갠 흔적)
  4. 지금 이름이 뜻 없는 것(빈칸·None·Untitled·숫자)

  python3 scripts/name_updown.py --dry-run
  python3 scripts/name_updown.py --apply [--cat 지속가능한 성장]
"""
import argparse, datetime, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
JUNK = re.compile(r"^\s*(|None|Untitled\s*\d*|-?[\d,]+(\.\d+)?)\s*$", re.I)


def classify(it):
    if len(it["series"]) != 2:
        return None
    a, b = it["series"]
    va = [v for v in a if v is not None]
    vb = [v for v in b if v is not None]
    if not va or not vb:
        return None
    if min(va) >= 0 and max(vb) <= 0:
        pos, neg = 0, 1
    elif min(vb) >= 0 and max(va) <= 0:
        pos, neg = 1, 0
    else:
        return None
    both = sum(1 for x, y in zip(a, b) if x is not None and y is not None)
    if both > max(1, len(a) * 0.02):        # 쪼갠 게 아니라 진짜 두 계열이다
        return None
    return pos, neg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cat", help="이 분류만")
    ap.add_argument("--force", action="store_true", help="이름이 멀쩡해도 덮어쓴다")
    a = ap.parse_args()
    if not a.apply:
        a.dry_run = True

    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    hits, skip = [], []
    for it in items:
        if a.cat and it.get("category") != a.cat:
            continue
        c = classify(it)
        if not c:
            continue
        pos, neg = c
        names = [str(n or "") for n in it["seriesNames"]]
        junk = all(JUNK.match(n) for n in names)
        if not junk and not a.force:
            skip.append((it.get("id"), it["title"][:28], names))
            continue
        new = [None, None]
        new[pos], new[neg] = "증가", "감소"
        hits.append((it.get("id"), it["title"][:30], it.get("category", ""), names, new))

    print(f"증감 쪼갠 차트 {len(hits)+len(skip)}개 · 이름 채울 것 {len(hits)} · 이미 이름 있음 {len(skip)}\n")
    for cid, t, cat, old, new in hits:
        print(f"  {cid}  [{cat[:10]:12s}] {t:32s} {old} → {new}")
    for cid, t, old in skip:
        print(f"  - {cid} {t:32s} 이름 있음 {old}")

    if a.apply and hits:
        ovp = os.path.join(DATA, "overrides.json")
        ov = json.load(open(ovp, encoding="utf-8"))
        stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        for cid, _, _, _, new in hits:
            o = ov.setdefault(cid, {})
            o["seriesNames"] = new
            o["revised"] = stamp
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n→ data/overrides.json 에 {len(hits)}건 반영. 다음: python3 scripts/build.py")
    elif hits:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
