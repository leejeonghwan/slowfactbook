#!/usr/bin/env python3
"""
정권별 비교 차트 — 취임 달을 0으로 놓고 임기 60개월을 나란히 그린다 (코스피 차트와 같은 틀).

  KOSIS_API_KEY=… python3 scripts/term_charts.py            # 미리보기
  KOSIS_API_KEY=… python3 scripts/term_charts.py --apply    # data/manual.json 에 반영 (같은 제목이면 제자리 갱신, id 유지)

만드는 차트
  1. 역대 정부 누적 물가 — 소비자물가지수(KOSIS DT_1J22003, 2020=100), 취임 달 대비 누적 %
  2. 역대 정부 서울 아파트 가격 — 부동산원 월간 아파트 매매가격지수, 취임 달 대비 누적 %
     1986.01~2012.12 (DT_304N_04_00001, 2011.6=100) → 2003.11~2025.03 (DT_40803_N0001) → 2021.06~ (DT_30404_B012)
     세 표를 겹치는 구간 비율(중앙값)로 연쇄해 1986년부터 한 줄로 만든다.

update.sh 가 KOSIS 수집 뒤에 이 스크립트를 돌리므로 달마다 알아서 늘어난다.
"""
import os, sys, json, datetime, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_api_charts as bac   # noqa: E402  (kosis_series 재사용)

# 취임 달 · 마지막 달(임기 만료·파면·사망). None 이면 현직.
TERMS = [
    ("노태우", "198802", "199301"),
    ("김영삼", "199302", "199801"),
    ("김대중", "199802", "200301"),
    ("노무현", "200302", "200801"),
    ("이명박", "200802", "201301"),
    ("박근혜", "201302", "201703"),   # 2017-03-10 파면
    ("문재인", "201705", "202204"),
    ("윤석열", "202205", "202504"),   # 2025-04-04 파면
    ("이재명", "202506", None),
]
MONTHS = 60
LABELS = [""] * (MONTHS + 1)
for k, name in enumerate(["1년차", "2년차", "3년차", "4년차", "5년차"]):
    LABELS[k * 12] = name
LABELS[MONTHS] = "임기 말"

CPI = {"orgId": "101", "tblId": "DT_1J22003", "itmId": "T+", "objL1": "T10+",
       "prdSe": "M", "startPrdDe": "196501", "endPrdDe": "203512"}
APT = [  # 오래된 것부터. 뒤 표가 앞 표를 덮어쓰고, 앞 표는 겹치는 구간 비율로 환산된다.
    {"orgId": "408", "tblId": "DT_304N_04_00001", "itmId": "16304304_01+",
     "objL1": "1530430404B+", "objL2": "15304A304_04_022+", "prdSe": "M", "startPrdDe": "198601", "endPrdDe": "201212"},
    {"orgId": "408", "tblId": "DT_40803_N0001", "itmId": "sales+",
     "objL1": "01+", "objL2": "a7+", "prdSe": "M", "startPrdDe": "200311", "endPrdDe": "202512"},
    {"orgId": "408", "tblId": "DT_30404_B012", "itmId": "sales+",
     "objL1": "01+", "objL2": "a7+", "prdSe": "M", "startPrdDe": "202106", "endPrdDe": "203512"},
]


def addm(ym, n):
    y, m = int(ym[:4]), int(ym[4:]) - 1 + n
    return f"{y + m // 12}{m % 12 + 1:02d}"


def chain(parts):
    """뒤 표를 기준으로, 앞 표를 겹치는 구간 비율로 환산해 앞에 붙인다."""
    cur = dict(parts[-1])
    for prev in reversed(parts[:-1]):
        common = sorted(set(prev) & set(cur))
        if not common:
            raise RuntimeError(f"겹치는 구간이 없음 ({min(prev)}~{max(prev)} vs {min(cur)}~{max(cur)})")
        rr = sorted(cur[p] / prev[p] for p in common if prev[p])
        ratio = rr[len(rr) // 2]
        dev = max(abs(cur[p] / prev[p] / ratio - 1) for p in common if prev[p])
        # 옛 표(1986~)는 새 조사가 시작된 2003.11 한 달만 겹친다 — 기준 시점 접속은 원래 한 점으로 한다
        note = " ※ 한 점 접속" if len(common) < 3 else ""
        print(f"    연쇄: {min(prev)}~{max(prev)} 표({len(prev)}달) → ×{ratio:.5f} (겹침 {len(common)}달, 최대 편차 {dev*100:.2f}%){note}")
        first = min(cur)                      # 루프 안에서 min(cur) 를 다시 재면 한 달만 붙는다
        for p, v in prev.items():
            if p < first:
                cur[p] = v * ratio
    return cur


def term_series(level):
    """월별 수준 → 정권별 취임 달 대비 누적 % (61점, 임기 밖은 None)."""
    names, series, meta = [], [], []
    for name, start, end in TERMS:
        if start not in level:
            continue
        base = level[start]
        row = []
        for k in range(MONTHS + 1):
            ym = addm(start, k)
            if (end and ym > end) or ym not in level:
                row.append(None)
            else:
                row.append(round((level[ym] / base - 1) * 100, 2))
        last = max(k for k, v in enumerate(row) if v is not None)
        names.append(name); series.append(row)
        meta.append((name, start, addm(start, last), row[last]))
    return names, series, meta


def upsert(doc, title, item):
    for i, it in enumerate(doc["items"]):
        if it["title"] == title:
            item["slide"] = it["slide"]
            doc["items"][i] = item
            return it["slide"], False
    n = 1 + max([int(it["slide"].split("-")[1]) for it in doc["items"]] or [0])
    item["slide"] = f"m-{n:04d}"
    doc["items"].append(item)
    return item["slide"], True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--cpi-file", help="테스트용: 월별 CPI JSON {YYYYMM: 값} (KOSIS 대신)")
    ap.add_argument("--apt-file", help="테스트용: 월별 서울 아파트 지수 JSON {YYYYMM: 값}")
    a = ap.parse_args()
    if not (a.cpi_file and a.apt_file) and not bac.KOSIS_KEY:
        print("KOSIS_API_KEY 가 필요합니다 (.env 또는 환경변수)")
        return 1
    today = datetime.date.today().isoformat()

    print("▶ 소비자물가지수")
    cpi = json.load(open(a.cpi_file)) if a.cpi_file else dict(bac.kosis_series(CPI))
    print(f"  {min(cpi)}~{max(cpi)} {len(cpi)}달")
    n1, s1, m1 = term_series(cpi)

    print("▶ 서울 아파트 매매가격지수")
    if a.apt_file:
        apt = json.load(open(a.apt_file))
    else:
        parts = []
        for spec in APT:
            d = dict(bac.kosis_series(spec))
            ks = sorted(d)
            gaps = sum(1 for a, b in zip(ks, ks[1:]) if addm(a, 1) != b)
            print(f"  표 {spec['tblId']}: {ks[0] if ks else '-'}~{ks[-1] if ks else '-'} {len(d)}달" + (f" (빈 구간 {gaps}곳)" if gaps else ""))
            parts.append(d)
        apt = chain(parts)
    print(f"  {min(apt)}~{max(apt)} {len(apt)}달")
    n2, s2, m2 = term_series(apt)

    for title, meta in (("누적 물가", m1), ("서울 아파트", m2)):
        print(f"\n{title}:")
        for name, s, e, v in meta:
            print(f"  {name:4s} {s}→{e}  {v:+.1f}%")

    charts = [
        {"title": "역대 정부 누적 물가 상승률", "category": "소비와 물가",
         "source": "국가데이터처 소비자물가지수(2020=100), 취임 달 대비 누적 상승률, 단위: %",
         "sourceUrl": "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1J22003",
         "vizType": "line", "labels": LABELS, "seriesNames": n1, "series": s1, "updated": today},
        {"title": "역대 정부 서울 아파트 가격 상승률", "category": "부동산",
         "source": "한국부동산원 월간 아파트 매매가격지수(1986~2012 구간은 2011.6=100 표를 연쇄 환산), 취임 달 대비 누적 상승률, 단위: %",
         "sourceUrl": "https://kosis.kr/statHtml/statHtml.do?orgId=408&tblId=DT_30404_B012",
         "vizType": "line", "labels": LABELS, "seriesNames": n2, "series": s2, "updated": today},
    ]
    if not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)")
        return 0
    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else \
        {"category": "새 데이터", "_origin": "manual", "items": []}
    clp = os.path.join(DATA, "changelog.json")
    cl = json.load(open(clp, encoding="utf-8")) if os.path.exists(clp) else []
    for c in charts:
        slide, new = upsert(doc, c["title"], c)
        cl.append({"date": today, "slide": slide, "id": "", "title": c["title"], "category": c["category"],
                   "mode": "new" if new else "replace", "from": "1년차", "to": "임기 말", "n": MONTHS + 1,
                   "sourceUrl": c["sourceUrl"], "note": "term_charts.py 자동 생성", "keynoteSynced": False})
        print(f"  → {slide} {'추가' if new else '갱신'}: {c['title']}")
    json.dump(doc, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(cl, open(clp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→ data/manual.json 반영. 다음: python3 scripts/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
