#!/usr/bin/env python3
"""
후보 통계표를 기계가 하나씩 꽂아 보는 자동 등록 쓸이.

match_fast 는 '제목으로 표를 찾고 값으로 대조'까지 한 번에 하는데, 분류축 구성이
복잡한 표에서는 대조 단계에서 떨어진다. 그런데 후보 표 자체는 맞게 찾아 놓은 경우가
많다(_match_review.json). register_auto 는 표를 찍어 주면 축을 끝까지 뒤져 맞춰 준다.

그래서 사람이 주소를 찾아 적는 대신, 후보를 기계가 차례로 꽂아 본다.
등록부가 늘어나면 성공, 안 늘어나면 다음 후보로 넘어간다.

  KOSIS_API_KEY=... python3 scripts/register_sweep.py --limit 10
  KOSIS_API_KEY=... python3 scripts/register_sweep.py --limit 10 --cands 3
"""
import os, sys, json, subprocess, argparse, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
MAP = os.path.join(DATA, "api_map_auto.json")
REV = os.path.join(DATA, "_match_review.json")
LOG = os.path.join(DATA, "_sweep_log.json")


def nmap():
    return len(json.load(open(MAP, encoding="utf-8")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--cands", type=int, default=3)
    ap.add_argument("--accept", type=float, default=0.9)
    a = ap.parse_args()

    rev = json.load(open(REV, encoding="utf-8"))
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {}
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import generate_site as g
    items = g.load_items(DATA)
    byslide = {it.get("slide"): it for it in items}

    todo = [r for r in rev if r.get("slide") not in log and (r.get("cands") or [])][:a.limit]
    print(f"검수 대기 {len(rev)}건 · 이번에 {len(todo)}건 시도 (후보 {a.cands}개씩)")
    ok = 0
    for r in todo:
        sl = r["slide"]
        it = byslide.get(sl)
        key = (it or {}).get("id") or sl
        title = r.get("title") or (it or {}).get("title") or sl
        before = nmap()
        hit = None
        for c in (r.get("cands") or [])[:a.cands]:
            tbl = c.get("tblId")
            if not tbl:
                continue
            cmd = [sys.executable, os.path.join(ROOT, "scripts", "register_auto.py"),
                   key, "--tbl", tbl, "--accept", str(a.accept), "--apply"]
            try:
                subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                continue
            if nmap() > before:
                hit = (tbl, c.get("tblNm"))
                break
        log[sl] = {"id": key, "title": title,
                   "tbl": hit[0] if hit else None, "tblNm": hit[1] if hit else None}
        json.dump(log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if hit:
            ok += 1
            print(f"  ✓ {key} {title[:26]:28s} → {hit[0]} {str(hit[1])[:24]}")
        else:
            print(f"  · {key} {title[:26]:28s} → 후보 {a.cands}개 모두 실패")
    print(f"\n성공 {ok}/{len(todo)} · 등록부 {nmap()}건 · 누적 시도 {len(log)}건")


if __name__ == "__main__":
    main()
