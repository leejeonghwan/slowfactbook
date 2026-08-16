#!/usr/bin/env python3
"""
차트 ↔ 정부 통계표 매칭기 (부분수열 대조 방식)

  1) 차트 제목 → KOSIS 통계표 검색 API로 후보 통계표
  2) 후보의 항목·분류 조합을 훑으며 시계열을 받는다 (연/분기/월 모두 시도)
  3) 차트의 값 시퀀스가 API 시퀀스의 '연속 부분수열'인지 대조한다
     - 시작 시점을 몰라도 맞출 수 있다 (라벨이 연도만 있어도 됨)
     - 단위 배수(천/만/억/조 환산)를 자동 탐지한다
  4) 맞으면 각 데이터 점의 실제 시점(YYYY / YYYYMM / YYYYQn)을 복원한다

3번이 핵심이다. 값이 안 맞으면 매핑이 틀린 것이므로 자동 채택하지 않는다.
그리고 4번 덕분에 "월간 데이터인데 연도만 찍힌" 차트의 x축을 원본대로 되살릴 수 있다.

출력:
  data/api_map_auto.json   확정 매핑 (+ 복원된 시점 라벨, 단위 배수)
  data/_match_review.json  검수 필요 목록

사용:
  KOSIS_API_KEY=... python3 scripts/match_kosis.py --limit 60 --offset 0
"""
import os, sys, json, time, re, math, collections, urllib.parse, urllib.request, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
KEY = os.environ.get("KOSIS_API_KEY", "")
CACHE = os.path.join(ROOT, ".cache", "kosis.json")
os.makedirs(os.path.dirname(CACHE), exist_ok=True)
_cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
_dirty = 0

# 사용자가 한국식 단위로 바꿔 쓴 경우를 흡수한다 (천/백만/10억 → 만/억/조 등)
SCALES = [1, 1e-1, 1e1, 1e-2, 1e2, 1e-3, 1e3, 1e-4, 1e4, 1e-6, 1e6, 1e-8, 1e8, 1e-9, 1e9, 1e-12, 1e12]


def api(url, ck, tries=3):
    global _dirty
    if ck in _cache:
        return _cache[ck]
    last = None
    for t in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
            if not isinstance(d, list):
                raise RuntimeError(str(d)[:110])   # 과부하/한도 응답은 캐시하지 않는다
            _cache[ck] = d
            _dirty += 1
            if _dirty % 40 == 0:
                save_cache()
            return d
        except Exception as e:
            last = e
            time.sleep(1 + t * 2)
    raise RuntimeError(str(last)[:110])


def save_cache():
    json.dump(_cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)


def search(term):
    u = ("https://kosis.kr/openapi/statisticsSearch.do?method=getList"
         f"&apiKey={urllib.parse.quote(KEY)}&format=json&jsonVD=Y"
         f"&searchNm={urllib.parse.quote(term)}")
    d = api(u, "S|" + term)
    return d if isinstance(d, list) else []


def meta(org, tbl):
    u = ("https://kosis.kr/openapi/statisticsData.do?method=getMeta"
         f"&apiKey={urllib.parse.quote(KEY)}&format=json&jsonVD=Y"
         f"&orgId={org}&tblId={tbl}&type=ITM")
    d = api(u, f"M|{org}|{tbl}")
    return d if isinstance(d, list) else []


def fetch(org, tbl, itm, objs, p0, p1, prdSe):
    q = {"method": "getList", "apiKey": KEY, "format": "json", "jsonVD": "Y",
         "orgId": org, "tblId": tbl, "itmId": itm, "prdSe": prdSe,
         "startPrdDe": str(p0), "endPrdDe": str(p1)}
    for i, o in enumerate(objs, 1):
        q[f"objL{i}"] = o
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + "&".join(f"{k}={urllib.parse.quote(str(v), safe='+')}" for k, v in q.items()))
    d = api(u, "D|" + json.dumps(q, sort_keys=True, ensure_ascii=False).replace(KEY, ""))
    if not isinstance(d, list):
        return []
    out = []
    for r in d:
        try:
            out.append((r["PRD_DE"], float(r["DT"])))
        except (TypeError, ValueError, KeyError):
            continue
    seen, ser = set(), []
    for p, v in sorted(out):
        if p not in seen:
            seen.add(p)
            ser.append((p, v))
    return ser


# ── 차트 쪽 ────────────────────────────────────────────────
def chart_years(item):
    out = []
    for l in item["labels"]:
        m = re.search(r"((?:19|20)\d{2})", str(l))
        if m:
            out.append(m.group(1))
        else:
            m2 = re.fullmatch(r"[’']?(\d{2})\s*년?", str(l).strip())
            if m2:
                v = int(m2.group(1))
                out.append(str(2000 + v if v < 50 else 1900 + v))
            else:
                out.append(None)
    return out


def infer_freq(years):
    ys = [y for y in years if y]
    if len(ys) < len(years) * 0.6:
        return None
    c = collections.Counter(ys)
    mode = collections.Counter(c.values()).most_common(1)[0][0]
    return {1: "Y", 2: "H", 4: "Q", 12: "M"}.get(mode)


def norm_title(t):
    t = re.sub(r"\s*—.*$", "", t)
    t = re.sub(r"[.·,()\[\]]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def subseq_match(chart_vals, api_vals, tol=0.02):
    """차트 시퀀스와 API 시퀀스를 정렬한다. 어느 쪽이 더 길어도 된다.

    1단계: 연속 두 점의 '비율'로 정렬 위치를 찾는다 (단위 배수에 영향받지 않음)
    2단계: 정렬된 구간에서 값 비를 중앙값으로 잡아 단위 배수를 복원하고 일치율을 잰다
    반환: (일치율, 차트 0번이 API의 몇 번째에 놓이는지, 단위 배수)
    """
    n, m = len(chart_vals), len(api_vals)
    if n < 4 or m < 4:
        return 0.0, None, None

    def ratios(v):
        out = []
        for i in range(len(v) - 1):
            a, b = v[i], v[i + 1]
            out.append(None if (a is None or b is None or a == 0) else b / a)
        return out

    cr, ar = ratios(chart_vals), ratios(api_vals)
    best_d, best_hits, best_tot = None, 0, 0
    for d in range(-(n - 2), m - 1):          # 차트 i ↔ API i+d
        hits = tot = 0
        for i, x in enumerate(cr):
            j = i + d
            if j < 0 or j >= len(ar) or x is None or ar[j] is None:
                continue
            tot += 1
            if abs(x - ar[j]) <= max(0.004, abs(ar[j]) * 0.004):
                hits += 1
        if tot >= max(3, min(n, m) * 0.4) and hits > best_hits:
            best_d, best_hits, best_tot = d, hits, tot
    if best_d is None or best_tot == 0 or best_hits / best_tot < 0.7:
        return 0.0, None, None

    # 단위 배수 복원
    rr = []
    for i, cv in enumerate(chart_vals):
        j = i + best_d
        if j < 0 or j >= m or cv in (None, 0) or api_vals[j] in (None, 0):
            continue
        rr.append(api_vals[j] / cv)
    if not rr:
        return 0.0, None, None
    rr.sort()
    med = rr[len(rr) // 2]
    scale = min(SCALES, key=lambda s: abs(math.log10(abs(med * s)) if med * s else 9))
    scale = 1 / med if not any(abs(med - 1 / s) / (1 / s) < 0.02 for s in SCALES) else \
        min(SCALES, key=lambda s: abs(med - 1 / s))

    hits = tot = 0
    for i, cv in enumerate(chart_vals):
        j = i + best_d
        if j < 0 or j >= m or cv is None:
            continue
        tot += 1
        a, v = api_vals[j], cv / scale if scale else cv
        if a == 0:
            hits += 1 if abs(v) < 1e-9 else 0
        elif abs(v - a) / abs(a) <= tol:
            hits += 1
    return (hits / tot if tot else 0.0), best_d, scale


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--cands", type=int, default=2)
    ap.add_argument("--combos", type=int, default=14)
    ap.add_argument("--accept", type=float, default=0.9)
    a = ap.parse_args()

    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import generate_site as g
    items = g.load_items(DATA)

    targets = []
    for it in items:
        ys = chart_years(it)
        f = infer_freq(ys)
        if not f or len(it["labels"]) < 5 or len(it["title"]) < 3:
            continue
        targets.append((it, ys, f))
    print(f"대상 시계열 {len(targets)}건 · 이번 실행 {a.offset}~{a.offset + a.limit}")

    conf_path = os.path.join(DATA, "api_map_auto.json")
    confirmed = json.load(open(conf_path, encoding="utf-8")) if os.path.exists(conf_path) else {}
    rev_path = os.path.join(DATA, "_match_review.json")
    review = json.load(open(rev_path, encoding="utf-8")) if os.path.exists(rev_path) else []

    tried_n = 0
    for it, ys, freq in targets[a.offset:a.offset + a.limit]:
        tried_n += 1
        yy = [y for y in ys if y]
        p0, p1 = min(yy), str(int(max(yy)) + 1)
        prds = {"Y": ["Y"], "Q": ["Q", "Y"], "M": ["M", "Q"], "H": ["H", "Y"]}[freq]
        pr = {"Y": (p0, p1), "Q": (p0 + "01", p1 + "04"), "M": (p0 + "01", p1 + "12"),
              "H": (p0 + "01", p1 + "02")}
        vals = it["series"][0]
        best = None
        try:
            cands = [c for c in search(norm_title(it["title"]))[:a.cands + 2]
                     if c.get("TBL_ID") and not c["TBL_ID"].startswith("INH_")][:a.cands]
        except Exception as e:
            review.append({"slide": it["slide"], "title": it["title"], "why": f"검색 실패: {e}"})
            continue
        if not cands:
            review.append({"slide": it["slide"], "title": it["title"], "freq": freq, "why": "검색 결과 없음"})
            print(f"  · ---- [{it['category'][:6]}] {it['title'][:30]}  검색 결과 없음")
            continue
        for c in cands:
            org, tbl = c["ORG_ID"], c["TBL_ID"]
            try:
                mi = meta(org, tbl)
            except Exception:
                continue
            itms = [r for r in mi if r.get("OBJ_ID") == "ITEM"]
            objs = collections.OrderedDict()
            for r in mi:
                if r.get("OBJ_ID") != "ITEM":
                    objs.setdefault(r["OBJ_ID"], []).append(r["ITM_ID"])
            if not itms:
                continue
            keys = list(objs)
            budget = a.combos
            for im in itms[:5]:
                first = objs[keys[0]][:budget] if keys else [None]
                for code in first:
                    if budget <= 0:
                        break
                    budget -= 1
                    ol = [(code if k == keys[0] else objs[k][0]) + "+" for k in keys]
                    for ps in prds:
                        lo, hi = pr[ps] if ps == freq else (p0, p1)
                        try:
                            ser = fetch(org, tbl, im["ITM_ID"] + "+", ol, lo, hi, ps)
                        except Exception:
                            continue
                        if len(ser) < 4:
                            continue
                        r, off, sc = subseq_match(vals, [v for _, v in ser])
                        if r > 0 and (best is None or r > best["score"]):
                            best = {"score": round(r, 3), "orgId": org, "tblId": tbl,
                                    "tblNm": c.get("TBL_NM"), "itmId": im["ITM_ID"] + "+",
                                    "itmNm": im["ITM_NM"], "objL": ol, "prdSe": ps,
                                    "offset": off, "scale": sc,
                                    "periods": [p for p, _ in ser], "start": lo, "end": hi}
                        if best and best["score"] >= 0.99:
                            break
                    if best and best["score"] >= 0.99:
                        break
                if best and best["score"] >= 0.99:
                    break
            if best and best["score"] >= 0.99:
                break

        if best and best["score"] >= a.accept:
            d = best["offset"]
            per = [best["periods"][i + d] if 0 <= i + d < len(best["periods"]) else None
                   for i in range(len(vals))]
            per = [p for p in per if p]
            confirmed[it["slide"]] = {
                "label": it["title"], "category": it["category"], "provider": "kosis",
                "orgId": best["orgId"], "tblId": best["tblId"], "itmId": best["itmId"],
                **{f"objL{i+1}": o for i, o in enumerate(best["objL"])},
                "prdSe": best["prdSe"], "startPrdDe": best["start"], "endPrdDe": best["end"],
                "scale": best["scale"],
                "sourceUrl": f"https://kosis.kr/statHtml/statHtml.do?orgId={best['orgId']}&tblId={best['tblId']}",
                "_matchScore": best["score"], "_tblNm": best["tblNm"], "_itmNm": best["itmNm"],
                "_chartFreq": freq,
                "_recoveredPeriods": [per[0], per[-1]] if per else None,
            }
            sc = best["scale"]
            scs = "" if sc == 1 else f" ×{sc:g}"
            print(f"  ✓ {best['score']:.2f} [{it['category'][:6]}] {it['title'][:28]:30s} "
                  f"→ {best['tblId']} {str(best['tblNm'])[:24]} [{best['prdSe']}{scs}] "
                  f"{per[0] if per else '?'}~{per[-1] if per else '?'}")
        else:
            review.append({"slide": it["slide"], "title": it["title"], "category": it["category"],
                           "freq": freq, "best_score": best["score"] if best else 0,
                           "best_tbl": best["tblId"] if best else None,
                           "best_tblNm": best["tblNm"] if best else None,
                           "cands": [{"tblId": c["TBL_ID"], "tblNm": c.get("TBL_NM")} for c in cands]})
            print(f"  · {(best['score'] if best else 0):.2f} [{it['category'][:6]}] {it['title'][:28]:30s} "
                  f"→ {(best or {}).get('tblId', '후보 미검증')}")

    json.dump(confirmed, open(conf_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(review, open(rev_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    save_cache()
    print(f"\n이번 실행 {tried_n}건 · 누적 확정 {len(confirmed)}건 · 검수 필요 {len(review)}건")


if __name__ == "__main__":
    main()
