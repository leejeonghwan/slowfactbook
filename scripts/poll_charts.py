#!/usr/bin/env python3
"""
여론조사 지지율 차트 자동 갱신 — 리얼미터 주간집계(월요일) / 한국갤럽 데일리오피니언(금요일).

  python3 scripts/poll_charts.py realmeter                 # 최신 PDF 받아 미리보기
  python3 scripts/poll_charts.py realmeter --apply         # 반영
  python3 scripts/poll_charts.py realmeter --file 어떤.pdf  # 받아둔 PDF 로

원칙: 겹치는 구간을 전수 대조해 한 점이라도 어긋나면 붙이지 않고 멈춘다.
PDF 양식이 바뀌었을 때 조용히 틀린 값이 들어가는 것이 가장 나쁘기 때문이다.
리얼미터 PDF 는 정당 지지도 '최근 6개월 주별 결과' 표를 싣고 있어 매주 27주치
대조가 공짜로 된다. 대통령 평가는 그 주 한 점만 실리므로 직전 값으로만 확인한다.
"""
import os, re, sys, json, argparse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, ".cache", "poll")
RM_LIST = "http://www.realmeter.net/category/pdf/"
KST = datetime.timezone(datetime.timedelta(hours=9))

WEEK_RE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})주")
TOTAL_RE = re.compile(r"◈\s*전\s*체\s*◈\s*\(?\d*\)?\s+" + r"\s+".join([r"([\d.]+)"] * 7))
PARTY_RE = re.compile(r"^(?:정당\s*)?(\d{1,2})월\s*(\d{1,2})주\s+" + r"\s+".join([r"([\d.]+)"] * 6) + r"\s*$")


def _get(url, binary=False):
    import requests
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0 slowfactbook"})
    r.raise_for_status()
    return r.content if binary else r.text


def realmeter_latest_pdf():
    """목록 페이지의 첫 PDF 링크를 받아 캐시에 저장하고 경로를 돌려준다."""
    html = _get(RM_LIST)
    # href 끝에 '#new_tab' 같은 조각이 붙어 있다.
    links = re.findall(r'href="([^"]+?\.pdf)(?:#[^"]*)?"', html)
    if not links:
        raise SystemExit("리얼미터 목록에서 PDF 링크를 찾지 못했습니다. 페이지 구조가 바뀐 듯합니다.")
    url = links[0]
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, os.path.basename(url.split("?")[0]))
    if not os.path.exists(path):
        open(path, "wb").write(_get(url, binary=True))
    return path, url


def parse_realmeter(path, allow_no_party=False):
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        pages = [(p.extract_text() or "") for p in pdf.pages]
    out = {"week": None, "approve": None, "disapprove": None, "party": []}
    for t in pages:
        m = WEEK_RE.search(t)
        if m:
            out["week"] = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            break
    # 대통령 국정수행 평가 쪽의 ◈전체◈ 행.
    # 열: 매우잘함 잘하는편 잘못하는편 매우잘못함 잘함(①+②) 잘못함(③+④) 잘모름
    for t in pages:
        if "대통령 국정수행 평가" not in t.split("\n")[0]:
            continue
        m = TOTAL_RE.search(t)
        if m:
            v = [float(x) for x in m.groups()]
            out["approve"], out["disapprove"] = v[4], v[5]
            break
    for t in pages:
        if "정당지지도 : 최근" not in t and "정당지지도: 최근" not in t:
            continue
        for line in t.split("\n"):
            mm = PARTY_RE.match(line.strip())
            if mm:
                g = mm.groups()
                out["party"].append({"month": int(g[0]), "week": int(g[1]),
                                     "민주당": float(g[2]), "국민의힘": float(g[3])})
        break
    miss = [k for k in ("week", "approve", "disapprove") if out[k] is None]
    if miss:
        raise SystemExit(f"PDF 에서 못 읽은 항목이 있습니다: {miss}. "
                         "양식이 바뀌었을 수 있습니다 — 사람이 봐야 합니다.")
    # 정당 지지도를 뺀 '대통령 국정수행 평가' 단독 호가 간혹 있다. 그때는 대조 그물이
    # 없을 뿐이니 평가 수치만 쓰고 넘어간다 — 값이 없다고 멈출 일은 아니다.
    if not out["party"] and not allow_no_party:
        raise SystemExit("정당 지지도 표를 못 찾았습니다. 양식이 바뀌었을 수 있습니다 — 사람이 봐야 합니다.")
    return out


def load_chart(key):
    ov = json.load(open(os.path.join(DATA, "overrides.json"), encoding="utf-8"))
    full = {i.get("slide"): i for i in json.load(open(os.path.join(DATA, "full.json"), encoding="utf-8"))["items"]}
    base = full.get(key) or next((i for i in full.values() if i.get("id") == key), None)
    if base is None:
        raise SystemExit(f"{key} 을 찾지 못했습니다.")
    cid = base.get("id") or key
    it = {**base, **(ov.get(cid) or ov.get(base.get("slide")) or {})}
    names = [str(x).strip().rstrip(".") for x in (it.get("seriesNames") or [])]
    return ov, it, names


def check(name, chart_tail, pdf_vals):
    bad = [(i, a, b) for i, (a, b) in enumerate(zip(chart_tail, pdf_vals)) if a != b]
    print(f"  {name}: 겹치는 {len(pdf_vals)}점 대조 — " +
          ("일치" if not bad else f"불일치 {len(bad)}건 {bad[:5]}"))
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=["realmeter"])
    ap.add_argument("--file")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if a.file:
        path, url = a.file, RM_LIST
    else:
        path, url = realmeter_latest_pdf()
    print(f"PDF: {os.path.basename(path)}")
    d = parse_realmeter(path)
    y, mo, wk = d["week"]
    label = str(mo) if wk == 1 else ""
    print(f"  {y}년 {mo}월 {wk}주  긍정 {d['approve']} / 부정 {d['disapprove']}  "
          f"민주 {d['party'][-1]['민주당']} / 국힘 {d['party'][-1]['국민의힘']}")

    ok = True
    # ── 1. 리얼미터 대통령 지지율 (긍정률·부정률)
    ov, c570, n570 = load_chart("slide-570")
    s570 = [list(x) for x in c570["series"]]
    ia, idis = n570.index("긍정률"), n570.index("부정률")
    fresh570 = (s570[ia][-1], s570[idis][-1]) != (d["approve"], d["disapprove"])

    # ── 2. 대통령과 정당 지지율 (리얼미터)
    ov2, c571, n571 = load_chart("slide-571")
    s571 = [list(x) for x in c571["series"]]
    im, ik = n571.index("민주당"), n571.index("국민의힘")
    ij = n571.index("이재명")
    pm = [w["민주당"] for w in d["party"]]
    pk = [w["국민의힘"] for w in d["party"]]
    fresh571 = (s571[im][-1], s571[ik][-1]) != (pm[-1], pk[-1])

    # 대조는 '이미 들어 있는 구간'끼리. 새 주가 아직이면 전수, 새 주면 마지막 한 점을 뺀다.
    cut = len(pm) - (1 if fresh571 else 0)
    if cut > 0:
        tail_m = s571[im][-cut:]
        tail_k = s571[ik][-cut:]
        ok &= check("민주당", tail_m, pm[:cut])
        ok &= check("국민의힘", tail_k, pk[:cut])
    if not fresh570:
        print("  대통령 평가: 이번 주 값이 이미 들어 있습니다.")
    if not ok:
        print("\n겹치는 구간이 어긋납니다. 붙이지 않았습니다 — 원자료와 차트를 사람이 대조해야 합니다.")
        return 1
    if not (fresh570 or fresh571):
        print("\n새로 붙일 주가 없습니다.")
        return 0
    print(f"\n붙일 것: {y}년 {mo}월 {wk}주 (라벨 '{label}')")
    if not a.apply:
        print("(미리보기입니다. 반영하려면 --apply)")
        return 0

    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    today = datetime.date.today().isoformat()
    cl = json.load(open(os.path.join(DATA, "changelog.json"), encoding="utf-8"))
    ovf = json.load(open(os.path.join(DATA, "overrides.json"), encoding="utf-8"))

    def push(slide, it, series, idx_vals, cid, title):
        # 열쇠는 차트 id 다 (슬라이드 번호는 덱이 바뀌면 밀린다).
        labs = list(it["labels"]) + [label]
        ser = [list(x) for x in series]
        for i, v in idx_vals:
            ser[i].append(v)
        for i in range(len(ser)):
            if len(ser[i]) < len(labs):
                ser[i].append(None)
        o = dict(ovf.get(cid) or ovf.get(slide) or {})
        o.update({"labels": labs, "series": ser, "source": "리얼미터", "unit": "%",
                  "sourceUrl": url, "updated": stamp})
        ovf[cid] = o
        cl.append({"date": today, "slide": slide, "id": cid, "title": title,
                   "category": "정치", "mode": "자동 갱신", "n": 1,
                   "note": f"리얼미터 {y}년 {mo}월 {wk}주", "url": url})
        print(f"  {cid} {title}: {len(labs)}점")

    if fresh570:
        push("slide-570", c570, s570, [(ia, d["approve"]), (idis, d["disapprove"])],
             "c2073", "리얼미터 대통령 지지율")
    if fresh571:
        push("slide-571", c571, s571,
             [(ij, d["approve"]), (im, pm[-1]), (ik, pk[-1])],
             "c2074", "대통령과 정당 지지율(리얼미터)")
    json.dump(ovf, open(os.path.join(DATA, "overrides.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(cl, open(os.path.join(DATA, "changelog.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\n→ data/overrides.json · data/changelog.json 반영. 다음: python3 scripts/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
