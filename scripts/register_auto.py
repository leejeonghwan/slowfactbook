#!/usr/bin/env python3
"""
차트 하나를 KOSIS 통계표 하나에 붙여 자동 갱신(refresh_charts.py) 대상으로 등록한다.

  KOSIS_API_KEY=... python3 scripts/register_auto.py slide-122 --tbl DT_118N_MON051 [--org 118]
  KOSIS_API_KEY=... python3 scripts/register_auto.py m-0001 --url "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1B81A17"

match_fast.py 가 제목 검색으로 표를 찾는 것과 달리, 여기서는 표를 사람이 찍어 준다.
그 표의 모든 항목×분류 계열을 받아 차트 값과 대조하고(match_fast.align), 맞는 계열을
data/api_map_auto.json 에 적는다. 그 다음부터는 refresh_charts.py 와 매일 빌드가 알아서 잇는다.

계열이 둘 이상인 차트는 refresh_charts 가 아직 못 잇는다(첫 계열만 등록되고, 갱신은 set_data.py 로).
"""
import os, sys, json, re, collections, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import generate_site as g       # noqa: E402
import match_fast as mf         # noqa: E402


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
    vals = it["series"][0]
    print(f"대상: {it['slide']} {it['id']} [{it['category']}] {it['title']}  주기 {freq}  {p0}~{max(yy)}  {len(vals)}점")
    if len(it["series"]) > 1:
        print(f"  ! 계열 {len(it['series'])}개 — 첫 계열('{(it.get('seriesNames') or ['?'])[0]}')만 대조·등록합니다.")

    mi = mf.meta(org, tbl)
    itms = [r["ITM_ID"] for r in mi if r.get("OBJ_ID") == "ITEM"]
    objs = collections.OrderedDict()
    for r in mi:
        if r.get("OBJ_ID") != "ITEM":
            objs.setdefault(r["OBJ_ID"], []).append(r["ITM_ID"])
    names = {r["ITM_ID"]: r.get("ITM_NM") for r in mi}
    keys = list(objs)
    print(f"  표 {tbl}: 항목 {len(itms)}개, 분류축 {len(keys)}개 " +
          " ".join(f"{k}({len(objs[k])})" for k in keys))

    best = None
    # 첫 축은 넓게, 나머지 축은 첫 코드(보통 '계'·'전국')부터. 못 찾으면 둘째 축도 넓힌다.
    plans = [[a.codes] + [1] * (len(keys) - 1)]
    if len(keys) >= 2:
        plans.append([a.codes, 30] + [1] * (len(keys) - 2))
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
                    r, off, sc = mf.align(vals, [v for _, v in ser])
                    if r > 0 and (best is None or r > best["score"]):
                        best = {"score": round(r, 3), "gk": gk, "prdSe": ps, "offset": off,
                                "scale": sc, "periods": [p for p, _ in ser], "start": lo, "end": hi}
                if best and best["score"] >= 0.99:
                    break
            if best and best["score"] >= 0.99:
                break
        if best and best["score"] >= a.accept:
            break

    if not best or best["score"] < a.accept:
        print(f"  맞는 계열을 못 찾았습니다 (최고 일치도 {best['score'] if best else 0}). "
              f"단위·주기가 다르거나 이 표가 아닐 수 있습니다.")
        return 1
    itm, c1, c2, c3 = best["gk"]
    d = best["offset"]
    per = [best["periods"][i + d] for i in range(len(vals)) if 0 <= i + d < len(best["periods"])]
    spec = {"label": it["title"], "category": it["category"], "provider": "kosis",
            "orgId": org, "tblId": tbl, "itmId": itm + "+", "prdSe": best["prdSe"],
            "startPrdDe": best["start"], "endPrdDe": str(int(p1) + 8) if best["prdSe"] == "Y" else best["end"][:4] + "9" + best["end"][5:],
            "scale": best["scale"],
            "sourceUrl": f"https://kosis.kr/statHtml/statHtml.do?orgId={org}&tblId={tbl}",
            "_matchScore": best["score"], "_itmNm": names.get(itm), "_chartFreq": freq,
            "_periodRange": [per[0], per[-1]] if per else None,
            "_recoveredPeriods": per if freq != "Y" else None, "_registeredBy": "register_auto"}
    for i, cc in enumerate([c1, c2, c3]):
        if cc is not None and i < len(keys):
            spec[f"objL{i+1}"] = cc + "+"
    cls = " / ".join(f"{keys[i]}={names.get(c, c)}" for i, c in enumerate([c1, c2, c3]) if c is not None and i < len(keys))
    scs = "" if best["scale"] == 1 else f" ×{best['scale']:g}"
    print(f"  ✓ 일치도 {best['score']:.2f}  항목 {names.get(itm, itm)}  {cls}  [{best['prdSe']}{scs}]  "
          f"{per[0] if per else '?'}~{per[-1] if per else '?'}")
    if best["score"] < 1.0:
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
