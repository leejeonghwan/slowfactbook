#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국갤럽과 리얼미터의 대통령 직무 수행 긍정률을 한 장에 겹친다.

  python3 scripts/approval_compare.py            # 미리보기
  python3 scripts/approval_compare.py --apply

두 기관의 주간 조사를 그대로 겹칠 수가 없다. 한국갤럽은 명절 등으로 쉬는 주가
있어 2025년 6월 이후 주 수가 리얼미터보다 적고, 두 차트(c2040, c2073)에는
발표일이 아니라 월 라벨만 남아 있어 주를 짝지을 근거가 없다.

그래서 달마다 묶는다. 한국갤럽이 따로 내는 '월별 통합' 수치를 쓰지 않는 이유는
그것이 주간값의 평균이 아니라 한 달치 표본을 다시 가중한 값이어서다. 한쪽만
공식 통합값을 쓰면 가중 방식이 어긋나 비교가 흐려진다. 양쪽 모두 주간 발표값의
단순 평균으로 맞춘다.

원천은 이미 자동 갱신되는 두 차트의 overrides 다. gallup_weekly.py 와
realmeter_weekly.py 가 새 주를 붙이면 이 차트도 따라 움직인다.
"""
import argparse, datetime, json, os, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

SLIDE = "manual-approval-gallup-realmeter"
GALLUP, REALMETER = "c2040", "c2073"


def monthly(ov, cid):
    """{'YYYY-MM': (평균, 주 수)} — 긍정률(계열 0)만 본다."""
    o = ov.get(cid) or {}
    lab = [str(x) for x in (o.get("labels") or [])]
    ser = (o.get("series") or [[]])[0]
    if not lab or len(ser) != len(lab):
        raise SystemExit(f"{cid}: 라벨과 값의 길이가 맞지 않습니다.")
    bag = {}
    for L, v in zip(lab, ser):
        if v is None:
            continue
        bag.setdefault(L[:7], []).append(float(v))
    return {m: (round(statistics.fmean(v), 1), len(v)) for m, v in bag.items()}


def upsert(item):
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    cur = next((i for i in doc["items"] if i.get("slide") == SLIDE), None)
    # id 를 반드시 항목 안에 적어 둔다. 없으면 build.py 가 ids.json 에만
    # 배정하고, cNNNN 키로 쓴 overrides 가 조용히 먹지 않는다.
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
    ov = json.load(open(os.path.join(DATA, "overrides.json"), encoding="utf-8"))
    gal, rea = monthly(ov, GALLUP), monthly(ov, REALMETER)
    months = sorted(set(gal) | set(rea))
    if not months:
        raise SystemExit("묶을 달이 없습니다.")

    g = [gal[m][0] if m in gal else None for m in months]
    r = [rea[m][0] if m in rea else None for m in months]
    both = [m for m in months if m in gal and m in rea]
    gaps = [round(gal[m][0] - rea[m][0], 1) for m in both]
    last = both[-1]
    wide = max(both, key=lambda m: abs(gal[m][0] - rea[m][0]))

    print(f"  한국갤럽   {len(gal)}달 {min(gal)} ~ {max(gal)} "
          f"(주 {sum(n for _, n in gal.values())}개)")
    print(f"  리얼미터 {len(rea)}달 {min(rea)} ~ {max(rea)} "
          f"(주 {sum(n for _, n in rea.values())}개)")
    for m in months[-4:]:
        print(f"    {m}  한국갤럽 {gal.get(m, ('-', 0))[0]:>5}  "
              f"리얼미터 {rea.get(m, ('-', 0))[0]:>5}")
    print(f"  겹치는 {len(both)}달 평균 격차 {round(statistics.fmean(gaps), 1)}%p, "
          f"가장 벌어진 달 {wide} {round(gal[wide][0] - rea[wide][0], 1)}%p")

    item = {
        "slide": SLIDE,
        "title": "대통령 지지율, 한국갤럽과 리얼미터",
        "category": "정치",
        "source": ("한국갤럽 데일리 오피니언, 리얼미터 주간 집계. 두 기관의 주간 "
                   "발표값을 달마다 단순 평균한 값. 단위: %."),
        "sourceUrl": "https://www.gallup.co.kr/gallupdb/report.asp",
        "vizType": "line", "unit": "%",
        # 두 선이 30~60 사이에서만 움직여서 0 부터 그리면 격차가 눌린다.
        "yMin": 20,
        "labels": months,
        "series": [g, r],
        "seriesNames": ["한국갤럽", "리얼미터"],
        "seriesColors": ["#2f5e8e", "#f5a623"],
        "notes": [
            "두 기관의 주간 발표값을 달마다 단순 평균했습니다. 주 단위로 겹치지 "
            "않은 이유는 한국갤럽이 명절 등으로 쉬는 주가 있어 발표 주 수가 다르고, "
            "두 조사의 조사 기간도 주마다 어긋나기 때문입니다.",
            "한국갤럽이 따로 내는 '월별 통합' 수치는 쓰지 않았습니다. 그것은 주간값의 "
            "평균이 아니라 한 달치 표본을 다시 가중한 값입니다. 한쪽만 공식 "
            "통합값을 쓰면 가중 방식이 어긋나 비교가 흐려집니다.",
            "한 달에 들어간 조사 수가 기관마다 다릅니다. 한국갤럽은 보통 3~4주, "
            "리얼미터는 4~5주입니다. 조사 수가 적은 달은 평균이 흔들립니다.",
            "조사 방식이 다릅니다. 한국갤럽은 전화 면접원이 직접 묻고, 리얼미터는 "
            "자동응답(ARS) 비중이 큽니다. 질문 문항도 다릅니다. 한국갤럽은 '잘하고 있다'"
            "와 '잘못하고 있다'를 묻고 모름과 응답거절을 따로 둡니다. 리얼미터는 "
            "'매우 잘함'부터 '매우 잘못함'까지 네 단계로 물어 앞의 둘을 긍정으로 "
            "묶습니다. 그래서 한국갤럽은 무응답이 10% 안팎 남고 리얼미터는 거의 "
            "남지 않습니다.",
            "두 선의 높낮이 차이는 민심의 차이라기보다 조사 설계의 차이로 보는 쪽이 "
            "안전합니다. 다만 어느 요인이 얼마나 작용하는지는 이 차트로 알 수 "
            "없습니다. 방식과 문항, 표본 추출, 가중이 모두 다릅니다.",
            f"겹치는 {len(both)}달의 평균 격차는 "
            f"{round(statistics.fmean(gaps), 1)}%p입니다. 가장 벌어진 달은 "
            f"{wide}로 {abs(round(gal[wide][0] - rea[wide][0], 1))}%p 차이였습니다. "
            f"{last}에는 한국갤럽 {gal[last][0]}%, 리얼미터 {rea[last][0]}%입니다.",
            "세로축은 0 이 아니라 20에서 시작합니다. 0 부터 그리면 두 선이 "
            "겹쳐 보여 격차를 읽을 수 없습니다. 축을 끊은 만큼 등락이 실제보다 "
            "커 보이는 점은 감안해 주십시오.",
            "두 기관의 절대 수치보다 방향이 같은지를 보는 쪽이 낫습니다. 한쪽만 "
            "꺾이면 표본이나 그 주의 사건 탓일 수 있고, 둘이 같이 꺾이면 흐름이 "
            "바뀐 것으로 읽을 여지가 커집니다.",
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
