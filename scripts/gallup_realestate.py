#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국갤럽 데일리 오피니언 '부동산 정책 평가와 집값·임대료 전망 – 최근 10년' 표
→ 향후 1년 집값 전망 시계열.

  python3 scripts/gallup_realestate.py            # 미리보기
  python3 scripts/gallup_realestate.py --apply
  python3 scripts/gallup_realestate.py --file 받아둔.pdf

갤럽은 부동산 문항을 돌릴 때마다 이 표를 10년 치 통째로 다시 싣는다. 그래서 한
번 받으면 수십 개 시점이 겹치고, 전수 대조가 공짜로 된다. 한 시점이라도 어긋나면
붙이지 않고 멈춘다 — 양식이 바뀌었을 때 조용히 틀린 값이 들어가는 것이 가장 나쁘다.

표는 아홉 칸(정책 긍정·부정·순지수, 집값 상승·하락·순지수, 임대료 상승·하락·순지수)
인데 빈 칸이 많아서, 토큰을 세는 대신 pdftotext -layout 이 지켜 주는 '글자 자리'로
어느 칸인지 가린다. 머리글의 ⓐ ⓑ ⓐ-ⓑ 자리를 읽어 경계를 잡는다.
오른쪽 주석에 '금리 3.25%' 같은 숫자가 섞여 있어 칸 밖은 버린다.
"""
import argparse, datetime, json, os, re, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, ".cache", "gallup")
LIST = "https://www.gallup.co.kr/gallupdb/report.asp"
CONTENT = "https://www.gallup.co.kr/gallupdb/reportContent.asp?seqNo=%s&bType=8"
PDF_RE = re.compile(r"https://www\.gallup\.co\.kr/dir/GallupKoreaDaily/"
                    r"GallupKoreaDailyOpinion_(\d+)\((\d{8})\)\.pdf")
TITLE = "부동산 정책 평가와 집값"
SLIDE = "manual-gallup-house-outlook"
KST = datetime.timezone(datetime.timedelta(hours=9))


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 slowfactbook"})
    return urllib.request.urlopen(req, timeout=60).read()


def latest_pdf():
    """목록을 훑어 이 표가 실린 가장 최근 호 PDF 를 받아 캐시 경로를 돌려준다."""
    html = _get(LIST).decode("euc-kr", "replace")
    os.makedirs(CACHE, exist_ok=True)
    for seq, title in re.findall(r"fn_viewContents\('(\d+)'\);[^>]*>(.*?)</a>", html, re.S):
        if "데일리 오피니언" not in re.sub("<[^>]+>", "", title):
            continue
        m = PDF_RE.search(_get(CONTENT % seq).decode("euc-kr", "replace"))
        if not m:
            continue
        path = os.path.join(CACHE, os.path.basename(m.group(0)))
        if not os.path.exists(path):
            open(path, "wb").write(_get(m.group(0)))
        if TITLE in text_of(path):
            return path, int(m.group(1))
    raise SystemExit("부동산 표가 실린 호를 목록에서 찾지 못했습니다.")


def text_of(path):
    return subprocess.run(["pdftotext", "-layout", path, "-"],
                          capture_output=True, text=True, check=True).stdout


def parse(txt):
    """{'YYYY-MM': (상승, 하락)} — 향후 1년 집값 전망."""
    lines = txt.split("\n")
    start = next(i for i, s in enumerate(lines) if TITLE in s)
    head = next(s for s in lines[start:start + 6] if "ⓐ" in s)
    cols = [m.start() for m in re.finditer(r"ⓐ|ⓑ", head)]   # 집값 상승·하락, 임대료 상승·하락
    lo, hi = cols[0] - 4, cols[1] + 4                       # 집값 두 칸만 쓴다
    out, year = {}, None
    for s in lines[start + 1:]:
        if s.strip().startswith("- 전국 유권자"):
            break
        d = re.sub(r"\[[^\]]*\]", " ", s)                   # [문재인] 같은 꼬리표를 걷는다
        ym = re.match(r"\s*(?:(20\d\d)\s*\.)?\s*(\d{1,2})\s*\.", d)
        if not ym:
            continue
        year = ym.group(1) or year
        if not year:
            continue
        key = "%s-%02d" % (year, int(ym.group(2)))
        cells = [(m.start(), int(m.group(1)))
                 for m in re.finditer(r"(\d+)%", s) if lo <= m.start() <= hi]
        if len(cells) != 2:
            continue
        out[key] = (cells[0][1], cells[1][1])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--file")
    a = ap.parse_args()

    if a.file:
        path, no = a.file, None
    else:
        path, no = latest_pdf()
    got = parse(text_of(path))
    if not got:
        raise SystemExit("표를 읽지 못했습니다. 양식이 바뀌었는지 보십시오.")

    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8"))
    cur = next((i for i in doc["items"] if i.get("slide") == SLIDE), None)
    old = dict(zip((cur or {}).get("labels") or [],
                   zip(*((cur or {}).get("series") or [[], []]))))

    bad = [k for k in sorted(set(old) & set(got)) if tuple(old[k]) != got[k]]
    if bad:
        for k in bad[:10]:
            print("  어긋남 %s: 차트 %s / PDF %s" % (k, tuple(old[k]), got[k]))
        raise SystemExit("겹치는 시점이 어긋나 멈춥니다(%d개)." % len(bad))
    print("  겹치는 시점 %d개 대조 — 일치" % len(set(old) & set(got)))
    print("  새로 붙일 시점: %s" % (sorted(set(got) - set(old)) or "없음"))

    keys = sorted(got)
    item = {
        "slide": SLIDE,
        "title": "향후 1년 집값 전망",
        "category": "부동산",
        "source": ("한국갤럽 데일리 오피니언%s. 전국 유권자 약 1,000명 전화조사. "
                   "'비슷할 것'과 의견 유보를 뺀 수치여서 둘을 더해도 100이 되지 않는다. "
                   "단위: %%." % (" 제%d호" % no if no else "")),
        "sourceUrl": "https://www.gallup.co.kr/gallupdb/reportContent.asp?seqNo=1665",
        "vizType": "line",
        "unit": "%",
        "labels": keys,
        "seriesNames": ["오를 것", "내릴 것"],
        "series": [[got[k][0] for k in keys], [got[k][1] for k in keys]],
        "seriesColors": ["#c0322f", "#2a5ca8"],
        "updated": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
    }
    if cur:
        item["id"] = cur.get("id", item.get("id"))
        item = {k: v for k, v in item.items() if v is not None}
        doc["items"][doc["items"].index(cur)] = item
    else:
        doc["items"].append(item)
    if a.apply:
        with open(mp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print("-> data/manual.json 에 반영했습니다. (%d시점)" % len(keys))
    else:
        print("\n(미리보기입니다. 반영하려면 --apply)")


if __name__ == "__main__":
    main()
