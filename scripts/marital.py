#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""혼인상태와 미혼율 — 인구주택총조사 표본조사.

2026년 11월 24일 국가데이터처가 2025년 표본조사 결과를 냈다. 전국 20%
표본가구를 조사했고 혼인상태는 15세 이상 내국인이 대상이다.

어디서 받는가.
  KOSIS 는 아직 이 회차를 API 로 내보내지 않는다(err 30). 2020년과
  2015년 표도 번호는 있는데 데이터가 안 나온다. 그래서 보도자료에 붙은
  공식 통계표 파일(xlsx)을 그때그때 내려받아 거기서 센다.
  2000~2020년 시계열은 보도자료 본문 [그림 4](남자)와 [그림 5](여자)에
  찍힌 값을 쓴다. 발표 기관이 같은 문서에서 같은 기준으로 그린 것이다.
  2025년 자리는 통계표에서 다시 계산해 그림과 맞는지 본다.

검산은 서로 다른 산출물끼리 맞춘다.
  사람 수는 통계표(xlsx)에서 세고, 비중은 보도자료 본문의 [표 4]와 [표 5]
  와 맞춘다. 같은 파일 안에서 더하고 빼는 자기검산이 아니다.

옛 차트를 왜 통째로 바꿨는가.
  c0096 과 c2225 에 들어 있던 2000~2020년 값은 기준이 다른 계열이었다.
  30대 여자가 2015년에 옛 차트 25.2%, 보도자료 28.1% 로 2.9%포인트
  어긋난다. 40대 여자는 2020년에 11.9% 대 12.1% 다. 이어 붙이면 기준이
  섞이므로 전 구간을 보도자료 쪽으로 다시 세운다.

섞으면 안 되는 것.
  미혼율의 분모는 해당 연령의 내국인이다. 총인구가 아니다.
  '혼인 경험 있음'은 배우자 있음에 사별과 이혼을 더한 것이다. 현재
  배우자가 있는 사람만이 아니다.
  표본조사라 등록센서스의 인구와 총계가 다르다.

40대 여자의 2000년과 2005년은 보도자료 그림에서 라벨이 겹쳐 가려져
있다. 짐작하지 않고 빈칸으로 둔다.
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
SRC = "국가데이터처 2025 인구주택총조사 표본조사"
URL_MARI = URL_INT = URL_KID = PRESS

AGE5 = ["15~19세", "20~24세", "25~29세", "30~34세", "35~39세",
        "40~44세", "45~49세", "50~54세", "55~59세", "60~64세",
        "65~69세", "70~74세", "75~79세", "80~84세", "85세 이상"]
BAND10 = {"15~19세": ["15~19세"], "20대": ["20~24세", "25~29세"],
          "30대": ["30~34세", "35~39세"], "40대": ["40~44세", "45~49세"],
          "50대": ["50~54세", "55~59세"],
          "60세 이상": ["60~64세", "65~69세", "70~74세", "75~79세",
                        "80~84세", "85세 이상"]}
YEARS = ["2000", "2005", "2010", "2015", "2020", "2025"]

# 보도자료 [그림 4]와 [그림 5] 에 찍힌 값
TREND = {
    "남자": {"20대": [84.2, 90.1, 91.8, 94.7, 95.5, 96.7],
             "30대": [19.2, 29.8, 37.9, 44.2, 50.8, 61.1],
             "40대": [3.8, 6.5, 10.9, 18.2, 23.6, 27.7]},
    "여자": {"20대": [63.2, 76.1, 81.3, 87.5, 89.8, 92.9],
             "30대": [7.5, 13.3, 20.4, 28.1, 33.6, 44.3],
             "40대": [None, None, 4.8, 8.8, 12.1, 16.3]},
}
# 보도자료 [표 4] 2025년 미혼 비중(%)
TAB4 = {"계": {"15~19세": 100.0, "20대": 94.8, "30대": 53.1,
               "40대": 22.1, "50대": 11.1, "60세 이상": 2.8},
        "남자": {"15~19세": 100.0, "20대": 96.7, "30대": 61.1,
                 "40대": 27.7, "50대": 15.1, "60세 이상": 3.7},
        "여자": {"15~19세": 100.0, "20대": 92.9, "30대": 44.3,
                 "40대": 16.3, "50대": 7.1, "60세 이상": 2.1}}
# 보도자료 본문의 사람 수 (천 명 단위로 적힌 것을 명으로 옮김)
GATE_N = {("계", "계", "계"): 44576851, ("계", "계", "미혼"): 13880833}
# 보도자료 [표 5] 결혼 계획이나 의향이 있다는 비중(%)
GATE_INT = {("계", "전체"): 57.8, ("남자", "전체"): 60.4,
            ("여자", "전체"): 54.4, ("계", "19~29세"): 69.1,
            ("계", "30대"): 64.5, ("계", "40대"): 40.1,
            ("계", "50대"): 19.9}
GATE_KID = {"미혼": 0.8, "기혼": 0.2}

COL3 = ["#2a5ca8", "#e8820c", "#9b9b9b"]
COL_SEX = ["#2a5ca8", "#e8820c"]


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


def table(ws, keycols):
    """앞쪽 분류 칸은 위에서 이어받고, 숫자 줄만 거둔다."""
    out, carry = {}, [None] * keycols
    for r in ws.iter_rows(values_only=True):
        c = list(r)
        while c and c[-1] in (None, ""):
            c.pop()                       # 꼬리의 빈 칸을 떼어낸다
        c = c + [None] * (keycols + 1 - len(c))
        key = []
        for i in range(keycols):
            v = c[i]
            v = str(v).strip() if v not in (None, "") else None
            if v is not None:
                carry[i] = v
            key.append(carry[i])
        vals = c[keycols:]
        if not isinstance(vals[0], (int, float)):
            continue
        out[tuple(key)] = vals
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    wb = book()
    m = table(wb["1-2"], 3)      # 행정, 성별, 연령 -> 계,미혼,배우자,사별,이혼
    print(f"    받음: 혼인상태 {len(m)}줄 (공식 통계표 1-2)")

    # 검산 1. 보도자료 본문의 사람 수와 같은가
    bad = []
    for (sx, _a, kind), want in GATE_N.items():
        row = m.get(("전국", sx, "계"))
        if row is None:
            bad.append((sx, kind, None, want))
            continue
        got = row[0] if kind == "계" else row[1]
        if got != want:
            bad.append((sx, kind, got, want))
    if bad:
        print(f"  검산 실패: 보도자료 본문의 사람 수와 다르다 {bad}")
        return 1
    tot = m[("전국", "계", "계")]
    print(f"    검산 원문: 15세 이상 내국인 {tot[0]:,.0f}명, "
          f"미혼 {tot[1]:,.0f}명으로 보도자료 본문과 일치")

    # 검산 2. 혼인상태 넷의 합이 계와 같은가
    bad = []
    for k, v in m.items():
        if k[2] == "계" or k[0] != "전국":
            continue
        s = sum(x for x in v[1:5] if isinstance(x, (int, float)))
        if abs(s - v[0]) > 2:
            bad.append((k, s, v[0]))
    if bad:
        print(f"  검산 실패: 혼인상태 합이 계와 다르다 {bad[:3]}")
        return 1
    print("    검산 합계: 모든 칸에서 미혼+배우자+사별+이혼 = 계")

    # 검산 3. 남자 + 여자 = 계
    bad = []
    for age in AGE5:
        for i, nm in ((0, "계"), (1, "미혼")):
            s = (m[("전국", "남자", age)][i] + m[("전국", "여자", age)][i])
            t = m[("전국", "계", age)][i]
            if abs(s - t) > 2:
                bad.append((age, nm, s, t))
    if bad:
        print(f"  검산 실패: 남자+여자가 계와 다르다 {bad[:3]}")
        return 1
    print("    검산 성별: 모든 연령에서 남자+여자 = 계")

    def rate(sex, ages):
        t = sum(m[("전국", sex, x)][0] for x in ages)
        u = sum(m[("전국", sex, x)][1] for x in ages)
        return round(u / t * 100, 1) if t else None

    # 검산 4. 10년 구간 비중이 보도자료 [표 4] 와 같은가
    bad = []
    for sex, bands in TAB4.items():
        for b, want in bands.items():
            mine = rate(sex, BAND10[b])
            if mine is None or abs(mine - want) > 0.15:
                bad.append((sex, b, want, mine))
    if bad:
        print("  검산 실패: 표 4 와 다르다 "
              + ", ".join(f"{s} {b} 표 {w} / 계산 {x}"
                          for s, b, w, x in bad[:4]))
        return 1
    print(f"    검산 표4: 성별 3 × 연령 6 = {len(TAB4) * 6}개 비중이 "
          "보도자료와 일치")

    # 검산 5. 그림 4와 5의 2025년 자리가 계산값과 같은가
    bad = []
    for sex, bands in TREND.items():
        for b, row in bands.items():
            mine = rate(sex, BAND10[b])
            if abs(mine - row[-1]) > 0.15:
                bad.append((sex, b, row[-1], mine))
    if bad:
        print(f"  검산 실패: 그림의 2025년과 계산값이 다르다 {bad[:3]}")
        return 1
    print("    검산 그림: 그림 4와 5의 2025년 6개 값이 계산값과 일치")

    out_ov, out_new = {}, []


    # 1~2. 남성 / 여성 미혼자 비율 (2000~2025)
    for sex, cid in (("남자", "c0096"), ("여자", "c2225")):
        nm = "남성" if sex == "남자" else "여성"
        ser = [TREND[sex][b] for b in ("20대", "30대", "40대")]
        t30 = ser[1]
        notes = [
            f"2025년 {nm} 30대 미혼율은 {t30[-1]}%입니다. 2020년 "
            f"{t30[-2]}%에서 {t30[-1]-t30[-2]:+.1f}%포인트, 2000년 "
            f"{t30[0]}%에서는 {t30[-1]-t30[0]:+.1f}%포인트입니다. "
            f"20대는 {ser[0][-1]}%, 40대는 {ser[2][-1]}%입니다.",
            "분모는 해당 연령의 내국인입니다. 총인구가 아닙니다. "
            "외국인을 넣으면 값이 달라집니다.",
            "5년마다 하는 조사라 점이 5년 간격입니다. 전국 20% "
            "표본가구를 조사한 표본조사 결과이고 15세 이상 내국인이 "
            "대상입니다. 전수조사가 아니므로 등록센서스 인구와 총계가 "
            "다릅니다.",
            "전에 들어 있던 숫자와 다릅니다. 옛 계열은 기준이 다른 "
            "것이었습니다. 30대 여성이 2015년에 옛 값 25.2%, 보도자료 "
            "28.1%로 2.9%포인트 어긋났습니다. 섞어 쓰지 않으려고 전 "
            "구간을 2025년 보도자료의 값으로 다시 세웠습니다.",
            f"출처 보도자료: {PRESS}",
        ]
        if sex == "여자":
            notes.insert(3, "40대 여성의 2000년과 2005년은 보도자료 "
                            "그림에서 라벨이 겹쳐 읽을 수 없어 "
                            "비워 뒀습니다.")
        out_ov[cid] = {
            "labels": list(YEARS), "series": ser,
            "seriesNames": ["20대", "30대", "40대"],
            "seriesColors": COL3, "unit": "%", "vizType": "line",
            "source": (f"{SRC} 보도자료. {nm} 가운데 미혼인 사람의 비율, "
                       "2000~2025년. 단위: %."),
            "sourceUrl": URL_MARI, "notes": notes, "updated": ymd,
        }

    # 3. 연령대별 미혼과 혼인 경험 (2025)
    rows, un, ev = [], [], []
    for b in ("20대", "30대", "40대"):
        for sex in ("남자", "여자"):
            rows.append(f"{b} {'남성' if sex=='남자' else '여성'}")
            r = rate(sex, BAND10[b])
            un.append(r)
            ev.append(round(100 - r, 1))
    out_ov["c0117"] = {
        "labels": rows, "series": [un, ev],
        "seriesNames": ["미혼.", "혼인 경험 있음."],
        "seriesColors": ["#2a5ca8", "#c9c9c9"],
        "unit": "%", "vizType": "stacked_bar_h",
        "source": f"{SRC}. 2025년 기준. 단위: %.",
        "sourceUrl": URL_MARI,
        "notes": [
            f"30대 남성은 {un[2]}%가 미혼이고 30대 여성은 {un[3]}%입니다. "
            f"40대로 가면 남성 {un[4]}%, 여성 {un[5]}%로 떨어집니다.",
            "오른쪽은 배우자가 있는 사람에 사별과 이혼까지 더한 "
            "것입니다. 곧 한 번이라도 혼인한 적이 있는 사람입니다. "
            "현재 배우자가 있는 사람만이 아닙니다.",
            "분모는 해당 연령의 내국인입니다.",
            f"출처 보도자료: {PRESS}",
        ],
        "updated": ymd,
    }

    # 4. 연령별 미혼율 (2025, 5세 구간)
    ser = [[rate(s, [x]) for x in AGE5] for s in ("남자", "여자")]
    out_new.append({
        "slide": "manual-marital-age", "category": "인구 구조",
        "title": "연령별 미혼율.",
        "vizType": "line", "unit": "%",
        "labels": list(AGE5), "series": ser,
        "seriesNames": ["남자", "여자"], "seriesColors": COL_SEX,
        "source": (f"{SRC}. 2025년 기준, "
                   "15세 이상 내국인. 단위: %."),
        "sourceUrl": URL_MARI,
        "notes": [
            f"30~34세에서 남자 {ser[0][3]}%, 여자 {ser[1][3]}%입니다. "
            f"35~39세에서는 남자 {ser[0][4]}%, 여자 {ser[1][4]}%로 "
            "내려갑니다. 가장 가파르게 꺾이는 구간입니다.",
            "남자가 모든 구간에서 여자보다 높습니다. 혼인 연령 차이와 "
            "미혼 남녀의 성비가 함께 작용한 결과입니다.",
            "분모는 해당 연령의 내국인입니다. 표본조사 결과입니다.",
            f"출처 보도자료: {PRESS}",
        ],
        "updated": ymd,
    })

    # 5. 미혼인구의 결혼 의향 (2025)
    iv = table(wb["1-3"], 3)     # 행정, 성별, 연령 -> 미혼인구, 있음, 없음
    iages = ["19~24세", "25~29세", "30~34세", "35~39세", "40~44세",
             "45~49세", "50~54세", "55~59세", "60~64세"]
    IB = {"전체": ["계"], "19~29세": ["19~24세", "25~29세"],
          "30대": ["30~34세", "35~39세"], "40대": ["40~44세", "45~49세"],
          "50대": ["50~54세", "55~59세"]}

    def ir(sex, ages):
        t = sum(iv[("전국", sex, x)][0] for x in ages)
        y = sum(iv[("전국", sex, x)][1] for x in ages)
        return round(y / t * 100, 1) if t else None

    bad = []
    for (sx, b), want in GATE_INT.items():
        mine = ir(sx, IB[b])
        if mine is None or abs(mine - want) > 0.15:
            bad.append((sx, b, want, mine))
    if bad:
        print(f"  검산 실패: 표 5 와 다르다 {bad[:3]}")
        return 1
    whole = ir("계", ["계"])
    print(f"    검산 표5: 결혼 의향 {len(GATE_INT)}개 값이 보도자료와 "
          f"일치 (전체 {whole}%)")
    si = [[ir(s, [x]) for x in iages] for s in ("남자", "여자")]
    out_new.append({
        "slide": "manual-marital-intent", "category": "인구 구조",
        "title": "미혼인구의 결혼 의향.",
        "vizType": "line", "unit": "%",
        "labels": list(iages), "series": si,
        "seriesNames": ["남자", "여자"], "seriesColors": COL_SEX,
        "source": (f"{SRC} 공식 통계표. 19세 이상 미혼인구 "
                   "가운데 결혼 계획이나 의향이 있다고 답한 비율, "
                   "2025년. 단위: %."),
        "sourceUrl": URL_INT,
        "notes": [
            f"19세 이상 미혼인구 "
            f"{iv[('전국','계','계')][0]/10000:,.0f}만 명 가운데 "
            f"{whole}%가 "
            f"결혼 계획이나 의향이 있다고 답했습니다. 남자 "
            f"{ir('남자',['계'])}%, 여자 {ir('여자',['계'])}%입니다. "
            f"30~34세는 남자 {si[0][2]}%, 여자 {si[1][2]}%입니다.",
            "모든 구간에서 남자가 여자보다 높습니다.",
            "2025년 조사에 새로 들어간 항목이라 견줄 과거 값이 "
            "없습니다.",
            "의향을 물은 것이고 실제 혼인이 아닙니다. 미혼인구만 "
            "대상입니다.",
            f"출처 보도자료: {PRESS}",
        ],
        "updated": ymd,
    })

    # 6. 추가로 낳을 계획인 자녀 수 (2025)
    kv = table(wb["1-4"], 4)     # 행정, 성별, 연령, 혼인상태 -> ..., 평균
    ks = ["19~29세", "30~39세", "40~49세"]
    bad = []
    for st, want in GATE_KID.items():
        row = kv.get(("전국", "계", "계", st))
        got = row[-1] if row else None
        if not isinstance(got, (int, float)) or abs(got - want) > 0.05:
            bad.append((st, want, got))
    if bad:
        print(f"  검산 실패: 평균 추가계획 자녀수가 보도자료와 다르다 "
              f"{bad}")
        return 1
    print(f"    검산 자녀: 전체 미혼 "
          f"{kv[('전국','계','계','미혼')][-1]}명, 기혼 "
          f"{kv[('전국','계','계','기혼')][-1]}명으로 보도자료와 일치")
    # 통계표가 '-' 로 적은 칸은 소수 첫째 자리에서 0.0 으로 떨어진
    # 것이다. 짐작하지 않고 분포(0명, 1명, 2명, 3명 이상)로 평균을 직접
    # 구해 정말 0.0 인지 확인한 다음에만 0.0 으로 둔다.
    dash = []
    sk = []
    for st in ("미혼", "기혼"):
        row = []
        for x in ks:
            v = kv[("전국", "계", x, st)]
            avg = v[-1]
            if not isinstance(avg, (int, float)):
                n = v[0]
                calc = (v[2] + 2 * v[3] + 3 * v[4]) / n if n else None
                if calc is None or round(calc, 1) != 0.0:
                    print(f"  검산 실패: {st} {x} 의 '-' 가 0.0 이 "
                          f"아니다 (계산 {calc})")
                    return 1
                dash.append(f"{st} {x}({calc:.3f})")
                avg = 0.0
            row.append(round(float(avg), 2))
        sk.append(row)
    if dash:
        print(f"    검산 빈칸: 통계표가 '-' 로 적은 {', '.join(dash)} 를 "
              "분포로 다시 구해 0.0 임을 확인")
    out_new.append({
        "slide": "manual-marital-addkids", "category": "출산",
        "title": "추가로 낳을 계획인 자녀 수.",
        "vizType": "column", "unit": "명",
        "labels": list(ks), "series": sk,
        "seriesNames": ["미혼", "기혼"], "seriesColors": COL_SEX,
        "source": (f"{SRC} 공식 통계표. 19~49세의 평균 "
                   "추가계획 자녀 수, 2025년. 단위: 명."),
        "sourceUrl": URL_KID,
        "notes": [
            f"30~39세에서 미혼은 {sk[0][1]}명, 기혼은 {sk[1][1]}명을 "
            "더 낳을 계획이라고 답했습니다.",
            "미혼이 기혼보다 높습니다. 아직 낳지 않았으니 미혼에게는 "
            "'추가'가 곧 전체 계획입니다. 기혼은 이미 낳은 자녀를 뺀 "
            "수입니다. 두 값을 같은 뜻으로 읽으면 안 됩니다.",
            "여기서 기혼은 배우자 있음과 이혼, 사별을 모두 "
            "포함합니다.",
            "계획이나 의향을 물은 것이고 실제 출산이 아닙니다. "
            "2025년 조사에 새로 들어간 항목입니다.",
            f"출처 보도자료: {PRESS}",
        ],
        "updated": ymd,
    })

    print()
    for cid, v in out_ov.items():
        print(f"  {cid} {len(v['labels'])}점 | 계열 {len(v['series'])}")
    for x in out_new:
        print(f"  {x['slide']} {len(x['labels'])}점 "
              f"| 계열 {len(x['series'])} | {x['title']}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    ovp = os.path.join(DATA, "overrides.json")
    o = json.load(open(ovp, encoding="utf-8"))
    for cid, v in out_ov.items():
        o.setdefault(cid, {}).update(v)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))

    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8"))
    idx = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for x in out_new:
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
    print(f"-> overrides {len(out_ov)}장, manual {len(out_new)}장을 "
          "반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
