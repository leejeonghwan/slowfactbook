#!/usr/bin/env python3
"""
확정 매칭된 기존 차트를 KOSIS 최신값으로 '제자리' 갱신한다.

  data/api_map_auto.json  (매칭 결과)
        │  KOSIS에서 최신 계열을 받는다
        ▼
  data/overrides.json     (슬라이드 id 로 덧씌우는 패치)
        ▼
  generate_site.load_items 가 병합 → 사이트

새 차트를 만들지 않는다. 기존 차트의 제목·분류·임베드 주소를 그대로 두고
꼬리에 새 시점만 이어붙인다. 그래서 독자가 보던 주소가 그대로 살아 있고,
기사 맥락(시작 시점)도 건드리지 않는다.

안전장치 셋:
  1. 값 대조를 다시 해서 일치도가 기준 미만이면 건드리지 않는다.
  2. 차트가 이미 담고 있는 구간의 값은 절대 고치지 않는다. 뒤에만 붙인다.
  3. 계열이 둘 이상인 차트는 건너뛴다 (어느 계열이 어느 통계표인지 확실치 않으므로).

  KOSIS_API_KEY=... python3 scripts/refresh_charts.py --dry-run
  KOSIS_API_KEY=... python3 scripts/refresh_charts.py --apply
"""
import os, sys, json, re, datetime, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import generate_site as g          # noqa: E402
import match_fast as mf            # noqa: E402

MINSCORE = 0.9


def fetch(spec):
    """매핑에 적힌 축 그대로 한 계열을 받는다."""
    q = {"orgId": spec["orgId"], "tblId": spec["tblId"], "itmId": spec["itmId"],
         "prdSe": spec["prdSe"], "startPrdDe": spec.get("startPrdDe", "1960"),
         "endPrdDe": spec.get("endPrdDe", "2035")}
    objs = [spec[f"objL{i}"] for i in range(1, 5) if spec.get(f"objL{i}")]
    ser = mf.fetch_bulk(q["orgId"], q["tblId"], [q["itmId"].rstrip("+")], objs,
                        q["startPrdDe"], q["endPrdDe"], q["prdSe"])
    # 계열이 여럿 돌아오면 가장 긴 것을 쓴다 (축을 하나로 좁혀둔 매핑이라 보통 하나다)
    return max(ser.values(), key=len) if ser else []


def fmt_like(sample, period, prdSe):
    """기존 라벨 생김새를 흉내 내 새 시점의 라벨을 만든다."""
    s = str(sample).strip()
    p = str(period)
    y, rest = p[:4], p[4:]
    if re.fullmatch(r"(19|20)\d{2}", s):                 # 2024
        return y
    if re.fullmatch(r"(19|20)\d{2}\s*년", s):            # 2024년
        return f"{y}년"
    if re.fullmatch(r"[’']?\d{2}", s):                   # ’24
        return ("’" if s.startswith("’") else "'") + y[2:] if not s[0].isdigit() else y[2:]
    m = re.fullmatch(r"(19|20)\d{2}([-./])(\d{1,2})", s)  # 2024-05
    if m and rest:
        return f"{y}{m.group(2)}{int(rest):02d}"
    m = re.fullmatch(r"(19|20)\d{2}\s*(\d)\s*[QqＱ분기]+", s)  # 2024 2Q
    if m and rest:
        return f"{y} {int(rest)}Q"
    m = re.fullmatch(r"(\d{1,2})\s*월", s)               # 5월
    if m and rest:
        return f"{int(rest)}월"
    return y if not rest else f"{y}-{int(rest):02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-score", type=float, default=MINSCORE)
    a = ap.parse_args()
    if not a.apply and not a.dry_run:
        a.dry_run = True

    mapping = {}
    for f in ("api_map.json", "api_map_auto.json"):
        p = os.path.join(DATA, f)
        if os.path.exists(p):
            mapping.update(json.load(open(p, encoding="utf-8")))

    items = {it["slide"]: it for it in g.load_items(DATA)}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    today = datetime.date.today().isoformat()

    ext, skip_multi, skip_score, skip_current, errs = [], [], [], [], []
    for slide, spec in mapping.items():
        it = items.get(slide)
        if not it or spec.get("provider", "kosis") != "kosis":
            continue
        series = it.get("series") or []
        if len(series) != 1:
            skip_multi.append(it["title"])
            continue
        try:
            api = fetch(spec)
        except Exception as e:
            errs.append((it["title"], str(e)[:60]))
            continue
        if len(api) < 4:
            continue
        av = [v for _, v in api]
        cv = [None if x is None else float(x) for x in series[0]]
        score, off, sc = mf.align(cv, av)
        if score < a.min_score or off is None:
            skip_score.append((it["title"], round(score, 2)))
            continue
        # 차트의 마지막 점이 API 계열의 몇 번째인가
        tail = off + len(cv) - 1
        if tail >= len(api) - 1:
            skip_current.append(it["title"])
            continue
        add = api[tail + 1:]
        newlabels = [fmt_like(it["labels"][-1], p, spec["prdSe"]) for p, _ in add]
        newvals = [round(v * sc, 6) for _, v in add]
        ext.append({"slide": slide, "title": it["title"], "id": it.get("id"),
                    "from": str(it["labels"][-1]), "to": newlabels[-1],
                    "n": len(add), "score": round(score, 3),
                    "labels": list(map(str, it["labels"])) + newlabels,
                    "series": [cv + newvals]})

    print(f"확정 매핑 {len(mapping)}건 검토")
    print(f"  이어붙일 수 있음 : {len(ext)}")
    print(f"  이미 최신        : {len(skip_current)}")
    print(f"  계열 둘 이상     : {len(skip_multi)}  (수동 · TSV로)")
    print(f"  값 대조 미달     : {len(skip_score)}")
    print(f"  조회 실패        : {len(errs)}")
    print()
    for e in sorted(ext, key=lambda x: -x["n"]):
        print(f"  + {e['title'][:28]:30s} {e['from']} → {e['to']}  ({e['n']}점 추가, 일치도 {e['score']})")

    if a.apply and ext:
        for e in ext:
            o = ov.setdefault(e["slide"], {})
            o["labels"] = e["labels"]
            o["series"] = e["series"]
            o["updated"] = today
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n→ data/overrides.json 에 {len(ext)}건 반영. 다음: python3 scripts/build.py")
    elif ext:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
