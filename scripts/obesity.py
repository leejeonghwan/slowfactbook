#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""비만율(국민건강영양조사) 차트.

KOSIS 177/DT_11702_N101 「비만 유병률(체질량지수 기준) 추이」.
  itmId=RATIO, objL1=SEX(1 전체 / 2 남자 / 3 여자),
  objL2=EX31(103 19세이상 표준화, 201~206 연령대).

함정 — 연령표준화.
e-나라지표와 보도자료의 '전체'는 EX31=103(19세이상 표준화)이다.
101(19세이상 조율)을 집으면 다른 숫자가 나온다. 지역사회건강조사
쪽에서 이미 한 번 밟은 함정이라 여기서도 표준화 쪽으로 고정한다.

연령대별(201~206)은 표준화가 아니라 조율이다. 표준화 값과 한 장에
섞으면 안 되므로 차트를 나눈다.
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

ORG, TBL = "177", "DT_11702_N101"
SRC = "질병관리청 「국민건강영양조사」(KOSIS 177/DT_11702_N101)"
URL = ("https://kosis.kr/statHtml/statHtml.do?orgId=177&tblId=DT_11702_N101")

SEX = [("전체", "1"), ("남자", "2"), ("여자", "3")]
AGES = [("19-29세", "201"), ("30-39세", "202"), ("40-49세", "203"),
        ("50-59세", "204"), ("60-69세", "205"), ("70세 이상", "206")]

# e-나라지표(idxCd=8021) 해설에 적힌 값. 이 숫자와 어긋나면 안 쓴다.
GATE_ALL = {"2007": 31.7, "2015": 33.2, "2020": 38.3, "2024": 38.1}
GATE_SEX = {"남자": ("2024", 48.8), "여자": ("2024", 26.2)}
GATE_AGE = ("40-49세", "2024", 44.1)


def envkey(k):
    v = os.environ.get(k)
    if v:
        return v
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.startswith(k + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def pull(key, l1, l2, tries=3):
    p = {"method": "getList", "apiKey": key, "itmId": "RATIO",
         "objL1": l1, "objL2": l2, "format": "json", "jsonVD": "Y",
         "prdSe": "Y", "startPrdDe": "1990", "endPrdDe": "2030",
         "orgId": ORG, "tblId": TBL}
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + urllib.parse.urlencode(p))
    last = None
    for i in range(tries):
        try:
            d = json.load(urllib.request.urlopen(u, timeout=40))
            if isinstance(d, dict) and d.get("err"):
                raise RuntimeError(f"KOSIS err {d.get('err')}: {d.get('errMsg')}")
            out = {}
            for r in d:
                v = r.get("DT")
                if v in (None, "", "-"):
                    continue
                out[r["PRD_DE"]] = round(float(v), 1)
            return out
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"받지 못했다(objL1={l1}, objL2={l2}): {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("KOSIS_API_KEY")
    if not key:
        print("KOSIS_API_KEY 가 없다")
        return 2
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    # ── 성별 추이(표준화)
    sex = {nm: pull(key, code, "103") for nm, code in SEX}
    years = sorted(set().union(*[set(v) for v in sex.values()]))
    allv = sex["전체"]

    for y, want in GATE_ALL.items():
        got = allv.get(y)
        if got != want:
            print(f"  검산 실패 전체 {y}년: e-나라지표 {want} vs KOSIS {got}")
            return 1
    print(f"    검산 전체: {len(GATE_ALL)}개 해 모두 e-나라지표와 일치")
    for nm, (y, want) in GATE_SEX.items():
        if sex[nm].get(y) != want:
            print(f"  검산 실패 {nm} {y}년: {want} vs {sex[nm].get(y)}")
            return 1
    print("    검산 성별: 2024년 남자, 여자 모두 일치")
    for y in years:
        m, w, t = sex["남자"].get(y), sex["여자"].get(y), allv.get(y)
        if None in (m, w, t):
            continue
        if not min(m, w) - 0.1 <= t <= max(m, w) + 0.1:
            print(f"  검산 실패 {y}년: 전체 {t} 가 남자 {m}, 여자 {w} 밖")
            return 1
    print(f"    검산 범위: {len(years)}개 해 모두 전체가 남녀 사이")

    trend = {
        "slide": "manual-obesity-sex",
        "category": "건강과 보건",
        "title": "비만율",
        "vizType": "line", "unit": "%",
        "labels": years,
        "series": [[sex[nm].get(y) for y in years] for nm, _ in SEX],
        "seriesNames": [nm for nm, _ in SEX],
        "seriesColors": ["#6a8f3c", "#2a5ca8", "#c0322f"],
        "source": (f"{SRC}. {years[0]}~{years[-1]}년. 19세 이상, "
                   "2005년 추계인구 기준 연령표준화. 단위: %."),
        "sourceUrl": URL,
        "notes": [
            f"{years[-1]}년 전체 {allv[years[-1]]}%입니다. 남자 "
            f"{sex['남자'][years[-1]]}%, 여자 {sex['여자'][years[-1]]}%로 "
            "남자가 크게 높습니다.",
            f"{years[0]}년 {allv[years[0]]}%에서 올랐습니다. 2020년 "
            f"{allv.get('2020')}%로 한 해 만에 크게 뛴 뒤 그 수준에 "
            "머물러 있습니다.",
            "체질량지수 25 이상을 비만으로 봅니다. 국제 기준인 30 초과와 "
            "달라서, 다른 나라 비만율과 그대로 견주면 안 됩니다.",
            "2005년 추계인구를 기준으로 연령을 보정한 값입니다. 보정하지 "
            "않은 조율과는 다른 숫자입니다. 섞어 읽으면 안 됩니다.",
            "조사가 해마다 있지는 않습니다. 1998년, 2001년, 2005년, "
            "2007년부터 해마다입니다. 가로축 간격이 고르지 않습니다.",
        ],
        "updated": ymd,
    }

    # ── 연령대별(조율)
    age = {nm: pull(key, "1", code) for nm, code in AGES}
    ay = sorted(set().union(*[set(v) for v in age.values()]))
    last = ay[-1]
    nm, gy, want = GATE_AGE
    if age[nm].get(gy) != want:
        print(f"  검산 실패 {nm} {gy}년: e-나라지표 {want} vs "
              f"KOSIS {age[nm].get(gy)}")
        return 1
    print(f"    검산 연령: {gy}년 {nm} {want}% 일치")
    vals = [age[n].get(last) for n, _ in AGES]
    if any(v is None for v in vals):
        print(f"  검산 실패: {last}년 연령대 값이 비었다")
        return 1
    top = AGES[vals.index(max(vals))][0]

    byage = {
        "slide": "manual-obesity-age",
        "category": "건강과 보건",
        "title": "연령대별 비만율",
        "vizType": "line", "unit": "%",
        "labels": ay,
        "series": [[age[n].get(y) for y in ay] for n, _ in AGES],
        "seriesNames": [n for n, _ in AGES],
        "source": (f"{SRC}. {ay[0]}~{last}년. 19세 이상. 단위: %."),
        "sourceUrl": URL,
        "notes": [
            f"{last}년에는 {top}가 {max(vals)}%로 가장 높습니다. "
            "그 뒤로는 나이가 들수록 낮아집니다.",
            "연령대별 값은 연령표준화를 하지 않은 조율입니다. 「비만율」 "
            "차트의 전체, 남자, 여자는 표준화한 값이라 여기 숫자와 "
            "바로 견주면 안 됩니다.",
            "체질량지수 25 이상 기준입니다.",
            "조사가 해마다 있지는 않아 가로축 간격이 고르지 않습니다.",
        ],
        "updated": ymd,
    }

    out = [trend, byage]
    for it in out:
        print(f"  {it['title']:14s} {len(it['labels'])}점 "
              f"{it['labels'][0]}~{it['labels'][-1]} 계열 {len(it['series'])}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0

    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    by = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for it in out:
        old = by.get(it["slide"])
        if old:
            keep = {k: old[k] for k in ("id",) if k in old}
            old.clear()
            old.update(it)
            old.update(keep)
        else:
            doc["items"].append(it)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(p, encoding="utf-8"))
    print(f"-> data/manual.json 에 {len(out)}장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
