#!/usr/bin/env python3
"""
연도만 반복되는 가로축을 원래 시점(2026-09)으로 되살린다.

월간·분기 자료인데 키노트에서 월 표시를 빼고 연도만 남긴 차트가 많다. 그런데 연도가
몇 번씩 반복되는지를 보면 월을 역산할 수 있다. 가운데 해가 모두 12번씩(분기면 4번씩)
나오고 처음·끝 해만 부분이면, 빠진 달 없이 이어진 것이므로 시점이 하나로 정해진다.

  2009 가 12번, …, 2026 이 9번 → 2009-01 부터 2026-09 까지 213개월

가운데 해에 개수가 어긋나면 중간에 빠진 달이 있다는 뜻이라 손대지 않는다.
등록된 차트(api_map_auto)는 원자료가 시점을 직접 주므로 그쪽이 우선이다.

  python3 scripts/restore_labels.py              되살릴 수 있는 것 목록
  python3 scripts/restore_labels.py --apply
"""
import os, re, sys, json, argparse, datetime
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
YEAR = re.compile(r"^((?:19|20)\d{2})$")


def plan_marks(labels):
    """연도가 12개(또는 4·2개)마다 한 번씩만 찍히고 사이가 비어 있는 꼴.

    예: ['2012','','',…,'2013','','',…]  → 눈금이 그 해의 첫 달이므로 월이 정해진다.
    """
    L = [str(x).strip() for x in labels]
    marks = [(i, int(x)) for i, x in enumerate(L) if YEAR.fullmatch(x)]
    if len(marks) < 3:
        return None, "연도 눈금이 3개 미만"
    if any(x and not YEAR.fullmatch(x) for x in L):
        return None, "연도 아닌 라벨이 섞여 있음"
    gaps = {b - a for (a, _), (b, _) in zip(marks, marks[1:])}
    if len(gaps) != 1:
        return None, "연도 눈금 간격이 일정하지 않음"
    per = gaps.pop()
    if per not in (2, 4, 12):
        return None, f"눈금 간격 {per} — 월·분기·반기가 아님"
    ys = [y for _, y in marks]
    if ys != list(range(ys[0], ys[0] + len(ys))):
        return None, "눈금 연도가 한 해씩 늘지 않음"
    i0, y0 = marks[0]
    step = 12 // per
    out = []
    for j in range(len(L)):
        k = j - i0                      # 첫 눈금 기준 위치(앞쪽은 음수)
        y = y0 + (k // per)
        m = (k % per) * step + 1
        out.append(f"{y}-{m:02d}" if per == 12 else
                   (f"{y}-Q{(m - 1)//3 + 1}" if per == 4 else f"{y}-H{(m - 1)//6 + 1}"))
    for i, yv in marks:                 # 역산 결과가 눈금과 맞는지 확인
        if out[i][:4] != str(yv):
            return None, "역산 결과가 눈금과 어긋남"
    return per, out


def plan(labels):
    """되살릴 수 있으면 (주기, 새 라벨), 아니면 (None, 이유)."""
    L = [str(x).strip() for x in labels]
    if not all(YEAR.fullmatch(x) for x in L):
        return None, "연도만 있는 라벨이 아님"
    years = [int(x) for x in L]
    if any(b < a for a, b in zip(years, years[1:])):
        return None, "연도가 뒤로 가는 구간이 있음"
    c = Counter(years)
    ks = sorted(c)
    if len(ks) < 3:
        return None, "해가 너무 적음"
    if ks != list(range(ks[0], ks[-1] + 1)):
        return None, "중간에 빠진 해가 있음"
    mid = [c[y] for y in ks[1:-1]]
    per = Counter(mid).most_common(1)[0][0] if mid else max(c.values())
    if per not in (2, 4, 12):
        return None, f"한 해 {per}개 — 월·분기·반기가 아님"
    if any(v != per for v in mid):
        return None, "가운데 해의 개수가 들쭉날쭉 — 빠진 구간이 있음"
    if c[ks[0]] > per or c[ks[-1]] > per:
        return None, "처음·끝 해 개수가 한 해치를 넘음"
    step = 12 // per
    start = (per - c[ks[0]]) * step + 1          # 첫 해가 부분이면 그만큼 뒤에서 시작
    out, y, m = [], ks[0], start
    for _ in range(len(L)):
        out.append(f"{y}-{m:02d}" if per == 12 else
                   (f"{y}-Q{(m - 1)//3 + 1}" if per == 4 else f"{y}-H{(m - 1)//6 + 1}"))
        m += step
        if m > 12:
            y, m = y + 1, m - 12
    if [o[:4] for o in out] != L:
        return None, "역산 결과가 원래 연도와 어긋남"
    return per, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--id", help="차트 하나만")
    a = ap.parse_args()

    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import generate_site as g
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    auto = set(json.load(open(os.path.join(DATA, "api_map_auto.json"), encoding="utf-8")))

    done, skip = [], Counter()
    for it in g.load_items(DATA):
        cid = it.get("id")
        if not cid or (a.id and cid != a.id):
            continue
        per, res = plan(it.get("labels") or [])
        if per is None:
            per2, res2 = plan_marks(it.get("labels") or [])
            if per2 is None:
                skip[res] += 1
                continue
            per, res = per2, res2
        done.append((cid, it["title"], per, len(res), res[0], res[-1], cid in auto))

    name = {12: "월", 4: "분기", 2: "반기"}
    print(f"되살릴 수 있는 차트 {len(done)}개")
    for k, v in Counter(d[2] for d in done).items():
        print(f"  {name[k]}간 {v}개")
    print("\n안 되는 이유")
    for why, n in skip.most_common(8):
        print(f"  {n:>5}  {why}")
    print("\n예시")
    for cid, t, per, n, a0, a1, reg in done[:12]:
        print(f"  {cid} {t[:26]:28s} {name[per]} {n:>4}점  {a0} ~ {a1}{'  [자동갱신 등록됨]' if reg else ''}")

    if a.apply and done:
        stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        by = {it.get("id"): it for it in g.load_items(DATA)}
        for cid, *_ in done:
            per, res = plan(by[cid]["labels"])
            if per is None:
                per, res = plan_marks(by[cid]["labels"])
            o = ov.setdefault(cid, {})
            o["labels"] = res
            o["updated"] = stamp
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n→ {len(done)}개 차트의 가로축을 되살렸습니다. 다음: python3 scripts/build.py")
    elif done:
        print("\n(미리보기입니다. 반영하려면 --apply)")


if __name__ == "__main__":
    main()
