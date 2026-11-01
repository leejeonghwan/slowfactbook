#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""산업재해 사망자 수와 사망만인율(c0081, c0083, c0084).

  python3 scripts/safety.py            # 미리보기
  python3 scripts/safety.py --apply

고용노동부 산업재해현황, KOSIS 표 DT_11806_N013(사망재해 현황 및 분석 - 규모별).

이 표는 '그해 확정 통계' 한 해치만 담는다. 그래서 통째로 다시 까는 대신
표에 담긴 해를 차트에 이어 붙인다. 이미 그 해가 들어 있으면 값이 맞는지만
보고 넘어간다. 어긋나면 건드리지 않는다.

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
]


def fetch(key):
    url = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
           "&apiKey=%s&format=json&jsonVD=Y&orgId=118&tblId=%s&prdSe=Y"
           "&itmId=16118AAD8+16118AAD9+&objL1=15118AI700+&objL2=ALL&newEstPrdCnt=1"
           % (key, TBL))
    with urllib.request.urlopen(url, timeout=150) as r:
        doc = json.loads(r.read().decode("utf-8"))
    if isinstance(doc, dict):
        raise SystemExit("KOSIS 응답이 이상합니다: %s" % doc)
    by_size, year = {}, None
    for x in doc:
        if not x.get("DT"):
            continue
        year = x["PRD_DE"]
        by_size.setdefault(x["C2_NM"], {})[x["ITM_NM"]] = float(x["DT"])
    return year, by_size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 가 필요합니다(.env).")

    year, sz = fetch(key)
    tot = sz.get("전체") or {}
    deaths, rate = tot.get("사망자수"), tot.get("사망만인율")
    if deaths is None or rate is None:
        raise SystemExit("총계를 읽지 못했습니다.")
    print("  KOSIS %s년: 사망자 %d명, 사망만인율 %s" % (year, deaths, rate))

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

    # (차트, 계열별로 넣을 값) — 계열 순서는 차트에 이미 있는 순서를 따른다
    PLAN = {"c0081": [rate, float(deaths)], "c0083": [float(deaths)], "c0084": [rate]}
    touched = 0
    for cid, vals in PLAN.items():
        cur = {**base.get(cid, {}), **(ov.get(cid) or {})}
        lab = [str(x) for x in (cur.get("labels") or [])]
        ser = [list(s) for s in (cur.get("series") or [])]
        if len(ser) != len(vals):
            print("  %s 계열 수가 달라 건너뜁니다." % cid)
            continue
        if year in lab:
            i = lab.index(year)
            diff = [j for j, v in enumerate(vals)
                    if ser[j][i] is not None and abs(ser[j][i] - v) > max(0.01, abs(v) * 0.005)]
            if diff:
                for j in diff:
                    print("  어긋남 %s %s: 차트 %s / KOSIS %s" % (cid, year, ser[j][i], vals[j]))
                print("  %s 는 건드리지 않습니다." % cid)
                continue
            # 값은 그대로여도 출처와 비고는 최신으로 둔다
            ov[cid] = {**(ov.get(cid) or {}), "id": cid, "sourceUrl": URL, "notes": NOTES}
            touched += 1
            print("  %s 이미 %s년 반영됨 (출처와 비고만 갱신)" % (cid, year))
            continue
        lab.append(year)
        for j, v in enumerate(vals):
            ser[j].append(v)
        order = sorted(range(len(lab)), key=lambda i: lab[i])
        lab = [lab[i] for i in order]
        ser = [[s[i] for i in order] for s in ser]
        ov[cid] = {**(ov.get(cid) or {}), "id": cid, "labels": lab, "series": ser,
                   "sourceUrl": URL, "notes": NOTES,
                   "updated": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")}
        print("  %s 에 %s년 추가" % (cid, year))
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
