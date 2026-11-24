#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""점유형태 — 자가와 전세, 월세의 비중.

어디서 가져왔는가.
  KOSIS 는 인구주택총조사 가구 표를 API 로 공개하지 않는다. 회차별 표
  번호(2005년 DT_1GA0508, 2015년 DT_1JC1003, 2025년 DT_1PE2502)를 다
  찾아 축 코드까지 맞춰도 전부 '데이터 없음'으로 돌아온다. 다른 KOSIS
  표는 정상 응답하므로 서버 문제가 아니라 공개 범위의 문제다.

  그래서 발표 기관의 보도자료를 쓴다.
    전국 1980~2020년  2020년 보도자료 [표 22]
    전국 2000~2025년  2025년 보도자료 [표 42]
    서울 2015·2020년  2020년 보도자료 [표 24]
    전국·서울 2025년  2025년 보도자료에 붙은 공식 통계표(xlsx) 2-23 시트
  2025년 값만 파일에서 그때그때 받아 세고, 과거는 보도자료의 값을 둔다.

두 표를 어떻게 맞췄는가 — 월세의 범위가 다르다.
  [표 22]는 월세와 사글세를 따로 적는다. [표 42]는 사글세를 '보증금 없는
  월세'에 넣는다. 그래서 월세는 양쪽 다 사글세까지 더해 하나로 묶었다.
    2000년  표22 1,803+310 = 2,113 = 표42 1,524+589
  겹치는 2000~2020년 다섯 시점이 모두 맞는 것을 검산으로 확인한다.
  반올림 때문에 천 가구 단위에서 1 차이가 나는 자리는 통과시킨다.

못 한 것.
  서울은 2015년부터 세 시점뿐이다. 2010년 이전 회차 보도자료는 mods.go.kr
  에서 옛 글 주소가 최신 글로 넘어가 받을 수 없었고, 서울 열린데이터광장의
  해당 데이터셋은 페이지가 'URL 오류'로 열리지 않는다. 짐작해서 채우지
  않는다.

섞으면 안 되는 것.
  '자가'는 자기집에 사는 가구이지 집을 가진 가구가 아니다. 서울에 집을
  두고 경기도에 전세로 사는 가구는 전세로 잡힌다.
  '무상'은 관사와 사택, 친척집처럼 세 없이 사는 경우다.
  표본조사라 등록센서스 가구 수와 총계가 다르다.
"""
import argparse
import datetime
import io as _io
import json
import os
import sys
import time
import urllib.request

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

XLSX = ("https://mods.go.kr/boardDownload.es?bid=203&list_no=448072"
        "&seq=4")
PRESS = ("https://mods.go.kr/board.es?mid=a10301010000&bid=203"
         "&list_no=448072&act=view&mainXml=Y")
SRC = "국가데이터처 인구주택총조사"

YEARS = ["1980", "1985", "1990", "1995", "2000", "2005", "2010",
         "2015", "2020", "2025"]
# 2020년 보도자료 [표 22] (천 가구). 월세와 사글세가 따로다.
T22 = {"계": [7969, 9571, 11355, 12958, 14312, 15887, 17339, 19112,
              20927],
       "자가": [4672, 5127, 5667, 6910, 7753, 8828, 9390, 10850, 11989],
       "전세": [1904, 2202, 3157, 3845, 4040, 3557, 3766, 2961, 3252],
       "월세": [1231, 1893, 2173, 1536, 1803, 2728, 3490, 4368, 4788],
       "사글세": [0, 0, 0, 339, 310, 284, 230, 161, 117],
       "무상": [162, 350, 358, 328, 406, 490, 464, 773, 781]}
# 2025년 보도자료 [표 42] (천 가구). 사글세는 보증금 없는 월세에 들었다.
T42Y = ["2000", "2005", "2010", "2015", "2020", "2025"]
T42 = {"계": [14312, 15887, 17339, 19112, 20927, 22495],
       "자가": [7753, 8828, 9390, 10850, 11989, 12816],
       "전세": [4040, 3557, 3766, 2961, 3252, 2998],
       "보증월세": [1524, 2395, 3148, 3878, 4387, 5426],
       "무보증월세": [589, 617, 571, 650, 518, 423],
       "무상": [406, 490, 464, 773, 781, 832]}
# 2020년 보도자료 [표 24] 서울 (%)
SEOUL = {"2015": {"자가": 42.1, "전세": 26.2, "월세": 28.5, "무상": 3.2},
         "2020": {"자가": 43.5, "전세": 25.7, "월세": 28.3, "무상": 2.5}}
# 2025년 보도자료 [표 44] 서울 (%) — 통계표로 다시 계산해 맞춘다
GATE_SEOUL25 = {"자가": 42.0, "전세": 21.7, "월세": 33.7, "무상": 2.5}

KINDS = ["자가", "전세", "월세", "무상"]
COLS = ["#2a5ca8", "#e8820c", "#c0322f", "#b8b8b8"]


def book(tries=3):
    last = None
    req = urllib.request.Request(XLSX, headers={"User-Agent":
                                                "Mozilla/5.0"})
    for i in range(tries):
        try:
            raw = urllib.request.urlopen(req, timeout=150).read()
            if len(raw) < 50000:
                raise RuntimeError(f"받은 파일이 {len(raw)}바이트뿐이다")
            return openpyxl.load_workbook(_io.BytesIO(raw),
                                          data_only=True)
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(3 + 3 * i)
    raise RuntimeError(f"통계표를 받지 못했다: {last}")


def sheet23(wb):
    """{행정구역: [일반가구, 자기집, 전세, 보증월세, 무보증월세,
    사글세, 무상]} — 거처의 종류가 '계'인 줄만."""
    out, area = {}, None
    for r in wb["2-23"].iter_rows(values_only=True):
        c = list(r) + [None] * 10
        if c[0] not in (None, ""):
            area = str(c[0]).strip()
        kind = str(c[1]).strip() if c[1] not in (None, "") else None
        if kind == "계" and isinstance(c[2], (int, float)):
            out[area] = [float(x) for x in c[2:9]]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    wb = book()
    s23 = sheet23(wb)
    print(f"    받음: 점유형태 {len(s23)}개 지역 (공식 통계표 2-23)")

    # 검산 1. 두 보도자료 표가 겹치는 2000~2020년에서 같은가
    bad = []
    for i, yr in enumerate(T42Y[:-1]):
        j = YEARS.index(yr)
        pair = [("계", T22["계"][j], T42["계"][i]),
                ("자가", T22["자가"][j], T42["자가"][i]),
                ("전세", T22["전세"][j], T42["전세"][i]),
                ("월세", T22["월세"][j] + T22["사글세"][j],
                 T42["보증월세"][i] + T42["무보증월세"][i]),
                ("무상", T22["무상"][j], T42["무상"][i])]
        for nm, x, y in pair:
            if abs(x - y) > 1:                      # 반올림 1천 가구는 통과
                bad.append((yr, nm, x, y))
    if bad:
        print(f"  검산 실패: 두 보도자료 표가 어긋난다 {bad[:4]}")
        return 1
    print("    검산 교차: 2000~2020년 다섯 시점 × 다섯 항목이 "
          "2020년 표 22와 2025년 표 42에서 일치")

    # 전국 계열을 세운다
    nat = {k: [] for k in ["계"] + KINDS}
    for j, yr in enumerate(YEARS):
        if yr == "2025":
            v = s23["전국"]
            nat["계"].append(v[0] / 1000)
            nat["자가"].append(v[1] / 1000)
            nat["전세"].append(v[2] / 1000)
            nat["월세"].append((v[3] + v[4] + v[5]) / 1000)
            nat["무상"].append(v[6] / 1000)
        else:
            nat["계"].append(T22["계"][j])
            nat["자가"].append(T22["자가"][j])
            nat["전세"].append(T22["전세"][j])
            nat["월세"].append(T22["월세"][j] + T22["사글세"][j])
            nat["무상"].append(T22["무상"][j])

    # 검산 2. 2025년 전국이 보도자료 표 42와 같은가
    bad = [(k, round(nat[k][-1]), T42[k][-1]) for k in ("계", "자가",
                                                        "전세", "무상")
           if abs(nat[k][-1] - T42[k][-1]) > 1]
    m25 = T42["보증월세"][-1] + T42["무보증월세"][-1]
    if abs(nat["월세"][-1] - m25) > 1:
        bad.append(("월세", round(nat["월세"][-1]), m25))
    if bad:
        print(f"  검산 실패: 통계표의 2025년이 표 42와 다르다 {bad}")
        return 1
    print(f"    검산 2025: 통계표의 전국 "
          f"{nat['계'][-1]*1000:,.0f}가구가 보도자료 표 42와 일치")

    # 검산 3. 네 항목의 합이 계와 같은가
    bad = []
    for j, yr in enumerate(YEARS):
        s = sum(nat[k][j] for k in KINDS)
        if abs(s - nat["계"][j]) > 1.5:
            bad.append((yr, round(s), round(nat["계"][j])))
    if bad:
        print(f"  검산 합계: 네 항목 합이 계와 다르다 {bad}")
        return 1
    print(f"    검산 합계: {len(YEARS)}개 시점 모두 "
          "자가+전세+월세+무상 = 계")

    pct = {k: [round(nat[k][j] / nat["계"][j] * 100, 1)
               for j in range(len(YEARS))] for k in KINDS}

    # 서울
    v = s23["서울특별시"]
    s25 = {"자가": v[1], "전세": v[2],
           "월세": v[3] + v[4] + v[5], "무상": v[6]}
    sp25 = {k: round(s25[k] / v[0] * 100, 1) for k in KINDS}
    bad = [(k, sp25[k], GATE_SEOUL25[k]) for k in KINDS
           if abs(sp25[k] - GATE_SEOUL25[k]) > 0.15]
    if bad:
        print(f"  검산 실패: 서울 2025년이 보도자료 표 44와 다르다 "
              f"{bad}")
        return 1
    print(f"    검산 서울: 통계표로 계산한 2025년 서울이 보도자료 "
          f"표 44와 일치 (자가 {sp25['자가']}%, 전세 "
          f"{sp25['전세']}%, 월세 {sp25['월세']}%)")

    sy = ["2015", "2020", "2025"]
    spct = {k: [SEOUL[y][k] if y in SEOUL else sp25[k] for y in sy]
            for k in KINDS}
    bad = [(y, round(sum(spct[k][i] for k in KINDS), 1))
           for i, y in enumerate(sy)
           if abs(sum(spct[k][i] for k in KINDS) - 100) > 0.3]
    if bad:
        print(f"  검산 실패: 서울 합이 100%가 아니다 {bad}")
        return 1
    print("    검산 서울합: 세 시점 모두 네 항목 합이 100%")

    out = []
    out.append({
        "slide": "manual-tenure-national", "category": "부동산",
        "title": "점유형태별 가구 비중.",
        "vizType": "line", "unit": "%",
        "labels": list(YEARS),
        "series": [pct[k] for k in KINDS],
        "seriesNames": list(KINDS), "seriesColors": COLS,
        "source": (f"{SRC}. 일반가구 기준, 1980~2025년. 2015년부터는 "
                   "표본조사 결과입니다. 단위: %."),
        "sourceUrl": PRESS,
        "notes": [
            f"2025년 자가 {pct['자가'][-1]}%, 월세 {pct['월세'][-1]}%, "
            f"전세 {pct['전세'][-1]}%입니다. 전세는 1995년 "
            f"{pct['전세'][3]}%로 가장 높았다가 계속 내려왔고, 월세는 "
            f"1995년 {pct['월세'][3]}%에서 올라와 2015년에 전세를 "
            "넘어섰습니다.",
            "월세는 보증금 있는 월세와 보증금 없는 월세, 사글세를 모두 "
            "더한 것입니다. 발표 기관이 회차마다 사글세를 따로 적기도 "
            "하고 월세에 넣기도 해서 하나로 묶었습니다. 겹치는 "
            "2000~2020년에서 두 방식의 숫자가 같은 것을 확인했습니다.",
            "자가는 자기집에 사는 가구이지 집을 가진 가구가 "
            "아닙니다. 서울에 집을 두고 다른 곳에 전세로 사는 가구는 "
            "전세로 잡힙니다.",
            "무상은 관사와 사택, 친척집처럼 세 없이 사는 경우입니다.",
            "5년마다 하는 조사입니다. 2015년부터는 전국 20% 표본가구를 "
            "조사한 표본조사 결과라 등록센서스 가구 수와 총계가 "
            "다릅니다.",
            f"출처 보도자료: {PRESS}",
        ],
        "updated": ymd,
    })
    out.append({
        "slide": "manual-tenure-seoul", "category": "부동산",
        "title": "서울의 점유형태별 가구 비중.",
        "vizType": "column", "unit": "%",
        "labels": list(sy),
        "series": [spct[k] for k in KINDS],
        "seriesNames": list(KINDS), "seriesColors": COLS,
        "source": (f"{SRC} 표본조사. 서울 일반가구 기준, "
                   "2015년과 2020년, 2025년. 단위: %."),
        "sourceUrl": PRESS,
        "notes": [
            f"2025년 서울은 자가 {spct['자가'][-1]}%, 월세 "
            f"{spct['월세'][-1]}%, 전세 {spct['전세'][-1]}%입니다. "
            f"전세는 2020년 {spct['전세'][1]}%에서 "
            f"{spct['전세'][-1]-spct['전세'][1]:+.1f}%포인트, 월세는 "
            f"{spct['월세'][1]}%에서 "
            f"{spct['월세'][-1]-spct['월세'][1]:+.1f}%포인트입니다. "
            "다섯 해 사이에 전세에서 월세로 옮겨 간 폭이 큽니다.",
            "서울은 전세와 월세 비중이 모두 시도 가운데 가장 "
            "높습니다. 자가 비중은 가장 낮습니다. 2025년 전국은 자가 "
            f"{pct['자가'][-1]}%, 전세 {pct['전세'][-1]}%, 월세 "
            f"{pct['월세'][-1]}%입니다.",
            "세 시점뿐입니다. 2010년 이전 회차는 발표 기관 게시판에서 "
            "옛 글 주소가 최신 글로 넘어가 받지 못했고, 서울시가 따로 "
            "내놓은 같은 자료는 내려받기 쪽이 열리지 않았습니다. "
            "짐작해서 채우지 않았습니다.",
            "월세는 보증금 있는 월세와 보증금 없는 월세, 사글세를 모두 "
            "더한 것입니다.",
            f"출처 보도자료: {PRESS}",
        ],
        "updated": ymd,
    })

    print()
    for x in out:
        print(f"  {x['slide']} {len(x['labels'])}점 | {x['title']}")
        for nm, s in zip(x["seriesNames"], x["series"]):
            print(f"     {nm}: {s}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8"))
    idx = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for x in out:
        prev = idx.get(x["slide"])
        if prev:
            keep = {k: prev[k] for k in ("id",) if k in prev}
            prev.clear()
            prev.update(x)
            prev.update(keep)
        else:
            doc["items"].append(x)
    with open(mp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(mp, encoding="utf-8"))
    print(f"-> data/manual.json 에 {len(out)}장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
