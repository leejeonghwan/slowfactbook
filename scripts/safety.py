#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""산업재해 사망자 수와 사망만인율(c0081, c0083, c0084).

  python3 scripts/safety.py            # 미리보기
  python3 scripts/safety.py --apply

고용노동부 산업재해현황, KOSIS 표 DT_11806_N013(사망재해 현황 및 분석 - 규모별).

표에 2001년부터 들어 있다. 처음에는 newEstPrdCnt=1 로 한 해만 받아 놓고
'한 해치만 있는 표'로 잘못 알았다. 지금은 전 구간을 받아 겹치는 해를 전수
대조하고, 어긋나면 그 차트는 건드리지 않는다.

확정 통계는 이듬해 하반기에 나온다. 그 전에 보도자료의 잠정치를 손으로
넣어 둔 해가 있으면, 확정치가 나올 때 이 어댑터가 값을 덮지 않고 멈춘다.
그때는 잠정치를 지우고 다시 돌린다.
"""
import argparse, datetime, json, os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
TBL = "DT_11806_N013"
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=" + TBL
NOTES = [
    "고용노동부 산업재해현황입니다. 산재보험이 적용되는 사업장에서 산업재해로 "
    "승인된 사망자이며, 업무상 사고와 업무상 질병을 모두 포함합니다.",
    "사망만인율은 근로자 1만 명당 사망자 수입니다. 사망자 수만 보면 고용이 "
    "늘어난 효과가 섞이므로, 추세는 사망만인율로 보는 것이 맞습니다.",
    "확정 통계는 이듬해 하반기에 나옵니다. 가장 최근 해가 보도자료의 잠정치인 "
    "경우가 있고, 확정 과정에서 수백 명 단위로 바뀌기도 합니다.",
    "2012년 이전 수치는 고용노동부가 뒤에 소급 수정한 값입니다. 산재보험 적용 "
    "범위가 넓어지면서 과거 집계가 다시 계산됐습니다. 2003년 사망자가 옛 공표로는 "
    "2,701명이었는데 지금은 2,923명입니다. 그 무렵 기사에 적힌 숫자와 다를 수 "
    "있습니다.",
]


def fetch(key):
    url = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
           "&apiKey=%s&format=json&jsonVD=Y&orgId=118&tblId=%s&prdSe=Y"
           "&itmId=16118AAD8+16118AAD9+&objL1=15118AI700+&objL2=ALL"
           "&startPrdDe=2000&endPrdDe=2035" % (key, TBL))
    with urllib.request.urlopen(url, timeout=150) as r:
        doc = json.loads(r.read().decode("utf-8"))
    if isinstance(doc, dict):
        raise SystemExit("KOSIS 응답이 이상합니다: %s" % doc)
    by_year = {}
    for x in doc:
        if not x.get("DT"):
            continue
        by_year.setdefault(x["PRD_DE"], {}).setdefault(x["C2_NM"], {})[x["ITM_NM"]] = float(x["DT"])
    return by_year


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 가 필요합니다(.env).")

    by_year = fetch(key)
    year = max(by_year)
    tot = by_year[year].get("전체") or {}
    print("  KOSIS %s ~ %s (%d해). 최근 %s년: 사망자 %d명, 사망만인율 %s"
          % (min(by_year), year, len(by_year), year,
             tot.get("사망자수", 0), tot.get("사망만인율")))

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    base = {}
    for f in sorted(os.listdir(DATA)):
        if not f.endswith(".json"):
            continue
        try:
            doc = json.load(open(os.path.join(DATA, f), encoding="utf-8"))
        except Exception:
            continue
        if isinstance(doc, dict) and "items" in doc:
            for it in doc["items"]:
                if it.get("id"):
                    base[it["id"]] = it

    rate = {y: round(v["전체"]["사망만인율"], 2) for y, v in by_year.items() if "전체" in v}
    dead = {y: v["전체"]["사망자수"] for y, v in by_year.items() if "전체" in v}
    # (차트, 계열별 값 묶음) — 계열 순서는 차트에 이미 있는 순서를 따른다
    PLAN = {"c0081": [rate, dead], "c0083": [dead], "c0084": [rate]}
    touched = 0
    for cid, maps in PLAN.items():
        cur = {**base.get(cid, {}), **(ov.get(cid) or {})}
        lab = [str(x) for x in (cur.get("labels") or [])]
        ser = [list(s) for s in (cur.get("series") or [])]
        if len(ser) != len(maps):
            print("  %s 계열 수가 달라 건너뜁니다." % cid)
            continue
        bad = 0
        for j, mp in enumerate(maps):
            for y, v in zip(lab, ser[j]):
                g = mp.get(y)
                if v is None or g is None:
                    continue
                if abs(g - v) > max(0.01, abs(v) * 0.005):
                    print("  어긋남 %s %s: 차트 %s / KOSIS %s" % (cid, y, v, g))
                    bad += 1
        # 어긋나는 해는 KOSIS 값으로 덮는다. 고용노동부가 2012년 이전 통계를
        # 소급 수정했는데(산재보험 적용 범위가 넓어졌다) 차트에는 옛 공표값이
        # 남아 있었다. 원천이 정본이다.
        if bad:
            print("  %s: %d해를 KOSIS 값으로 덮습니다(2012년 이전 소급 수정분)." % (cid, bad))
        # 차트에만 있고 KOSIS 에 없는 해(보도자료 잠정치)는 그대로 둔다
        years = sorted(set(lab) | set(maps[0]))
        new_ser = []
        for j, mp in enumerate(maps):
            old_v = dict(zip(lab, ser[j]))
            new_ser.append([mp.get(y, old_v.get(y)) for y in years])
        ov[cid] = {**(ov.get(cid) or {}), "id": cid, "labels": years, "series": new_ser,
                   "sourceUrl": URL, "notes": NOTES,
                   "updated": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")}
        print("  %s %s ~ %s (%d해) — 겹치는 구간 일치" % (cid, years[0], years[-1], len(years)))
        touched += 1

    if a.apply and touched:
        with open(ovp, "w", encoding="utf-8") as fh:
            json.dump(ov, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write("\n")
        print("-> data/overrides.json 에 반영했습니다(%d장)." % touched)
    elif not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)")


if __name__ == "__main__":
    main()
