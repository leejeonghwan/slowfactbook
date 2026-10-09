#!/usr/bin/env python3
"""
차트 전수 대장 — 무엇이 자동이고 무엇이 손이고, 주기는 얼마이고, 라벨이 성한가.

  python3 scripts/registry.py            요약
  python3 scripts/registry.py --tsv      data/registry.tsv 로 전수 출력

판정 기준
  소스종류  : api_map_auto / api_map / api_charts / kb_charts / poll(리얼미터) 등록 여부
  주기      : 라벨 모양에서 읽는다. 연도만 반복되면 '연', 같은 연도가 4번이면 '분기',
              12번이면 '월', 그보다 잦으면 '주' 로 본다. 비시계열은 '없음'.
  라벨품질  : 월·분기 자료인데 라벨이 연도로 뭉개져 있으면 '뭉갬' 으로 표시한다.
              원본 소스가 확보된 차트는 원래 시점으로 되살릴 수 있다.
  소스후보  : 출처 문자열에서 기관을 읽어 자동 창구가 있는 곳인지 가른다.
"""
import os, re, sys, json, glob, csv, io, argparse
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SEP = "\x1f"

API_OK = {           # 자동 조회 창구가 있는 기관
    "국가데이터처": "KOSIS", "통계청": "KOSIS", "KOSIS": "KOSIS", "국가통계포털": "KOSIS",
    "고용노동부": "KOSIS", "보건복지부": "KOSIS", "행정안전부": "KOSIS", "교육부": "KOSIS",
    "국세청": "KOSIS", "기획재정부": "KOSIS", "건강보험": "KOSIS", "국토교통부": "KOSIS",
    "한국부동산원": "KOSIS", "한국은행": "ECOS", "ECOS": "ECOS",
    "OECD": "OECD", "World Bank": "WorldBank", "IMF": "IMF", "Eurostat": "Eurostat",
    "FRED": "FRED", "한국갤럽": "갤럽PDF", "갤럽": "갤럽PDF", "리얼미터": "리얼미터PDF",
    "KB": "KB엑셀", "KRX": "KRX",
}


def load_all():
    ov = json.load(open(os.path.join(DATA, "overrides.json"), encoding="utf-8"))
    ids = json.load(open(os.path.join(DATA, "ids.json"), encoding="utf-8"))
    idof = {}
    for k, v in ids.items():
        p = k.split(SEP)
        if len(p) >= 3 and p[0] == "S":
            idof.setdefault((p[1], p[2]), v)
    items = []
    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not (isinstance(d, dict) and "items" in d):
            continue
        for it0 in d["items"]:
            if not it0.get("vizType"):
                continue
            it = {**it0, **(ov.get(it0.get("slide")) or {})}
            t = (it0.get("title") or "").strip().rstrip(".")
            if not t:
                continue
            it["_id"] = idof.get((it0.get("slide"), t)) or ""
            it["_title"] = t
            items.append(it)
    return items


def cadence(labels):
    """라벨 모양에서 주기와 라벨품질을 읽는다."""
    labs = [str(x).strip() for x in labels]
    nonempty = [x for x in labs if x]
    if not nonempty:
        return "없음", "-"
    # YYYY-MM / YYYY.MM / YYYYMM 처럼 시점이 적혀 있으면 그대로 믿는다
    if any(re.fullmatch(r"(19|20)\d{2}[-./]?(0[1-9]|1[0-2])", x) for x in nonempty):
        return "월", "정상"
    if any(re.fullmatch(r"(19|20)\d{2}[-./]\d{2}[-./]\d{2}", x) for x in nonempty):
        return "일·주", "정상"
    years = [x for x in nonempty if re.fullmatch(r"(19|20)\d{2}", x)]
    if len(years) < max(3, len(nonempty) * 0.6):
        return "없음", "-"          # 지역·연령 등 비시계열
    c = Counter(years)
    rep = sum(c.values()) / len(c)
    # 연도 하나가 여러 번 반복되면 월·분기인데 연도로 뭉갠 것이다
    if rep >= 8:
        return "월", "뭉갬"
    if rep >= 3:
        return "분기", "뭉갬"
    # 빈 라벨이 섞인 채 연도가 드문드문이면 월·주를 연도만 찍은 것
    if len(labs) >= len(years) * 3:
        return "월·주", "뭉갬"
    return "연", "정상"


def source_kind(src):
    s = src or ""
    for k, v in API_OK.items():
        if k in s:
            return v
    return "손" if s.strip() else "출처없음"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", action="store_true")
    a = ap.parse_args()

    reg_auto = json.load(open(os.path.join(DATA, "api_map_auto.json"), encoding="utf-8"))
    reg_man = json.load(open(os.path.join(DATA, "api_map.json"), encoding="utf-8"))
    kb = json.load(open(os.path.join(DATA, "kb_charts.json"), encoding="utf-8"))
    poll_slides = {"slide-570", "slide-571"}

    rows = []
    for it in load_all():
        sl = it.get("slide")
        cid = it["_id"]
        if sl in reg_auto:
            track = "KOSIS 자동"
        elif sl in reg_man:
            track = "KOSIS 수동"
        elif str(sl).startswith("api-"):
            track = "API 트랙"
        elif cid in kb:
            track = "KB 엑셀"
        elif sl in poll_slides:
            track = "리얼미터"
        else:
            track = "미등록"
        labs = it.get("labels") or []
        cad, qual = cadence(labs)
        last = next((str(x) for x in reversed(labs) if str(x).strip()), "")
        src = (it.get("source") or "").strip()
        rows.append({
            "id": cid, "제목": it["_title"][:50], "분류": it.get("category") or "",
            "트랙": track, "주기": cad, "라벨": qual, "점수": len(labs),
            "계열": len(it.get("series") or []), "마지막": last,
            "소스후보": source_kind(src), "출처": src[:70],
            "링크": (it.get("sourceUrl") or "")[:90],
        })

    print(f"차트 {len(rows)}개\n")
    def tab(key, order=None):
        c = Counter(r[key] for r in rows)
        ks = order or [k for k, _ in c.most_common()]
        for k in ks:
            if c.get(k):
                print(f"  {k:<12} {c[k]:>5}")
    print("■ 트랙"); tab("트랙")
    print("\n■ 주기(라벨에서 추정)"); tab("주기", ["주", "일·주", "월", "월·주", "분기", "연", "없음"])
    print("\n■ 라벨 상태"); tab("라벨", ["정상", "뭉갬", "-"])
    print("\n■ 소스 후보"); tab("소스후보")

    auto = [r for r in rows if r["트랙"] != "미등록"]
    ts = [r for r in rows if r["주기"] in ("주", "일·주", "월", "월·주", "분기", "연")]
    print(f"\n시계열 {len(ts)}개 중 자동 {len([r for r in ts if r['트랙'] != '미등록'])}개, "
          f"손 {len([r for r in ts if r['트랙'] == '미등록'])}개")
    print(f"라벨이 뭉개진 시계열 {len([r for r in ts if r['라벨'] == '뭉갬'])}개 "
          f"(그중 소스 확보 {len([r for r in ts if r['라벨'] == '뭉갬' and r['트랙'] != '미등록'])}개 — 바로 되살릴 수 있다)")

    if a.tsv:
        p = os.path.join(DATA, "registry.tsv")
        with io.open(p, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter="\t")
            w.writeheader()
            w.writerows(sorted(rows, key=lambda r: (r["트랙"], r["주기"], r["id"])))
        print(f"\n→ {os.path.relpath(p, ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
