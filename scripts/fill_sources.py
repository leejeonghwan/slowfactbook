#!/usr/bin/env python3
"""
확정 매칭을 근거로 출처 표기를 보강한다. 사람이 쓴 출처는 함부로 갈아치우지 않는다.

정책 셋:
  1. 출처가 비어 있거나 부스러기('(' 같은 것)면 → 매칭된 조사명으로 채운다.
  2. 사람이 써 둔 출처가 멀쩡하면 → 건드리지 않는다. 원자료 링크만 단다.
  3. 'e-지방지표' '국제통계연감' 처럼 여러 조사를 모아놓은 표는 조사명으로 쓰지 않는다.
     그 표를 근거로 출처를 새로 쓰면 오히려 부정확해진다.

  python3 scripts/fill_sources.py --dry-run
  python3 scripts/fill_sources.py --apply
"""
import os, sys, json, re, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import generate_site as g  # noqa: E402

# 조사가 아니라 '모아놓은 표' — 출처 조사명으로 쓰면 안 된다
AGGREGATOR = {"e-지방지표", "국제통계연감", "OECD", "World Bank", "IMF", "KOSIS 100대 지표",
              "북한통계", "국가주요지표", "시군구통계"}
JUNK = re.compile(r"^[\s.,()\[\]·/-]*$")


def is_junk(s):
    return not s or bool(JUNK.fullmatch(s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.apply:
        a.dry_run = True

    mapping = {}
    for f in ("api_map.json", "api_map_auto.json", "cross_map.json"):
        p = os.path.join(DATA, f)
        if os.path.exists(p):
            mapping.update(json.load(open(p, encoding="utf-8")))

    items = {it["slide"]: it for it in g.load_items(DATA)}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}

    filled, linked, kept, skipped = [], [], 0, []
    for slide, spec in mapping.items():
        it = items.get(slide)
        if not it:
            continue
        st = (spec.get("_statNm") or "").split("(")[0].strip()
        url = spec.get("sourceUrl") or ""
        src = (it.get("source") or "").strip()
        o = ov.setdefault(slide, {})

        # 원자료 링크는 무조건 단다 — 독자가 표로 바로 갈 수 있게
        if url and not it.get("sourceUrl"):
            o["sourceUrl"] = url
            linked.append(it["title"])

        if is_junk(src):
            if st and st not in AGGREGATOR:
                o["source"] = f"국가데이터처 「{st}」"
                filled.append((it["title"], o["source"]))
            else:
                skipped.append((it["title"], st or "(조사명 없음)"))
        else:
            kept += 1

    print(f"확정 매핑 {len(mapping)}건 검토")
    print(f"  출처를 새로 채움 : {len(filled)}")
    print(f"  원자료 링크 추가 : {len(linked)}")
    print(f"  사람이 쓴 출처 유지: {kept}")
    print(f"  채우지 않고 넘김 : {len(skipped)}  (모아놓은 표라 조사명으로 부적절)")
    print()
    for t, s in filled:
        print(f"  + {t[:28]:30s} → {s}")
    if skipped:
        print()
        for t, s in skipped:
            print(f"  · {t[:28]:30s} 넘김 ({s})")

    if a.apply:
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n→ data/overrides.json 반영. 다음: python3 scripts/build.py")
    else:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
