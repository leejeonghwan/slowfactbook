#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""뉴욕타임스 분기 실적을 SEC 공시에서 모아 data/nyt_cache.json 에 쌓는다.

  python3 scripts/nyt_fetch.py              # 새 공시만 받아 캐시에 넣는다
  python3 scripts/nyt_fetch.py --all        # 캐시를 버리고 전부 다시 받는다
  python3 scripts/nyt_fetch.py --limit 8    # 한 번에 받을 공시 수(시간 제한 때문)

회사 투자자 페이지는 받아올 수 없어 SEC EDGAR 를 쓴다. 실적 발표는 8-K
항목 2.02 로 올라오고, 첨부 EX-99.1 이 보도자료 전문이다.

보도자료 하나에서 세 군데를 읽는다.
  1) 맨 앞 'Summary of Quarterly Results' — 최근 다섯 분기가 한꺼번에 있다.
     구독자 수, 디지털 전용 구독자, 분기 순증, ARPU, 디지털 구독 매출,
     디지털 광고 매출, 총매출, 영업이익, 이익률.
  2) 각주 (a)(b) — 구독 매출과 광고 매출의 디지털·종이 구분. 해당 분기와
     한 해 전 같은 분기 둘뿐이다. 그래서 공시를 전부 받아야 분기가 이어진다.
  3) 'Supplemental Subscriber' 표 — 구독자 구성. 회사는 2025년 4분기로
     번들·뉴스 전용·기타 단품 구분 공표를 끝냈다.

같은 분기가 여러 공시에 나오므로 겹치는 값이 어긋나면 그 자리는 버리고
기록해 둔다. 회사가 뒤에 수치를 고친 경우와 파싱이 틀린 경우를 구분하려면
사람이 봐야 한다.
"""
import argparse, html as H, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "nyt_cache.json")
CIK = "0000071691"
UA = "slowfactbook/1.0 (contact: top@leejeonghwan.com)"
QRE = re.compile(r"^Q([1-4])\s*(20\d\d)$")


def get(url, tries=3):
    last = ""
    for _ in range(tries):
        r = subprocess.run(["curl", "-sS", "--max-time", "60",
                            "-H", "User-Agent: " + UA, url], capture_output=True)
        if r.returncode == 0 and r.stdout:
            return r.stdout.decode("utf-8", "replace")
        last = r.stderr.decode()[:120]
        time.sleep(1.5)
    raise SystemExit(f"{url} 내려받기 실패: {last}")


RAW = os.path.expanduser("~/.cache/nyt_pressrelease")


def lines(url, acc=None):
    if acc:
        f = os.path.join(RAW, acc + ".txt")
        if os.path.exists(f):
            return open(f, encoding="utf-8").read().split("\n")
    t = get(url)
    t = re.sub(r"<(script|style).*?</\1>", "", t, flags=re.S | re.I)
    x = H.unescape(re.sub(r"<[^>]+>", "\n", t))
    out = []
    for l in (l.strip() for l in x.split("\n")):
        if l and (not out or out[-1] != l):
            out.append(l)
    if acc:
        os.makedirs(RAW, exist_ok=True)
        with open(os.path.join(RAW, acc + ".txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(out))
    return out


def filings():
    """실적 8-K 목록 [(발표일, accession)] — 새것부터."""
    d = json.loads(get(f"https://data.sec.gov/submissions/CIK{CIK}.json"))
    rows, seen = [], set()
    bunches = [d["filings"]["recent"]]
    for f in d["filings"].get("files", []):
        bunches.append(json.loads(get("https://data.sec.gov/submissions/" + f["name"])))
    for r in bunches:
        for i in range(len(r["form"])):
            if r["form"][i] != "8-K":
                continue
            if "2.02" not in (r.get("items") or [""] * len(r["form"]))[i]:
                continue
            acc = r["accessionNumber"][i]
            if acc in seen:
                continue
            seen.add(acc)
            rows.append((r["filingDate"][i], acc))
    rows.sort(reverse=True)
    return rows


def exhibit(acc):
    a = acc.replace("-", "")
    idx = get(f"https://www.sec.gov/Archives/edgar/data/71691/{a}/{acc}-index.html")
    cand = re.findall(r'href="(/Archives/edgar/data/71691/%s/[^"]+\.htm)"' % a, idx)
    pr = [c for c in cand if re.search(r"press|ex99|exhibit|release|ex-99", c, re.I)]
    pick = pr[0] if pr else (cand[0] if cand else None)
    if not pick:
        raise SystemExit(acc + ": 첨부를 찾지 못했습니다.")
    return "https://www.sec.gov" + pick


def num(s):
    s = s.replace(",", "").replace("$", "").replace("%", "").strip()
    if s in ("—", "-", "*", ""):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def read_q_table(seg, wanted):
    """'Q3 2026' 머리글로 시작하는 표에서 {라벨: {분기: 값}}.

    한 줄의 값 개수가 분기 수와 정확히 같을 때만 받는다. 표에 빈 칸이 있으면
    다음 줄의 첫 값을 끌어와 한 칸씩 밀리는데, 그러면 종이 구독자 자리에
    전체 구독자 수가 들어앉는다.
    """
    qi = next((k for k, l in enumerate(seg) if QRE.match(l)), None)
    if qi is None:
        return {}
    qs = []
    while qi + len(qs) < len(seg) and QRE.match(seg[qi + len(qs)]):
        m = QRE.match(seg[qi + len(qs)])
        qs.append(f"{m.group(2)}-Q{m.group(1)}")
    out, name, buf = {}, None, []

    def flush():
        if name and len(buf) == len(qs):
            out.setdefault(name, dict(zip(qs, buf)))

    for l in seg[qi + len(qs):]:
        if re.fullmatch(r"(\([a-z0-9]\)){1,4}", l):
            continue
        v = num(l)
        if v is not None and not re.search(r"[A-Za-z]{3}", l):
            buf.append(v)
        elif re.search(r"[A-Za-z]", l):
            flush()
            if l.startswith("The sum of") or l.startswith("ARPU metrics"):
                return out
            key = next((w for w in wanted if re.fullmatch(w, l, re.I)), None)
            name, buf = (key or None), []
    flush()
    return out


def two_col(seg, labels):
    """각주 표: 라벨 뒤 '해당분기, 전년동기' 두 값만 집어 온다."""
    out, name, buf = {}, None, []
    for l in seg:
        if re.fullmatch(r"(\([a-z0-9]\)){1,4}", l):
            continue
        v = num(l)
        if v is not None and not re.search(r"[A-Za-z]{3}", l):
            buf.append(v)
            if name and len(buf) >= 2:
                out.setdefault(name, buf[:2])
                name, buf = None, []
        elif re.search(r"[A-Za-z]", l):
            key = next((k for k in labels if re.fullmatch(labels[k], l, re.I)), None)
            name, buf = (key or None), []
    return out


SWEEP = {
    "subs_total": r"Total subscribers",
    "subs_digital": r"(Total )?Digital-only subscribers",
    "subs_print": r"Print subscribers",
    "net_adds_digital": r"(Digital-only subscribers )?(quarterly )?net additions",
    "arpu_digital": r"(Total )?Digital-only (subscriber )?ARPU",
    "rev_sub_digital": r"Digital-only subscription revenues?",
    "rev_ad_digital": r"Digital advertising revenues?",
    "rev_total": r"Total revenues",
    "cost_total": r"Total operating costs",
    "cost_adj": r"Adjusted operating costs",
    "op_profit": r"Operating profit",
    "op_margin": r"Operating profit margin %",
    "aop": r"Adjusted operating profit( \(.AOP.\))?",
    "eps": r"Diluted EPS|Diluted earnings per share \(.EPS.\)",
}
# 값의 크기로 자리를 잘못 읽은 것을 걸러낸다. 구독자 표 바로 뒤에 ARPU 표가
# 오는 해가 있어, 라벨만 믿으면 ARPU 를 구독자 수로 집어 온다.
RANGE = {"subs_total": (100, 1e5), "subs_digital": (100, 1e5),
         "subs_print": (100, 1e5), "net_adds_digital": (1, 5000),
         "arpu_digital": (1, 50), "op_margin": (-50, 60),
         "rev_total": (100, 3000), "rev_sub_digital": (10, 2000),
         "rev_ad_digital": (10, 2000), "cost_total": (100, 3000),
         "cost_adj": (100, 3000), "op_profit": (0.5, 600),
         "aop": (0.5, 600), "eps": (-5, 5)}
STMT = {"rev_sub": r"Subscription",
        "rev_ad": r"Advertising",
        "rev_other": r"Affiliate, licensing and other|Other",
        "rev_total": r"Total revenues",
        "cost_total": r"Total operating costs",
        "op_profit": r"Operating profit"}
FOOT_SUB = {"rev_sub_digital": r"Digital-only subscription revenues",
            "rev_sub_print": r"Print subscription revenues",
            "rev_sub": r"Total subscription revenues"}
FOOT_AD = {"rev_ad_digital": r"Digital advertising revenues",
           "rev_ad_print": r"Print advertising revenues",
           "rev_ad": r"Total advertising revenues"}


def quarter_of(L, date=None):
    """보도자료가 다루는 분기.

    공시일이 가장 믿을 만하다. 2월 공시는 전해 4분기, 5월은 1분기, 8월은
    2분기, 11월은 3분기다. 제목은 시대에 따라 어순이 달라
    ('Reports Third-Quarter 2026' 와 'Reports 2018 Fourth-Quarter')
    제목만 믿으면 본문의 전년 동기를 집어 온다. 그래서 공시일로 정하고
    제목으로 맞는지만 확인한다.
    """
    want = {"first": 1, "second": 2, "third": 3, "fourth": 4}
    byname = None
    for l in L[:40]:
        m = re.search(r"Reports (?:(20\d\d) )?(First|Second|Third|Fourth)[- ]Quarter"
                      r"(?: and Full[- ]Year)?(?: (20\d\d))?", l, re.I)
        if m:
            y = m.group(1) or m.group(3)
            if y:
                byname = f"{y}-Q{want[m.group(2).lower()]}"
            break
    if not date:
        return byname
    y, mo = int(date[:4]), int(date[5:7])
    bydate = f"{y - 1}-Q4" if mo <= 3 else f"{y}-Q{(mo - 1) // 3}"
    if byname and byname != bydate:
        print(f"    ※ 제목({byname})과 공시일({bydate})이 어긋납니다 — 공시일을 씁니다")
    return bydate


def prev_year(q):
    y, k = q.split("-Q")
    return f"{int(y) - 1}-Q{k}"


def parse(url, date=None, acc=None):
    """보도자료 한 건에서 {분기: {항목: 값}}. 매출과 이익은 100만 달러."""
    L = lines(url, acc)
    q = quarter_of(L, date)
    if not q:
        return None, {}
    out = {}

    def put(qq, key, val):
        # 먼저 넣은 쪽이 이긴다. 그래서 정밀한 표를 앞에서 읽는다.
        if val is not None:
            out.setdefault(qq, {}).setdefault(key, val)

    def put2(key, pair, scale=1.0):
        put(q, key, pair[0] * scale if pair[0] is not None else None)
        put(prev_year(q), key, pair[1] * scale if pair[1] is not None else None)

    # 1) 손익계산서. 천 달러 단위이고 반올림이 없다. 해당 분기와 한 해 전
    #    같은 분기 두 열. 첨부 목록에도 같은 제목이 있어 대문자 줄만 본다.
    for i in [k for k, l in enumerate(L)
              if l == l.upper() and "CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS" in l]:
        got = two_col(L[i:i + 160], STMT)
        for key, pair in got.items():
            put2(key, pair, 1 / 1000.0)
        if "rev_total" in got:
            break

    # 2) 각주 (a)(b). 구독과 광고의 디지털·종이 구분. 천 달러 단위.
    for labels in (FOOT_SUB, FOOT_AD):
        anchor = list(labels.values())[0]
        i = next((k for k, l in enumerate(L)
                  if re.fullmatch(anchor, l, re.I) and k > len(L) // 3), None)
        if i is None:
            continue
        for key, pair in two_col(L[i - 3:i + 40], labels).items():
            put2(key, pair, 1 / 1000.0)

    # 3) 분기 머리글('Q3 2026')이 붙은 표를 전부 훑는다. 해에 따라 섹션
    #    제목이 'SUPPLEMENTAL SUBSCRIBER' 가 아니라 'FOOTNOTES' 아래 있거나
    #    제목이 없기도 해서, 제목으로 찾으면 2022년 이전이 통째로 빠진다.
    heads = [k for k, l in enumerate(L)
             if QRE.match(l) and (k == 0 or not QRE.match(L[k - 1]))]
    for k in heads:
        for name, by_q in read_q_table(L[k:k + 300], list(SWEEP.values())).items():
            key = next(kk for kk, v in SWEEP.items() if v == name)
            lo, hi = RANGE.get(key, (-1e12, 1e12))
            for qq, v in by_q.items():
                if v is None or not (lo <= abs(v) <= hi if key in RANGE else True):
                    continue
                put(qq, key, v)
    return q, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=8)
    # 2017년 이전 보도자료는 표 모양이 달라 분기 시계열을 못 세운다. 구독 매출을
    # 'Circulation' 으로 쓰던 시절이고 구독자 표도 없다.
    ap.add_argument("--since", default="2017-01-01")
    a = ap.parse_args()

    cache = {"filings": {}, "conflicts": []}
    if os.path.exists(CACHE) and not a.all:
        cache = json.load(open(CACHE, encoding="utf-8"))
    cache.setdefault("filings", {})
    cache.setdefault("conflicts", [])

    todo = [(d, acc) for d, acc in filings()
            if acc not in cache["filings"] and d >= a.since]
    print(f"받을 공시 {len(todo)}건 (캐시에 {len(cache['filings'])}건)")
    for d, acc in todo[:a.limit]:
        u = exhibit(acc)
        q, got = parse(u, d, acc)
        n = sum(len(v) for v in got.values())
        if not n:
            print(f"  {d} {acc} — 값이 없어 건너뜁니다(실적 발표가 아닌 8-K)")
            cache["filings"][acc] = {"date": d, "url": u, "quarter": None, "data": {}}
            time.sleep(0.3)
            continue
        cache["filings"][acc] = {"date": d, "url": u, "quarter": q, "data": got}
        print(f"  {d} {acc} {q} — 분기 {len(got)}개, 항목 {n}개")
        time.sleep(0.3)
    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    rest = len(todo) - min(len(todo), a.limit)
    print(f"-> {CACHE} ({len(cache['filings'])}건). 남은 공시 {rest}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
