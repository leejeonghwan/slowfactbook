#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""이재명 정부 출범 이후 서울 구별 아파트값 등락(실거래가격지수).

  KOSIS_API_KEY=... python3 scripts/seoul_gu_change.py            # 미리보기
  KOSIS_API_KEY=... python3 scripts/seoul_gu_change.py --apply

한국부동산원 아파트 매매 실거래가격지수를 쓴다. 구별은 시군구 분기별 표
(DT_KAB_11672_S5), 서울 전체는 시도 월별 표(DT_KAB_11672_S1)에서 같은 분기를
평균해 맞춘다. 둘 다 같은 통계다.

처음에는 KB 월간 평균 매매가격으로 그렸는데 바꿨다. 평균가격은 지수가 아니라
거래되거나 표본에 든 아파트 값의 평균이라, 표본이 바뀌면 가격이 움직이지
않아도 평균이 뛴다. 강동구가 2025년 10월에 한 달 +5.75%, 2026년 9월에 +9.89%
튀었는데(같은 달 서울 평균은 +1.75%, +1.08%) 25개 구에서 그런 달이 있는 곳은
강동구뿐이었다. 그 두 달 때문에 강동구 상승률이 +41.8% 로 1위가 됐다.
같은 구간을 실거래가격지수로 보면 KB 와 6.5%p 벌어진다.

기준은 2025년 1분기다. 이재명 대통령 취임이 2025년 6월 4일이어서 취임 직전에
끝난 분기를 출발점으로 둔다. 2분기는 취임 전후가 섞여 있다.

구 이름은 서울 밖에도 같은 것이 있다(중구, 강서구 등). 그래서 이름이 아니라
행정구역 코드 10001~10025 로 고른다.
"""
import argparse, collections, datetime, json, os, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

SLIDE = "manual-seoul-gu-change"
GU_TBL, SEOUL_TBL = "DT_KAB_11672_S5", "DT_KAB_11672_S1"
BASE = "202501"          # 2025년 1분기
ALL = "서울 평균"
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=408&tblId=DT_KAB_11672_S5"


def pull(key, tbl, prd, s, e):
    q = {"method": "getList", "apiKey": key, "format": "json", "jsonVD": "Y",
         "orgId": "408", "tblId": tbl, "itmId": "T1+", "objL1": "ALL",
         "prdSe": prd, "startPrdDe": s, "endPrdDe": e}
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + "&".join(f"{a}={urllib.parse.quote(str(b), safe='+')}" for a, b in q.items()))
    d = json.loads(urllib.request.urlopen(u, timeout=150).read().decode("utf-8"))
    if isinstance(d, dict):
        raise SystemExit(f"KOSIS {tbl}: " + str(d)[:120])
    out = collections.defaultdict(dict)
    for r in d:
        if str(r.get("ITM_ID")) != "T1":
            continue
        out[(str(r["C1"]), str(r["C1_NM"]).strip())][str(r["PRD_DE"])] = float(r["DT"])
    return out


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


def qname(p):
    return f"{p[:4]}년 {int(p[4:])}분기"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 가 필요합니다(.env).")
    yr = datetime.datetime.now(KST).year + 1

    gu = {n: m for (c, n), m in pull(key, GU_TBL, "Q", "20241", f"{yr}4").items()
          if c.startswith("10") and len(c) == 5}
    if len(gu) != 25:
        raise SystemExit(f"서울 구가 {len(gu)}개로 잡혔습니다 — 쓰지 않습니다.")
    per = sorted(set.intersection(*[set(m) for m in gu.values()]))
    if BASE not in per:
        raise SystemExit(f"기준 분기 {BASE} 이 없습니다. 있는 분기: {per}")
    last = per[-1]

    rows = sorted(((n, round((m[last] / m[BASE] - 1) * 100, 1))
                   for n, m in gu.items()), key=lambda r: -r[1])

    # 서울 전체는 시도 월별 표에서 같은 분기를 평균해 맞춘다.
    sm = pull(key, SEOUL_TBL, "M", "202401", f"{yr}12")
    seoul = next(m for (c, n), m in sm.items() if n == "서울")

    def qavg(p):
        y, q = int(p[:4]), int(p[4:])
        v = [seoul[f"{y}{mm:02d}"] for mm in range(q * 3 - 2, q * 3 + 1)
             if f"{y}{mm:02d}" in seoul]
        return sum(v) / len(v) if len(v) == 3 else None

    b, e = qavg(BASE), qavg(last)
    if not (b and e):
        raise SystemExit(f"서울 전체 지수로 {BASE} 또는 {last} 분기를 채우지 못했습니다.")
    allp = round((e / b - 1) * 100, 1)

    print(f"부동산원 아파트 매매 실거래가격지수 — {qname(BASE)} -> {qname(last)}")
    for n, p in rows:
        print(f"  {n:7s} {p:+6.1f}%")
    print(f"  {ALL:7s} {allp:+6.1f}%")
    up = sum(1 for _, p in rows if p > 0)
    print(f"  오른 구 {up}/25, 가장 큼 {rows[0][0]} {rows[0][1]:+}%, "
          f"가장 작음 {rows[-1][0]} {rows[-1][1]:+}%")

    item = {
        "slide": SLIDE,
        "title": "이재명 정부 출범 이후 서울 구별 아파트값",
        "category": "부동산",
        "source": (f"한국부동산원 아파트 매매 실거래가격지수. {qname(BASE)}(취임 직전 "
                   f"분기) 대비 {qname(last)}. 단위: %."),
        "sourceUrl": URL,
        "vizType": "bar", "unit": "%",
        "labels": [n for n, _ in rows] + [ALL],
        "series": [[p for _, p in rows] + [allp]],
        "seriesNames": ["실거래가격지수 변동률"],
        "signColors": {"plus": "#2a5ca8", "minus": "#c0322f"},
        "labelColors": {ALL: "#6e6e6e"},
        "notes": [
            f"이재명 대통령 취임이 2025년 6월 4일이어서 취임 직전에 끝난 "
            f"{qname(BASE)}을 출발점으로 삼았습니다. 끝은 {qname(last)}입니다. "
            "2025년 2분기는 취임 전후가 섞여 있습니다.",
            "실제로 거래된 가격으로 만든 지수입니다. 처음에는 KB 월간 평균 "
            "매매가격으로 그렸다가 바꿨습니다. 평균가격은 거래되거나 표본에 든 "
            "아파트 값의 평균이어서, 표본이 바뀌면 가격이 움직이지 않아도 평균이 "
            "뜁니다.",
            "바꾼 이유가 강동구입니다. KB 평균가격으로는 +41.8%로 1위였는데, "
            "2025년 10월에 한 달 +5.75%, 2026년 9월에 +9.89% 튄 달이 있었습니다. "
            "같은 달 서울 평균은 +1.75%와 +1.08%였고, 25개 구 가운데 그런 달이 "
            "있는 곳은 강동구뿐이었습니다. 대단지 입주로 표본이 바뀐 것으로 "
            "보입니다.",
            "분기 단위입니다. 실거래가격지수는 거래가 끝난 뒤 신고 기간을 거쳐 "
            "집계해서 월간 지수보다 늦게 나옵니다. 그만큼 최근 움직임은 "
            "이 차트에 아직 반영되지 않습니다.",
            "자료는 KOSIS 의 두 표입니다. 구별은 시군구 분기별 표"
            "(DT_KAB_11672_S5), 서울 전체는 시도 월별 표(DT_KAB_11672_S1)를 "
            "분기로 묶은 값입니다.",
            f"'{ALL}'은 구가 아니라 서울 전체여서 회색으로 구분했습니다. {allp:+}%입니다. "
            "구별 표에는 서울 합계가 없어서 시도 표의 서울 지수를 같은 분기로 "
            "묶어 넣었습니다. 같은 통계의 다른 집계 단위입니다.",
            "지수라 변동률만 보여 줍니다. 같은 1%라도 강남구와 도봉구는 금액 "
            "차이가 큽니다. 절대 금액은 서울 구별 아파트 평균 매매가격 차트를 "
            "보십시오.",
            "구 이름이 서울 밖에도 있어서(중구, 강서구 등) 이름이 아니라 "
            "행정구역 코드로 서울 25개 구를 골랐습니다.",
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
