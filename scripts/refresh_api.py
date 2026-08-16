#!/usr/bin/env python3
"""
정부 데이터 API로 차트를 자동 갱신한다.

  data/api_map.json  (차트 ↔ 통계표 매핑)
        │
        ├─ KOSIS 파라미터 API / 한국은행 ECOS API 호출
        │
        ▼
  data/overrides.json  (slide id → {labels, series} 패치)
        │
        ▼
  scripts/build.py → site/  (기존 파이프라인 그대로)

핵심: 키노트 원본은 건드리지 않는다. generate_site.load_items()가 이미 지원하는
overrides.json 훅에 최신 수치를 얹는 방식이라, 차트 id(=임베드 URL)도 그대로 유지된다.

사용:
  KOSIS_API_KEY=... python3 scripts/refresh_api.py            # 갱신 + 리포트
  KOSIS_API_KEY=... python3 scripts/refresh_api.py --dry-run  # 뭐가 바뀔지만 출력
"""
import os, sys, json, time, datetime, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
MAP = os.path.join(DATA, "api_map.json")
OVR = os.path.join(DATA, "overrides.json")
REPORT = os.path.join(DATA, "_api_refresh.json")

KOSIS_KEY = os.environ.get("KOSIS_API_KEY", "")
ECOS_KEY = os.environ.get("ECOS_API_KEY", "")


def _get(url, tries=5):
    last = None
    for t in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(2 + t * 2)
    raise RuntimeError(f"fetch failed: {last}")


def fetch_kosis(spec):
    """spec: {orgId, tblId, itmId, objL1..objL4, prdSe, startPrdDe, endPrdDe}"""
    q = {
        "method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
        "orgId": spec.get("orgId", "101"), "tblId": spec["tblId"],
        "itmId": spec.get("itmId", "T1+"), "prdSe": spec.get("prdSe", "Y"),
        "startPrdDe": str(spec["startPrdDe"]), "endPrdDe": str(spec["endPrdDe"]),
    }
    for i in range(1, 5):
        k = f"objL{i}"
        if spec.get(k):
            q[k] = spec[k]
    url = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
           + "&".join(f"{k}={urllib.parse.quote(str(v), safe='+')}" for k, v in q.items()))
    rows = _get(url)
    if isinstance(rows, dict):
        raise RuntimeError(f"KOSIS error: {rows}")
    return rows


def fetch_ecos(spec):
    """spec: {statCode, itemCode, cycle, start, end} — scripts/ecos.py 어댑터를 쓴다."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import ecos
    ser = ecos.search(spec["statCode"], spec.get("cycle", "A"),
                      spec["start"], spec["end"], spec.get("itemCode"))
    return [{"TIME": p, "DATA_VALUE": v} for p, v in ser]


def to_series(rows, spec):
    """API 응답을 (labels, series) 로 정규화."""
    prov = spec.get("provider", "kosis")
    scale = float(spec.get("scale", 1))
    nd = spec.get("round", 3)
    if prov == "kosis":
        pairs = [(r["PRD_DE"], r["DT"]) for r in rows if r.get("DT") not in (None, "")]
    else:
        pairs = [(r["TIME"], r["DATA_VALUE"]) for r in rows if r.get("DATA_VALUE") not in (None, "")]
    seen, out = set(), []
    for p, v in sorted(pairs):
        if p in seen:
            continue
        seen.add(p)
        out.append((p, round(float(v) * scale, nd)))
    labels = [p[:4] if spec.get("prdSe", "Y") == "Y" else p for p, _ in out]
    return labels, [[v for _, v in out]]


def main():
    dry = "--dry-run" in sys.argv
    if not os.path.exists(MAP):
        print(f"매핑 파일이 없습니다: {MAP}")
        return 1
    mapping = json.load(open(MAP, encoding="utf-8"))
    overrides = json.load(open(OVR, encoding="utf-8")) if os.path.exists(OVR) else {}
    # 현재 차트 상태 (비교용)
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import generate_site as g
    cur = {it["slide"]: it for it in g.load_items(DATA)}

    report, changed = [], 0
    for slide, spec in mapping.items():
        if spec.get("disabled"):
            continue
        try:
            rows = fetch_kosis(spec) if spec.get("provider", "kosis") == "kosis" else fetch_ecos(spec)
            labels, series = to_series(rows, spec)
        except Exception as e:
            report.append({"slide": slide, "status": "error", "detail": str(e)[:200]})
            print(f"  ✗ {slide}  {spec.get('label','')}: {e}")
            continue
        old = cur.get(slide)
        old_last = (old["labels"][-1], old["series"][0][-1]) if old and old["labels"] else None
        new_last = (labels[-1], series[0][-1]) if labels else None
        diff = old_last != new_last
        report.append({"slide": slide, "label": spec.get("label", ""),
                       "status": "changed" if diff else "same",
                       "old_last": old_last, "new_last": new_last,
                       "n_old": len(old["labels"]) if old else 0, "n_new": len(labels)})
        mark = "●" if diff else "·"
        print(f"  {mark} {slide}  {spec.get('label','')}: {old_last} → {new_last}  (n {len(old['labels']) if old else 0}→{len(labels)})")
        if diff:
            changed += 1
        if not dry:
            ov = overrides.get(slide, {})
            ov.update({"labels": labels, "series": series,
                       "updated": datetime.date.today().isoformat(),
                       "source": spec.get("source", ov.get("source", "")),
                       "sourceUrl": spec.get("sourceUrl", ov.get("sourceUrl", ""))})
            overrides[slide] = ov

    if not dry:
        json.dump(overrides, open(OVR, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(report, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n{'[dry-run] ' if dry else ''}대상 {len(mapping)}건 · 값이 바뀐 차트 {changed}건")
    print("다음: python3 scripts/build.py && git diff data/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
