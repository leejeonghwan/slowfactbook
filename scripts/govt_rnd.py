#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정부 연구개발 예산과 총지출에서 차지하는 몫(c23xx).

  KOSIS_API_KEY=... python3 scripts/govt_rnd.py            # 미리보기
  KOSIS_API_KEY=... python3 scripts/govt_rnd.py --apply

과학기술정보통신부 '국가연구개발사업의 총괄 투자 추이'(KOSIS 표 DT_127003_001)
한 표에서 정부 R&D 예산과 정부 총지출을 같이 받는다. 두 숫자를 다른 표에서
가져오면 회계 범위와 발표 시점이 어긋나 비중이 틀린다.

정부 R&D 예산은 '일반+특별+기금' 을 쓴다. 기금 사업이 R&D 의 큰 몫이라
일반회계만 보면 실제 규모를 놓친다.
"""
import argparse, datetime, json, os, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

SLIDE = "manual-govt-rnd"
ORG, TBL = "127", "DT_127003_001"
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=127&tblId=DT_127003_001"
RND, TOTAL = "일반+특별+기금", "총지출규모"


def pull(key):
    q = {"method": "getList", "apiKey": key, "format": "json", "jsonVD": "Y",
         "orgId": ORG, "tblId": TBL, "itmId": "ALL", "objL1": "ALL",
         "prdSe": "Y", "startPrdDe": "1990",
         "endPrdDe": str(datetime.datetime.now(KST).year)}
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + "&".join(f"{a}={urllib.parse.quote(str(b), safe='+')}" for a, b in q.items()))
    d = json.loads(urllib.request.urlopen(u, timeout=90).read().decode("utf-8"))
    if isinstance(d, dict):
        raise SystemExit("KOSIS: " + str(d)[:120])
    out = {}
    for r in d:
        out.setdefault(r["C1_NM"], {})[r["PRD_DE"]] = float(r["DT"])
    return out


def upsert(item):
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    cur = next((i for i in doc["items"] if i.get("slide") == SLIDE), None)
    if cur and cur.get("id"):
        item["id"] = cur["id"]
    else:
        ids = json.load(open(os.path.join(DATA, "ids.json"), encoding="utf-8"))
        key = "S\x1f%s\x1f%s" % (SLIDE, item["title"])
        if ids.get(key):
            item["id"] = ids[key]
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

    raw = pull(key)
    rnd, tot = raw.get(RND) or {}, raw.get(TOTAL) or {}
    # R&D 예산은 2011년부터, 총지출은 그보다 짧다. 막대는 끝까지 그리고
    # 몫은 총지출이 있는 해에만 둔다. 모자란 해를 다른 표에서 메우면
    # 회계 범위가 섞인다.
    years = sorted(rnd)
    if len(set(rnd) & set(tot)) < 5:
        raise SystemExit("총지출과 겹치는 해가 너무 적습니다 — 쓰지 않습니다.")
    # 억 원 -> 조 원.
    amt = [round(rnd[y] / 10000, 1) for y in years]
    share = [round(rnd[y] / tot[y] * 100, 2) if y in tot else None for y in years]
    last, prev = years[-1], years[-2]
    chg = (rnd[last] / rnd[prev] - 1) * 100

    print(f"KOSIS {TBL} — {years[0]} ~ {last} ({len(years)}개 해)")
    print(f"{'해':6s}{'R&D(조원)':>12s}{'총지출(조원)':>14s}{'몫(%)':>9s}")
    for y, m, s in zip(years, amt, share):
        print(f"{y:6s}{m:12.1f}" + (f"{tot[y] / 10000:14.1f}{s:9.2f}"
                                    if s is not None else f"{'-':>14s}{'-':>9s}"))
    print(f"  {last}년 전년 대비 {chg:+.1f}%")

    item = {
        "slide": SLIDE,
        "title": "정부 연구개발 예산",
        "category": "조세와 재정",
        "source": ("과학기술정보통신부 국가연구개발사업의 총괄 투자 추이"
                   f"(KOSIS 표 {TBL}). 정부 R&D 예산은 일반회계와 특별회계, 기금을 "
                   "합한 값. 몫은 정부 총지출 대비. 단위: 조 원, %."),
        "sourceUrl": URL,
        "vizType": "combo", "unit": "조 원",
        "seriesKinds": ["bar", "line"], "seriesAxes": [0, 1],
        "labels": years,
        "series": [amt, share],
        "seriesNames": ["정부 R&D 예산(조 원)", "정부 총지출에서 차지하는 몫(%)"],
        "seriesColors": ["#9aa7bd", "#c0322f"],
        "notes": [
            "정부 R&D 예산과 정부 총지출을 같은 표에서 받았습니다. 두 숫자를 "
            "다른 자료에서 가져오면 회계 범위와 발표 시점이 어긋나 몫이 틀립니다.",
            "R&D 예산은 일반회계와 특별회계, 기금을 모두 합한 값입니다. 기금 "
            "사업이 R&D 의 큰 몫이어서 일반회계만 보면 실제 규모를 놓칩니다. "
            f"{last}년 기준 일반회계만 보면 {raw['일반회계'][last] / 10000:.1f}조 원이지만 "
            f"기금까지 더하면 {amt[-1]}조 원입니다.",
            f"{prev}년에서 {last}년 사이 {chg:+.1f}% 움직였습니다. 금액이 줄어도 "
            "정부 총지출은 늘어나는 해가 있어, 막대와 선이 반대로 가는 구간을 "
            "눈여겨볼 만합니다.",
            "예산이지 집행액이 아닙니다. 같은 표의 집행액은 해마다 예산과 "
            "조금씩 다릅니다. 불용과 이월 때문입니다.",
            "이 표는 2011년부터입니다. 그 전 자료는 집계 방식이 달라 이어 붙이지 "
            "않았습니다. 총지출은 이 표에 2015년부터만 있어서 앞의 네 해는 몫 "
            "선이 비어 있습니다. 모자란 해를 다른 표에서 메우면 회계 범위가 "
            "섞이므로 비워 두었습니다.",
            "민간 연구개발비는 들어 있지 않습니다. 한국은 연구개발비의 4분의 3 "
            "가까이를 기업이 씁니다. 나라 전체의 연구개발 규모를 보려면 "
            "다른 차트를 봐야 합니다.",
        ],
        "updated": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
    }
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0
    upsert(item)
    print("-> data/manual.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
