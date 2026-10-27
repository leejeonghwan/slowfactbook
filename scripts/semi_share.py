#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""수출에서 반도체가 차지하는 비중(c2290).

  python3 scripts/semi_share.py            # 미리보기
  python3 scripts/semi_share.py --apply

분자는 과기정통부 ICT수출입통계(KOSIS)의 반도체 수출액, 분모는 한국은행
ECOS 통관기준 총수출이다. 둘 다 관세청 통관 기준이라 나눌 수 있다.

refresh_api.py 의 "ratio" 는 한 표 안의 두 항목을 나누는 장치라 여기엔 못 쓴다.
소스가 둘이라 따로 둔다. 분모가 아직 안 나온 달은 버린다. 반쪽짜리 비중을
내면 안 되기 때문이다.

겹치는 달을 전수 대조해서 하나라도 어긋나면 손대지 않는다.
"""
import argparse, datetime, json, os, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

CID = "c2290"
KOSIS = dict(orgId="127", tblId="DT_092_115_2009_S023",
             itmId="13103131003T1+", objL1="13102131003A.AF11100000+")
ECOS_STAT, ECOS_ITEM = "901Y118", "T002"
KST = datetime.timezone(datetime.timedelta(hours=9))
TOL = 0.11          # 소수 한 자리로 반올림한 값이라 0.1 까지는 같은 값으로 본다


def semiconductor():
    key = os.environ["KOSIS_API_KEY"]
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?" +
         urllib.parse.urlencode(dict(method="getList", apiKey=key, prdSe="M",
                                     startPrdDe="199601", endPrdDe="203512",
                                     format="json", jsonVD="Y", **KOSIS)))
    rows = json.load(urllib.request.urlopen(u, timeout=120))
    if isinstance(rows, dict):
        raise RuntimeError(f"KOSIS: {rows}")
    return {r["PRD_DE"]: float(r["DT"]) for r in rows if r.get("DT") not in (None, "")}


def total_exports():
    key = os.environ["ECOS_API_KEY"]
    u = (f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/5000/"
         f"{ECOS_STAT}/M/200001/203512/{ECOS_ITEM}")
    r = json.load(urllib.request.urlopen(u, timeout=120))
    rows = r.get("StatisticSearch", {}).get("row")
    if not rows:
        raise RuntimeError(f"ECOS: {json.dumps(r, ensure_ascii=False)[:200]}")
    return {x["TIME"]: float(x["DATA_VALUE"]) * 1000 for x in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    semi, tot = semiconductor(), total_exports()
    months = sorted(p for p in semi if p in tot and tot[p])
    if not months:
        print("겹치는 달이 없습니다."); return 1
    share = {p: round(semi[p] / tot[p] * 100, 1) for p in months}
    print(f"원자료 {len(months)}개월: {months[0]} ~ {months[-1]}")

    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    it = {x["id"]: x for x in items if x.get("id")}.get(CID)
    if not it:
        print(f"{CID} 차트를 찾지 못했습니다."); return 1

    labels = [str(x) for x in it["labels"]]
    have = dict(zip(labels, it["series"][0]))
    bad = []
    for p, v in share.items():
        k = f"{p[:4]}-{p[4:6]}"
        if k in have and have[k] is not None and abs(have[k] - v) > TOL:
            bad.append((k, have[k], v))
    if bad:
        print(f"겹치는 {len(bad)}곳이 어긋납니다 (예 {bad[:3]}) — 손대지 않습니다")
        return 1
    print(f"겹치는 {sum(1 for p in share if f'{p[:4]}-{p[4:6]}' in have)}개월 대조 — 일치")

    new = [p for p in months if f"{p[:4]}-{p[4:6]}" not in have]
    if not new:
        print(f"· 이미 최신 ({labels[-1]}, {len(labels)}점)"); return 0
    for p in new:
        print(f"+ {p[:4]}-{p[4:6]}  {share[p]}%")

    if not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)"); return 0

    for p in new:
        labels.append(f"{p[:4]}-{p[4:6]}")
    series = [[share[p] for p in months]]
    labels = [f"{p[:4]}-{p[4:6]}" for p in months]
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
