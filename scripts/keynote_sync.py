#!/usr/bin/env python3
"""
팩트북에서 바뀐 것을 키노트에 옮길 수 있게 정리한다. 방향은 팩트북 → 키노트 하나다.

  python3 scripts/keynote_sync.py                 # 아직 키노트에 안 옮긴 변경 목록 + 차트별 TSV
  python3 scripts/keynote_sync.py --done c0718    # 옮겼다고 표시 (여러 개는 쉼표로, 전부는 all)
  python3 scripts/keynote_sync.py --all           # 동기화 여부와 관계없이 changelog 전체

TSV 는 latest/keynote/<id>_<제목>.tsv 에 쓴다. 키노트에서 차트를 고른 뒤
「차트 데이터 편집」을 열고 표 전체를 붙여넣으면 된다 (첫 행 = 계열 이름, 첫 열 = 라벨).
같은 차트가 여러 번 바뀌었으면 마지막 상태 하나만 만든다.
"""
import os, sys, json, argparse, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "latest", "keynote")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import generate_site as g       # noqa: E402

CL = os.path.join(DATA, "changelog.json")


def safe(s):
    return "".join(c if c.isalnum() or c in " _-()·" else "_" for c in s)[:40].strip()


def fmt(v):
    if v is None:
        return ""
    return f"{v:.6f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def write_tsv(it):
    os.makedirs(OUT, exist_ok=True)
    names = it.get("seriesNames") or [f"계열{i+1}" for i in range(len(it["series"]))]
    names = [n or f"계열{i+1}" for i, n in enumerate(names)]
    p = os.path.join(OUT, f"{it['id']}_{safe(it['title'])}.tsv")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\t" + "\t".join(names) + "\n")
        for i, l in enumerate(it["labels"]):
            f.write(str(l) + "\t" + "\t".join(fmt(s[i] if i < len(s) else None) for s in it["series"]) + "\n")
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--done", help="키노트에 옮긴 차트 id (쉼표 구분) 또는 all")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    cl = json.load(open(CL, encoding="utf-8")) if os.path.exists(CL) else []
    if a.done:
        ids = None if a.done == "all" else {x.strip() for x in a.done.split(",")}
        n = 0
        for e in cl:
            if not e.get("keynoteSynced") and (ids is None or e["id"] in ids or e["slide"] in ids):
                e["keynoteSynced"] = True; n += 1
        json.dump(cl, open(CL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{n}건을 동기화 완료로 표시했습니다.")
        return 0

    todo = [e for e in cl if a.all or not e.get("keynoteSynced")]
    if not todo:
        print("키노트에 옮길 변경이 없습니다.")
        return 0
    items = {it["slide"]: it for it in g.load_items(DATA)}
    g.assign_ids(list(items.values()), os.path.join(DATA, "ids.json"))
    by = collections.OrderedDict()
    for e in todo:
        by.setdefault(e["slide"], []).append(e)
    print(f"키노트에 옮길 차트 {len(by)}개 (변경 {len(todo)}건)\n")
    for slide, es in by.items():
        it = items.get(slide)
        last = es[-1]
        modes = "·".join(sorted({e.get("mode", "?") for e in es}))
        rng = f"{es[0].get('from', '')} → {last.get('to', '')}"
        flag = {"new": "신규 슬라이드", "replace": "통째 교체", "revise": "값 수정", "append": "이어붙임", "auto": "자동 갱신"}
        print(f"  {last['id']}  {slide:10s} [{last.get('category', '')}] {last['title']}")
        print(f"      {' + '.join(flag.get(m, m) for m in modes.split('·'))}  {rng}  ({sum(e.get('n', 0) for e in es)}점)  {es[0]['date']}~{last['date']}"
              + (f"  ← {last['sourceUrl']}" if last.get("sourceUrl") else ""))
        if it:
            p = write_tsv(it)
            print(f"      TSV: {os.path.relpath(p, ROOT)}")
        else:
            print("      (현재 사이트 데이터에서 이 차트를 찾지 못함 — 제목이 바뀌었나?)")
        for e in es:
            if e.get("note"):
                print(f"      메모: {e['note']}")
    print(f"\n옮긴 뒤: python3 scripts/keynote_sync.py --done {','.join(es[-1]['id'] for es in by.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
