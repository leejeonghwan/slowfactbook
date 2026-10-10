#!/usr/bin/env python3
"""
한국갤럽 데일리 오피니언 '월별 통합 교차집계표' → 성별·연령대별 대통령 직무 수행 긍정률(c2228).

  python3 scripts/gallup_update.py            # 최신 통합 호를 찾아 미리보기
  python3 scripts/gallup_update.py --apply
  python3 scripts/gallup_update.py --file 받아둔.pdf

갤럽은 매월 마지막 호에 그 해 1월부터 해당 월까지의 월별 통합표를 통째로 다시 싣는다.
그래서 한 번 받으면 겹치는 달이 수십 개 생기고, 전수 대조가 공짜로 된다.
한 달이라도 어긋나면 붙이지 않고 멈춘다 — 양식이 바뀌었을 때 조용히 틀린 값이
들어가는 것이 가장 나쁘기 때문이다.
"""
import os, re, sys, json, argparse, datetime, subprocess, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, ".cache", "gallup")
LIST = "https://www.gallup.co.kr/gallupdb/report.asp"
CONTENT = "https://www.gallup.co.kr/gallupdb/reportContent.asp?seqNo=%d&bType=8"
KST = datetime.timezone(datetime.timedelta(hours=9))
CHART = "c2228"

AGES = ["18~29세", "30대", "40대", "50대", "60대", "70대 이상"]
KEYS = [f"{s} {a}" for s in ("남성", "여성") for a in AGES]
MONTH_RE = re.compile(r"(\d{1,2})월\([^)]*\)\s*통합")
# '남성 18~29세   304   309   30%' — 사례수 두 칸 뒤 첫 % 가 '잘하고 있다'.
ROW_RE = re.compile(
    r"(남성|여성)\s*(18~29세|30대|40대|50대|60대|70대\s*이상)"
    r"[^\S\n]+[\d,]+[^\S\n]+[\d,]+[^\S\n]+(\d+)%")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 slowfactbook"})
    return urllib.request.urlopen(req, timeout=60).read()


def latest_pdf():
    """목록에서 '통합 포함' 이라 적힌 가장 최근 호의 PDF 를 받아 캐시 경로를 돌려준다."""
    html = _get(LIST).decode("euc-kr", "replace")
    rows = re.findall(r"fn_viewContents\('(\d+)'\);[^>]*>(.*?)</a>", html, re.S)
    for seq, title in rows:
        if "통합 포함" not in title:
            continue
        page = _get(CONTENT % int(seq)).decode("euc-kr", "replace")
        m = re.search(r"https://www\.gallup\.co\.kr/dir/GallupKoreaDaily/"
                      r"GallupKoreaDailyOpinion_\d+\(\d{8}\)\.pdf", page)
        if not m:
            continue
        url = m.group(0)
        os.makedirs(CACHE, exist_ok=True)
        path = os.path.join(CACHE, os.path.basename(url))
        if not os.path.exists(path):
            open(path, "wb").write(_get(url))
        return path, url
    raise SystemExit("목록에서 'N월 통합 포함' 호를 찾지 못했습니다 — 페이지 구조가 바뀐 듯합니다.")


def parse(path):
    """{'2026-01': {'남성 18~29세': 30, ...}, ...}"""
    txt = subprocess.run(["pdftotext", "-layout", path, "-"],
                         capture_output=True, text=True).stdout
    m = re.search(r"\((\d{4})\d{4}\)", os.path.basename(path))
    year = int(m.group(1)) if m else int(re.search(r"(20\d{2})년", txt).group(1))
    lines = txt.split("\n")
    # '대통령 직무 수행 평가' 월별 통합 구간만. 뒤쪽의 정당 지지도·정치 성향 표에도
    # 같은 모양의 행이 있어서 구간을 자르지 않으면 섞인다.
    start = next((i for i, l in enumerate(lines)
                  if "월별 통합 교차집계표" in l), None)
    if start is None:
        raise SystemExit("'월별 통합 교차집계표' 를 찾지 못했습니다 — 사람이 봐야 합니다.")
    end = next((i for i in range(start + 1, len(lines))
                if "월별 통합 교차집계표" in lines[i]), len(lines))
    seg = lines[start:end]
    heads = [i for i, l in enumerate(seg) if MONTH_RE.search(l)]
    out = {}
    for n, h in enumerate(heads):
        months = [int(x) for x in MONTH_RE.findall(seg[h])]
        block = seg[h: heads[n + 1] if n + 1 < len(heads) else len(seg)]
        got = {}
        for line in block:
            for m in ROW_RE.finditer(line):
                age = re.sub(r"\s+", " ", m.group(2))
                k = m.group(1) + " " + age
                got.setdefault(k, []).append(int(m.group(3)))
        for col, mo in enumerate(months):
            vals = {k: v[col] for k, v in got.items() if len(v) > col}
            if len(vals) == 12:
                out[f"{year}-{mo:02d}"] = vals
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if a.file:
        path, url = a.file, LIST
    else:
        path, url = latest_pdf()
    print(f"PDF: {os.path.basename(path)}")
    months = parse(path)
    if not months:
        raise SystemExit("월별 통합표에서 성/연령별 행을 읽지 못했습니다 — 사람이 봐야 합니다.")
    print(f"  읽은 달: {', '.join(sorted(months))}")

    ov = json.load(open(os.path.join(DATA, "overrides.json"), encoding="utf-8"))
    man = json.load(open(os.path.join(DATA, "manual.json"), encoding="utf-8"))
    items = man["items"] if isinstance(man, dict) else man
    base = next(x for x in items if x.get("id") == CHART)
    it = {**base, **(ov.get(CHART) or {})}
    names = [str(x).strip() for x in it["seriesNames"]]
    assert names == KEYS, names
    labs = list(it["labels"])
    ser = [list(x) for x in it["series"]]

    bad = []
    for j, L in enumerate(labs):
        if L not in months:
            continue
        for i, k in enumerate(names):
            if ser[i][j] != months[L][k]:
                bad.append((L, k, ser[i][j], months[L][k]))
    overlap = [L for L in labs if L in months]
    print(f"  겹치는 {len(overlap)}개월 × 12계열 대조 — " +
          ("일치" if not bad else f"불일치 {len(bad)}건 {bad[:5]}"))
    if bad:
        print("\n겹치는 구간이 어긋납니다. 붙이지 않았습니다 — 원자료를 사람이 봐야 합니다.")
        return 1

    new = [L for L in sorted(months) if L not in labs and (not labs or L > labs[-1])]
    if not new:
        print("\n새로 붙일 달이 없습니다.")
        return 0
    print(f"\n붙일 것: {', '.join(new)}")
    for L in new:
        print("   " + L + "  " + "  ".join(f"{k} {months[L][k]}" for k in names[:3]) + " …")
    if not a.apply:
        print("(미리보기입니다. 반영하려면 --apply)")
        return 0

    for L in new:
        labs.append(L)
        for i, k in enumerate(names):
            ser[i].append(months[L][k])
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    o = dict(ov.get(CHART) or {})
    o.update({"labels": labs, "series": ser, "unit": "%",
              "source": "한국갤럽 갤럽리포트. 월간 평균. 단위: %.",
              "sourceUrl": url, "updated": stamp})
    ov[CHART] = o
    json.dump(ov, open(os.path.join(DATA, "overrides.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    cl_path = os.path.join(DATA, "changelog.json")
    cl = json.load(open(cl_path, encoding="utf-8"))
    cl.append({"date": datetime.date.today().isoformat(), "slide": base.get("slide"),
               "id": CHART, "title": base.get("title"), "category": "정치",
               "mode": "자동 갱신", "n": len(new),
               "note": "한국갤럽 월별 통합 " + ", ".join(new), "url": url})
    json.dump(cl, open(cl_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n→ {CHART}: {len(labs)}점. data/overrides.json 반영. 다음: python3 scripts/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
