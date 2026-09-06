#!/usr/bin/env python3
"""
등록된 API 차트를 매 빌드마다 최신값으로 받아 data/api.json 을 만든다.

  data/api_charts.json  (등록부 — newchart.py 가 채운다)
        │  빌드할 때마다 KOSIS·ECOS에서 새로 받는다
        ▼
  data/api.json         (generate_site.load_items 가 자동으로 읽는 형식)
        ▼
  site/

이 트랙의 차트는 사람이 갱신할 일이 없다. 빌드하면 그 시점의 최신이 된다.
키노트에서 만든 기존 차트(origin=keynote)와는 파일이 분리돼 있어 섞이지 않는다.

  KOSIS_API_KEY=... ECOS_API_KEY=... python3 scripts/build_api_charts.py

API 에 없는 옛 구간을 앞에 붙일 수 있다 ("prefix": "api-0005.json" → data/api_prefix/ 의 파일).
파일은 {"series": {"계열명": [["YYYYMMDD", 값], ...]}} 꼴. 기준 시점이 달라도 된다 — 겹치는 구간의
비율(중앙값)로 환산해 잇고, 겹치는 구간이 상수배로 안 맞으면(0.5% 초과) 그 계열은 붙이지 않는다.

계열이 여럿인 차트는 등록부에 "series" 를 둔다. 각 원소는 기본 spec 위에 덮어쓰는 조각이다.
  "series": [{"name": "서울", "objL1": "a7"}, {"name": "강남권역", "objL1": "a702"}]
"""
import os, sys, json, time, datetime, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
REG = os.path.join(DATA, "api_charts.json")
OUTP = os.path.join(DATA, "api.json")
KOSIS_KEY = os.environ.get("KOSIS_API_KEY", "")


def kosis_series(spec):
    q = {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
         "orgId": spec["orgId"], "tblId": spec["tblId"], "itmId": spec["itmId"],
         "prdSe": spec["prdSe"], "startPrdDe": spec.get("startPrdDe", "1960"),
         "endPrdDe": spec.get("endPrdDe", "2030")}
    for i in range(1, 5):
        if spec.get(f"objL{i}"):
            q[f"objL{i}"] = spec[f"objL{i}"]
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + "&".join(f"{k}={urllib.parse.quote(str(v), safe='+')}" for k, v in q.items()))
    last = None
    for t in range(2):                       # KOSIS 가 멈춰 있을 때 빌드가 몇십 분씩 끌리지 않게: 2회, 25초
        try:
            with urllib.request.urlopen(u, timeout=25) as r:
                d = json.loads(r.read().decode("utf-8"))
            if not isinstance(d, list):
                raise RuntimeError(str(d)[:100])
            out = {}
            for row in d:
                try:
                    out[row["PRD_DE"]] = float(row["DT"])
                except (TypeError, ValueError, KeyError):
                    continue
            return sorted(out.items())
        except Exception as e:
            last = e
            time.sleep(1 + t)
    raise RuntimeError(str(last)[:100])


def ecos_series(spec):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import ecos
    return ecos.search(spec["statCode"], spec["cycle"], spec["start"], spec["end"],
                       spec.get("itemCode"))


def chain_prefix(fetched, spec):
    """API 계열 앞에 옛 구간(prefix 파일)을 연쇄로 이어붙인다. 계열 이름으로 맞춘다."""
    pf = spec.get("prefix")
    if not pf:
        return fetched
    path = os.path.join(DATA, "api_prefix", pf)
    if not os.path.exists(path):
        print(f"    ! prefix 파일 없음: {path}")
        return fetched
    pre = json.load(open(path, encoding="utf-8")).get("series", {})
    out = []
    for name, d in fetched:
        old = pre.get(name)
        if not old:
            out.append((name, d))
            continue
        od = {p: v for p, v in old if v is not None}
        common = sorted(set(od) & set(d))
        if len(common) < 4:
            print(f"    ! {name}: 겹치는 시점이 {len(common)}개뿐 — 옛 구간을 붙이지 않음")
            out.append((name, d))
            continue
        first = min(d)
        if spec.get("prefixMode") == "abs":
            # 변동률처럼 0 근처 값: 환산 없이 그대로 잇고, 겹치는 구간은 절대 차이로 검증한다
            tol = spec.get("prefixTol", 0.02)
            dev = max(abs(d[p] - od[p]) for p in common)
            if dev > tol:
                print(f"    ! {name}: 겹치는 구간이 안 맞음 (최대 차이 {dev:.3f}) — 옛 구간을 붙이지 않음")
                out.append((name, d))
                continue
            merged = {p: v for p, v in od.items() if p < first}
            merged.update(d)
            print(f"    + {name}: {min(merged)}부터 이어붙임 (겹침 {len(common)}점, 최대 차이 {dev:.3f})")
            out.append((name, merged))
            continue
        rr = sorted(d[p] / od[p] for p in common if od[p])
        ratio = rr[len(rr) // 2]
        dev = max(abs(d[p] / od[p] / ratio - 1) for p in common if od[p])
        if dev > 0.005:
            print(f"    ! {name}: 겹치는 구간이 상수배로 안 맞음 (최대 {dev*100:.2f}%) — 옛 구간을 붙이지 않음")
            out.append((name, d))
            continue
        merged = {p: round(v * ratio, 4) for p, v in od.items() if p < first}
        merged.update(d)
        print(f"    + {name}: {min(merged)}부터 이어붙임 (환산 ×{ratio:.5f}, 겹침 {len(common)}점, 최대 편차 {dev*100:.2f}%)")
        out.append((name, merged))
    return out


def pp(t, cyc):
    t = str(t)
    if cyc == "M" and len(t) == 6:
        return f"{t[:4]}-{t[4:]}"
    if cyc == "Q" and len(t) > 4:
        return f"{t[:4]} {t[4:].lstrip('0Q') or '1'}Q"
    if cyc == "D" and len(t) == 8:
        return f"{t[:4]}-{t[4:6]}-{t[6:]}"
    return t[:4]


def main():
    prev = []
    if os.path.exists(OUTP):
        try:
            prev = json.load(open(OUTP, encoding="utf-8")).get("items", [])
        except Exception:
            prev = []
    if not KOSIS_KEY:
        print("!! KOSIS_API_KEY 가 비어 있습니다. GitHub Secrets 에 등록하세요.")
        print(f"   기존 data/api.json({len(prev)}건)을 그대로 둡니다.")
        return 0
    if not os.path.exists(REG):
        print("등록된 API 차트가 없습니다. scripts/newchart.py 로 추가하세요.")
        json.dump({"category": "새 데이터", "items": []},
                  open(OUTP, "w", encoding="utf-8"), ensure_ascii=False)
        return 0
    reg = json.load(open(REG, encoding="utf-8"))
    today = datetime.date.today().isoformat()
    items, errs = [], 0
    streak = 0                               # 연속 실패 — 3번 연달아 실패하면 KOSIS 장애로 보고 그만둔다
    for key, c in reg.items():
        if c.get("disabled"):
            continue
        if streak >= 3:
            print(f"  · {key} 건너뜀 (KOSIS 연속 실패)")
            errs += 1
            continue
        parts = c.get("series") or [{"name": c["title"]}]
        fetched = []
        try:
            for part in parts:
                spec = {**c, **{k: v for k, v in part.items() if k != "name"}}
                ser = ecos_series(spec) if spec.get("provider") == "ecos" else kosis_series(spec)
                fetched.append((part.get("name") or c["title"], dict(ser)))
        except Exception as e:
            print(f"  ✗ {key} {c['title']}: {str(e)[:60]}")
            errs += 1
            streak += 1
            continue
        streak = 0
        fetched = chain_prefix(fetched, c)
        periods = sorted(set().union(*[d.keys() for _, d in fetched]))
        if len(periods) < 2:
            continue
        sc = c.get("scale", 1) or 1
        cyc = c.get("cycle", "Y")
        items.append({
            "slide": key,
            "title": c["title"],
            "category": c.get("category", "새 데이터"),
            "source": f"{c.get('source','')} 「{c.get('table','')}」"
                      + (f", 단위: {c['unit']}" if c.get("unit") else ""),
            "sourceUrl": c.get("sourceUrl", ""),
            "vizType": c.get("vizType", "line"),
            "labels": [pp(p, cyc) for p in periods],
            "seriesNames": [n for n, _ in fetched],
            "updated": today,
            "series": [[None if d.get(p) is None else round(d[p] * sc, 6) for p in periods] for _, d in fetched],
        })
        print(f"  · {key} {c['title'][:26]:28s} {pp(periods[0],cyc)}~{pp(periods[-1],cyc)} ({len(periods)}개 × {len(fetched)}계열)")
    if not items and prev:
        print(f"\n!! 수집 0건. 기존 data/api.json({len(prev)}건)을 그대로 둡니다.")
        return 0
    json.dump({"category": "새 데이터", "_origin": "api", "items": items},
              open(OUTP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nAPI 차트 {len(items)}건 → data/api.json  (실패 {errs})")
    print("다음: python3 scripts/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
