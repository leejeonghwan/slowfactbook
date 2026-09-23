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
  3. 계열이 둘 이상인 차트는 매핑에 계열별 축(series)이 적혀 있을 때만 잇는다.
     그때도 모든 계열의 시점 정렬이 똑같아야 한다 (하나라도 어긋나면 통째로 건너뛴다).

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


def fetch_many(spec):
    """매핑에 적힌 축 그대로 계열들을 받는다.

    spec["series"] = [{"itmId": ..., "objL1": ...}, ...] 가 있으면 계열마다 따로 조회한다.
    각 항목에 없는 값은 spec 의 것을 쓴다 (보통 itmId 는 같고 분류축만 다르다).
    """
    subs = spec.get("series") or [{}]
    out = []
    for sub in subs:
        get = lambda k, d=None: sub.get(k, spec.get(k, d))
        objs = [get(f"objL{i}") for i in range(1, 5)]
        objs = [o for o in objs if o]
        ser = mf.fetch_bulk(get("orgId"), get("tblId"), [str(get("itmId")).rstrip("+")], objs,
                            get("startPrdDe", "1960"), get("endPrdDe", "2035"), get("prdSe"))
        # 계열이 여럿 돌아오면 가장 긴 것을 쓴다 (축을 하나로 좁혀둔 매핑이라 보통 하나다)
        out.append(max(ser.values(), key=len) if ser else [])
    return out


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

    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))   # changelog 에 id 를 남기려면 필요하다
    items = {it["slide"]: it for it in _items}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    today = datetime.date.today().isoformat()

    ext, skip_multi, skip_score, skip_current, skip_align, errs = [], [], [], [], [], []
    streak = 0                                   # 연속 조회 실패 — KOSIS 장애면 나머지는 건너뛴다
    for slide, spec in mapping.items():
        it = items.get(slide)
        if not it or spec.get("provider", "kosis") != "kosis":
            continue
        if streak >= 3:
            errs.append((it["title"], "건너뜀(연속 실패)"))
            continue
        series = it.get("series") or []
        nser = len(series)
        if nser == 0:
            continue
        if nser > 1 and not spec.get("series"):
            skip_multi.append(it["title"])
            continue
        if spec.get("series") and len(spec["series"]) != nser:
            skip_multi.append(it["title"] + " (매핑 계열 수 불일치)")
            continue
        try:
            apis = fetch_many(spec)
        except Exception as e:
            errs.append((it["title"], str(e)[:60]))
            streak += 1
            continue
        streak = 0
        if any(len(x) < 4 for x in apis):
            continue
        offs, scs, scores = [], [], []
        for cvi, api in zip(series, apis):
            cv = [None if x is None else float(x) for x in cvi]
            score, off, sc = mf.align(cv, [v for _, v in api])
            offs.append(off); scs.append(sc); scores.append(score)
        if min(scores) < a.min_score or None in offs:
            skip_score.append((it["title"], round(min(scores), 2)))
            continue
        if len(set(offs)) != 1:
            skip_align.append((it["title"], offs))
            continue
        off = offs[0]
        # 계열마다 시점→값 (같은 표의 다른 축이라 시점 축은 보통 같다)
        maps = [dict(api) for api in apis]
        periods = [p for p, _ in apis[0]]
        tail = off + len(series[0]) - 1
        if tail >= len(periods) - 1:
            skip_current.append(it["title"])
            continue
        addp = periods[tail + 1:]
        newlabels = [fmt_like(it["labels"][-1], p, spec["prdSe"]) for p in addp]
        newseries = []
        for cvi, m, sc in zip(series, maps, scs):
            cv = [None if x is None else float(x) for x in cvi]
            newseries.append(cv + [None if m.get(p) is None else round(m[p] * sc, 6) for p in addp])
        ext.append({"slide": slide, "title": it["title"], "id": it.get("id"),
                    "from": str(it["labels"][-1]), "to": newlabels[-1],
                    "n": len(addp), "score": round(min(scores), 3), "nser": nser,
                    "labels": list(map(str, it["labels"])) + newlabels,
                    "series": newseries})

    print(f"확정 매핑 {len(mapping)}건 검토")
    print(f"  이어붙일 수 있음 : {len(ext)}")
    print(f"  이미 최신        : {len(skip_current)}")
    print(f"  계열 축 미등록   : {len(skip_multi)}  (register_auto.py 로 등록하면 이어붙는다)")
    print(f"  계열 정렬 불일치 : {len(skip_align)}")
    print(f"  값 대조 미달     : {len(skip_score)}")
    print(f"  조회 실패        : {len(errs)}")
    print()
    for e in sorted(ext, key=lambda x: -x["n"]):
        print(f"  + {e['title'][:28]:30s} {e['from']} → {e['to']}  ({e['n']}점 추가"
              + (f" × {e['nser']}계열" if e['nser'] > 1 else "") + f", 일치도 {e['score']})")

    if a.apply and ext:
        for e in ext:
            o = ov.setdefault(e["slide"], {})
            o["labels"] = e["labels"]
            o["series"] = e["series"]
            o["updated"] = today
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        # 키노트에 옮길 목록(changelog)에도 남긴다 — keynote_sync.py 가 읽는다
        clp = os.path.join(DATA, "changelog.json")
        cl = json.load(open(clp, encoding="utf-8")) if os.path.exists(clp) else []
        for e in ext:
            cl.append({"date": today, "slide": e["slide"], "id": e["id"], "title": e["title"],
                       "category": items[e["slide"]]["category"], "mode": "auto",
                       "from": e["from"], "to": e["to"], "n": e["n"],
                       "sourceUrl": mapping[e["slide"]].get("sourceUrl", ""), "keynoteSynced": False})
        json.dump(cl, open(clp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n→ data/overrides.json 에 {len(ext)}건 반영 (changelog 기록). 다음: python3 scripts/build.py")
    elif ext:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
