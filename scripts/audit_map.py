#!/usr/bin/env python3
"""
확정 매칭을 다시 값으로 검증해서, 우연히 맞아떨어진 것을 걸러낸다.

match_fast 의 정렬 점수만으로는 부족하다. 짧은 계열이나 0이 늘어선 계열은
'연속 비율'이 우연히 일치해 만점이 나오는 일이 있다. 실제로 상장기업 수가
첨단세라믹산업조사에 1.00 으로 붙는 일이 있었다.

여기서는 겹치는 구간의 값을 하나하나 대조해서 셋을 요구한다.
  · 겹치는 점이 8개 이상
  · 그중 99% 이내로 맞는 점이 90% 이상
  · 차트 값의 종류가 5가지 이상 (0만 늘어선 계열 걸러내기)

  KOSIS_API_KEY=... python3 scripts/audit_map.py            # 보기만
  KOSIS_API_KEY=... python3 scripts/audit_map.py --prune    # 탈락분을 매핑에서 뺀다
"""
import os, sys, json, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import generate_site as g      # noqa: E402
import match_fast as mf        # noqa: E402
import refresh_charts as rc    # noqa: E402

MIN_OVERLAP, MIN_FRAC, MIN_DISTINCT = 8, 0.9, 5

# 숫자는 맞아도 뜻이 다른 것 — 사람이 보고 뺀 목록
DENY = {
    "한국의 수출과 수입": "중소기업수출동향은 중소기업 수출이라 전체 수출입과 다른 값이다",
}


def audit(spec, it):
    try:
        api = rc.fetch(spec)
    except Exception as e:
        return None, f"조회 실패 ({str(e)[:40]})"
    if len(api) < 4:
        return None, "원자료가 너무 짧음"
    av = [v for _, v in api]
    best = None
    for s in it.get("series") or []:
        cv = [None if x is None else float(x) for x in s]
        _, off, sc = mf.align(cv, av)
        if off is None:
            continue
        ov = [(cv[i], av[i + off] * sc) for i in range(len(cv))       # 차트 ≈ 원자료 × 배수
              if cv[i] is not None and 0 <= i + off < len(av) and av[i + off] is not None]
        if len(ov) < 2:
            continue
        good = sum(1 for a, b in ov if abs(a - b) / max(abs(b), 1e-9) <= 0.01)
        distinct = len({round(a, 6) for a, _ in ov})
        cand = (good / len(ov), len(ov), distinct)
        if best is None or cand > best:
            best = cand
    if best is None:
        return None, "정렬 실패"
    frac, n, distinct = best
    if n < MIN_OVERLAP:
        return best, f"겹치는 점 {n}개 (기준 {MIN_OVERLAP})"
    if frac < MIN_FRAC:
        return best, f"값 일치율 {frac:.0%} (기준 {MIN_FRAC:.0%})"
    if distinct < MIN_DISTINCT:
        return best, f"값 종류 {distinct}가지 (기준 {MIN_DISTINCT})"
    return best, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prune", action="store_true")
    a = ap.parse_args()

    p = os.path.join(DATA, "api_map_auto.json")
    mapping = json.load(open(p, encoding="utf-8"))
    items = {it["slide"]: it for it in g.load_items(DATA)}

    keep, drop = {}, []
    for slide, spec in mapping.items():
        it = items.get(slide)
        if not it:
            drop.append((slide, "(차트 없음)", "차트를 찾지 못함"))
            continue
        if it["title"] in DENY:
            drop.append((slide, it["title"], DENY[it["title"]]))
            continue
        if spec.get("provider", "kosis") != "kosis":
            keep[slide] = spec
            continue
        best, why = audit(spec, it)
        if why:
            drop.append((slide, it["title"], why))
        else:
            spec["_auditOverlap"], spec["_auditFrac"] = best[1], round(best[0], 3)
            keep[slide] = spec

    print(f"확정 {len(mapping)}건 감사 → 통과 {len(keep)} · 탈락 {len(drop)}\n")
    for _, t, why in drop:
        print(f"  ✗ {t[:30]:32s} {why}")

    if a.prune and drop:
        json.dump(keep, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n→ data/api_map_auto.json 에서 {len(drop)}건 제외 (남은 {len(keep)}건)")
    elif drop:
        print("\n(보기만 했습니다. 빼려면 --prune)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
