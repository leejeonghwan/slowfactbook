#!/usr/bin/env python3
"""
차트 ↔ KOSIS 통계표 매칭기 (일괄 조회판)

match_kosis.py 와 논리는 같지만, 분류 코드를 하나씩 조회하지 않고
objL1 에 코드를 한꺼번에 넣어 **한 번의 요청으로 수십 개 계열을 받아**
클라이언트에서 계열별로 쪼개 대조한다. 요청 수가 1/40 로 준다.

정렬은 '연속 두 점의 비율'로 잡는다 → 단위 배수(천/만/억/조)와
시작 시점을 몰라도 맞춰지고, 맞으면 각 점의 실제 시점을 복원한다.

  KOSIS_API_KEY=... python3 scripts/match_fast.py --limit 400 --offset 0
"""
import os, sys, json, time, re, collections, urllib.parse, urllib.request, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
KEY = os.environ.get("KOSIS_API_KEY", "")
CACHE = os.path.join(ROOT, ".cache", "kosis.json")
os.makedirs(os.path.dirname(CACHE), exist_ok=True)



def _load_cache():
    """다른 프로세스가 쓰는 중이면 깨진 JSON을 읽을 수 있다. 그때는 빈 캐시로 시작한다.
    (NOCACHE=1 이면 아예 읽지 않는다 — align 만 쓰려고 import 하는 쪽을 위해)"""
    if os.environ.get("MATCH_FAST_NOCACHE") == "1" or not os.path.exists(CACHE):
        return {}
    try:
        return json.load(open(CACHE, encoding="utf-8"))
    except Exception as e:
        print(f"!! 캐시를 읽지 못해 빈 캐시로 시작합니다 ({str(e)[:60]})", file=sys.stderr)
        return {}


_cache = _load_cache()
_n = 0

SCALES = [1, 1e-1, 1e1, 1e-2, 1e2, 1e-3, 1e3, 1e-4, 1e4, 1e-6, 1e6, 1e-8, 1e8, 1e-9, 1e9, 1e-12, 1e12]


def api(url, ck, tries=2):
    global _n
    if ck in _cache:
        return _cache[ck]
    last = None
    for t in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=25) as r:
                d = json.loads(r.read().decode("utf-8"))
            if not isinstance(d, list):
                if str(d.get("err")) == "30":
                    return []
                raise RuntimeError(str(d)[:100])
            _cache[ck] = d
            _n += 1
            if _n % 30 == 0:
                json.dump(_cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
            return d
        except Exception as e:
            last = e
            time.sleep(0.5 + t)
    raise RuntimeError(str(last)[:100])


def search(term):
    u = ("https://kosis.kr/openapi/statisticsSearch.do?method=getList"
         f"&apiKey={urllib.parse.quote(KEY)}&format=json&jsonVD=Y&searchNm={urllib.parse.quote(term)}")
    return api(u, "S|" + term)


def meta(org, tbl):
    u = ("https://kosis.kr/openapi/statisticsData.do?method=getMeta"
         f"&apiKey={urllib.parse.quote(KEY)}&format=json&jsonVD=Y"
         f"&orgId={org}&tblId={tbl}&type=ITM")
    return api(u, f"M|{org}|{tbl}")


def fetch_bulk(org, tbl, itms, objs, p0, p1, prdSe):
    """itms·objL1 을 한꺼번에 넣어 여러 계열을 한 번에 받는다."""
    q = {"method": "getList", "apiKey": KEY, "format": "json", "jsonVD": "Y",
         "orgId": org, "tblId": tbl, "itmId": "+".join(itms) + "+", "prdSe": prdSe,
         "startPrdDe": str(p0), "endPrdDe": str(p1)}
    for i, o in enumerate(objs, 1):
        q[f"objL{i}"] = o
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + "&".join(f"{k}={urllib.parse.quote(str(v), safe='+')}" for k, v in q.items()))
    rows = api(u, "B|" + json.dumps(q, sort_keys=True, ensure_ascii=False).replace(KEY, ""))
    ser = collections.defaultdict(dict)
    for r in rows:
        try:
            v = float(r["DT"])
        except (TypeError, ValueError, KeyError):
            continue
        key = (r.get("ITM_ID"), r.get("C1"), r.get("C2"), r.get("C3"))
        ser[key][r["PRD_DE"]] = v
    out = {}
    for k, d in ser.items():
        if len(d) >= 4:
            out[k] = sorted(d.items())
    return out


def chart_years(item):
    out = []
    for l in item["labels"]:
        m = re.search(r"((?:19|20)\d{2})", str(l))
        if m:
            out.append(m.group(1))
        else:
            m2 = re.fullmatch(r"[’']?(\d{2})\s*년?", str(l).strip())
            out.append(str(2000 + int(m2.group(1)) if int(m2.group(1)) < 50 else 1900 + int(m2.group(1))) if m2 else None)
    return out


def infer_freq(years):
    ys = [y for y in years if y]
    if len(ys) < len(years) * 0.6:
        return None
    c = collections.Counter(ys)
    return {1: "Y", 2: "H", 4: "Q", 12: "M"}.get(collections.Counter(c.values()).most_common(1)[0][0])


def norm_title(t):
    t = re.sub(r"\s*—.*$", "", t)
    t = re.sub(r"[.·,()\[\]]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# 기사용 제목을 통계용 검색어로 바꾼다.
# KOSIS 전문검색은 짧은 통계 용어에 강하고 긴 서술형 제목에는 아무것도 못 돌려준다.
#   '월별 취업자 수 증감'          → 취업자 수 / 취업자
#   '최저임금 인상율과 소비자 물가 상승율' → 최저임금 / 소비자 물가 상승율 / 소비자 물가
_MODIFIER = re.compile(
    r"(월별|연도별|년도별|분기별|지역별|시도별|국가별|성별|연령별|학력별|업종별|규모별|유형별|"
    r"추이|변화|비교|현황|전망|증감|추계|누적|기준|현재|전체|국내|우리나라|한국의|"
    r"상위\s*\d+|하위\s*\d+|\d+대\s*기업)")
_TAILNOISE = re.compile(r"\s*\(\s*\d+\s*\)\s*$|\s*\d+\s*$")
_SPLIT = re.compile(r"\s*(?:과|와|및|vs\.?|대비|그리고|,|/)\s+")


def query_terms(title, maxn=4):
    """제목 하나에서 검색어 후보를 짧은 것 위주로 몇 개 뽑는다."""
    base = _TAILNOISE.sub("", norm_title(title)).strip()
    out, seen = [], set()

    def push(s):
        s = re.sub(r"\s+", " ", s).strip(" -–—의")
        if 1 < len(s) <= 20 and s not in seen:
            seen.add(s)
            out.append(s)

    # 1) 접속사로 쪼갠 조각 (‘최저임금과 물가’ → 둘 다 따로 찾는다)
    parts = [p for p in _SPLIT.split(base) if p.strip()]
    for p in parts if len(parts) > 1 else []:
        push(_MODIFIER.sub(" ", p))
    # 2) 수식어를 걷어낸 통짜
    push(_MODIFIER.sub(" ", base))
    # 3) 그래도 길면 뒤쪽 2~3 어절 (통계 용어는 대개 끝에 온다)
    w = _MODIFIER.sub(" ", base).split()
    for k in (3, 2, 1):
        if len(w) > k:
            push(" ".join(w[-k:]))
    push(base)
    return out[:maxn]


def search_multi(title, want=6):
    """검색어를 여러 개 시도해 후보 통계표를 모은다. 짧은 질의부터 순서대로."""
    got, seen = [], set()
    for term in query_terms(title):
        for c in search(term) or []:
            tid = c.get("TBL_ID")
            if not tid or tid.startswith("INH_") or tid in seen:
                continue
            seen.add(tid)
            got.append(c)
        if len(got) >= want:
            break
    return got[:want]


def align(cv, av, tol=0.02):
    n, m = len(cv), len(av)
    if n < 4 or m < 4:
        return 0.0, None, None
    def R(v):
        return [None if (v[i] is None or v[i + 1] is None or v[i] == 0) else v[i + 1] / v[i]
                for i in range(len(v) - 1)]
    cr, ar = R(cv), R(av)
    bd, bh, bt = None, 0, 0
    for d in range(-(n - 2), m - 1):
        h = t = 0
        for i, x in enumerate(cr):
            j = i + d
            if j < 0 or j >= len(ar) or x is None or ar[j] is None:
                continue
            t += 1
            if abs(x - ar[j]) <= max(0.004, abs(ar[j]) * 0.004):
                h += 1
        if t >= max(3, min(n, m) * 0.4) and h > bh:
            bd, bh, bt = d, h, t
    if bd is None or not bt or bh / bt < 0.7:
        return 0.0, None, None
    rr = sorted(av[i + bd] / c for i, c in enumerate(cv)
                if c not in (None, 0) and 0 <= i + bd < m and av[i + bd] not in (None, 0))
    if not rr:
        return 0.0, None, None
    med = rr[len(rr) // 2]
    sc = min(SCALES, key=lambda s: abs(med - 1 / s))
    # 단위 배수는 10의 거듭제곱이어야 한다. 어중간한 배수면 다른 계열을 잘못 잡은 것.
    if abs(med - 1 / sc) / abs(1 / sc) > 0.03:
        return 0.0, None, None
    h = t = 0
    for i, c in enumerate(cv):
        j = i + bd
        if j < 0 or j >= m or c is None:
            continue
        t += 1
        a, v = av[j], c / sc
        if a == 0:
            h += 1 if abs(v) < 1e-9 else 0
        elif abs(v - a) / abs(a) <= tol:
            h += 1
    if t < max(5, min(n, m) * 0.5):
        return 0.0, None, None
    return (h / t if t else 0.0), bd, sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--cands", type=int, default=3)
    ap.add_argument("--redo", action="store_true", help="후보를 못 찾았던 차트를 다시 시도")
    ap.add_argument("--codes", type=int, default=45)
    ap.add_argument("--accept", type=float, default=0.9)
    a = ap.parse_args()

    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import generate_site as g
    items = g.load_items(DATA)
    targets = []
    for it in items:
        ys = chart_years(it)
        f = infer_freq(ys)
        if f and len(it["labels"]) >= 5 and len(it["title"]) >= 3:
            targets.append((it, ys, f))
    print(f"대상 {len(targets)}건 · 실행 {a.offset}~{a.offset + a.limit}", flush=True)

    cp = os.path.join(DATA, "api_map_auto.json")
    rp = os.path.join(DATA, "_match_review.json")
    conf = json.load(open(cp, encoding="utf-8")) if os.path.exists(cp) else {}
    rev = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else []
    if a.redo:
        # 검색어 생성기가 바뀌었으니 후보를 못 찾았던 것만 다시 돌린다
        rev = [r for r in rev if r.get("why") not in ("검색 결과 없음",) and r.get("best_score")]
    done = set(conf) | {r["slide"] for r in rev}

    for it, ys, freq in targets[a.offset:a.offset + a.limit]:
        if it["slide"] in done:
            continue
        yy = [y for y in ys if y]
        p0, p1 = min(yy), str(int(max(yy)) + 1)
        span = {"Y": (p0, p1), "Q": (p0 + "01", p1 + "04"),
                "M": (p0 + "01", p1 + "12"), "H": (p0 + "01", p1 + "02")}
        prds = {"Y": ["Y"], "Q": ["Q"], "M": ["M", "Q"], "H": ["H", "Y"]}[freq]
        vals = it["series"][0]
        best = None
        try:
            cands = search_multi(it["title"], want=max(6, a.cands))[:a.cands]
        except Exception as e:
            rev.append({"slide": it["slide"], "title": it["title"], "category": it["category"],
                        "freq": freq, "why": f"검색 실패: {str(e)[:60]}"})
            continue
        if not cands:
            rev.append({"slide": it["slide"], "title": it["title"], "category": it["category"],
                        "freq": freq, "why": "검색 결과 없음"})
            print(f"  · ---- [{it['category'][:6]}] {it['title'][:30]}", flush=True)
            continue
        for c in cands:
            org, tbl = c["ORG_ID"], c["TBL_ID"]
            try:
                mi = meta(org, tbl)
            except Exception:
                continue
            itms = [r["ITM_ID"] for r in mi if r.get("OBJ_ID") == "ITEM"][:8]
            objs = collections.OrderedDict()
            for r in mi:
                if r.get("OBJ_ID") != "ITEM":
                    objs.setdefault(r["OBJ_ID"], []).append(r["ITM_ID"])
            if not itms:
                continue
            keys = list(objs)
            ol = []
            for i, k in enumerate(keys):
                ol.append("+".join(objs[k][:a.codes] if i == 0 else objs[k][:1]) + "+")
            for ps in prds:
                lo, hi = span[ps] if ps == freq else (p0, p1)
                try:
                    groups = fetch_bulk(org, tbl, itms, ol, lo, hi, ps)
                except Exception:
                    continue
                for gk, ser in groups.items():
                    r, off, sc = align(vals, [v for _, v in ser])
                    if r > 0 and (best is None or r > best["score"]):
                        best = {"score": round(r, 3), "orgId": org, "tblId": tbl,
                                "tblNm": c.get("TBL_NM"), "statNm": c.get("STAT_NM"),
                                "gk": gk, "prdSe": ps, "offset": off, "scale": sc,
                                "periods": [p for p, _ in ser], "start": lo, "end": hi,
                                "objs": keys}
                if best and best["score"] >= 0.99:
                    break
            if best and best["score"] >= 0.99:
                break

        if best and best["score"] >= a.accept:
            d = best["offset"]
            per = [best["periods"][i + d] for i in range(len(vals))
                   if 0 <= i + d < len(best["periods"])]
            itm, c1, c2, c3 = best["gk"]
            spec = {"label": it["title"], "category": it["category"], "provider": "kosis",
                    "orgId": best["orgId"], "tblId": best["tblId"], "itmId": itm + "+",
                    "prdSe": best["prdSe"], "startPrdDe": best["start"], "endPrdDe": best["end"],
                    "scale": best["scale"],
                    "sourceUrl": f"https://kosis.kr/statHtml/statHtml.do?orgId={best['orgId']}&tblId={best['tblId']}",
                    "_matchScore": best["score"], "_tblNm": best["tblNm"], "_statNm": best["statNm"],
                    "_chartFreq": freq, "_periodRange": [per[0], per[-1]] if per else None,
                    "_recoveredPeriods": per if freq != "Y" else None}
            for i, cc in enumerate([c1, c2, c3]):
                if cc is not None and i < len(best["objs"]):
                    spec[f"objL{i+1}"] = cc + "+"
            conf[it["slide"]] = spec
            scs = "" if best["scale"] == 1 else f" ×{best['scale']:g}"
            print(f"  ✓ {best['score']:.2f} [{it['category'][:6]}] {it['title'][:26]:28s} → "
                  f"{best['tblId']} {str(best['statNm'])[:18]} [{best['prdSe']}{scs}] "
                  f"{per[0] if per else '?'}~{per[-1] if per else '?'}", flush=True)
        else:
            rev.append({"slide": it["slide"], "title": it["title"], "category": it["category"],
                        "freq": freq, "n": len(vals),
                        "source": it["source"], "best_score": best["score"] if best else 0,
                        "best_tbl": best["tblId"] if best else None,
                        "best_tblNm": best["tblNm"] if best else None,
                        "cands": [{"tblId": c["TBL_ID"], "tblNm": c.get("TBL_NM"),
                                   "statNm": c.get("STAT_NM")} for c in cands]})
            print(f"  · {(best['score'] if best else 0):.2f} [{it['category'][:6]}] "
                  f"{it['title'][:26]:28s} → {(best or {}).get('tblId', '미검증')}", flush=True)

        json.dump(conf, open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(rev, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(_cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\n확정 {len(conf)}건 · 검수 {len(rev)}건", flush=True)


if __name__ == "__main__":
    main()
