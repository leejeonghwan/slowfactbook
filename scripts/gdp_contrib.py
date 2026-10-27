#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""지출항목별 성장기여도(c2294).

  python3 scripts/gdp_contrib.py            # 미리보기
  python3 scripts/gdp_contrib.py --apply

한국은행 ECOS 200Y126(지출항목별 성장기여도, 원계열, 실질, 분기).

막대를 모두 더하면 그 분기 성장률이 되어야 한다. 그래서 주요 다섯 항목을
받은 뒤 '기타'를 성장률에서 빼서 만든다. 지식재산생산물투자, 재고증감,
통계상 불일치가 거기 들어간다. ecos_update.py 는 계열을 더하거나 빼지
못해서 여기에 따로 둔다.

겹치는 분기를 전수 대조해 하나라도 어긋나면 손대지 않는다.
"""
import argparse, datetime, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

CID = "c2294"
STAT = "200Y126"
PARTS = [("민간소비", "1010110"), ("정부소비", "1010120"), ("건설투자", "1020111"),
         ("설비투자", "1020112"), ("순수출", "1060150")]
TOTAL = "10601"
FROM = "2010Q1"
KST = datetime.timezone(datetime.timedelta(hours=9))
TOL = 0.051          # 소수 한 자리로 반올림한 값이라 0.05 까지는 같은 값으로 본다


def ser(item):
    key = os.environ["ECOS_API_KEY"]
    u = (f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/5000/"
         f"{STAT}/Q/{FROM}/2099Q4/{item}")
    r = json.load(urllib.request.urlopen(u, timeout=120))
    rows = r.get("StatisticSearch", {}).get("row")
    if not rows:
        raise RuntimeError(f"ECOS {item}: {json.dumps(r, ensure_ascii=False)[:160]}")
    return {x["TIME"]: round(float(x["DATA_VALUE"]), 2) for x in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    parts = [ser(c) for _, c in PARTS]
    total = ser(TOTAL)
    qs = sorted(total)
    if not qs:
        print("내려온 값이 없습니다."); return 1
    print(f"원자료 {len(qs)}분기: {qs[0]} ~ {qs[-1]}")

    labels = [f"{q[:4]}-Q{q[-1]}" for q in qs]
    series = [[d.get(q) for q in qs] for d in parts]
    series.append([round(total[q] - sum(d.get(q, 0) for d in parts), 2) for q in qs])

    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    it = {x["id"]: x for x in items if x.get("id")}.get(CID)
    if not it:
        print(f"{CID} 차트를 찾지 못했습니다."); return 1
    if len(it["series"]) != len(series):
        print(f"차트 계열 {len(it['series'])}개 != 만든 계열 {len(series)}개 — 손대지 않습니다")
        return 1

    old = {l: [s[i] for s in it["series"]] for i, l in enumerate(str(x) for x in it["labels"])}
    bad, seen = [], 0
    for i, l in enumerate(labels):
        if l not in old:
            continue
        seen += 1
        for si, v in enumerate(series[si][i] for si in range(len(series))):
            a0 = old[l][si]
            if a0 is not None and v is not None and abs(a0 - v) > TOL:
                bad.append((l, si, a0, v))
    if bad:
        print(f"겹치는 구간 {len(bad)}곳이 어긋납니다 (예 {bad[:3]}) — 손대지 않습니다")
        return 1
    print(f"겹치는 {seen}분기 대조 — 일치")

    new = [l for l in labels if l not in old]
    if not new:
        print(f"· 이미 최신 ({labels[-1]}, {len(labels)}점)"); return 0
    for l in new:
        i = labels.index(l)
        print(f"+ {l}  " + "  ".join(f"{n} {series[k][i]}" for k, (n, _) in enumerate(PARTS))
              + f"  기타 {series[-1][i]}  합 {round(sum(s[i] for s in series),2)}")

    if not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)"); return 0

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    o = ov.setdefault(CID, {}); o["id"] = CID
    o["labels"] = labels; o["series"] = series
    o["updated"] = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(ovp, "a", encoding="utf-8").write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
