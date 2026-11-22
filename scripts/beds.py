#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""의료기관 병상 수(c1173) — 건강보험심사평가원 요양기관 종별 입원실 현황.

옛 c1173 은 행정안전부 표(KOSIS 110/DT_11001N_2013_A042)였는데 그 표가
2020년에 끝났다. 후속 표(110/DT_110001_A038)는 2023년부터라 2021년과
2022년이 비어 있다. 그래서 2012년부터 지금까지 끊기지 않는 심사평가원
표(354/DT_HIRA45_1)로 옮긴다.

두 출처는 총계가 거의 같지만 칸을 다르게 자른다.
  2020년 총 병상: 행안부 711,778 / 심평원 716,292 (0.6% 차이)
  종합병원: 행안부 154,517 ≈ 심평원 상급종합 45,536 + 종합 109,674
  행안부의 '특수병원'과 '부속병의원'은 심평원에 없다
  요양병원: 행안부 275,325 / 심평원 308,111 — 여기서 크게 갈린다
그래서 과거 값이 바뀐다. 섞어 이어 붙이지 않고 통째로 심평원 기준으로
다시 세운다.

함정 — 정신병원은 2021년 1분기에 새로 갈라져 나왔다.
  그 전에는 병원에 묶여 있었다. 2020년 4분기 정신병원 0, 2021년 1분기
  부터 6만 병상대다. 병원 계열이 그 시점에 뚝 떨어지는 것은 실제 감소가
  아니라 분류가 갈린 결과다. 검산으로 그 시점을 확인하고 비고에 적는다.

시점 표기는 YYYYQQ 다(201201 = 2012년 1분기). 축은 objL1 이 입원실
현황, objL2 가 요양기관 종별이다. 뒤집으면 err 21 이 난다.
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

ORG, TBL = "354", "DT_HIRA45_1"
PFX = "1635413103140058SC"
SRC = ("건강보험심사평가원 요양기관 종별 입원실 현황"
       "(KOSIS 354/DT_HIRA45_1)")
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=354&tblId=DT_HIRA45_1"

TOTAL = ("계", "0")
# 그릴 계열: (이름, 코드 꼬리) — '기타'로 묶을 것은 ETC 에 둔다
SHOW = [("상급종합병원", "1"), ("종합병원", "2"), ("병원", "3"),
        ("정신병원", "G"), ("요양병원", "F"), ("의원", "4"),
        ("한방병원", "C"), ("한의원", "D")]
ETC = [("치과병원", "5"), ("치과의원", "6"), ("조산원", "7"),
       ("보건의료원", "8"), ("보건소", "9"), ("보건지소", "A"),
       ("보건진료소", "B")]
COLS = ["#2a5ca8", "#5b8bc9", "#c0322f", "#e07a74", "#e8820c",
        "#6a8f3c", "#8a6fb0", "#c9a08f", "#b8b8b8"]

SPLIT = "202101"            # 정신병원이 병원에서 갈라져 나온 분기
GATE_2020_AHN = 711778      # 옛 c1173(행안부)의 2020년 총 병상


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


def ser(key, sfx, tries=3):
    p = {"method": "getList", "apiKey": key, "itmId": "01",
         "objL1": "1", "objL2": PFX + sfx, "format": "json", "jsonVD": "Y",
         "prdSe": "Q", "startPrdDe": "20111", "endPrdDe": "20994",
         "orgId": ORG, "tblId": TBL}
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + urllib.parse.urlencode(p))
    last = None
    for i in range(tries):
        try:
            d = json.load(urllib.request.urlopen(u, timeout=90))
            if isinstance(d, dict):
                raise RuntimeError(f"KOSIS err {d.get('err')}")
            return {r["PRD_DE"]: int(float(r["DT"])) for r in d
                    if r.get("DT") not in (None, "", "-")}
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"{sfx} 를 받지 못했다: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("KOSIS_API_KEY")
    if not key:
        print("KOSIS_API_KEY 가 없다")
        return 2
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    d = {}
    for nm, sfx in [TOTAL] + SHOW + ETC:
        d[nm] = ser(key, sfx)
        time.sleep(0.4)
    qs = sorted(d["계"])
    print(f"    받음: {len(qs)}분기 {qs[0]}~{qs[-1]}")

    # 검산 1. 종별 합이 '계'와 같은가
    bad = []
    for q in qs:
        s = sum(d[nm].get(q, 0) for nm, _s in SHOW + ETC)
        if abs(s - d["계"][q]) > 2:
            bad.append((q, s, d["계"][q]))
    if bad:
        print(f"  검산 실패: 종별 합이 계와 다르다 {bad[:3]}")
        return 1
    print(f"    검산 합계: {len(qs)}분기 모두 종별 합 = 계")

    # 검산 2. 정신병원이 분할 시점 전에는 없고 뒤에는 있는가
    before = [q for q in qs if q < SPLIT and d["정신병원"].get(q, 0) > 0]
    after = [q for q in qs if q >= SPLIT and d["정신병원"].get(q, 0) > 0]
    if before or len(after) < 4:
        print(f"  검산 실패: 정신병원 분할 시점이 {SPLIT} 가 아닌 듯하다 "
              f"(앞 {len(before)}, 뒤 {len(after)})")
        return 1
    print(f"    검산 분할: 정신병원이 {SPLIT} 부터만 잡힘 "
          "(그 전에는 병원에 묶여 있었다)")

    # 검산 3. 2020년 총계가 옛 행안부 값과 2% 안인가
    t20 = d["계"].get("202004")
    if not t20 or abs(t20 / GATE_2020_AHN - 1) > 0.02:
        print(f"  검산 실패: 2020년 총계 {t20} 가 행안부 "
              f"{GATE_2020_AHN:,} 와 2% 넘게 다르다")
        return 1
    print(f"    검산 교차: 2020년 총계 심평원 {t20:,} 대 행안부 "
          f"{GATE_2020_AHN:,} ({(t20/GATE_2020_AHN-1)*100:+.1f}%)")

    # 검산 4. 계가 한 분기에 20% 넘게 튀지 않는가
    jump = [(qs[i], round(d["계"][qs[i]] / d["계"][qs[i-1]] - 1, 3))
            for i in range(1, len(qs))
            if abs(d["계"][qs[i]] / d["계"][qs[i-1]] - 1) > 0.2]
    if jump:
        print(f"  검산 실패: 계가 한 분기에 20% 넘게 튄다 {jump[:3]}")
        return 1
    print(f"    검산 연속: {len(qs)}분기 모두 전분기 대비 20% 안")

    # 연도별로 4분기를 쓰고, 끝나지 않은 해는 가장 최근 분기를 쓴다
    picks, labels = [], []
    for y in sorted({q[:4] for q in qs}):
        inyr = [q for q in qs if q.startswith(y)]
        q4 = f"{y}04"
        if q4 in inyr:
            picks.append(q4)
            labels.append(y)
        else:
            picks.append(inyr[-1])
            labels.append(f"{y}({int(inyr[-1][4:])}분기)")
    names = [nm for nm, _s in SHOW] + ["기타"]
    # 정신병원처럼 어느 시점부터만 잡히는 계열은 행 자체가 없다.
    # 쌓는 막대라 0 으로 채워야 합이 맞는다.
    series = [[d[nm].get(q, 0) for q in picks] for nm, _s in SHOW]
    series.append([sum(d[nm].get(q, 0) for nm, _s in ETC) for q in picks])

    last, lastq = labels[-1], picks[-1]
    tot = d["계"][lastq]
    big = sorted(((names[i], series[i][-1]) for i in range(len(names))),
                 key=lambda x: -x[1])[:3]
    it = {
        "id": "c1173", "category": "건강과 보건",
        "title": "한국의 의료기관 병상 수.",
        "vizType": "stacked_bar", "unit": "개",
        "labels": labels, "series": series, "seriesNames": names,
        "seriesColors": COLS,
        "source": (f"{SRC}. 각 해 4분기 기준, {labels[0]}~{last}. "
                   "단위: 개."),
        "sourceUrl": URL,
        "notes": [
            f"{last} 기준 전체 {tot:,}개입니다. "
            + ", ".join(f"{n} {v:,}개" for n, v in big) + " 순입니다.",
            "정신병원은 2021년 1분기부터 따로 집계합니다. 그 전에는 "
            "병원에 묶여 있었습니다. 2020년과 2021년 사이에 병원이 뚝 "
            "떨어지고 정신병원이 솟는 것은 실제 변화가 아니라 분류가 "
            "갈린 결과입니다. 그 자리를 건너뛰고 읽어야 합니다.",
            "전에는 행정안전부 표(2009~2020년)로 그려져 있었습니다. 그 "
            "표가 2020년에 끝나고 후속 표는 2023년부터라 2021년과 "
            "2022년이 비었습니다. 끊기지 않는 심사평가원 표로 옮겼고 "
            "2009년부터 2011년까지는 빠졌습니다.",
            "두 출처는 총계가 거의 같지만 칸을 다르게 자릅니다. 2020년 "
            f"총 병상이 심사평가원 {t20:,}개, 행정안전부 "
            f"{GATE_2020_AHN:,}개로 "
            f"{abs(t20-GATE_2020_AHN):,}개 차이입니다. 종합병원은 "
            "심사평가원에서 상급종합병원과 종합병원으로 갈라지고, "
            "행정안전부의 '특수병원'과 '부속병의원'은 심사평가원에 "
            "없습니다. 옛 숫자와 지금 숫자를 섞어 쓰면 안 됩니다.",
            "각 해 4분기 기준입니다. 아직 끝나지 않은 해는 가장 최근 "
            "분기를 쓰고 괄호에 적었습니다.",
            "병상 수이고 병실 수가 아닙니다. 요양기관이 심사평가원에 "
            "신고한 입원실 기준입니다.",
        ],
        "updated": ymd,
    }

    print(f"  c1173 {len(labels)}점 {labels[0]}~{last} "
          f"계열 {len(names)} | 전체 {tot:,}개")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    ovp = os.path.join(DATA, "overrides.json")
    o = json.load(open(ovp, encoding="utf-8"))
    o.setdefault("c1173", {}).update(it)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))
    print("-> data/overrides.json 에 c1173 을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
