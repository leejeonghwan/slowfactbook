#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""질병관리청 「한 눈에 보는 건강수명, 2023」 에서 뽑은 차트.

  python3 scripts/hale_kdca.py            # 미리보기
  python3 scripts/hale_kdca.py --apply

해마다 한 번 나오는 통계집이라 자동으로 받아올 API 가 없다. 값은 아래에
박아 두고, 쓸 때마다 문서에 따로 적혀 있던 격차 라벨과 대조해 옮겨 적다가
틀린 곳이 없는지 확인한다.

소득수준별 건강수명은 통계집의 표에서 읽었다. 통계집 차트에는 5분위와
1분위의 격차가 해마다 따로 적혀 있는데, 표에서 읽은 값으로 계산한 격차
열여섯 개와 그 라벨 열여섯 개가 같은 묶음인지 본다. 옮겨 적다 한 자리만
틀려도 여기서 걸린다.

시도별 건강위험요인은 통계집의 표를 그대로 옮겼다. 열일곱 개 시도가 모두
있다.

2023년 시도별 건강수명은 넣지 않았다. 통계집에 지도 위 라벨로만 있고 열일곱
개 가운데 여덟 개는 어느 시도 값인지 문서에서 확정되지 않는다. 순서대로
맞추면 경기도가 67.95세가 되는데 같은 문서에 성남 분당 72.84세와 과천
72.73세가 있어 앞뒤가 맞지 않는다. 시군구 값으로 역산해 확정한 뒤에 넣는다.
"""
import argparse, datetime, json, os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
SRC = "질병관리청 「한 눈에 보는 건강수명, 2023」(정책-04-2025-011-01)"
URL = "https://www.kdca.go.kr/"

YS = list(range(2008, 2024))
Q = {
    "5분위(상위)": [71.76, 72.01, 72.00, 71.80, 71.48, 72.39, 72.93, 73.44,
                 73.37, 73.58, 73.28, 73.41, 73.93, 73.36, 72.69, 71.07],
    "4분위": [70.39, 70.66, 70.59, 70.63, 70.33, 71.08, 71.47, 72.00,
            71.98, 72.21, 72.10, 72.12, 72.61, 72.14, 71.37, 70.25],
    "3분위": [69.61, 69.61, 69.81, 69.94, 69.56, 70.25, 70.73, 71.30,
            71.40, 71.59, 71.48, 71.90, 72.15, 71.85, 70.84, 69.43],
    "2분위": [69.52, 69.53, 69.43, 69.42, 69.25, 70.03, 70.37, 70.80,
            70.89, 71.10, 70.81, 70.95, 71.17, 70.90, 70.35, 69.19],
    "1분위(하위)": [63.82, 64.06, 64.53, 64.72, 64.76, 65.25, 65.58, 66.00,
                 65.78, 66.03, 65.24, 65.25, 65.58, 65.15, 64.34, 62.94],
}
QCOL = ["#2a5ca8", "#8aa6c8", "#9a9a9a", "#c9a08f", "#c0322f"]
# 통계집 차트에 적혀 있던 격차(5분위 - 1분위) 라벨. 순서는 모르고 묶음만 쓴다.
GAP_LABELS = [8.35, 8.35, 8.04, 8.16, 8.21, 8.13, 7.94, 7.95,
              7.47, 7.44, 7.59, 7.55, 7.35, 7.08, 6.72, 7.14]

# 건강수명과 기대수명 추이(통계집 9쪽 그림). 2008~2023년.
# 그림의 값 표기를 그대로 옮겼고, 같은 그림에 적힌 격차로 해마다 검산한다.
TREND_Y = list(range(2008, 2024))
EXPECT = [79.60, 80.04, 80.24, 80.62, 80.87, 81.36, 81.80, 82.06,
          82.36, 82.69, 82.74, 83.29, 83.48, 83.61, 82.74, 83.49]
HALE = [68.89, 69.05, 69.16, 69.20, 68.97, 69.69, 70.10, 70.59,
        70.56, 70.78, 70.43, 70.58, 70.93, 70.51, 69.89, 68.56]
TREND_GAP = [10.71, 10.99, 11.08, 11.42, 11.90, 11.67, 11.70, 11.47,
             11.80, 11.91, 12.31, 12.71, 12.55, 13.10, 12.85, 14.93]

NAT23 = {"건강수명": 68.56, "기대수명": 83.49}

# 2023년 시도별 건강위험요인. 열 순서는 아래 RISK_COLS 와 같다.
RISK_COLS = [("현재흡연율", "#c0322f", "흡연"),
             ("고위험음주율", "#c0322f", "음주"),
             ("신체활동실천율", "#2a5ca8", "신체활동"),
             ("아침식사실천율", "#2a5ca8", "아침식사"),
             ("비만율", "#c0322f", "비만"),
             ("건강생활실천율", "#2a5ca8", "건강생활")]
RISK = {
    "서울": [17.9, 11.2, 26.2, 45.0, 28.8, 48.4],
    "부산": [18.8, 12.6, 24.4, 48.9, 32.1, 39.3],
    "대구": [19.4, 10.8, 23.1, 46.0, 32.0, 38.1],
    "인천": [19.3, 12.7, 25.7, 50.1, 34.5, 42.1],
    "광주": [18.3, 10.9, 21.2, 47.4, 29.2, 35.2],
    "대전": [19.0, 12.0, 25.3, 42.2, 28.4, 36.1],
    "울산": [19.7, 13.6, 27.1, 46.9, 33.2, 37.7],
    "세종": [13.2, 9.3, 23.5, 47.5, 29.3, 38.1],
    "경기": [19.2, 12.4, 23.8, 45.2, 33.0, 38.5],
    "강원": [22.3, 16.9, 23.8, 46.9, 35.0, 28.1],
    "충북": [21.9, 16.2, 27.4, 47.0, 34.5, 35.0],
    "충남": [22.2, 14.0, 26.1, 47.0, 34.4, 32.0],
    "전북": [20.6, 13.7, 25.1, 44.3, 34.1, 33.5],
    "전남": [20.2, 13.9, 25.2, 48.4, 34.0, 30.9],
    "경북": [21.3, 13.2, 27.4, 47.0, 33.9, 29.9],
    "경남": [19.1, 13.9, 25.9, 51.3, 32.4, 31.3],
    "제주": [19.1, 14.0, 23.7, 44.4, 36.1, 29.2],
}
DEFN = {
    "현재흡연율": "평생 5갑(100개비) 이상 피웠고 지금도 피우는 사람의 비율입니다.",
    "고위험음주율": "한 번의 술자리에서 남자는 7잔, 여자는 5잔 이상을 주 2회 "
               "이상 마시는 사람의 비율입니다.",
    "신체활동실천율": "최근 1주일 동안 고강도 활동을 하루 20분 이상 주 3일 이상 "
                "하거나, 중강도 활동을 하루 30분 이상 주 5일 이상 한 19세 이상 "
                "인구의 비율입니다. 전국 통계의 유산소 신체활동 실천율과 기준이 "
                "달라 그대로 견주면 안 됩니다.",
    "아침식사실천율": "최근 1주일 동안 아침을 5일 이상 먹은 사람의 비율입니다.",
    "비만율": "스스로 보고한 키와 몸무게로 계산한 체질량지수가 25 이상인 사람의 "
           "비율입니다. 재서 얻은 값이 아니라 자가보고라 실제보다 낮게 나오는 "
           "경향이 있습니다.",
    "건강생활실천율": "금연과 절주와 걷기를 모두 실천하는 사람의 비율입니다. 셋을 "
                "다 만족해야 하므로 세 지표 가운데 가장 나쁜 쪽에 끌려갑니다.",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    # ── 검산 1. 격차 라벨 묶음
    calc = [round(Q["5분위(상위)"][i] - Q["1분위(하위)"][i], 2) for i in range(len(YS))]
    if Counter(calc) != Counter(GAP_LABELS):
        raise SystemExit(f"격차가 통계집 라벨과 어긋납니다.\n  계산 {sorted(calc)}\n"
                         f"  라벨 {sorted(GAP_LABELS)}")
    print(f"    검산 격차: 계산 {len(calc)}개와 통계집 라벨 묶음이 일치")

    # ── 검산 2. 분위 순서
    ks = list(Q)
    for i, y in enumerate(YS):
        v = [Q[k][i] for k in ks]
        if v != sorted(v, reverse=True):
            raise SystemExit(f"{y}년 분위 순서가 어긋납니다: {dict(zip(ks, v))}")
    print(f"    검산 분위 순서: {len(YS)}년 모두 5분위 >= 1분위")

    # ── 검산 3. 시도별 표
    if len(RISK) != 17:
        raise SystemExit(f"시도가 {len(RISK)}개뿐입니다.")
    for s, v in RISK.items():
        if len(v) != len(RISK_COLS):
            raise SystemExit(f"{s} 의 값이 {len(v)}개뿐입니다.")
        if not all(0 < x < 100 for x in v):
            raise SystemExit(f"{s} 에 비율 범위를 벗어난 값이 있습니다: {v}")
    print(f"    검산 시도별 표: 17개 시도 x {len(RISK_COLS)}개 지표 모두 정상")

    # ── 검산 4. 기대수명과 건강수명 추이
    if not (len(TREND_Y) == len(EXPECT) == len(HALE) == len(TREND_GAP) == 16):
        raise SystemExit("추이 자료의 길이가 안 맞습니다.")
    bad = [(y, round(e - h, 2), g) for y, e, h, g
           in zip(TREND_Y, EXPECT, HALE, TREND_GAP) if abs(round(e - h, 2) - g) > 0.011]
    if bad:
        raise SystemExit(f"기대수명에서 건강수명을 뺀 값이 그림의 격차와 다릅니다: {bad[:4]}")
    print(f"    검산 추이: {len(TREND_Y)}년 모두 격차가 기대수명 빼기 건강수명과 일치")
    if abs(EXPECT[-1] - NAT23["기대수명"]) > 0.011 or abs(HALE[-1] - NAT23["건강수명"]) > 0.011:
        raise SystemExit("2023년 값이 통계집 표지 수치와 다릅니다.")

    out = []
    # ── 0 기대수명과 건강수명 추이
    pk = TREND_Y[HALE.index(max(HALE))]
    trend = {
        "id": "c0237",
        "title": "기대수명과 건강수명.",
        "vizType": "column", "unit": "세",
        "labels": [str(y) for y in TREND_Y],
        "series": [EXPECT, HALE],
        "seriesNames": ["기대수명", "건강수명"],
        "seriesColors": ["#8a7f72", "#6a8f3c"],
        "source": (f"{SRC}. {TREND_Y[0]}~{TREND_Y[-1]}년. 단위: 세."),
        "sourceUrl": URL,
        "notes": [
            f"{TREND_Y[-1]}년 기대수명 {EXPECT[-1]}세, 건강수명 {HALE[-1]}세로 "
            f"{TREND_GAP[-1]}년 차이입니다. {TREND_Y[0]}년에는 {TREND_GAP[0]}년 "
            "차이였습니다. 아프지 않고 사는 기간보다 앓는 기간이 더 빨리 "
            "늘었습니다.",
            f"건강수명은 {pk}년 {max(HALE)}세가 가장 높았고 {TREND_Y[-1]}년 "
            f"{HALE[-1]}세입니다. {TREND_Y[0]}년의 {HALE[0]}세보다도 낮습니다. "
            "같은 기간 기대수명은 계속 늘었습니다.",
            "건강수명은 아프지 않고 산 기간입니다. 기대수명에서 질병으로 앓은 "
            "기간을 뺀 값이고, 설리반 방식으로 생명표와 건강손실년수를 합쳐 "
            "계산합니다.",
            "질병관리청 통계집 기준입니다. 국가데이터처 생명표의 '유병기간 제외 "
            "기대수명' 과는 다른 지표라 같은 해에도 값이 크게 다릅니다. 그쪽은 "
            "설문으로 물은 주관적 건강상태를 쓰고 이쪽은 질병 자료로 계산합니다. "
            "섞어 읽으면 안 됩니다.",
            "전에는 2년 간격 일곱 점이었고 2020년 값이 기대수명 84.55세, 건강수명 "
            "71.82세로 적혀 있었습니다. 통계집의 2020년은 83.48세와 70.93세입니다. "
            "해마다 모든 해를 넣고 통계집에 함께 적힌 격차로 열여섯 해를 "
            "대조했습니다.",
            "2023년에 건강수명이 1.33년 떨어졌습니다. 한 가지 이유로 설명할 수 "
            "없습니다. 코로나 유행기의 의료 이용 변화, 진단과 등록이 늘어난 몫, "
            "실제 건강 악화가 섞여 있습니다.",
        ],
        "updated": ymd,
    }

    # ── 1 소득수준별 건강수명 추이
    top, bot = Q["5분위(상위)"], Q["1분위(하위)"]
    pk = YS[top.index(max(top))]
    pb = YS[bot.index(max(bot))]
    out.append({
        "slide": "manual-hale-income",
        "category": "건강과 보건",
        "title": "소득수준별 건강수명",
        "vizType": "line", "unit": "세",
        "labels": [str(y) for y in YS],
        "series": [Q[k] for k in ks],
        "seriesNames": ks,
        "seriesColors": QCOL,
        "source": (f"{SRC}. {YS[0]}~{YS[-1]}년. 건강보험료 기준 소득 5분위. "
                   f"단위: 세."),
        "sourceUrl": URL,
        "notes": [
            f"상위 20%는 {pk}년 {max(top)}세까지 올랐다가 {YS[-1]}년 {top[-1]}세로 "
            f"내렸습니다. 하위 20%는 {pb}년 {max(bot)}세가 가장 높았고 {YS[-1]}년 "
            f"{bot[-1]}세입니다. {YS[0]}년 {bot[0]}세보다도 낮습니다.",
            f"두 계층의 격차는 {YS[calc.index(min(calc))]}년 {min(calc)}년까지 "
            f"좁혀졌다가 {YS[-1]}년 {calc[-1]}년으로 다시 벌어졌습니다. "
            f"{YS[0]}년의 {calc[0]}년보다 넓습니다.",
            "건강수명은 아프지 않고 산 기간입니다. 기대수명에서 질병으로 앓은 "
            "기간을 뺀 값이고, 설리반 방식으로 생명표와 건강손실년수를 합쳐 "
            f"계산합니다. {YS[-1]}년 전국 기대수명은 {NAT23['기대수명']}세, "
            f"건강수명은 {NAT23['건강수명']}세로 {round(NAT23['기대수명'] - NAT23['건강수명'], 2)}년 "
            "차이가 납니다.",
            "소득 분위는 건강보험료를 기준으로 나눕니다. 보험료는 직장과 지역 "
            "가입자의 산정 방식이 달라, 분위가 실제 소득 순서와 완전히 같지는 "
            "않습니다.",
            "질병관리청 통계집 기준입니다. 팩트북의 c0237 기대수명과 건강수명은 "
            "국가데이터처 수치여서 같은 해에도 값이 다릅니다. 두 계열을 섞어 "
            "읽으면 안 됩니다.",
            "최근 몇 해의 하락을 한 가지 이유로 설명할 수는 없습니다. 코로나 "
            "유행기의 의료 이용 변화, 진단과 등록이 늘어난 몫, 실제 건강 악화가 "
            "섞여 있습니다.",
        ],
        "updated": ymd,
    })

    # ── 2~7 시도별 건강위험요인
    for i, (nm, col, short) in enumerate(RISK_COLS):
        order = sorted(RISK, key=lambda s: -RISK[s][i])
        v = [RISK[s][i] for s in order]
        hi, lo = order[0], order[-1]
        good = col == "#2a5ca8"
        out.append({
            "slide": f"manual-hale-risk-{short}",
            "category": "건강과 보건",
            "title": f"시도별 {nm}",
            "vizType": "bar", "unit": "%",
            "labels": order, "series": [v],
            "seriesNames": [nm], "seriesColors": [col],
            "source": (f"{SRC}, 2023년 지역사회건강조사. 19세 이상. 단위: %."),
            "sourceUrl": URL,
            "notes": [
                f"가장 높은 곳은 {hi} {v[0]}%, 가장 낮은 곳은 {lo} {v[-1]}% 로 "
                f"{round(v[0] - v[-1], 1)}%포인트 차이입니다."
                + (f" 이 지표는 높은 쪽이 좋습니다." if good else ""),
                DEFN[nm],
                "지역사회건강조사는 조사원이 가구를 찾아가 묻는 자가보고 조사입니다. "
                "재서 얻은 값이 아니고, 시도마다 연령 구성이 달라 그 영향도 "
                "섞여 있습니다. 연령을 보정한 값이 아닙니다.",
                "시도 단위 값이라 그 안의 시군구 차이는 보이지 않습니다. 통계집에는 "
                "시군구별 값도 함께 실려 있습니다.",
            ],
            "updated": ymd,
        })

    print(f"  {trend['title']:22s} {len(trend['labels'])}점 "
          f"{trend['labels'][0]}~{trend['labels'][-1]} (c0237, overrides)")
    for it in out:
        print(f"  {it['title']:22s} {len(it['labels'])}점 "
              f"{it['labels'][0]}~{it['labels'][-1]} 계열 {len(it['series'])} "
              f"({it['vizType']})")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    ov.setdefault("c0237", {}).update(trend)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 에 c0237 을 반영했습니다.")

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
    print(f"-> data/manual.json 에 반영했습니다({len(doc['items'])}장).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
