#!/usr/bin/env python3
"""
조사명으로 후보 표를 좁혀서 자동 등록한다.

차트 제목으로 KOSIS 를 검색하면 「고용률」·「취업자 수」 처럼 흔한 제목은 엉뚱한 표가
올라온다. 반면 출처에 적힌 조사명(예 '경제활동인구조사')으로 검색하면 그 조사에 속한
표만 20개쯤 나온다. 그 안에서 값으로 대조하면 훨씬 잘 붙는다.

조사명은 사람이 적은 것이라 틀릴 수 있다. 그래도 위험하지 않다 — 표를 찍어 주는 것일
뿐이고, 등록 여부는 끝까지 '값이 맞느냐'가 정한다. 조사명이 틀렸으면 그냥 안 붙는다.

  KOSIS_API_KEY=... python3 scripts/register_by_survey.py --limit 8
  KOSIS_API_KEY=... python3 scripts/register_by_survey.py --limit 8 --cands 8
"""
import os, re, sys, json, subprocess, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
MAP = os.path.join(DATA, "api_map_auto.json")
LOG = os.path.join(DATA, "_survey_log.json")
AGENCY = ("국가데이터처", "통계청", "KOSIS", "고용노동부", "보건복지부", "행정안전부",
          "교육부", "국세청", "기획재정부", "건강보험", "국토교통부", "한국부동산원")


def nmap():
    return len(json.load(open(MAP, encoding="utf-8")))


def survey_of(src):
    """출처 문자열에서 조사명을 끄집어낸다. 「」 안이 1순위, 없으면 기관명 뒤 어절."""
    m = re.findall(r"[「『]([^」』]+)[」』]", src or "")
    if m:
        return m[0].strip()
    s = re.sub(r"[,.·]\s*단위.*$", "", src or "").strip()
    for a in AGENCY:
        if s.startswith(a):
            rest = s[len(a):].strip(" ,.·")
            if len(rest) >= 4 and ("조사" in rest or "통계" in rest or "추계" in rest):
                return rest.split(",")[0].strip()
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--cands", type=int, default=8)
    ap.add_argument("--accept", type=float, default=0.9)
    a = ap.parse_args()

    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import generate_site as g
    import match_fast as mf

    auto = set(json.load(open(MAP, encoding="utf-8")))
    auto |= set(json.load(open(os.path.join(DATA, "api_map.json"), encoding="utf-8")))
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {}

    todo = []
    for it in g.load_items(DATA):
        cid = it.get("id")
        if not cid or cid in auto or cid in log:
            continue
        if not mf.infer_freq(mf.chart_years(it)):
            continue
        src = it.get("source") or ""
        if not any(k in src for k in AGENCY):
            continue
        sv = survey_of(src)
        if sv:
            todo.append((cid, it, sv))
    print(f"조사명이 있는 미등록 시계열 {len(todo)}건 · 이번에 {min(a.limit, len(todo))}건")

    tables = {}
    ok = 0
    for cid, it, sv in todo[:a.limit]:
        if sv not in tables:
            r = mf.search(sv) or []
            tables[sv] = [(x.get("TBL_ID"), x.get("TBL_NM"), x.get("ORG_ID")) for x in r]
            print(f"  [{sv}] 표 {len(tables[sv])}개")
        hit = None
        for tbl, nm, org in tables[sv][:a.cands]:
            if not tbl:
                continue
            before = nmap()
            cmd = [sys.executable, os.path.join(ROOT, "scripts", "register_auto.py"),
                   cid, "--tbl", tbl, "--accept", str(a.accept), "--apply"]
            if org:
                cmd += ["--org", str(org)]
            try:
                subprocess.run(cmd, capture_output=True, text=True, timeout=110)
            except subprocess.TimeoutExpired:
                continue
            if nmap() > before:
                hit = (tbl, nm)
                break
        log[cid] = {"title": it["title"], "survey": sv,
                    "tbl": hit[0] if hit else None, "tblNm": hit[1] if hit else None}
        json.dump(log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if hit:
            ok += 1
            print(f"  ✓ {cid} {it['title'][:24]:26s} → {hit[0]} {str(hit[1])[:28]}")
        else:
            print(f"  · {cid} {it['title'][:24]:26s} → [{sv}] 표 {a.cands}개 모두 실패")
    print(f"\n성공 {ok} · 등록부 {nmap()}건 · 누적 시도 {len(log)}건")


if __name__ == "__main__":
    main()
