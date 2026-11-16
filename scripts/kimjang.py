#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""김치 조달 방식. 직접 담그느냐 사 먹느냐.

  python3 scripts/kimjang.py            # 미리보기
  python3 scripts/kimjang.py --apply

한국농촌경제연구원 농업관측센터가 해마다 11월에 내는 「소비자 김장 의향 및 주요
채소류 공급 전망」 에서 옮겼다. 2026년판은 농정포커스 제240호(2026년 11월 6일)다.
조사는 엠브레인리서치 소비자패널 1,000가구 온라인 조사다. API 가 없어 값을
박아 둔다.

두 가지를 조심해야 한다.

첫째, 여기서 '직접 담금' 은 지인에게 얻거나 사는 몫까지 포함한다. 보고서 표기가
'직접 담금 및 지인 조달' 이다. 상품 김치 구매와 둘로만 나누므로 해마다 합이
100이다.

둘째, 2025년에 조사 표본이 바뀌면서 과거 수치가 다시 집계됐다. 보고서 각주가
"2025년에 조사 표본이 변경됨에 따라 과거 직접 담금과 상품 김치 비중은 실제
발표치와 차이가 있음" 이라고 밝히고 있다. 그래서 2019년 이전 발표치를 앞에 이어
붙일 수 없다. 2025년판 보고서만 해도 2025년을 직접 담금 62.3%, 상품 김치 32.5%
(지인 조달을 따로 두어 합이 100이 아님)로 적었는데, 2026년판의 재집계 시계열은
같은 해를 64.1%와 35.9%로 적는다. 기준이 다른 숫자다.

검산은 보고서 본문에 적힌 변화폭으로 한다. 두 계열의 합이 해마다 100인지,
2020년과 2026년 사이 변화가 본문의 13.6%p 와 맞는지, 연령대별 2025년과 2026년
차이가 본문의 감소폭(전체 5.5, 30대 이하 6.3, 40대 4.9, 50대 5.6, 60대 이상
5.4%p)과 맞는지, 그리고 연령대별 직접 김장과 지인 조달을 더한 값이 직접 담금
비중과 맞는지 본다.
"""
import argparse, datetime, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
SRC = ("한국농촌경제연구원 농업관측센터 「2026년 소비자 김장 의향 및 주요 채소류 "
       "공급 전망」(농정포커스 제240호, 2026년 11월 6일)")
URL = "https://repository.krei.re.kr/bitstream/2018.oak/33456/1/PRN240.pdf"

YS = list(range(2020, 2027))
SELF = [72.2, 70.2, 70.5, 66.9, 66.9, 64.1, 58.6]      # 직접 담금(지인 조달 포함)
BUY = [27.8, 29.8, 29.5, 33.1, 33.1, 35.9, 41.4]       # 상품 김치 구매

# 2026년 연령대별. 직접 김장, 지인 조달, 상품 김치 구매.
AGE = [("30대 이하", 17.9, 40.8, 41.3, 65.0, 58.7, 6.3),
       ("40대", 22.9, 42.7, 34.3, 70.6, 65.7, 4.9),
       ("50대", 29.4, 25.2, 45.4, 60.2, 54.6, 5.6),
       ("60대 이상", 37.1, 18.9, 43.9, 61.5, 56.1, 5.4)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    # 검산 1. 해마다 합이 100
    bad = [(y, s, b) for y, s, b in zip(YS, SELF, BUY) if abs(s + b - 100) > 0.11]
    if bad:
        raise SystemExit(f"두 계열의 합이 100이 아닌 해: {bad}")
    print(f"    검산 합계: {len(YS)}년 모두 100")

    # 검산 2. 본문에 적힌 2020년과 2026년 사이 변화폭
    for nm, v, want in (("직접 담금", SELF, -13.6), ("상품 김치", BUY, 13.6)):
        got = round(v[-1] - v[0], 1)
        if abs(got - want) > 0.11:
            raise SystemExit(f"{nm} 변화폭 {got}%p 가 본문의 {want}%p 와 다릅니다.")
    print("    검산 변화폭: 2020년과 2026년 사이 13.6%p 로 본문과 일치")

    # 검산 3. 연령대별
    tot25, tot26 = SELF[-2], SELF[-1]
    if abs(round(tot26 - tot25, 1) + 5.5) > 0.11:
        raise SystemExit(f"전체 감소폭 {round(tot26 - tot25, 1)}%p 가 본문의 5.5%p 와 다릅니다.")
    for nm, own, kin, buy, p25, p26, drop in AGE:
        if abs(round(p25 - p26, 1) - drop) > 0.11:
            raise SystemExit(f"{nm} 감소폭 {round(p25 - p26, 1)}%p 가 본문의 {drop}%p 와 다릅니다.")
        if abs(own + kin - p26) > 0.21:
            raise SystemExit(f"{nm} 직접 김장({own}) + 지인 조달({kin}) 이 "
                             f"직접 담금 비중({p26}) 과 맞지 않습니다.")
        if abs(p26 + buy - 100) > 0.21:
            raise SystemExit(f"{nm} 직접 담금({p26}) + 상품 김치({buy}) 가 100이 아닙니다.")
    print(f"    검산 연령대별: {len(AGE)}개 연령층 모두 감소폭과 내역 합이 본문과 일치")

    out = [{
        "slide": "manual-kimjang-trend",
        "category": "식량",
        "title": "김치를 담그는 집과 사 먹는 집",
        "vizType": "line", "unit": "%",
        "labels": [str(y) for y in YS],
        "series": [SELF, BUY],
        "seriesNames": ["직접 담금(지인 조달 포함)", "상품 김치 구매"],
        "seriesColors": ["#c0322f", "#2a5ca8"],
        "source": f"{SRC}. {YS[0]}~{YS[-1]}년. 단위: %.",
        "sourceUrl": URL,
        "notes": [
            f"직접 담그는 집이 {YS[0]}년 {SELF[0]}%에서 {YS[-1]}년 {SELF[-1]}%로 "
            f"{abs(round(SELF[-1] - SELF[0], 1))}%포인트 줄었습니다. 사 먹는 집은 "
            f"{BUY[0]}%에서 {BUY[-1]}%로 같은 폭만큼 늘었습니다. 한 해 사이 "
            f"{YS[-2]}년에서 {YS[-1]}년으로만 {abs(round(SELF[-1] - SELF[-2], 1))}%포인트 "
            f"움직였습니다.",
            "'직접 담금' 에는 지인에게 얻거나 사는 몫이 들어 있습니다. 보고서 표기가 "
            "'직접 담금 및 지인 조달' 입니다. 본인이 직접 담그겠다는 비율만 보면 "
            "2026년 기준 30대 이하 17.9%, 40대 22.9%, 50대 29.4%, 60대 이상 "
            "37.1%로 훨씬 낮습니다.",
            "2020년 이전은 이어 붙일 수 없습니다. 2025년에 조사 표본이 바뀌면서 "
            "과거 수치가 다시 집계됐고, 보고서가 각주로 예전 발표치와 다르다고 "
            "밝히고 있습니다. 2025년판 보고서만 해도 2025년을 직접 담금 62.3%, "
            "상품 김치 32.5%로 적었습니다. 지인 조달을 따로 두어 합이 100이 아닌 "
            "기준이었습니다.",
            "조사는 해마다 10월 초에 전국 20대 이상 1,000가구를 온라인으로 묻습니다. "
            "실제로 담근 양이 아니라 담그겠다는 의향입니다. 온라인 패널 조사라 "
            "표본이 전체 가구를 그대로 대표하지는 않습니다.",
        ],
        "updated": ymd,
    }, {
        "slide": "manual-kimjang-age",
        "category": "식량",
        "title": "연령대별 김치 조달 방식(2026년)",
        "vizType": "stacked_bar", "unit": "%",
        "labels": [nm for nm, *_ in AGE],
        "series": [[own for _, own, _, _, _, _, _ in AGE],
                   [kin for _, _, kin, _, _, _, _ in AGE],
                   [buy for _, _, _, buy, _, _, _ in AGE]],
        "seriesNames": ["직접 김장", "지인에게 조달", "상품 김치 구매"],
        "seriesColors": ["#c0322f", "#e8a23c", "#2a5ca8"],
        "source": f"{SRC}. 2026년. 단위: %.",
        "sourceUrl": URL,
        "notes": [
            "직접 김장을 하겠다는 비율은 나이가 많을수록 높습니다. 30대 이하 17.9%, "
            "40대 22.9%, 50대 29.4%, 60대 이상 37.1%입니다.",
            "앞 차트의 '직접 담금' 은 이 그림의 직접 김장과 지인 조달을 더한 값입니다. "
            "그래서 그 숫자만 보면 40대(65.7%)가 50대(54.6%)보다 높게 나옵니다. "
            "40대가 더 많이 담근다는 뜻이 아니라 부모에게 받아 먹는 몫이 크다는 "
            "뜻입니다. 지인 조달 비율이 30대 이하 40.8%, 40대 42.7%인 반면 50대는 "
            "25.2%, 60대 이상은 18.9%입니다.",
            "상품 김치를 사는 비율은 50대가 45.4%로 가장 높습니다. 직접 담그지도 "
            "않고 받을 데도 줄어드는 구간입니다.",
            "2025년과 견주면 모든 연령층에서 직접 담금이 줄었습니다. 30대 이하가 "
            "6.3%포인트로 가장 크고 50대 5.6%포인트, 60대 이상 5.4%포인트, 40대 "
            "4.9%포인트 순입니다.",
            "실제로 담근 양이 아니라 담그겠다는 의향입니다.",
        ],
        "updated": ymd,
    }]

    for it in out:
        print(f"\n  {it['title']} ({it['vizType']})")
        for nm, s in zip(it["seriesNames"], it["series"]):
            print(f"    {nm:22s} {s}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    by = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for it in out:
        o = by.get(it["slide"])
        if o:
            keep = {k: o[k] for k in ("id",) if k in o}
            o.clear(); o.update(it); o.update(keep)
        else:
            doc["items"].append(it)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"-> data/manual.json 에 반영했습니다({len(doc['items'])}장).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
