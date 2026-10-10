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
ANNUAL = ("https://www.gallup.co.kr/dir/GallupKoreaDaily/"
          "GallupKoreaDailyOpinion_Monthly_%d12.pdf")
KST = datetime.timezone(datetime.timedelta(hours=9))
# (차트 id, 표, 읽을 계열, 그 표에서 몇 번째 비율인가)
#   대통령 표: 0 = 잘하고 있다
#   정당 표  : 0 = 더불어민주당, 1 = 국민의힘
CHARTS = [
    ("c2228", "대통령 직무 수행 평가", None, 0),
    ("c0405", "정당 지지도", ["남성 18~29세", "여성 18~29세"], 0),
    ("c0406", "정당 지지도", ["남성 18~29세", "여성 18~29세"], 1),
]

AGES = ["18~29세", "30대", "40대", "50대", "60대", "70대 이상"]
KEYS = [f"{s} {a}" for s in ("남성", "여성") for a in AGES]
MONTH_RE = re.compile(r"(\d{1,2})월\([^)]*\)\s*통합")
# '남성 18~29세   304   309   30%' — 사례수 두 칸 뒤 첫 % 가 '잘하고 있다'.
ROW_RE = re.compile(
    r"(남성|여성)\s*(18~29세|30대|40대|50대|60대|70대\s*이상)"
    r"[^\S\n]+[\d,]+[^\S\n]+[\d,]+[^\S\n]+(\d+)%[^\S\n]+(\d+)%")


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


def annual_pdf(year):
    """그 해 12월에 나오는 '연간 통합' 호. 월별 통합표는 해가 바뀌면 1월부터 다시
    시작하므로, 지난해 10~12월은 이 파일에서만 얻을 수 있다. 없으면 None."""
    url = ANNUAL % year
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, os.path.basename(url))
    if not os.path.exists(path):
        try:
            body = _get(url)
        except Exception:
            return None
        if len(body) < 100_000:      # 없는 해는 빈 껍데기가 200 으로 온다
            return None
        open(path, "wb").write(body)
    return path


def parse(path, section="대통령 직무 수행 평가"):
    """{'2026-01': {'남성 18~29세': [30, 57], ...}, ...}  (비율 두 칸)"""
    txt = subprocess.run(["pdftotext", "-layout", path, "-"],
                         capture_output=True, text=True).stdout
    m = re.search(r"\((\d{4})\d{4}\)", os.path.basename(path))
    year = int(m.group(1)) if m else int(re.search(r"(20\d{2})년", txt).group(1))
    lines = txt.split("\n")
    # '대통령 직무 수행 평가' 월별 통합 구간만. 뒤쪽의 정당 지지도·정치 성향 표에도
    # 같은 모양의 행이 있어서 구간을 자르지 않으면 섞인다.
    # 목차에도 '월별 통합 교차집계표' 라는 글자가 나오고, 뒤쪽 정당 지지도·정치 성향
    # 표에도 같은 제목과 같은 모양의 성/연령별 행이 있다. 그래서 '대통령 직무 수행 평가'
    # 가 바로 뒤따르고 월 머리글이 실제로 들어 있는 첫 구간만 고른다.
    hits = [i for i, l in enumerate(lines) if "월별 통합 교차집계표" in l]
    seg = None
    for n, i in enumerate(hits):
        end = hits[n + 1] if n + 1 < len(hits) else len(lines)
        cand = lines[i:end]
        head = "\n".join(cand[:10])
        if section not in head:
            continue
        if any(MONTH_RE.search(l) for l in cand) and any(ROW_RE.search(l) for l in cand):
            seg = cand
            break
    if seg is None:
        raise SystemExit(f"'{section}' 월별 통합표를 찾지 못했습니다 — 사람이 봐야 합니다.")
    if section == "정당 지지도":
        # 열 순서(더불어민주당, 국민의힘)가 바뀌면 조용히 틀린 값이 들어간다.
        head = "\n".join(seg[:12])
        if "더불어" not in head or "국민의" not in head or head.index("더불어") > head.index("국민의"):
            raise SystemExit("정당 표의 열 순서가 예전과 다릅니다 — 사람이 봐야 합니다.")
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
                got.setdefault(k, []).append((int(m.group(3)), int(m.group(4))))
        for col, mo in enumerate(months):
            vals = {k: v[col] for k, v in got.items() if len(v) > col}
            if len(vals) == 12:
                out[f"{year}-{mo:02d}"] = vals
    return out


def read_months(path, section):
    """최신 호 + (필요하면) 지난해 연간 통합 호를 합쳐 월별 값을 돌려준다."""
    months = parse(path, section)
    if months:
        prev = annual_pdf(int(min(months)[:4]) - 1)
        if prev:
            months = {**parse(prev, section), **months}
    return months


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

    ov = json.load(open(os.path.join(DATA, "overrides.json"), encoding="utf-8"))
    man = json.load(open(os.path.join(DATA, "manual.json"), encoding="utf-8"))
    full = json.load(open(os.path.join(DATA, "full.json"), encoding="utf-8"))
    pool = (man["items"] if isinstance(man, dict) else man) + full["items"]
    cache, touched, fail = {}, [], False
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    for cid, section, keys, col in CHARTS:
        if section not in cache:
            cache[section] = read_months(path, section)
            if not cache[section]:
                raise SystemExit(f"'{section}' 월별 통합표를 읽지 못했습니다 — 사람이 봐야 합니다.")
            print(f"  [{section}] 읽은 달: {min(cache[section])} ~ {max(cache[section])}"
                  f" ({len(cache[section])}개월)")
        months = cache[section]
        base = next((x for x in pool if x.get("id") == cid), None)
        if base is None:
            print(f"  {cid}: 차트를 찾지 못해 건너뜁니다.")
            continue
        it = {**base, **(ov.get(cid) or {})}
        names = [str(x).strip().rstrip(".") for x in it["seriesNames"]]
        want = keys or KEYS
        if names != want:
            print(f"  {cid}: 계열 이름이 예상과 다릅니다 {names} — 건너뜁니다.")
            fail = True
            continue
        labs = list(it["labels"])
        ser = [list(x) for x in it["series"]]

        bad = []
        for j, L in enumerate(labs):
            if L not in months:
                continue
            for i, k in enumerate(names):
                if ser[i][j] != months[L][k][col]:
                    bad.append((L, k, ser[i][j], months[L][k][col]))
        overlap = [L for L in labs if L in months]
        print(f"  {cid} {base.get('title', '').rstrip('.')}: "
              f"겹치는 {len(overlap)}개월 × {len(names)}계열 대조 — " +
              ("일치" if not bad else f"불일치 {len(bad)}건 {bad[:4]}"))
        if bad:
            fail = True
            continue

        new = [L for L in sorted(months) if L not in labs and (not labs or L > labs[-1])]
        if not new:
            print(f"      새로 붙일 달 없음 ({len(labs)}점)")
            continue
        print(f"      붙일 것: {', '.join(new)}")
        if not a.apply:
            continue
        for L in new:
            labs.append(L)
            for i, k in enumerate(names):
                ser[i].append(months[L][k][col])
        o = dict(ov.get(cid) or {})
        o.pop("revised", None)
        o.update({"labels": labs, "series": ser, "unit": "%",
                  "sourceUrl": url, "updated": stamp})
        o.setdefault("source", "한국갤럽 갤럽리포트. 월간 평균. 단위: %.")
        ov[cid] = o
        touched.append((cid, base, new, len(labs)))

    if fail:
        print("\n겹치는 구간이 어긋나거나 양식이 달라진 차트가 있습니다. "
              "그 차트는 붙이지 않았습니다 — 원자료를 사람이 봐야 합니다.")
    if not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)")
        return 1 if fail else 0
    if not touched:
        print("\n붙인 것이 없습니다.")
        return 1 if fail else 0

    json.dump(ov, open(os.path.join(DATA, "overrides.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    cl_path = os.path.join(DATA, "changelog.json")
    cl = json.load(open(cl_path, encoding="utf-8"))
    for cid, base, new, n in touched:
        cl.append({"date": datetime.date.today().isoformat(), "slide": base.get("slide"),
                   "id": cid, "title": base.get("title"), "category": "정치",
                   "mode": "자동 갱신", "n": len(new),
                   "note": "한국갤럽 월별 통합 " + ", ".join(new), "url": url})
        print(f"→ {cid}: {n}점")
    json.dump(cl, open(cl_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("data/overrides.json 반영. 다음: python3 scripts/build.py")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
