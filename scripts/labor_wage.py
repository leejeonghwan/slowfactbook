#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""고용형태별근로실태조사 임금·근로시간 차트.

  python3 scripts/labor_wage.py            # 미리보기
  python3 scripts/labor_wage.py --apply

KOSIS 표 두 개를 읽는다.

  DT_118N_LCE0002  성별 임금 및 근로시간   (고용형태 × 성별)
  DT_118N_LCE0001  고용형태별 임금 및 근로시간 (고용형태)

차트마다 '어느 표의 어느 칸'인지만 아래 REGISTRY 에 적는다. 겹치는 해를
전수 대조해 하나라도 어긋나면 그 차트는 건드리지 않는다.

주의. 이 조사는 상용근로자 5인 이상 사업체가 대상이다. 월 단위 '사업체
노동력조사'와는 모집단도 정의도 달라 숫자가 다르다. 섞어 쓰면 안 된다.
"""
import argparse, datetime, json, os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
P = "13102732815"

SEX = {"남": "SEXS.1", "여": "SEXS.2"}
TYPE = {"전체": "TYPES.00", "정규": "TYPES.02", "비정규": "TYPES.03"}
ITM = {"총근로시간": "13103732814DD_2", "시간당임금총액": "16118DD_11",
       "월임금총액": "16118DD_10"}

NOTE_BASE = ("고용노동부 고용형태별근로실태조사입니다. 상용근로자 5인 이상 사업체가 "
             "대상이라 5인 미만 사업장과 자영업자는 빠집니다.")
NOTE_MIX = ("해마다 6월 한 달을 조사해 연간값으로 씁니다. 매달 내는 사업체노동력조사와는 "
            "모집단도 정의도 달라 숫자가 다릅니다. 두 통계를 섞어 비교하면 안 됩니다.")

REGISTRY = {
    "c0026": {"title": "남녀 노동시간 격차", "itm": "총근로시간", "unit": "시간",
              "by": "sex", "type": "전체", "round": 1,
              "source": "고용노동부 고용형태별근로실태조사. 월 총근로시간. 단위: 시간.",
              "names": ["남", "여"], "colors": ["#2a5ca8", "#c0322f"]},
    "c0027": {"title": "남녀 시간당 임금 총액", "itm": "시간당임금총액", "unit": "원",
              "by": "sex", "type": "전체",
              "source": "고용노동부 고용형태별근로실태조사. 시간당 임금총액. 단위: 원.",
              "names": ["남", "여"], "colors": ["#2a5ca8", "#c0322f"]},
    "c2046": {"title": "남녀 월 임금 총액", "itm": "월임금총액", "unit": "만 원",
              "by": "sex", "type": "전체", "scale": 0.1, "round": 1,
              "source": "고용노동부 고용형태별근로실태조사. 월 임금총액. 단위: 만 원.",
              "names": ["남성", "여성"], "colors": ["#2a5ca8", "#c0322f"]},
    "c0064": {"title": "정규직과 비정규직 시간당 임금", "itm": "시간당임금총액",
              "unit": "원", "by": "type",
              "source": "고용노동부 고용형태별근로실태조사. 시간당 임금총액. 단위: 원.",
              "names": ["정규직 노동자", "비정규직 노동자"],
              "colors": ["#2a5ca8", "#c0322f"]},
}


def pull(tbl, itm, keys, obj_level, fixed, key):
    """keys: [(이름, 코드꼬리)] → {이름: {연도: 값}}"""
    codes = "".join("%s%s+" % (P, k) for _, k in keys)
    if obj_level == 1:
        o1, o2 = codes, "%s%s+" % (P, fixed)
    else:
        o1, o2 = "%s%s+" % (P, fixed), codes
    url = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
           "&apiKey=%s&format=json&jsonVD=Y&orgId=118&tblId=%s&prdSe=Y&itmId=%s+"
           "&objL1=%s&objL2=%s&startPrdDe=1990&endPrdDe=2035"
           % (key, tbl, ITM[itm], o1, o2))
    with urllib.request.urlopen(url, timeout=120) as r:
        doc = json.loads(r.read().decode("utf-8"))
    if isinstance(doc, dict):
        return {}
    col = "C1" if obj_level == 1 else "C2"
    tail = {k: n for n, k in keys}
    out = {}
    for x in doc:
        if not x.get("DT"):
            continue
        for k, n in tail.items():
            if x[col].endswith(k.split(".")[-1]):
                out.setdefault(n, {})[x["PRD_DE"]] = float(x["DT"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 가 필요합니다(.env).")

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
                if it.get("id") in REGISTRY:
                    base[it["id"]] = it

    touched = 0
    for cid, spec in REGISTRY.items():
        if spec["by"] == "sex":
            got = pull("DT_118N_LCE0002", spec["itm"],
                       [("A", SEX["남"]), ("B", SEX["여"])], 2, TYPE[spec["type"]], key)
        else:
            got = pull("DT_118N_LCE0001", spec["itm"],
                       [("A", TYPE["정규"]), ("B", TYPE["비정규"])], 1, None, key) \
                  if False else pull("DT_118N_LCE0002", spec["itm"],
                       [("A", TYPE["정규"]), ("B", TYPE["비정규"])], 1,
                       SEX and "SEXS.0", key)
        if len(got) != 2:
            print("  %s 자료를 받지 못했습니다." % cid)
            continue
        sc, nd = spec.get("scale", 1), spec.get("round", 0)
        for k in got:
            got[k] = {y: (round(v * sc, nd) if nd else round(v * sc)) for y, v in got[k].items()}

        cur = {**base.get(cid, {}), **(ov.get(cid) or {})}
        lab = [str(x) for x in (cur.get("labels") or [])]
        bad = 0
        for j, k in enumerate(("A", "B")):
            old = cur.get("series", [[], []])[j] if j < len(cur.get("series", [])) else []
            for y, v in zip(lab, old):
                g = got[k].get(y)
                if v is None or g is None:
                    continue
                if abs(g - v) > max(0.2, abs(v) * 0.003):
                    print("  어긋남 %s %s %s: 차트 %s / KOSIS %s" % (cid, y, k, v, g))
                    bad += 1
        if bad:
            print("  %s 는 건드리지 않습니다(%d군데)." % (cid, bad))
            continue
        years = sorted(set(got["A"]) | set(got["B"]))
        print("  %s %s: %s ~ %s (%d해) — 겹치는 구간 일치"
              % (cid, spec["title"], years[0], years[-1], len(years)))
        ov[cid] = {
            **(ov.get(cid) or {}), "id": cid, "title": spec["title"],
            "source": spec["source"], "unit": spec["unit"],
            "sourceUrl": "https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=DT_118N_LCE0002",
            "labels": years,
            "series": [[got["A"].get(y) for y in years], [got["B"].get(y) for y in years]],
            "seriesNames": spec["names"], "seriesColors": spec["colors"],
            "notes": [NOTE_BASE, NOTE_MIX],
            "updated": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        }
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
