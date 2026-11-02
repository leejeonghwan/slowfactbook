#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""연령대별 정규직과 비정규직 시간당 임금.

  python3 scripts/wage_by_age.py            # 미리보기
  python3 scripts/wage_by_age.py --apply

고용노동부 고용형태별근로실태조사, KOSIS 표 DT_118N_LCE0004(연령별 임금 및
근로시간). 2006년부터 들어 있고 해마다 6월 한 달을 조사한다.

두 장을 만든다.
  스냅샷  가장 최근 해의 연령대별 정규직·비정규직 시간당 임금
  추이    연령대별 격차(비정규직 ÷ 정규직)의 20년 흐름

일자리행정통계의 대기업·중소기업 구분(c0188)과는 조사도 기준도 다르다.
그쪽은 행정자료 기반 월평균 소득이고 이쪽은 표본조사 시간당 임금이다.
"""
import argparse, datetime, json, os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
P = "13102732817"
TBL = "DT_118N_LCE0004"
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=" + TBL
AGES = [("29세 이하", "1", "29세이하"), ("30대", "2", "30~39세"), ("40대", "3", "40~49세"),
        ("50대", "4", "50~59세"), ("60세 이상", "5", "60세이상")]
TYPES = [("정규직", "02", "정규근로자"), ("비정규직", "03", "비정규근로자")]
NOTE_BASE = ("고용노동부 고용형태별근로실태조사입니다. 상용근로자 5인 이상 사업체를 "
             "해마다 6월 한 달 조사합니다. 5인 미만 사업장과 자영업자는 빠집니다.")
NOTE_HOUR = ("시간당 임금총액입니다. 월급이 아니라 시간당이라 근로시간 차이가 "
             "걸러집니다. 비정규직은 월 근로시간이 짧아 월급으로 견주면 격차가 "
             "실제보다 커 보입니다.")
NOTE_OTHER = ("대기업과 중소기업으로 가른 차트(c0188)는 일자리행정통계 기반이라 "
              "조사도 기준도 다릅니다. 그쪽은 행정자료의 월평균 소득이고 이쪽은 "
              "표본조사의 시간당 임금입니다. 두 숫자를 나란히 놓으면 안 됩니다.")


def pull(itm, key):
    url = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
           "&apiKey=%s&format=json&jsonVD=Y&orgId=118&tblId=%s&prdSe=Y&itmId=%s+"
           "&objL1=%s&objL2=%s&startPrdDe=2000&endPrdDe=2035"
           % (key, TBL, itm,
              "".join("%sTYPES.%s+" % (P, t) for _, t, _ in TYPES),
              "".join("%sAGES.%s+" % (P, c) for _, c, _ in AGES)))
    with urllib.request.urlopen(url, timeout=150) as r:
        doc = json.loads(r.read().decode("utf-8"))
    if isinstance(doc, dict):
        raise SystemExit("KOSIS 응답이 이상합니다: %s" % doc)
    out = {}
    for x in doc:
        if x.get("DT"):
            out.setdefault((x["C1_NM"], x["C2_NM"]), {})[x["PRD_DE"]] = float(x["DT"])
    return out


def upsert(slide, item):
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    cur = next((i for i in doc["items"] if i.get("slide") == slide), None)
    if cur and cur.get("id"):
        item["id"] = cur["id"]
    if cur:
        doc["items"][doc["items"].index(cur)] = item
    else:
        doc["items"].append(item)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 가 필요합니다(.env).")
    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    r = pull("16118DD_11", key)
    years = sorted({y for v in r.values() for y in v})
    last = years[-1]
    get = lambda t, a_: r.get((t, a_), {})

    snap = []
    for label, _, raw in AGES:
        snap.append((label,
                     get("정규근로자", raw).get(last),
                     get("비정규근로자", raw).get(last)))
    if any(v is None for _, v, w in snap for v in (v, w)):
        raise SystemExit("빈 칸이 있어 멈춥니다.")

    item1 = {
        "slide": "manual-wage-age-type", "category": "노동",
        "title": "%s년 연령대별 정규직과 비정규직 시간당 임금" % last,
        "source": ("고용노동부 고용형태별근로실태조사(KOSIS 표 %s). %s년, 상용근로자 "
                   "5인 이상 사업체. 시간당 임금총액. 단위: 원." % (TBL, last)),
        "sourceUrl": URL, "vizType": "column", "unit": "원",
        "labels": [n for n, _, _ in snap],
        "series": [[v for _, v, _ in snap], [w for _, _, w in snap]],
        "seriesNames": ["정규직", "비정규직"],
        "seriesColors": ["#2a5ca8", "#c0322f"],
        "notes": [NOTE_BASE, NOTE_HOUR, NOTE_OTHER],
        "updated": now,
    }

    ratio = []
    for label, _, raw in AGES:
        reg, non = get("정규근로자", raw), get("비정규근로자", raw)
        ratio.append([round(non[y] / reg[y] * 100, 1) if y in reg and y in non and reg[y] else None
                      for y in years])
    item2 = {
        "slide": "manual-wage-age-gap", "category": "노동",
        "title": "연령대별 비정규직 임금 수준",
        "source": ("고용노동부 고용형태별근로실태조사(KOSIS 표 %s). 시간당 임금총액 기준, "
                   "같은 연령대 정규직을 100으로 둔 비정규직의 수준. 단위: %%." % TBL),
        "sourceUrl": URL, "vizType": "line", "unit": "%",
        "labels": years, "series": ratio,
        "seriesNames": [n for n, _, _ in AGES],
        "notes": [NOTE_BASE, NOTE_HOUR,
                  "같은 연령대 정규직을 100으로 둔 값입니다. 연령대를 가르지 않고 "
                  "전체로 비교하면 비정규직에 고령층이 많이 몰려 있어 격차가 더 크게 "
                  "보입니다. 그 효과를 걷어낸 것이 이 차트입니다.",
                  NOTE_OTHER],
        "updated": now,
    }

    print("  %s년 시간당 임금(원)" % last)
    for n, v, w in snap:
        print("    %-8s 정규 %6d  비정규 %6d  (%.1f%%)" % (n, v, w, w / v * 100))
    print("  추이 %s ~ %s (%d해)" % (years[0], years[-1], len(years)))

    if a.apply:
        upsert("manual-wage-age-type", item1)
        upsert("manual-wage-age-gap", item2)
        print("-> data/manual.json 에 반영했습니다(2장).")
    else:
        print("\n(미리보기입니다. 반영하려면 --apply)")


if __name__ == "__main__":
    main()
