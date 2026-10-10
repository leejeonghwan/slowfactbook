#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""단위가 비어 있는 차트에 '확실한 것만' 단위를 채운다.

툴팁과 데이터 표가 단위를 읽는 자리는 overrides 의 "unit" 이다. 지금은 비어 있으면
출처 문자열의 '단위: …' 를 대신 읽는데, 그것도 없으면 숫자만 덩그러니 뜬다.

채우는 경우는 넷뿐이다. 애매하면 건드리지 않는다.
  A. 출처에 '단위: X' 가 적혀 있다 → 그 X 를 unit 에 옮겨 적는다
  B. 제목이나 모든 계열 이름이 '…율/률' 로 끝나고 값이 -200~200 안이다 → %
  C. 제목에 비중·비율·구성비·점유율이 있고 값이 -200~200 안이다 → %
  D. 누적 그래프인데 줄마다 합이 100 으로 떨어진다 → %

  python3 scripts/fill_units.py --dry-run
  python3 scripts/fill_units.py --apply
"""
import argparse, datetime, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
RATE = re.compile(r"(율|률)\s*$")
# '…율/률' 이라고 다 퍼센트가 아니다. 합계출산율은 명, 자살률은 10만 명당,
# 조혼인율은 천 명당이다. 이런 건 손대지 않는다.
NOT_PCT = re.compile(r"출산율|출산률|출생률|출생율|사망률|사망율|자살률|자살율|"
                     r"혼인율|이혼율|부양비|성비|사고율|재해율|발생률|발생율")
SHARE = re.compile(r"비중|비율|구성비|점유율")


def decide(it):
    vals = [v for s in it["series"] for v in s if v is not None]
    if not vals:
        return None, None
    lo, hi = min(vals), max(vals)
    title = (it.get("title") or "").strip().rstrip(".")
    names = [str(n or "").strip().rstrip(".") for n in it["seriesNames"]]

    m = re.search(r"단위\s*[:：]\s*([^,.]+)", it.get("source") or "")
    if m:
        u = m.group(1).strip()
        # '단위: 2026=100' 처럼 기준 시점을 적어 둔 건 단위가 아니다
        if u and not re.fullmatch(r"[\d\s=.,년]+", u) and len(u) <= 12:
            return u, "출처에 적힌 단위"

    inrange = (-200 <= lo and hi <= 200 and hi >= 2)
    if NOT_PCT.search(title):
        inrange = False
    if inrange and RATE.search(title):
        return "%", "제목이 …율/률"
    if inrange and names and all(n and RATE.search(n) for n in names):
        return "%", "계열 이름이 모두 …율/률"
    if inrange and SHARE.search(title):
        return "%", "제목에 비중·비율"

    st = it["vizType"] in ("stacked_bar", "stacked_bar_h") or (it["vizType"] == "area" and len(it["series"]) > 1)
    if st:
        tot, n = [], 0
        for i in range(len(it["labels"])):
            t, any_ = 0, False
            for s in it["series"]:
                if i < len(s) and s[i] is not None:
                    t += s[i]; any_ = True
            if any_:
                tot.append(t); n += 1
        if n >= 2 and min(tot) >= 99.5 and max(tot) <= 100.5:
            return "%", "누적 합이 100"
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.apply:
        a.dry_run = True

    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    hits, why = [], {}
    for it in items:
        if (it.get("unit") or "").strip():
            continue
        u, w = decide(it)
        if not u:
            continue
        hits.append((it.get("id"), it["title"][:30] or "(제목 없음)", u, w))
        why[w] = why.get(w, 0) + 1

    empty = sum(1 for it in items if not (it.get("unit") or "").strip())
    print(f"단위 비어 있는 차트 {empty}개 중 채울 수 있는 것 {len(hits)}개")
    for w, c in sorted(why.items(), key=lambda x: -x[1]):
        print(f"   {w}: {c}")
    print()
    for cid, t, u, w in hits[:25]:
        print(f"  {cid}  {t:32s} → {u:10s} ({w})")
    if len(hits) > 25:
        print(f"  … 외 {len(hits)-25}건")

    if a.apply and hits:
        ovp = os.path.join(DATA, "overrides.json")
        ov = json.load(open(ovp, encoding="utf-8"))
        stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        for cid, _, u, _ in hits:
            o = ov.setdefault(cid, {})
            o["unit"] = u
            o["revised"] = stamp
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n→ data/overrides.json 에 {len(hits)}건 반영. 다음: python3 scripts/build.py")
    elif hits:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
