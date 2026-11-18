#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""엔비디아 분기 매출과 영업이익(c1140).

  python3 scripts/nvidia_quarters.py            # 미리보기
  python3 scripts/nvidia_quarters.py --apply

미국 증권거래위원회 전자공시(EDGAR)에서 받는다.

  분기 숫자   companyconcept API 의 Revenues 와 OperatingIncomeLoss
  최근 분기   실적 발표 8-K(항목 2.02)에 붙는 보도자료의 손익계산서

분기보고서는 분기가 끝난 뒤 한참 있다 올라오므로, 실적 발표는 났는데 공시는
아직인 구간이 생긴다. 그 구간을 보도자료로 메운다. 분기보고서가 올라오면
companyconcept 쪽이 같은 값을 주고 보도자료 몫은 쓰이지 않는다.

회계연도 4분기는 따로 공시되지 않는다. 연간값에서 3분기 누계를 빼 되돌린다.
통신 3사(telecom_results.py)와 같은 방식이다.

라벨은 분기가 끝난 달이 속한 달력 분기다. 엔비디아 회계연도는 1월 말에
끝나므로 회계연도 표기와 한 분기쯤 어긋난다. 2026년 10월 25일에 끝난 분기는
회사 기준으로 2027회계연도 3분기이고 이 차트에서는 2026-Q4다.
"""
import argparse, datetime, json, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
CIK = "0001045810"
NUM = CIK.lstrip("0")
UA = re.search(r'^UA = "(.+)"',
               open(os.path.join(HERE, "nyt_fetch.py"), encoding="utf-8").read(),
               re.M).group(1)
URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=NVDA&type=8-K"


def get(u):
    r = subprocess.run(["curl", "-sS", "--max-time", "120", "--compressed",
                        "-H", "User-Agent: " + UA, u], capture_output=True)
    if r.returncode:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    return r.stdout.decode("utf-8", "replace")


def days(a, b):
    return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days


def concept(tag):
    d = json.loads(get(f"https://data.sec.gov/api/xbrl/companyconcept/"
                       f"CIK{CIK}/us-gaap/{tag}.json"))
    if "units" not in d:
        raise SystemExit(f"{tag} 응답에 units 가 없습니다: {str(d)[:140]}")
    q, nine, year = {}, {}, {}
    for x in d["units"]["USD"]:
        s, e, v = x.get("start"), x.get("end"), x["val"]
        if not s:
            continue
        n = days(s, e)
        if 80 <= n <= 100:
            q[e] = v
        elif 255 <= n <= 285:
            nine[e] = v
        elif 355 <= n <= 375:
            year[e] = v
    return q, nine, year


def label(end):
    d = datetime.date.fromisoformat(end)
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def press():
    """가장 최근 실적 발표 8-K 의 보도자료에서 분기 손익을 읽는다."""
    sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{CIK}.json"))
    r = sub["filings"]["recent"]
    hit = None
    for f, dt, acc, items in zip(r["form"], r["filingDate"],
                                 r["accessionNumber"], r["items"]):
        if f == "8-K" and "2.02" in (items or ""):
            hit = (dt, acc.replace("-", ""))
            break
    if not hit:
        return None
    dt, acc = hit
    idx = get(f"https://www.sec.gov/Archives/edgar/data/{NUM}/{acc}/")
    cand = [f for f in sorted(set(re.findall(r'href="[^"]*/(\S+?\.htm)"', idx)))
            if re.fullmatch(r"q\dfy\d+pr\.htm", f)]
    if not cand:
        return None
    t = get(f"https://www.sec.gov/Archives/edgar/data/{NUM}/{acc}/{cand[0]}")
    x = re.sub(r"<[^>]+>", " ", t).replace("&#160;", " ").replace("&nbsp;", " ")
    x = re.sub(r"\s+", " ", x)
    i = x.find("CONDENSED CONSOLIDATED STATEMENTS OF INCOME")
    if i < 0:
        return None
    seg = x[i:i + 1200]
    # 표 머리에서는 월과 연도가 서로 다른 줄에 있다.
    #   "Three Months Ended Nine Months Ended October 25, October 26, ... 2026 2025 ..."
    # 그래서 월 토막과 연도 토막을 따로 모아 첫 짝을 쓴다.
    head = seg[:500]
    mons = re.findall(r"([A-Z][a-z]+ \d{1,2}),", head)
    yrs = re.findall(r"\b(20\d{2})\b", head)
    end = None
    if mons and yrs:
        try:
            end = datetime.datetime.strptime(f"{mons[0]} {yrs[0]}",
                                             "%B %d %Y").date().isoformat()
        except ValueError:
            end = None
    def num(key):
        mm = re.search(key + r"\s+\$?\s*([\d,]+)", seg)
        return int(mm.group(1).replace(",", "")) * 1_000_000 if mm else None
    rev, op = num("Revenue"), num("Operating income")
    if not (end and rev and op):
        return None
    return {"end": end, "rev": rev, "op": op, "date": dt, "file": cand[0]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    rq, rn, ry = concept("Revenues")
    oq, on, oy = concept("OperatingIncomeLoss")
    print(f"  공시 분기 매출 {len(rq)}개, 영업이익 {len(oq)}개")

    # 회계연도 4분기 되돌리기: 연간 - 3분기 누계
    for q, nine, year, nm in ((rq, rn, ry, "매출"), (oq, on, oy, "영업이익")):
        back = 0
        for e, v in sorted(year.items()):
            if e in q:
                continue
            prev = [x for x in nine if days(x, e) and 85 <= days(x, e) <= 100]
            if not prev:
                continue
            q[e] = round(v - nine[prev[0]], 0)
            back += 1
        if back:
            print(f"    {nm}: 회계연도 4분기 {back}개를 연간에서 되돌렸습니다")

    pr = press()
    if pr:
        tag = "새로" if pr["end"] not in rq else "이미 있음"
        print(f"    보도자료({pr['date']}, {pr['file']}): {pr['end']} "
              f"매출 {pr['rev']/1e6:,.0f} 영업이익 {pr['op']/1e6:,.0f} 백만 달러 [{tag}]")
        for d, v in ((rq, pr["rev"]), (oq, pr["op"])):
            if pr["end"] in d and abs(d[pr["end"]] - v) > max(1e6, abs(v) * 0.002):
                raise SystemExit(f"보도자료와 공시가 어긋납니다: {pr['end']} "
                                 f"{d[pr['end']]:,} 대 {v:,}")
        rq.setdefault(pr["end"], pr["rev"])
        oq.setdefault(pr["end"], pr["op"])

    ends = sorted(set(rq) & set(oq))
    if len(ends) < 40:
        raise SystemExit(f"분기가 {len(ends)}개뿐입니다.")
    labs = [label(e) for e in ends]
    if len(set(labs)) != len(labs):
        dup = [x for x in set(labs) if labs.count(x) > 1]
        raise SystemExit(f"라벨이 겹칩니다: {dup[:4]}")

    # 검산. 차트에 있던 값과 대조
    base = {}
    for f in ("full.json", "manual.json", "api.json"):
        p = os.path.join(DATA, f)
        if not os.path.exists(p):
            continue
        for i in json.load(open(p, encoding="utf-8"))["items"]:
            if i.get("id"):
                base.setdefault(i["id"], {}).update(i)
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    cur = {**base.get("c1140", {}), **(ov.get("c1140") or {})}
    new = {l: (rq[e] / 1e6, oq[e] / 1e6) for l, e in zip(labs, ends)}
    bad, seen = [], 0
    for idx, nm in ((0, "매출"), (1, "영업이익")):
        for l, v in zip([str(x) for x in cur["labels"]], cur["series"][idx]):
            if v is None or l not in new:
                continue
            seen += 1
            if abs(new[l][idx] - v) > max(1, abs(v) * 0.0005):
                bad.append((nm, l, v, round(new[l][idx])))
    print(f"    검산 기존 값: {seen}칸 중 {seen - len(bad)}칸 일치")
    for b in bad:
        print(f"      바로잡음 {b[0]} {b[1]}: {b[2]:,.0f} -> {b[3]:,.0f}")
    if len(bad) > seen * 0.05:
        raise SystemExit(f"기존 값과 너무 많이 어긋납니다({len(bad)}/{seen}).")

    rev = [round(rq[e] / 1e6) for e in ends]
    op = [round(oq[e] / 1e6) for e in ends]
    last, prev = labs[-1], labs[-5] if len(labs) > 5 else labs[0]
    loss = [(l, v) for l, v in zip(labs, op) if v < 0]
    out = {"c1140": {
        "id": "c1140", "title": "엔비디아 매출과 영업이익",
        "vizType": "column", "unit": "백만 달러", "yMin": 0,
        "labels": labs, "series": [rev, op],
        "seriesNames": ["매출", "영업이익"],
        "seriesColors": ["#2a5ca8", "#6a8f3c"],
        "source": (f"미국 증권거래위원회 전자공시(EDGAR). 엔비디아 분기 실적. "
                   f"{labs[0]}~{labs[-1]}. 단위: 백만 달러."),
        "sourceUrl": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={CIK}&type=8-K",
        "notes": [
            f"{last.replace('-Q', '년 ')}분기 매출 {rev[-1]:,}백만 달러, 영업이익 "
            f"{op[-1]:,}백만 달러입니다. 영업이익률 {op[-1]/rev[-1]*100:.0f}%입니다. "
            f"한 해 전 같은 분기({prev.replace('-Q', '년 ')}분기)의 "
            f"{rev[-5]:,}백만 달러에서 {rev[-1]/rev[-5]:.1f}배가 됐습니다.",
            "라벨은 분기가 끝난 달이 속한 달력 분기입니다. 엔비디아 회계연도는 1월 "
            "말에 끝나므로 회사가 쓰는 회계연도 표기와 한 분기쯤 어긋납니다. 이 "
            f"차트의 {last} 는 회사 기준으로 2027회계연도 3분기입니다.",
            "영업이익은 회계기준(GAAP) 값입니다. 회사가 함께 발표하는 조정 "
            "영업이익(non-GAAP)은 이보다 큽니다. 순이익과도 다릅니다.",
            "회계연도 4분기는 따로 공시되지 않아 연간값에서 3분기 누계를 빼 "
            "되돌렸습니다.",
            ("세로축 바닥을 0에 고정했습니다. 그래서 영업이익이 적자였던 "
             f"{len(loss)}개 분기가 0으로 보입니다. "
             + ", ".join(f"{l.replace('-Q', '년 ')}분기 {v:,}" for l, v in loss)
             + "백만 달러였습니다. 지금 분기의 "
             f"{op[-1]:,}과 견주면 화면에서 구분되지 않는 크기입니다."
             ) if loss else
            "세로축 바닥을 0에 고정했습니다.",
            "가장 최근 분기는 분기보고서가 아직 올라오지 않아 실적 발표 보도자료의 "
            "손익계산서에서 가져왔습니다. 보고서가 올라오면 공시값으로 바뀝니다.",
        ],
        "updated": ymd,
    }}
    print(f"\n  c1140 {len(labs)}분기 {labs[0]}~{labs[-1]}")
    print(f"    매출     {rev[0]:,} ... {rev[-1]:,}")
    print(f"    영업이익  {op[0]:,} ... {op[-1]:,}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
        return 0
    for cid, o in out.items():
        ov.setdefault(cid, {}).update(o)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
