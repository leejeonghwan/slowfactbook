#!/usr/bin/env python3
"""
한국은행 ECOS OpenAPI 어댑터.

KOSIS와 다른 점 두 가지를 흡수한다.

  1) 전문 검색 API가 없다 → 통계표 목록(약 700개)을 통째로 받아 로컬에서 제목 매칭
  2) 통계표 하나 안에 항목이 계층(최대 3단)으로 들어 있다 → 말단 항목까지 펼쳐서 대조

값 대조 검증(align)은 match_fast.py 것을 그대로 쓴다. 단위 배수와 시작 시점을
모르는 채로 맞출 수 있고, 맞으면 실제 시점을 복원한다.

  ECOS_API_KEY=... python3 scripts/ecos.py --list          통계표 목록 캐시
  ECOS_API_KEY=... python3 scripts/ecos.py --match         차트 매칭
  ECOS_API_KEY=... python3 scripts/ecos.py --probe 722Y001 통계표 하나 훑어보기
"""
import os, sys, json, time, re, collections, urllib.parse, urllib.request, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE_DIR = os.path.join(ROOT, ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE = os.path.join(CACHE_DIR, "ecos.json")
KEY = os.environ.get("ECOS_API_KEY", "")
BASE = "https://ecos.bok.or.kr/api"

_cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
_n = 0

# ECOS 주기 코드 ↔ 차트에서 추정한 주기
CYCLE = {"Y": "A", "H": "S", "Q": "Q", "M": "M"}
CYCLE_BACK = {"A": "Y", "S": "H", "Q": "Q", "M": "M", "D": "D"}


def save():
    json.dump(_cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)


def call(service, *parts, rows=100000, ck=None):
    """ECOS는 경로 파라미터 방식이다. /api/{서비스}/{키}/json/kr/{시작}/{끝}/{...}"""
    global _n
    path = "/".join(urllib.parse.quote(str(p), safe="") for p in parts)
    url = f"{BASE}/{service}/{KEY}/json/kr/1/{rows}" + (f"/{path}" if path else "")
    ck = ck or f"{service}|{path}|{rows}"
    if ck in _cache:
        return _cache[ck]
    last = None
    for t in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
            if "RESULT" in d:                       # 오류 응답
                code = d["RESULT"].get("CODE", "")
                if code in ("INFO-200",):           # 해당 데이터 없음
                    _cache[ck] = []
                    return []
                raise RuntimeError(f"{code} {d['RESULT'].get('MESSAGE','')[:60]}")
            body = d.get(service, {})
            out = body.get("row", [])
            _cache[ck] = out
            _n += 1
            if _n % 25 == 0:
                save()
            return out
        except Exception as e:
            last = e
            time.sleep(0.6 + t)
    raise RuntimeError(str(last)[:110])


def table_list():
    """통계표 전체 목록. SRCH_YN=='Y' 인 것만 실제 조회 가능하다."""
    rows = call("StatisticTableList", ck="TBL|ALL")
    return [r for r in rows if r.get("SRCH_YN") == "Y"]


def item_list(stat_code):
    return call("StatisticItemList", stat_code, ck=f"ITM|{stat_code}")


def search(stat_code, cycle, start, end, *item_codes):
    parts = [stat_code, cycle, start, end] + [c for c in item_codes if c]
    rows = call("StatisticSearch", *parts)
    out = []
    for r in rows:
        try:
            out.append((str(r["TIME"]), float(r["DATA_VALUE"])))
        except (TypeError, ValueError, KeyError):
            continue
    seen, ser = set(), []
    for p, v in sorted(out):
        if p not in seen:
            seen.add(p)
            ser.append((p, v))
    return ser


def span(cycle, y0, y1):
    """주기별 시작·종료 문자열."""
    if cycle == "A":
        return str(y0), str(y1)
    if cycle == "S":
        return f"{y0}S1", f"{y1}S2"
    if cycle == "Q":
        return f"{y0}Q1", f"{y1}Q4"
    if cycle == "M":
        return f"{y0}01", f"{y1}12"
    return f"{y0}0101", f"{y1}1231"


def pretty(t, cycle):
    t = str(t)
    if cycle == "M" and len(t) == 6:
        return f"{t[:4]}-{t[4:]}"
    if cycle == "Q":
        return t.replace("Q", " ").strip() + "Q" if "Q" in t else t
    if cycle == "D" and len(t) == 8:
        return f"{t[:4]}-{t[4:6]}-{t[6:]}"
    return t[:4]


# ── 제목 매칭 ────────────────────────────────────────────────
STOP = re.compile(r"(추이|현황|비교|변화|월별|연도별|한국의|한국|비율|증감률|상승률|격차)")


NUMPREFIX = re.compile(r"^[\d.]+\s*")


def clean_name(s):
    return NUMPREFIX.sub("", str(s or "")).strip()


def tokens(s):
    s = clean_name(s)
    s = re.sub(r"[^\w가-힣]+", " ", s)
    return [w for w in s.split() if len(w) >= 2 and not STOP.fullmatch(w)]


def score_title(chart_title, stat_name, item_name=""):
    ct = set(tokens(chart_title))
    st = set(tokens(stat_name + " " + (item_name or "")))
    if not ct or not st:
        return 0.0
    inter = len(ct & st)
    # 부분 문자열도 인정 (환율 ↔ 원/달러환율)
    for c in ct:
        if c not in st and any(c in s or s in c for s in st):
            inter += 0.5
    return inter / len(ct)


def build_index(tl, verbose=True):
    """(통계표 × 말단 항목) 색인을 한 번 만들어 캐시한다. 이후 매칭은 로컬에서 한다."""
    idx = []
    for i, r in enumerate(tl):
        code = r["STAT_CODE"]
        try:
            its = item_list(code)
        except Exception:
            continue
        for im in its:
            idx.append({"statCode": code, "statName": clean_name(r["STAT_NAME"]),
                        "cycle": r.get("CYCLE"), "itemCode": im.get("ITEM_CODE"),
                        "itemName": im.get("ITEM_NAME"), "unit": im.get("UNIT_NAME"),
                        "start": im.get("START_TIME"), "end": im.get("END_TIME"),
                        "grp": im.get("GRP_CODE")})
        if verbose and (i + 1) % 50 == 0:
            print(f"  색인 {i+1}/{len(tl)} · 항목 {len(idx):,}", flush=True)
            save()
    save()
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", action="store_true", help="전체 항목 색인 생성")
    ap.add_argument("--list", action="store_true", help="통계표 목록만 받아 캐시")
    ap.add_argument("--probe", help="통계표 코드 하나의 항목 구조 출력")
    ap.add_argument("--match", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--cands", type=int, default=4)
    ap.add_argument("--items", type=int, default=60)
    ap.add_argument("--accept", type=float, default=0.9)
    a = ap.parse_args()

    if not KEY:
        print("ECOS_API_KEY 환경변수가 필요합니다. https://ecos.bok.or.kr/api/ 에서 발급.")
        return 1

    tl = table_list()
    print(f"조회 가능한 ECOS 통계표 {len(tl)}개")
    if a.list:
        save()
        by_cycle = collections.Counter(r.get("CYCLE") for r in tl)
        print("주기별:", dict(by_cycle))
        for r in tl[:20]:
            print(f"  {r['STAT_CODE']:12s} {r['STAT_NAME'][:44]:46s} {r.get('CYCLE','')}")
        return 0

    if a.index:
        idx = build_index(tl)
        json.dump(idx, open(os.path.join(CACHE_DIR, "ecos_index.json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
        print(f"항목 색인 {len(idx):,}건 → .cache/ecos_index.json")
        return 0

    if a.probe:
        for r in item_list(a.probe)[:40]:
            print(f"  {r.get('GRP_CODE','')}/{r['ITEM_CODE']:10s} {r['ITEM_NAME'][:34]:36s} "
                  f"{r.get('CYCLE','')} {r.get('START_TIME','')}~{r.get('END_TIME','')} {r.get('UNIT_NAME','')}")
        save()
        return 0

    # ── 매칭 ──
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import generate_site as g
    from match_fast import align, chart_years, infer_freq

    items = g.load_items(DATA)
    kosis = {}
    for f in ("api_map.json", "api_map_auto.json"):
        p = os.path.join(DATA, f)
        if os.path.exists(p):
            kosis.update(json.load(open(p, encoding="utf-8")))

    ipath = os.path.join(CACHE_DIR, "ecos_index.json")
    if not os.path.exists(ipath):
        print("먼저 색인을 만드세요:  python3 scripts/ecos.py --index")
        return 1
    index = json.load(open(ipath, encoding="utf-8"))
    print(f"항목 색인 {len(index):,}건")

    ECOS_CAT = {"환율", "금융", "주식", "세계 경제", "부동산", "소비와 물가",
                "조세와 재정", "수출과 무역", "물가와 생활", "기업과 산업"}
    KW = ["환율", "금리", "국고채", "회사채", "예금", "대출", "통화", "코스피", "코스닥", "주가",
          "시가총액", "외환보유", "경상수지", "무역수지", "국제수지", "GDP", "국민총소득",
          "경제성장", "물가", "수출", "수입", "가계부채", "기업부채", "부채", "달러", "엔화"]

    targets = []
    for it in items:
        if it["slide"] in kosis:                # KOSIS로 이미 잡힌 건 건너뛴다
            continue
        ys = chart_years(it)
        fr = infer_freq(ys)
        if not fr or len(it["labels"]) < 5 or len(it["title"]) < 3:
            continue
        if it["category"] in ECOS_CAT or any(k in it["title"] for k in KW):
            targets.append((it, ys, fr))
    print(f"ECOS 매칭 대상 {len(targets)}건 · 실행 {a.offset}~{a.offset + a.limit}")

    cp = os.path.join(DATA, "ecos_map.json")
    rp = os.path.join(DATA, "_ecos_review.json")
    conf = json.load(open(cp, encoding="utf-8")) if os.path.exists(cp) else {}
    rev = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else []
    done = set(conf) | {r["slide"] for r in rev}

    for it, ys, fr in targets[a.offset:a.offset + a.limit]:
        if it["slide"] in done:
            continue
        cyc = CYCLE.get(fr, "A")
        yy = [y for y in ys if y]
        y0, y1 = min(yy), str(int(max(yy)) + 1)
        vals = it["series"][0]
        # 색인에서 (통계표 × 항목) 후보를 제목 유사도로 뽑는다
        pool = [e for e in index if e["cycle"] == cyc]
        ranked = sorted(pool, key=lambda e: -score_title(it["title"], e["statName"], e["itemName"]))
        ranked = [e for e in ranked
                  if score_title(it["title"], e["statName"], e["itemName"]) >= 0.34][:a.items]
        lo, hi = span(cyc, y0, y1)
        best = None
        for e in ranked:
            try:
                ser = search(e["statCode"], cyc, lo, hi, e["itemCode"])
            except Exception:
                continue
            if len(ser) < 5:
                continue
            sc, off, mul = align(vals, [v for _, v in ser])
            if sc > 0 and (best is None or sc > best["score"]):
                best = {"score": round(sc, 3), "statCode": e["statCode"], "statName": e["statName"],
                        "itemCode": e["itemCode"], "itemName": e["itemName"],
                        "unit": e["unit"], "cycle": cyc, "offset": off,
                        "scale": mul, "periods": [p for p, _ in ser], "start": lo, "end": hi}
            if best and best["score"] >= 0.99:
                break

        if best and best["score"] >= a.accept:
            d = best["offset"]
            per = [best["periods"][i + d] for i in range(len(vals))
                   if 0 <= i + d < len(best["periods"])]
            conf[it["slide"]] = {
                "label": it["title"], "category": it["category"], "provider": "ecos",
                "statCode": best["statCode"], "itemCode": best["itemCode"],
                "cycle": best["cycle"], "start": best["start"], "end": best["end"],
                "scale": best["scale"], "unit": best["unit"],
                "sourceUrl": f"https://ecos.bok.or.kr/#/Short/{best['statCode']}",
                "_matchScore": best["score"], "_statNm": best["statName"],
                "_itemNm": best["itemName"], "_chartFreq": fr,
                "_periodRange": [per[0], per[-1]] if per else None,
                "_recoveredPeriods": per if fr != "Y" else None,
            }
            scs = "" if best["scale"] == 1 else f" ×{best['scale']:g}"
            print(f"  ✓ {best['score']:.2f} [{it['category'][:6]}] {it['title'][:26]:28s} → "
                  f"{best['statCode']} {best['statName'][:18]} / {str(best['itemName'])[:14]} "
                  f"[{best['cycle']}{scs}] {per[0] if per else '?'}~{per[-1] if per else '?'}", flush=True)
        else:
            rev.append({"slide": it["slide"], "title": it["title"], "category": it["category"],
                        "freq": fr, "source": it["source"],
                        "best_score": best["score"] if best else 0,
                        "cands": [{"statCode": e["statCode"], "statName": e["statName"],
                                   "itemName": e["itemName"]} for e in ranked[:3]]})
            print(f"  · {(best['score'] if best else 0):.2f} [{it['category'][:6]}] "
                  f"{it['title'][:26]:28s} → {(ranked[0]['statCode'] if ranked else '후보 없음')}", flush=True)
        json.dump(conf, open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(rev, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    save()
    print(f"\nECOS 확정 {len(conf)}건 · 검수 {len(rev)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
