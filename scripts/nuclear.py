#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""핵탄두 보유량(SIPRI 연감).

SIPRI Yearbook, Table 8A.1 "World nuclear forces". 해마다 6월에 나오고
기준 시점은 그해 1월이다. API 가 없어 표를 손으로 옮긴다. 대신 표가
스스로 품고 있는 항등식으로 검산한다.

  배치 + 저장 = 군사 비축분
  군사 비축분 + 퇴역 = 총 보유량
  각 열의 나라별 합 = 연감이 발표한 합계

새 연감이 나오면 YEARS 에 한 해를 더하고 돌리면 된다. 항등식이 깨지면
쓰지 않고 멈춘다.

함정 — 프랑스 290 -> 370.
2026년에 프랑스 총 보유량이 290에서 370으로 뛴 것은 핵무기가 늘어서가
아니다. 해체를 기다리는 퇴역 TN 75 탄두 80발이 그해부터 총 보유량에
잡힌 결과다. 군사 비축분은 290으로 그대로다. 두 해를 나란히 놓고
'프랑스가 28% 늘렸다'고 읽으면 틀린다.
"""
import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

SRC = "SIPRI 연감 표 8A.1 세계 핵전력"
URL = ("https://www.sipri.org/sites/default/files/"
       "YB26%2008%20World%20Nuclear%20Forces.pdf")

NAMES = ["미국", "러시아", "영국", "프랑스", "중국",
         "인도", "파키스탄", "북한", "이스라엘"]

# 나라: (배치, 저장, 군사 비축분, 퇴역, 총 보유량)
YEARS = {
    "2025": {
        "미국":     (1770, 1930, 3700, 1477, 5177),
        "러시아":   (1718, 2591, 4309, 1150, 5459),
        "영국":     (120, 105, 225, 0, 225),
        "프랑스":   (280, 10, 290, 0, 290),
        "중국":     (24, 576, 600, 0, 600),
        "인도":     (0, 180, 180, 0, 180),
        "파키스탄": (0, 170, 170, 0, 170),
        "북한":     (0, 50, 50, 0, 50),
        "이스라엘": (0, 90, 90, 0, 90),
    },
    "2026": {
        "미국":     (1770, 1930, 3700, 1342, 5042),
        "러시아":   (1796, 2604, 4400, 1020, 5420),
        "영국":     (120, 105, 225, 0, 225),
        "프랑스":   (280, 10, 290, 80, 370),
        "중국":     (34, 586, 620, 0, 620),
        "인도":     (12, 178, 190, 0, 190),
        "파키스탄": (0, 170, 170, 0, 170),
        "북한":     (0, 60, 60, 0, 60),
        "이스라엘": (0, 90, 90, 0, 90),
    },
}
# 연감이 발표한 합계. 보도자료 본문에서 따로 확인한 값이다.
TOTALS = {
    "2025": (3912, 5702, 9614, 2627, 12241),
    "2026": (4012, 5733, 9745, 2442, 12187),
}
COLS = ["배치", "저장", "군사 비축분", "퇴역", "총 보유량"]


def check():
    for y, tbl in YEARS.items():
        for nm in NAMES:
            dep, sto, stk, ret, tot = tbl[nm]
            if dep + sto != stk:
                return f"{y} {nm}: 배치 {dep} + 저장 {sto} != 비축 {stk}"
            if stk + ret != tot:
                return f"{y} {nm}: 비축 {stk} + 퇴역 {ret} != 총 {tot}"
        for i, col in enumerate(COLS):
            s = sum(tbl[nm][i] for nm in NAMES)
            if s != TOTALS[y][i]:
                return f"{y} {col}: 합 {s} != 발표 합계 {TOTALS[y][i]}"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    bad = check()
    if bad:
        print(f"  검산 실패: {bad}")
        return 1
    ys = sorted(YEARS)
    y0, y1 = ys[0], ys[-1]
    print(f"    검산 항등식: {len(ys)}개 해 x {len(NAMES)}개 나라 모두 "
          "배치+저장=비축, 비축+퇴역=총계")
    print(f"    검산 합계: {len(ys)}개 해 x {len(COLS)}개 열 모두 "
          "발표 합계와 일치")

    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    order = sorted(NAMES, key=lambda n: -YEARS[y1][n][4])
    t0, t1 = TOTALS[y0][4], TOTALS[y1][4]

    main_it = {
        "id": "c1267",
        "category": "국방과 안보",
        "title": "핵탄두 보유량.",
        "vizType": "bar", "unit": "개",
        "labels": order,
        "series": [[YEARS[y][n][4] for n in order] for y in (y0, y1)],
        "seriesNames": [f"{y0}년", f"{y1}년"],
        "seriesColors": ["#b8b8b8", "#c0322f"],
        "source": (f"{SRC}. {y0}년과 {y1}년 1월 기준 총 보유량. "
                   "단위: 개."),
        "sourceUrl": URL,
        "notes": [
            f"{y1}년 1월 기준 전 세계 {t1:,}개입니다. {y0}년 {t0:,}개에서 "
            f"{t0-t1:,}개 줄었습니다. 러시아와 미국이 "
            f"{YEARS[y1]['러시아'][4]+YEARS[y1]['미국'][4]:,}개로 "
            f"{round((YEARS[y1]['러시아'][4]+YEARS[y1]['미국'][4])/t1*100)}%를 "
            "차지합니다.",
            "프랑스가 290개에서 370개로 뛴 것은 핵무기를 늘려서가 "
            "아닙니다. 해체를 기다리는 퇴역 탄두 80개가 그해부터 총 "
            "보유량에 잡혔습니다. 군사 비축분은 290개로 그대로입니다. "
            "두 해를 견줄 때 프랑스만 기준이 다릅니다.",
            f"중국은 {YEARS[y0]['중국'][4]}개에서 {YEARS[y1]['중국'][4]}개로 "
            "늘었습니다. SIPRI는 중국이 어느 나라보다 빠르게 늘리고 "
            "있다고 봅니다. 북한은 "
            f"{YEARS[y0]['북한'][4]}개에서 {YEARS[y1]['북한'][4]}개입니다.",
            "총 보유량은 군사 비축분에 아직 해체하지 않은 퇴역 탄두를 "
            "더한 값입니다. 당장 쓸 수 있는 수가 아닙니다. 실제로 "
            f"미사일과 항공기에 실려 있는 것은 {TOTALS[y1][0]:,}개입니다.",
            "모두 추정치입니다. 북한은 조립된 탄두를 약 60개로 보고, "
            "핵분열성 물질로는 최소 90개를 만들 수 있다고 봅니다. "
            "이스라엘은 핵 보유를 공식 인정하지 않습니다. 프랑스는 "
            "2026년 3월에 규모를 더 이상 공개하지 않겠다고 밝혔습니다.",
        ],
        "updated": ymd,
    }

    parts = ["배치", "저장", "퇴역"]
    pidx = [0, 1, 3]
    comp = {
        "slide": "manual-nuclear-parts",
        "category": "국방과 안보",
        "title": "핵탄두 보유량의 구성",
        "vizType": "stacked_bar_h", "unit": "개",
        "labels": order,
        "series": [[YEARS[y1][n][i] for n in order] for i in pidx],
        "seriesNames": ["배치", "저장", "퇴역(해체 대기)"],
        "seriesColors": ["#c0322f", "#e8a33d", "#b8b8b8"],
        "source": (f"{SRC}. {y1}년 1월 기준. 단위: 개."),
        "sourceUrl": URL,
        "notes": [
            f"막대 전체가 총 보유량입니다. {y1}년 전 세계 {t1:,}개 가운데 "
            f"실제로 미사일과 항공기에 실려 있는 것은 {TOTALS[y1][0]:,}개, "
            f"중앙 저장고에 있는 것이 {TOTALS[y1][1]:,}개, 해체를 기다리는 "
            f"퇴역 탄두가 {TOTALS[y1][3]:,}개입니다.",
            "퇴역 탄두를 가진 나라는 미국, 러시아, 프랑스 셋뿐입니다. "
            "총 보유량만 보면 이 세 나라가 실제보다 커 보입니다.",
            "중국은 620개 가운데 배치된 것이 34개입니다. SIPRI는 최대 "
            "34기 미사일에 탄두가 실려 있을 수 있다는 추정이고 "
            "불확실성이 크다고 밝힙니다.",
            "배치와 저장을 더한 것이 군사 비축분입니다. 영국, 중국, "
            "인도, 파키스탄, 북한, 이스라엘은 퇴역 탄두가 없어 군사 "
            "비축분과 총 보유량이 같습니다.",
        ],
        "updated": ymd,
    }

    print(f"  {main_it['title']:18s} {len(order)}칸 {y0}년과 {y1}년 "
          f"(c1267, overrides)")
    print(f"  {comp['title']:18s} {len(order)}칸 {y1}년 계열 3 "
          "(manual)")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    ov.setdefault("c1267", {}).update(main_it)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))
    print("-> data/overrides.json 에 c1267 을 반영했습니다.")

    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    idx = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    old = idx.get(comp["slide"])
    if old:
        keep = {k: old[k] for k in ("id",) if k in old}
        old.clear()
        old.update(comp)
        old.update(keep)
    else:
        doc["items"].append(comp)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(p, encoding="utf-8"))
    print("-> data/manual.json 에 1장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
