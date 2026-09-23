#!/usr/bin/env python3
"""
차트 하나를 KOSIS 통계표 하나에 붙여 자동 갱신(refresh_charts.py) 대상으로 등록한다.

  KOSIS_API_KEY=... python3 scripts/register_auto.py slide-122 --tbl DT_118N_MON051 [--org 118]
  KOSIS_API_KEY=... python3 scripts/register_auto.py m-0001 --url "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1B81A17"

match_fast.py 가 제목 검색으로 표를 찾는 것과 달리, 여기서는 표를 사람이 찍어 준다.
그 표의 모든 항목×분류 계열을 받아 차트 값과 대조하고(match_fast.align), 맞는 계열을
data/api_map_auto.json 에 적는다. 그 다음부터는 refresh_charts.py 와 매일 빌드가 알아서 잇는다.

계열이 둘 이상이면 계열마다 따로 대조해 축을 각각 찾아 적는다(spec["series"]).
모든 계열이 같은 시점에서 맞아떨어져야 등록한다 — 그래야 refresh_charts 가 통째로 이어붙인다.
"""
import os, sys, json, re, collections, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import generate_site as g       # noqa: E402
import match_fast as mf         # noqa: E402


def _far(prdSe, p1):
    """자동 갱신이 앞으로 몇 해는 더 긁어오도록 끝 시점을 넉넉히 잡는다."""
    y = int(str(p1)[:4]) + 8
    return {"Y": f"{y}", "H": f"{y}02", "Q": f"{y}04", "M": f"{y}12"}.get(prdSe, f"{y}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slide", help="slide-964 · m-0001 · 964 · c0718")
    ap.add_argument("--tbl", help="KOSIS 통계표 ID (DT_…)")
    ap.add_argument("--org", default=None, help="기관 코드 (기본 101=국가데이터처, URL에 있으면 거기서)")
    ap.add_argument("--url", help="KOSIS statHtml URL (orgId·tblId 를 여기서 읽는다)")
    ap.add_argument("--codes", type=int, default=60, help="첫 분류축에서 시도할 코드 수")
    ap.add_argument("--accept", type=float, default=0.9)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not mf.KEY:
        print("KOSIS_API_KEY 환경변수가 필요합니다.")
        return 1
    org, tbl = a.org, a.tbl
    if a.url:
        m = re.search(r"tblId=([A-Za-z0-9_]+)", a.url)
        tbl = tbl or (m.group(1) if m else None)
        m = re.search(r"orgId=(\d+)", a.url)
        org = org or (m.group(1) if m else None)
    org = org or "101"
    if not tbl:
        print("--tbl 또는 --url 로 통계표를 지정하세요.")
        return 1

    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    k = a.slide if not re.fullmatch(r"\d+", a.slide) else "slide-" + a.slide
    it = next((x for x in items if x["slide"] == k or x["id"] == k), None)
    if not it:
        print(f"차트를 찾지 못했습니다: {a.slide}")
        return 1
    ys = mf.chart_years(it)
    freq = mf.infer_freq(ys)
    if not freq:
        print("시계열 차트가 아니거나 주기를 알 수 없습니다. (지역별·연령별 표는 match_cross.py)")
        return 1
    yy = [y for y in ys if y]
    p0, p1 = min(yy), str(int(max(yy)) + 1)
    span = {"Y": (p0, p1), "Q": (p0 + "01", p1 + "04"), "M": (p0 + "01", p1 + "12"), "H": (p0 + "01", p1 + "02")}
    prds = {"Y": ["Y"], "Q": ["Q"], "M": ["M"], "H": ["H", "Y"]}[freq]
    targets = [[None if v is None else float(v) for v in row] for row in it["series"]]
    names = it.get("seriesNames") or [f"계열{i+1}" for i in range(len(targets))]
    print(f"대상: {it['slide']} {it['id']} [{it['category']}] {it['title']}  주기 {freq}  {p0}~{max(yy)}  "
          f"{len(targets[0])}점 × {len(targets)}계열")

    mi = mf.meta(org, tbl)
    itms = [r["ITM_ID"] for r in mi if r.get("OBJ_ID") == "ITEM"]
    objs = collections.OrderedDict()
    for r in mi:
        if r.get("OBJ_ID") != "ITEM":
            objs.setdefault(r["OBJ_ID"], []).append(r["ITM_ID"])
    names_meta = {r["ITM_ID"]: r.get("ITM_NM") for r in mi}
    # 축마다 따로 — 축이 달라도 코드값이 같을 수 있어 한 데 묶으면 엉뚱한 이름이 붙는다
    names_ax = {}
    for r in mi:
        if r.get("OBJ_ID") != "ITEM":
            names_ax.setdefault(r["OBJ_ID"], {})[r["ITM_ID"]] = r.get("ITM_NM")
    keys = list(objs)
    print(f"  표 {tbl}: 항목 {len(itms)}개, 분류축 {len(keys)}개 " +
          " ".join(f"{k}({len(objs[k])})" for k in keys))

    best = [None] * len(targets)          # 계열마다 가장 잘 맞는 KOSIS 계열
    # KOSIS 는 한 번에 40,000셀까지만 준다. 시점이 많으면(월 단위 수십 년) 코드를 그만큼 적게 넣어야 한다.
    nper = (int(p1) - int(p0) + 1) * {"Y": 1, "H": 2, "Q": 4, "M": 12}[freq]
    budget = max(2, 38000 // max(1, nper))
    sizes = [len(objs[k]) for k in keys]
    def fit(plan):
        plan = [max(1, min(n, sz)) for n, sz in zip(plan, sizes)]
        while len(plan) > 1 and plan[0] * plan[1] > budget:
            if plan[1] >= plan[0]:
                plan[1] = max(1, plan[1] // 2)
            else:
                plan[0] = max(1, plan[0] // 2)
            if plan[0] == plan[1] == 1:
                break
        prod = 1
        for x in plan:
            prod *= x
        while plan[0] > 1 and prod > budget:
            plan[0] = max(1, plan[0] // 2)
            prod = 1
            for x in plan:
                prod *= x
        return plan
    cands = []
    for i in range(len(keys)):                       # 축을 하나씩 넓게 훑는다
        pl = [1] * len(keys); pl[i] = min(a.codes, budget)
        cands.append(fit(pl))
    if len(keys) >= 2:                               # 두 축을 함께 (계열이 여럿일 때 흔한 꼴)
        h = max(2, int(budget ** 0.5))
        cands.append(fit([h, h] + [1] * (len(keys) - 2)))
    if len(targets) > 1 and len(keys) >= 2:          # 계열이 여럿이면 분류축을 넓게 보는 쪽을 먼저
        cands.insert(0, cands.pop(1))
    uniq, seen_plans = [], set()
    for pl in cands:
        if tuple(pl) not in seen_plans:
            seen_plans.add(tuple(pl)); uniq.append(pl)
    plans = uniq
    print(f"  한 번에 받을 수 있는 코드 수 {budget}개 (시점 {nper}개) → 탐색 계획 {plans}")

    def done():
        return all(b and b["score"] >= 0.99 for b in best)

    for plan in plans:
        ol = ["+".join(objs[k][:n]) + "+" for k, n in zip(keys, plan)]
        for ps in prds:
            lo, hi = span[ps] if ps == freq else (p0, p1)
            for chunk in range(0, max(1, len(itms)), 8):
                try:
                    groups = mf.fetch_bulk(org, tbl, itms[chunk:chunk + 8], ol, lo, hi, ps)
                except Exception as e:
                    print(f"  조회 실패: {str(e)[:80]}")
                    continue
                for gk, ser in groups.items():
                    av = [v for _, v in ser]
                    for i, vals in enumerate(targets):
                        r, off, sc = mf.align(vals, av)
                        if r > 0 and (best[i] is None or r > best[i]["score"]):
                            best[i] = {"score": round(r, 3), "gk": gk, "prdSe": ps, "offset": off,
                                       "scale": sc, "periods": [p for p, _ in ser], "start": lo, "end": hi}
                if done():
                    break
            if done():
                break
        if all(b and b["score"] >= a.accept for b in best):
            break

    bad = [i for i, b in enumerate(best) if not b or b["score"] < a.accept]
    if bad:
        for i in bad:
            print(f"  ✗ '{names[i]}' 계열을 못 찾았습니다 (최고 일치도 {best[i]['score'] if best[i] else 0}).")
        print("  단위·주기가 다르거나 이 표가 아닐 수 있습니다.")
        return 1
    if len({b["prdSe"] for b in best}) != 1 or len({b["offset"] for b in best}) != 1:
        print("  ✗ 계열마다 주기나 시점 정렬이 다릅니다 — 자동 갱신을 걸면 어긋납니다.")
        for i, b in enumerate(best):
            print(f"     {names[i]}: 주기 {b['prdSe']} 시작 오프셋 {b['offset']}")
        return 1

    b0 = best[0]
    d = b0["offset"]
    per = [b0["periods"][i + d] for i in range(len(targets[0])) if 0 <= i + d < len(b0["periods"])]
    spec = {"label": it["title"], "category": it["category"], "provider": "kosis",
            "orgId": org, "tblId": tbl, "prdSe": b0["prdSe"],
            "startPrdDe": b0["start"],
            "endPrdDe": _far(b0["prdSe"], p1),
            "sourceUrl": f"https://kosis.kr/statHtml/statHtml.do?orgId={org}&tblId={tbl}",
            "_matchScore": min(b["score"] for b in best), "_chartFreq": freq,
            "_periodRange": [per[0], per[-1]] if per else None,
            "_recoveredPeriods": per if freq != "Y" else None, "_registeredBy": "register_auto"}
    subs = []
    for i, b in enumerate(best):
        itm, c1, c2, c3 = b["gk"]
        sub = {"name": names[i], "itmId": itm + "+", "scale": b["scale"]}
        for j, cc in enumerate([c1, c2, c3]):
            if cc is not None and j < len(keys):
                sub[f"objL{j+1}"] = cc + "+"
        subs.append(sub)
        cls = " / ".join(f"{keys[j]}={names_ax.get(keys[j], {}).get(c, c)}" for j, c in enumerate([c1, c2, c3])
                         if c is not None and j < len(keys))
        scs = "" if b["scale"] == 1 else f" ×{b['scale']:g}"
        print(f"  ✓ '{names[i]}' 일치도 {b['score']:.2f}  항목 {names_meta.get(itm, itm)}  {cls}  [{b['prdSe']}{scs}]")
    if len(subs) == 1:
        spec.update({k: v for k, v in subs[0].items() if k != "name"})
    else:
        spec["series"] = subs
    print(f"  {per[0] if per else '?'}~{per[-1] if per else '?'}")
    if min(b["score"] for b in best) < 1.0:
        print("  · 일치도 1.00 이 아니면 몇 점이 어긋난 것입니다. 원자료 수정치일 수도, 다른 계열일 수도 있으니 확인하세요.")
    if not a.apply:
        print("\n(미리보기입니다. 등록하려면 --apply)")
        return 0
    cp = os.path.join(DATA, "api_map_auto.json")
    conf = json.load(open(cp, encoding="utf-8")) if os.path.exists(cp) else {}
    conf[it["slide"]] = spec
    json.dump(conf, open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(mf._cache, open(mf.CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\n→ data/api_map_auto.json 에 등록. 이제 refresh_charts.py 와 매일 빌드가 이 차트를 잇습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
