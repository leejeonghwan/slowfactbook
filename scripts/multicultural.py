#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""다문화 혼인과 출생(c2299), 전체에서 다문화가 차지하는 비중(c2300).

  python3 scripts/multicultural.py            # 미리보기
  python3 scripts/multicultural.py --apply

분자는 국가데이터처 인구동향조사의 다문화 표 둘(혼인 DT_1BB0001, 출생
DT_1BB0005), 분모는 같은 조사의 월.분기.연간 인구동향(DT_1B8000G)이다.

refresh_api.py 는 차트 하나에 표 하나만 붙일 수 있어서 여기에 따로 둔다.
c2299 는 표 둘을 한 장에 담고, c2300 은 거기에 분모를 또 하나 쓴다.

다문화 표는 성별(C1)로 갈라져 있는데 '계'(C2=0)는 남녀가 같은 값이다.
전체 건수를 두 번 세지 않으려고 C1=1 한쪽만 읽는다.

겹치는 해를 전수 대조해 하나라도 어긋나면 손대지 않는다.
"""
import argparse, datetime, json, os, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
MARRIAGE, BIRTH, VITAL = "DT_1BB0001", "DT_1BB0005", "DT_1B8000G"


def kosis(**kw):
    p = dict(method="getList", apiKey=os.environ["KOSIS_API_KEY"], orgId="101",
             prdSe="Y", startPrdDe="2008", endPrdDe="2099", format="json", jsonVD="Y")
    p.update(kw)
    u = "https://kosis.kr/openapi/Param/statisticsParameterData.do?" + urllib.parse.urlencode(p)
    r = json.load(urllib.request.urlopen(u, timeout=120))
    if isinstance(r, dict):
        raise RuntimeError(f"{kw.get('tblId')}: {r}")
    return r


def multi(tbl):
    return {x["PRD_DE"]: float(x["DT"])
            for x in kosis(tblId=tbl, itmId="T00+", objL1="1+", objL2="0+")}


def vital():
    out = {}
    for x in kosis(tblId=VITAL, itmId="T1+", objL1="00+", objL2="10+20+"):
        out.setdefault(x["PRD_DE"], {})[x["C2_NM"]] = float(x["DT"])
    return out


def check(it, labels, series, tol):
    """겹치는 해를 전수 대조. 어긋난 곳을 돌려준다."""
    old = {str(l): [s[i] for s in it["series"]]
           for i, l in enumerate(str(x) for x in it["labels"])}
    bad, seen = [], 0
    for i, l in enumerate(labels):
        if l not in old:
            continue
        seen += 1
        for si in range(len(series)):
            a, b = old[l][si], series[si][i]
            if a is not None and b is not None and abs(a - b) > tol:
                bad.append((l, si, a, b))
    return bad, seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    mar, bir, tot = multi(MARRIAGE), multi(BIRTH), vital()
    ys = [y for y in sorted(mar) if y in bir]
    if not ys:
        print("내려온 값이 없습니다."); return 1
    print(f"원자료 {len(ys)}개 해: {ys[0]} ~ {ys[-1]}")

    plans = [
        ("c2299", ys, [[mar[y] for y in ys], [bir[y] for y in ys]], 0.5),
    ]
    zs = [y for y in ys if y in tot and tot[y].get("혼인건수(건)") and tot[y].get("출생아수(명)")]
    if zs:
        plans.append(("c2300", zs,
                      [[round(mar[y] / tot[y]["혼인건수(건)"] * 100, 1) for y in zs],
                       [round(bir[y] / tot[y]["출생아수(명)"] * 100, 1) for y in zs]], 0.11))

    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    items = {x["id"]: x for x in items if x.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    changed = False
    for cid, labels, series, tol in plans:
        it = items.get(cid)
        if not it:
            print(f"  - {cid}: 차트를 찾지 못했습니다"); continue
        title = it.get("title") or cid
        if len(it["series"]) != len(series):
            print(f"  - {cid} {title}: 계열 수가 맞지 않습니다"); continue
        bad, seen = check(it, labels, series, tol)
        if bad:
            print(f"  - {cid} {title}: 겹치는 {len(bad)}곳 어긋남 (예 {bad[:2]}) — 손대지 않습니다")
            continue
        print(f"  · {cid} {title}: 겹치는 {seen}개 해 대조 — 일치")
        have = {str(x) for x in it["labels"]}
        new = [l for l in labels if l not in have]
        if not new:
            print(f"    이미 최신 ({labels[-1]}, {len(labels)}점)"); continue
        for l in new:
            i = labels.index(l)
            print(f"    + {l}  " + "  ".join(f"{n} {series[k][i]}"
                  for k, n in enumerate(it.get("seriesNames") or range(len(series)))))
        if a.apply:
            o = ov.setdefault(cid, {}); o["id"] = cid
            o["labels"] = labels; o["series"] = series; o["updated"] = stamp
            changed = True

    if a.apply and changed:
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        open(ovp, "a", encoding="utf-8").write("\n")
        print("-> data/overrides.json 에 반영했습니다.")
    elif not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
