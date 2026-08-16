#!/usr/bin/env python3
"""
비시계열 차트(지역별·연령별·국가별) ↔ KOSIS 통계표 매칭기.

시계열 매칭기(match_fast.py)와 방향이 반대다.

  시계열 차트  : 값의 '시간 순서'를 맞춘다        → 어느 통계표인지 알아낸다
  비시계열 차트: 라벨(서울·부산·…)을 '분류 코드'와 맞추고
                 값이 일치하는 '연도'를 찾아낸다   → 통계표 + 기준 시점을 알아낸다

이게 중요한 이유: 「지역별 합계출산율」은 시계열이 아닌 게 아니라
시도별 합계출산율 표에서 한 해를 잘라낸 것이다. 매칭이 되면
  · 기준 연도가 확정되고
  · 더 최신 연도가 나왔는지 바로 알 수 있고
  · 갱신하면 차트 전체가 최신 연도 기준으로 바뀐다 (점 하나 추가가 아니라)

출력:
  data/cross_map.json      확정 매핑 (+ 기준 시점, 최신 시점, 단위 배수)
  data/_cross_review.json  검수 필요 목록

  KOSIS_API_KEY=... python3 scripts/match_cross.py --limit 200
"""
import os, sys, json, time, re, collections, urllib.parse, urllib.request, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
KEY = os.environ.get("KOSIS_API_KEY", "")
CACHE = os.path.join(ROOT, ".cache", "kosis_cross.json")
os.makedirs(os.path.dirname(CACHE), exist_ok=True)
_cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
_n = 0

SCALES = [1, 1e-1, 1e1, 1e-2, 1e2, 1e-3, 1e3, 1e-4, 1e4, 1e-6, 1e6, 1e-8, 1e8, 1e-9, 1e9]


def api(url, ck, tries=2):
    global _n
    if ck in _cache:
        return _cache[ck]
    last = None
    for t in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=45) as r:
                d = json.loads(r.read().decode("utf-8"))
            if not isinstance(d, list):
                if str(d.get("err")) == "30":
                    return []
                raise RuntimeError(str(d)[:90])
            _cache[ck] = d
            _n += 1
            if _n % 25 == 0:
                json.dump(_cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
            return d
        except Exception as e:
            last = e
            time.sleep(0.5 + t)
    raise RuntimeError(str(last)[:90])


def search(term):
    u = ("https://kosis.kr/openapi/statisticsSearch.do?method=getList"
         f"&apiKey={urllib.parse.quote(KEY)}&format=json&jsonVD=Y&searchNm={urllib.parse.quote(term)}")
    return api(u, "S|" + term)


def meta(org, tbl):
    u = ("https://kosis.kr/openapi/statisticsData.do?method=getMeta"
         f"&apiKey={urllib.parse.quote(KEY)}&format=json&jsonVD=Y"
         f"&orgId={org}&tblId={tbl}&type=ITM")
    return api(u, f"M|{org}|{tbl}")


def fetch(org, tbl, itm, objs, p0, p1, prdSe):
    """여러 분류 코드 × 여러 시점을 한 번에 받아 {시점: {코드: 값}} 으로 돌려준다."""
    q = {"method": "getList", "apiKey": KEY, "format": "json", "jsonVD": "Y",
         "orgId": org, "tblId": tbl, "itmId": itm, "prdSe": prdSe,
         "startPrdDe": str(p0), "endPrdDe": str(p1)}
    for i, o in enumerate(objs, 1):
        q[f"objL{i}"] = o
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + "&".join(f"{k}={urllib.parse.quote(str(v), safe='+')}" for k, v in q.items()))
    rows = api(u, "X|" + json.dumps(q, sort_keys=True, ensure_ascii=False).replace(KEY, ""))
    out = collections.defaultdict(dict)
    for r in rows:
        try:
            out[r["PRD_DE"]][r.get("C1")] = float(r["DT"])
        except (TypeError, ValueError, KeyError):
            continue
    return out


# ── 라벨 정규화 ────────────────────────────────────────────
SUFFIX = re.compile(r"(특별자치시|특별자치도|특별시|광역시|자치시|자치도|시$|도$)")
ALIAS = {"충북": "충청북", "충남": "충청남", "전북": "전라북", "전남": "전라남",
         "경북": "경상북", "경남": "경상남", "제주": "제주", "강원": "강원",
         "서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천",
         "광주": "광주", "대전": "대전", "울산": "울산", "세종": "세종",
         "경기": "경기", "전국": "전국", "계": "전국"}


def norm(s):
    s = str(s).strip()
    s = re.sub(r"[\s.·,()]+", "", s)
    s = SUFFIX.sub("", s)
    return ALIAS.get(s, s)


REGION = set(ALIAS)
AGE = re.compile(r"^\d+[~\-–]\d+세?$|^\d+세(이상|미만)?$|^\d+대$")


def label_kind(labels):
    ls = [norm(l) for l in labels]
    if sum(1 for l in ls if l in REGION) >= max(3, len(ls) * 0.6):
        return "지역별"
    if sum(1 for l in ls if AGE.match(re.sub(r"\s", "", str(l)))) >= max(3, len(ls) * 0.6):
        return "연령별"
    if sum(1 for l in labels if re.fullmatch(r"[A-Za-z .\-']{3,}", str(l).strip())) >= max(3, len(ls) * 0.6):
        return "국가별"
    return None


def norm_title(t):
    t = re.sub(r"\s*—.*$", "", t)
    t = re.sub(r"[.·,()\[\]]", " ", t)
    t = re.sub(r"(지역별|시도별|연령별|국가별|비교|현황|추이)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def align_cross(labels, vals, code2name, period_map, tol=0.02):
    """라벨 이름으로 값을 맞춰보고, 가장 잘 맞는 시점과 단위 배수를 찾는다."""
    name2code = {}
    for code, nm in code2name.items():
        name2code.setdefault(norm(nm), code)
    pairs = []                                   # (차트 인덱스, 분류 코드)
    for i, l in enumerate(labels):
        c = name2code.get(norm(l))
        if c is not None and vals[i] is not None:
            pairs.append((i, c))
    if len(pairs) < max(3, len(labels) * 0.5):
        return None

    best = None
    for prd, byc in period_map.items():
        got = [(i, c) for i, c in pairs if c in byc]
        if len(got) < max(3, len(pairs) * 0.7):
            continue
        rr = sorted(byc[c] / vals[i] for i, c in got if vals[i] not in (None, 0) and byc[c] not in (None, 0))
        if not rr:
            continue
        med = rr[len(rr) // 2]
        sc = min(SCALES, key=lambda s: abs(med - 1 / s))
        if abs(med - 1 / sc) / abs(1 / sc) > 0.03:
            continue
        hit = sum(1 for i, c in got
                  if byc[c] != 0 and abs(vals[i] / sc - byc[c]) / abs(byc[c]) <= tol)
        r = hit / len(got)
        if best is None or r > best["score"]:
            best = {"score": round(r, 3), "period": prd, "scale": sc,
                    "matched": len(got), "of": len(labels),
                    "map": {labels[i]: c for i, c in got}}
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--cands", type=int, default=3)
    ap.add_argument("--accept", type=float, default=0.9)
    ap.add_argument("--kinds", default="지역별,연령별")
    a = ap.parse_args()

    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import generate_site as g
    items = g.load_items(DATA)

    def _years(item):
        out = []
        for l in item["labels"]:
            m = re.search(r"((?:19|20)\d{2})", str(l))
            out.append(m.group(1) if m else None)
        return out

    def infer_freq(ys):
        ys = [y for y in ys if y]
        if not ys:
            return None
        return True   # 연도 라벨이 하나라도 있으면 시계열로 보고 제외

    chart_years = _years

    kinds = set(a.kinds.split(","))
    targets = []
    for it in items:
        if infer_freq(chart_years(it)):
            continue                              # 시계열은 match_fast 담당
        k = label_kind(it["labels"])
        if k in kinds and len(it["title"]) >= 3 and len(it["labels"]) >= 3:
            targets.append((it, k))
    print(f"비시계열 대상 {len(targets)}건 · 실행 {a.offset}~{a.offset + a.limit}", flush=True)

    cp = os.path.join(DATA, "cross_map.json")
    rp = os.path.join(DATA, "_cross_review.json")
    conf = json.load(open(cp, encoding="utf-8")) if os.path.exists(cp) else {}
    rev = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else []
    done = set(conf) | {r["slide"] for r in rev}

    for it, kind in targets[a.offset:a.offset + a.limit]:
        if it["slide"] in done:
            continue
        vals = it["series"][0]
        best = None
        try:
            cands = [c for c in search(norm_title(it["title"]))[:6]
                     if c.get("TBL_ID") and not c["TBL_ID"].startswith("INH_")][:a.cands]
        except Exception as e:
            rev.append({"slide": it["slide"], "title": it["title"], "category": it["category"],
                        "kind": kind, "why": f"검색 실패: {str(e)[:50]}"})
            continue
        if not cands:
            rev.append({"slide": it["slide"], "title": it["title"], "category": it["category"],
                        "kind": kind, "why": "검색 결과 없음"})
            print(f"  · ---- [{kind}] {it['title'][:28]}", flush=True)
            continue

        for c in cands:
            org, tbl = c["ORG_ID"], c["TBL_ID"]
            try:
                mi = meta(org, tbl)
            except Exception:
                continue
            itms = [r["ITM_ID"] for r in mi if r.get("OBJ_ID") == "ITEM"][:6]
            axes = collections.OrderedDict()
            for r in mi:
                if r.get("OBJ_ID") != "ITEM":
                    axes.setdefault(r["OBJ_ID"], {})[r["ITM_ID"]] = r["ITM_NM"]
            if not itms or not axes:
                continue
            # 라벨과 겹치는 분류축을 고른다
            want = {norm(l) for l in it["labels"]}
            axis = None
            for aid, code2name in axes.items():
                names = {norm(v) for v in code2name.values()}
                if len(want & names) >= max(3, len(want) * 0.5):
                    axis = (aid, code2name)
                    break
            if not axis:
                continue
            aid, code2name = axis
            keys = list(axes)
            codes = [c2 for c2, nm in code2name.items() if norm(nm) in want][:60]
            if len(codes) < 3:
                continue
            ol = []
            for k in keys:
                ol.append("+".join(codes) + "+" if k == aid else list(axes[k])[0] + "+")
            for prdSe, p0, p1 in (("Y", "1990", "2030"), ("M", "199001", "203012")):
                try:
                    pm = fetch(org, tbl, "+".join(itms) + "+", ol, p0, p1, prdSe)
                except Exception:
                    continue
                if not pm:
                    continue
                r = align_cross(it["labels"], vals, code2name, pm)
                if r and (best is None or r["score"] > best["score"]):
                    latest = max(pm)
                    best = {**r, "orgId": org, "tblId": tbl, "tblNm": c.get("TBL_NM"),
                            "statNm": c.get("STAT_NM"), "axis": aid, "codes": codes,
                            "itms": itms, "prdSe": prdSe, "latest": latest,
                            "keys": keys, "otherAxes": {k: list(axes[k])[0] for k in keys if k != aid}}
                if best and best["score"] >= 0.99:
                    break
            if best and best["score"] >= 0.99:
                break

        if best and best["score"] >= a.accept:
            newer = best["latest"] != best["period"]
            conf[it["slide"]] = {
                "label": it["title"], "category": it["category"], "kind": kind,
                "provider": "kosis", "orgId": best["orgId"], "tblId": best["tblId"],
                "axis": best["axis"], "codes": best["codes"], "itmIds": best["itms"],
                "prdSe": best["prdSe"], "otherAxes": best["otherAxes"],
                "chartPeriod": best["period"], "latestPeriod": best["latest"],
                "hasNewer": newer, "scale": best["scale"],
                "labelToCode": best["map"],
                "sourceUrl": f"https://kosis.kr/statHtml/statHtml.do?orgId={best['orgId']}&tblId={best['tblId']}",
                "_matchScore": best["score"], "_statNm": best["statNm"], "_tblNm": best["tblNm"],
            }
            mark = "●" if newer else "·"
            print(f"  ✓ {best['score']:.2f} [{kind}] {it['title'][:24]:26s} → {best['tblId']} "
                  f"{str(best['statNm'])[:16]} 기준 {best['period']} {mark} 최신 {best['latest']} "
                  f"({best['matched']}/{best['of']}개 라벨)", flush=True)
        else:
            rev.append({"slide": it["slide"], "title": it["title"], "category": it["category"],
                        "kind": kind, "best_score": best["score"] if best else 0,
                        "best_tbl": best["tblId"] if best else None,
                        "cands": [{"tblId": c["TBL_ID"], "statNm": c.get("STAT_NM")} for c in cands]})
            print(f"  · {(best['score'] if best else 0):.2f} [{kind}] {it['title'][:24]:26s} "
                  f"→ {(best or {}).get('tblId', '후보 미검증')}", flush=True)
        json.dump(conf, open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(rev, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(_cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    newer_n = sum(1 for v in conf.values() if v.get("hasNewer"))
    print(f"\n확정 {len(conf)}건 (그중 더 최신 데이터 있음 {newer_n}건) · 검수 {len(rev)}건")


if __name__ == "__main__":
    main()
