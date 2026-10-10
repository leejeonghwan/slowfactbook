#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""출처·제목 표기를 통일한다.

  1. 겹낫표 「」 『』 를 뺀다.  국가데이터처 「경제활동인구조사」 → 국가데이터처 경제활동인구조사
  2. 문장 끝에 마침표를 찍는다.  (숫자·닫는 괄호·…·물음표·느낌표로 끝나도 찍는다,
     이미 마침표면 그대로 둔다)

data/*.json 의 items, overrides.json, api_map*.json, market_map.json 을 모두 훑는다.

  python3 scripts/normalize_sources.py --dry-run
  python3 scripts/normalize_sources.py --apply
"""
import argparse, glob, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SKIP = {"versions.json", "overrides_legacy.json", "ids.json", "changelog.json"}
BRACKET = str.maketrans({"「": "", "」": "", "『": "", "』": ""})


def fix(s, period=True):
    if not isinstance(s, str):
        return s
    t = s.translate(BRACKET)
    t = re.sub(r"\s{2,}", " ", t).strip()
    # 제목은 겹낫표만 뺀다. 마침표는 화면에 그릴 때 붙이고, 저장값에는 넣지 않는다
    # (load_items 가 제목 끝 마침표를 떼어내므로 넣어 봐야 지워진다).
    if period and t and not t.endswith((".", "…", "?", "!")):
        t += "."
    return t


def walk(obj, keys, hits):
    """dict 를 훑으며 keys 에 해당하는 문자열을 고친다."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and isinstance(v, str):
                nv = fix(v, period=(k != "title"))
                if nv != v:
                    hits.append((k, v, nv))
                    obj[k] = nv
            else:
                walk(v, keys, hits)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, keys, hits)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--titles", action="store_true", help="제목에서도 겹낫표를 뺀다")
    a = ap.parse_args()
    if not a.apply:
        a.dry_run = True

    keys = {"source"} | ({"title"} if a.titles else set())
    total = 0
    for fp in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        if os.path.basename(fp).startswith("_") or os.path.basename(fp) in SKIP:
            continue
        try:
            doc = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        hits = []
        walk(doc, keys, hits)
        if not hits:
            continue
        total += len(hits)
        print(f"{os.path.basename(fp)}: {len(hits)}건")
        for k, old, new in hits[:4]:
            print(f"   {old[:58]}\n → {new[:58]}")
        if a.apply:
            json.dump(doc, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n{'[미리보기] ' if a.dry_run else ''}합계 {total}건")
    if a.dry_run and total:
        print("반영하려면 --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
