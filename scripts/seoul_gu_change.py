#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""이재명 정부 출범 이후 서울 구별 아파트값 등락.

  python3 scripts/seoul_gu_change.py            # 미리보기
  python3 scripts/seoul_gu_change.py --apply

원천을 따로 받지 않는다. 이미 KB 부동산 API 로 날마다 갱신되는 두 차트에서
읽는다. 구별은 c2261(서울 구별 아파트 평균 매매가격 추이), 서울 전체는
c0718(아파트 매매 평균 가격)이다. 둘 다 KB 자료라 기준이 같다.

기준 달은 2025년 5월이다. 이재명 대통령 취임이 2025년 6월 4일이어서 취임
직전 달을 출발점으로 둔다. 취임한 달을 출발점으로 잡으면 그달의 움직임이
빠진다.

KB 평균가격은 지수가 아니라 표본 아파트 값의 평균이다. 대단지 입주나 표본
교체로 구성이 바뀌면 실제 가격이 움직이지 않아도 평균이 움직인다. 그래서
'지수 상승률' 이 아니라 '평균가격 변동률' 이라고 적는다.
"""
import argparse, datetime, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

SLIDE = "manual-seoul-gu-change"
GU, SEOUL = "c2261", "c0718"
BASE = "2025-05"
ALL = "서울 평균"


def read(ov, full, cid):
    cur = {**full.get(cid, {}), **(ov.get(cid) or {})}
    lab = [str(x) for x in cur["labels"]]
    nm = [str(n).strip().rstrip(".") for n in cur["seriesNames"]]
    return lab, nm, cur["series"]


def upsert(item):
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    cur = next((i for i in doc["items"] if i.get("slide") == SLIDE), None)
    if cur and cur.get("id"):
        item["id"] = cur["id"]
    else:
        ids = json.load(open(os.path.join(DATA, "ids.json"), encoding="utf-8"))
        k = "S\x1f%s\x1f%s" % (SLIDE, item["title"])
        if ids.get(k):
            item["id"] = ids[k]
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
    full = {}
    for f in ("full.json", "manual.json"):
        for i in json.load(open(os.path.join(DATA, f), encoding="utf-8"))["items"]:
            if i.get("id"):
                full.setdefault(i["id"], {}).update(i)

    glab, gnm, gser = read(ov, full, GU)
    if BASE not in glab:
        raise SystemExit(f"{GU} 에 기준 달 {BASE} 이 없습니다.")
    b, e = glab.index(BASE), len(glab) - 1
    last = glab[e]

    rows = []
    for n, s in zip(gnm, gser):
        x, y = s[b], s[e]
        if x and y:
            rows.append((n, round((y / x - 1) * 100, 1), x, y))
    if len(rows) < 20:
        raise SystemExit(f"구가 {len(rows)}개뿐입니다 — 쓰지 않습니다.")

    slab, snm, sser = read(ov, full, SEOUL)
    i = snm.index("서울")
    sx = sser[i][slab.index(BASE)]
    sy = sser[i][slab.index(last)] if last in slab else None
    if sy is None:
        raise SystemExit(f"{SEOUL} 에 {last} 값이 없습니다 — 두 차트의 기준 달이 다릅니다.")
    allp = round((sy / sx - 1) * 100, 1)

    rows.sort(key=lambda r: -r[1])
    labels = [n for n, _, _, _ in rows] + [ALL]
    vals = [p for _, p, _, _ in rows] + [allp]

    print(f"KB 평균 매매가격 — {BASE} -> {last}")
    for n, p, x, y in rows:
        print(f"  {n:7s} {x:6.2f} -> {y:6.2f}  {p:+6.1f}%")
    print(f"  {ALL:7s} {sx:6.2f} -> {sy:6.2f}  {allp:+6.1f}%")
    up = [r for r in rows if r[1] > 0]
    print(f"  오른 구 {len(up)} / {len(rows)}, 가장 큼 {rows[0][0]} {rows[0][1]:+}%, "
          f"가장 작음 {rows[-1][0]} {rows[-1][1]:+}%")

    item = {
        "slide": SLIDE,
        "title": "이재명 정부 출범 이후 서울 구별 아파트값",
        "category": "부동산",
        "source": ("KB부동산 데이터허브 월간 아파트 매매평균가격. "
                   f"{BASE}(취임 직전 달) 대비 {last} 변동률. 지수가 아니라 "
                   "표본 아파트 평균가격의 변동률이다. 단위: %."),
        "sourceUrl": "https://data.kbland.kr/kbstats/wmh?tIdx=HT06&tsIdx=aptSaleAvgPrice",
        "vizType": "bar", "unit": "%",
        "labels": labels,
        "series": [vals],
        "seriesNames": ["평균가격 변동률"],
        "signColors": {"plus": "#2a5ca8", "minus": "#c0322f"},
        "labelColors": {ALL: "#6e6e6e"},
        "notes": [
            f"이재명 대통령 취임이 2025년 6월 4일이어서 직전 달인 {BASE} 을 "
            f"출발점으로 삼았습니다. 끝은 {last} 입니다.",
            "KB 가 내는 평균 매매가격입니다. 지수가 아닙니다. 표본 아파트 값의 "
            "평균이어서 대단지가 새로 입주하거나 표본이 바뀌면 실제 가격이 "
            "움직이지 않아도 평균이 움직입니다. 특히 대규모 입주가 있었던 구는 "
            "이 수치를 그대로 '값이 그만큼 올랐다'로 읽기 어렵습니다.",
            f"'{ALL}' 은 구가 아니라 서울 전체 평균이어서 회색으로 구분했습니다. "
            f"{allp:+}% 입니다.",
            "강남구와 서초구가 오히려 아래쪽에 있습니다. 이미 값이 높은 구는 "
            "같은 금액이 올라도 비율로는 작게 나옵니다. 절대 금액으로 보려면 "
            "서울 구별 아파트 평균 매매가격 차트를 같이 보십시오.",
            "오른 구는 파랑, 내린 구는 빨강입니다. 지금은 모두 올랐지만 "
            "구간에 따라 내리는 구가 생기면 색이 갈립니다.",
            "KB 자료는 표본 조사입니다. 거래가 적은 달에도 값이 나오고, "
            "실거래가격지수와는 움직임이 다릅니다.",
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
