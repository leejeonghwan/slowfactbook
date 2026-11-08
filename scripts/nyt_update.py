#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""뉴욕타임스 분기 실적 차트. data/nyt_cache.json 을 읽어 여섯 장을 세운다.

  python3 scripts/nyt_fetch.py       # 먼저 공시를 받아 캐시에 쌓는다
  python3 scripts/nyt_update.py      # 미리보기
  python3 scripts/nyt_update.py --apply

손보는 차트
  c1667 유료 구독(분기)        전체·디지털 전용·종이 세 줄로 늘린다
  c1476 분기 순증              뉴스 구독 기준에서 디지털 전용 기준으로 갈아탄다
새로 만드는 차트
  분기 매출 구성 / 분기 영업이익과 이익률 / 디지털 구독자당 매출

기준을 갈아타는 이유. 회사가 2025년 4분기 보도자료에 이렇게 적었다.
"Following the fourth quarter of 2025 ... we will discontinue reporting
digital-only subscribers and ARPU by the categories of bundle and
multiproduct, news-only, and other single product." c1476 이 그리던
'번들과 뉴스 전용을 더한 수의 순증' 은 2026년 1분기부터 공표되지 않는다.
c1480 도 같은 지표였지만 c1667 과 겹쳐 이미 내려간 차트여서 손대지 않는다.

같은 분기가 공시 여러 건에 나오므로 겹치는 값을 전부 대조한다. 어긋나면
늦게 낸 공시(재작성된 값)를 쓰되, 차이가 크면 쓰지 않고 멈춘다. 2017년
영업이익은 연금 회계 개정(ASU 2017-07)을 거꾸로 적용해 100만 달러 남짓
어긋나므로 이익 차트는 2018년 1분기부터 그린다.
"""
import argparse, collections, datetime, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
SRC_URL = "https://www.nytco.com/investors/"

SUBS, ADDS = "c1667", "c1476"
SL_REV = "manual-nyt-revenue-mix"
SL_OP = "manual-nyt-operating-profit"
SL_ARPU = "manual-nyt-arpu"

BLUE, LBLUE, RED, GRAY, ORANGE = "#2f5e8e", "#7bb0e0", "#c0322f", "#aaaaaa", "#e8820c"


def load():
    """{분기: {항목: 값}} — 겹치는 값은 대조하고 늦은 공시를 쓴다."""
    c = json.load(open(os.path.join(DATA, "nyt_cache.json"), encoding="utf-8"))
    bag = collections.defaultdict(lambda: collections.defaultdict(list))
    for acc, f in c["filings"].items():
        for q, d in (f.get("data") or {}).items():
            for k, v in d.items():
                bag[q][k].append((f["date"], v))
    out, clash = {}, []
    for q in bag:
        for k, pairs in bag[q].items():
            vs = [v for _, v in pairs]
            lo, hi = min(vs), max(vs)
            # 요약표는 0.1 단위로 반올림돼 있어 그만큼은 봐 준다.
            if hi - lo > max(0.06, abs(hi) * 0.0016):
                clash.append((q, k, sorted(set(round(v, 3) for v in vs))))
            out.setdefault(q, {})[k] = sorted(pairs)[-1][1]
    return out, clash


def qlist(d, first, last):
    """first~last 사이 분기 라벨을 빠짐없이."""
    def nxt(q):
        y, k = int(q[:4]), int(q[-1])
        return f"{y + 1}-Q1" if k == 4 else f"{y}-Q{k + 1}"
    out, q = [], first
    while True:
        out.append(q)
        if q == last:
            return out
        q = nxt(q)
        if q > last + "z":
            raise SystemExit(f"{first}~{last} 분기 목록을 못 만들었습니다.")


def prev(q):
    y, k = int(q[:4]), int(q[-1])
    return f"{y - 1}-Q4" if k == 1 else f"{y}-Q{k - 1}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    D, clash = load()
    qs = sorted(D)
    last = qs[-1]
    print(f"캐시 {qs[0]} ~ {last} ({len(qs)}개 분기)")

    # ── 1) 종이 구독자를 전체에서 디지털 전용을 빼서 구한다. 회사가 표에 적는
    #    해도 있고 칸을 비우는 해도 있어, 적힌 해로 계산이 맞는지 확인한다.
    chk = []
    for q in qs:
        d = D[q]
        if "subs_total" in d and "subs_digital" in d:
            der = round(d["subs_total"] - d["subs_digital"])
            if "subs_print" in d and abs(der - d["subs_print"]) > 10:
                chk.append((q, d["subs_print"], der))
            d["subs_print_calc"] = der
    if chk:
        raise SystemExit(f"종이 구독자 계산이 공표값과 어긋납니다: {chk[:5]}")
    npub = sum(1 for q in qs if "subs_print" in D[q])
    print(f"  종이 구독자: 공표된 {npub}개 분기 모두 '전체 - 디지털 전용' 과 일치")

    # ── 2) 분기 순증을 디지털 전용 구독자의 차이로 구한다. 공표된 순증과
    #    맞는지 확인한다. 구독자 수는 만 명 단위로 끊어 발표하므로 딱 맞아야 한다.
    chk = []
    for q in qs:
        p = prev(q)
        if p in D and "subs_digital" in D[p] and "subs_digital" in D[q]:
            der = round(D[q]["subs_digital"] - D[p]["subs_digital"])
            if "net_adds_digital" in D[q] and abs(der - D[q]["net_adds_digital"]) > 10:
                chk.append((q, D[q]["net_adds_digital"], der))
            D[q]["net_adds_calc"] = der
    if chk:
        raise SystemExit(f"분기 순증 계산이 공표값과 어긋납니다: {chk[:5]}")
    npub = sum(1 for q in qs if "net_adds_digital" in D[q])
    print(f"  분기 순증: 공표된 {npub}개 분기 모두 디지털 전용 구독자 차이와 일치")

    # ── 3) 종이 매출을 전체에서 디지털을 빼서 구한다.
    for tag in ("sub", "ad"):
        chk = []
        for q in qs:
            d = D[q]
            if f"rev_{tag}" in d and f"rev_{tag}_digital" in d:
                der = round(d[f"rev_{tag}"] - d[f"rev_{tag}_digital"], 3)
                if f"rev_{tag}_print" in d and abs(der - d[f"rev_{tag}_print"]) > 0.6:
                    chk.append((q, d[f"rev_{tag}_print"], der))
                d[f"rev_{tag}_print_calc"] = der
        if chk:
            raise SystemExit(f"{tag} 종이 매출 계산이 어긋납니다: {chk[:5]}")
        npub = sum(1 for q in qs if f"rev_{tag}_print" in D[q])
        print(f"  종이 {tag} 매출: 공표된 {npub}개 분기 모두 '전체 - 디지털' 과 일치")

    # ── 4) 매출 다섯 갈래를 더하면 총매출이 되어야 한다.
    chk = []
    for q in qs:
        d = D[q]
        parts = ["rev_sub_digital", "rev_sub_print_calc", "rev_ad_digital",
                 "rev_ad_print_calc", "rev_other"]
        if all(p in d for p in parts) and "rev_total" in d:
            s = sum(d[p] for p in parts)
            if abs(s - d["rev_total"]) > 0.6:
                chk.append((q, round(s, 2), d["rev_total"]))
    if chk:
        raise SystemExit(f"매출 갈래의 합이 총매출과 어긋납니다: {chk[:5]}")

    # ── 5) 영업이익률이 영업이익 / 총매출과 맞아야 한다.
    chk = []
    for q in qs:
        d = D[q]
        if "op_margin" in d and "op_profit" in d and "rev_total" in d:
            m = d["op_profit"] / d["rev_total"] * 100
            if abs(m - d["op_margin"]) > 0.12:
                chk.append((q, d["op_margin"], round(m, 2)))
    if chk:
        raise SystemExit(f"영업이익률이 어긋납니다: {chk[:5]}")
    print("  매출 갈래 합계, 영업이익률 검산 통과")

    # ── 어긋난 자리 보고. 쓰려는 구간에 걸리면 멈춘다.
    WINDOWS = {"subs_total": "2021-Q1", "subs_digital": "2021-Q1",
               "arpu_digital": "2021-Q1", "rev_sub_digital": "2021-Q3",
               "rev_ad_digital": "2021-Q3", "rev_other": "2021-Q3",
               "rev_total": "2018-Q1", "op_profit": "2018-Q1"}
    hit = [x for x in clash if x[1] in WINDOWS and x[0] >= WINDOWS[x[1]]]
    print(f"  겹치는 값이 어긋난 자리 {len(clash)}곳 (쓰려는 구간 안 {len(hit)}곳)")
    for q, k, vs in sorted(clash):
        print(f"    {q} {k}: {vs}" + ("  ※ 쓰려는 구간" if (q, k, vs) in hit else ""))
    if hit:
        raise SystemExit("쓰려는 구간에 어긋난 값이 있습니다 — 쓰지 않습니다.")

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    full = {}
    for f in ("full.json", "manual.json"):
        for i in json.load(open(os.path.join(DATA, f), encoding="utf-8"))["items"]:
            if i.get("id"):
                full.setdefault(i["id"], {}).update(i)
    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    SURVEY = ("원천은 회사가 SEC 에 올리는 실적 발표(8-K 항목 2.02)의 보도자료 "
              "전문입니다. 회사 투자자 페이지는 기계가 받아올 수 없어 SEC 공시를 "
              "씁니다. 보도자료 한 건에 최근 다섯 분기가 담기고 각주에 디지털과 "
              "종이 구분이 있어, 같은 분기가 공시 여러 건에 나옵니다. 겹치는 값은 "
              "전부 대조하고 어긋나면 쓰지 않습니다.")
    BASIS = ("2022년부터 회사가 집계 기준을 '구독 건수(subscriptions)' 에서 "
             "'구독자 수(subscribers)' 로 바꿨습니다. 번들 하나는 구독 건수로는 "
             "여럿, 구독자 수로는 한 명입니다. 그래서 두 기준의 수치를 한 선으로 "
             "이으면 2021년 말에 없는 급락이 생깁니다.")
    DISC = ("회사가 2025년 4분기 보도자료에서 구독자 공표 방식을 줄이겠다고 "
            "밝혔습니다. 디지털 전용 구독자와 ARPU 총계는 계속 내지만, 번들과 "
            "다중상품, 뉴스 전용, 기타 단품으로 나눈 수와 ARPU 는 2026년 1분기부터 "
            "내지 않습니다. 그래서 '뉴스를 보는 구독자' 기준으로는 더 이을 수 "
            "없고, 회사가 계속 내는 디지털 전용 기준으로 갈아탔습니다.")
    ROUND = ("구독자 수는 회사가 만 명 단위로 끊어 발표합니다. 그래서 분기 순증도 "
             "만 명 단위이고, 작은 변화는 보이지 않습니다.")

    # ── c1667 유료 구독(분기)
    cur = {**full.get(SUBS, {}), **(ov.get(SUBS) or {})}
    old_lab = [str(x) for x in cur["labels"]]
    old_names = [str(n).strip().rstrip(".") for n in cur["seriesNames"]]
    def pick(*prefixes):
        """계열 이름으로 찾되 앞머리만 본다. 이 어댑터가 이름을 바꿔 쓰기
        때문에 두 번째 실행에서 못 찾으면 안 된다."""
        for k, n in enumerate(old_names):
            if any(n.startswith(x) for x in prefixes):
                return dict(zip(old_lab, cur["series"][k]))
        raise SystemExit(f"c1667 에서 {prefixes} 계열을 못 찾았습니다: {old_names}")

    cnt = pick("구독 건수")
    sub_first = min(q for q in qs if "subs_total" in D[q])
    lab = qlist(D, old_lab[0], last)
    # 겹치는 구간에서 기존 '구독자 수' 값과 공시가 맞는지 본다.
    old_tot = pick("구독자 수", "전체 구독자")
    bad = [(q, old_tot[q], D[q]["subs_total"] / 10)
           for q in lab if old_tot.get(q) is not None and "subs_total" in D.get(q, {})
           and abs(old_tot[q] - D[q]["subs_total"] / 10) > 1.0]
    if bad:
        raise SystemExit(f"c1667 기존 값이 공시와 어긋납니다: {bad[:5]}")
    print(f"  c1667 겹치는 구간 대조 일치, {old_lab[-1]} -> {last} 로 늘립니다")
    ov.setdefault(SUBS, {}).update({
        "id": SUBS, "title": "뉴욕타임스 유료 구독(분기)", "vizType": "line",
        "unit": "만 명", "labels": lab,
        "series": [
            [cnt.get(q) for q in lab],
            [round(D[q]["subs_total"] / 10, 1) if "subs_total" in D.get(q, {}) else None for q in lab],
            [round(D[q]["subs_digital"] / 10, 1) if "subs_digital" in D.get(q, {}) else None for q in lab],
            [round(D[q]["subs_print_calc"] / 10, 1) if "subs_print_calc" in D.get(q, {}) else None for q in lab],
        ],
        "seriesNames": ["구독 건수(옛 기준)", "전체 구독자", "디지털 전용 구독자", "종이 구독자"],
        "seriesColors": [GRAY, BLUE, LBLUE, RED],
        "source": ("뉴욕타임스 실적 발표(SEC 8-K). 분기말 기준. 단위: 만 명."),
        "sourceUrl": SRC_URL,
        "notes": [
            f"{last.replace('-Q', '년 ')}분기 전체 구독자 "
            f"{D[last]['subs_total'] / 10:,.0f}만 명입니다. 이 가운데 디지털 전용이 "
            f"{D[last]['subs_digital'] / 10:,.0f}만 명, 종이가 "
            f"{D[last]['subs_print_calc'] / 10:,.0f}만 명입니다. 전체에서 디지털 "
            "전용을 뺀 것이 종이 구독자인데, 종이를 받는 사람은 디지털도 같이 "
            "보기 때문에 디지털 전용에서 빠집니다.",
            BASIS,
            "그래서 선을 끊어 두었습니다. 회색이 2021년 4분기까지의 구독 건수, "
            f"파랑이 {sub_first.replace('-Q', '년 ')}분기부터의 구독자 수입니다. "
            "두 선의 높낮이를 비교하지 마십시오.",
            f"종이 구독자는 {D[min(q for q in qs if 'subs_print_calc' in D[q])]['subs_print_calc'] / 10:,.0f}"
            f"만 명에서 {D[last]['subs_print_calc'] / 10:,.0f}만 명으로 꾸준히 "
            "줄고 있습니다. 전체가 늘어나는 동안에도 한 번도 늘지 않았습니다.",
            "종이 구독자 수는 회사가 표에 적는 분기도 있고 칸을 비우는 분기도 "
            "있습니다. 그래서 '전체 - 디지털 전용' 으로 계산했고, 적혀 있는 모든 "
            "분기에서 계산이 공표값과 맞는 것을 확인했습니다.",
            ROUND, SURVEY,
        ],
        "updated": now,
    })

    # ── c1476 분기 순증
    adds_first = min(q for q in qs if "net_adds_calc" in D[q])
    lab2 = qlist(D, adds_first, last)
    vals = [round(D[q]["net_adds_calc"] / 10, 1) for q in lab2]
    peak = max(lab2, key=lambda q: D[q]["net_adds_calc"])
    ov.setdefault(ADDS, {}).update({
        "id": ADDS, "title": "뉴욕타임스 디지털 구독자 분기 순증",
        "vizType": "column", "unit": "만 명", "labels": lab2,
        "series": [vals], "seriesNames": ["디지털 전용 구독자 순증"],
        "seriesColors": [BLUE],
        "source": ("뉴욕타임스 실적 발표(SEC 8-K). 디지털 전용 구독자의 전분기 대비 "
                   "순증. 단위: 만 명."),
        "sourceUrl": SRC_URL,
        "notes": [
            f"{last.replace('-Q', '년 ')}분기 순증은 {vals[-1]:,.0f}만 명입니다. "
            f"가장 많았던 분기는 {peak.replace('-Q', '년 ')}분기의 "
            f"{D[peak]['net_adds_calc'] / 10:,.0f}만 명입니다.",
            "기준이 바뀐 차트입니다. 전에는 번들과 뉴스 전용을 더한 '뉴스를 보는 "
            "구독자' 의 순증을 그렸습니다.",
            DISC,
            "그래서 구간도 짧아졌습니다. 디지털 전용 구독자를 분기마다 공표한 "
            f"뒤부터라 {adds_first.replace('-Q', '년 ')}분기에서 시작합니다.",
            "공표된 순증과 디지털 전용 구독자 수의 분기 차이가 모든 분기에서 "
            "일치하는 것을 확인하고, 회사가 순증을 따로 내지 않은 분기는 차이로 "
            "채웠습니다.",
            ROUND,
            "4분기가 유독 큰 해가 있습니다. 연말 할인 판촉과 게임, 쿠킹 같은 "
            "단품 구독이 겹치는 시기입니다. 분기끼리 견주기보다 전년 같은 분기와 "
            "비교하는 쪽이 낫습니다.",
            SURVEY,
        ],
        "updated": now,
    })

    # ── 새 차트: 분기 매출 구성
    rev_q = [q for q in qs if all(k in D[q] for k in
             ("rev_sub_digital", "rev_sub_print_calc", "rev_ad_digital",
              "rev_ad_print_calc", "rev_other"))]
    lab4 = qlist(D, rev_q[0], rev_q[-1])
    def ser(k):
        return [round(D[q][k], 1) for q in lab4]
    f0, l0 = lab4[0], lab4[-1]
    items = [{
        "slide": SL_REV, "category": "미디어와 저널리즘",
        "title": "뉴욕타임스 분기 매출 구성",
        "vizType": "stacked_bar", "unit": "100만 달러", "labels": lab4,
        "series": [ser("rev_sub_digital"), ser("rev_sub_print_calc"),
                   ser("rev_ad_digital"), ser("rev_ad_print_calc"), ser("rev_other")],
        "seriesNames": ["디지털 구독", "종이 구독", "디지털 광고", "종이 광고",
                        "제휴와 라이선스 등"],
        "seriesColors": [BLUE, LBLUE, ORANGE, "#f0c070", GRAY],
        "source": ("뉴욕타임스 실적 발표(SEC 8-K). 분기 매출. 단위: 100만 달러."),
        "sourceUrl": SRC_URL,
        "notes": [
            f"{l0.replace('-Q', '년 ')}분기 총매출 {D[l0]['rev_total']:,.1f}백만 "
            f"달러입니다. 디지털 구독이 {D[l0]['rev_sub_digital']:,.1f}백만으로 "
            f"{D[l0]['rev_sub_digital'] / D[l0]['rev_total'] * 100:.0f}% 를 "
            "차지합니다.",
            f"{f0.replace('-Q', '년 ')}분기와 견주면 디지털 구독이 "
            f"{D[f0]['rev_sub_digital']:,.1f}백만에서 "
            f"{D[l0]['rev_sub_digital']:,.1f}백만으로 늘고, 종이 구독은 "
            f"{D[f0]['rev_sub_print_calc']:,.1f}백만에서 "
            f"{D[l0]['rev_sub_print_calc']:,.1f}백만으로 줄었습니다. 종이 광고도 "
            f"{D[f0]['rev_ad_print_calc']:,.1f}백만에서 "
            f"{D[l0]['rev_ad_print_calc']:,.1f}백만으로 줄었습니다.",
            "종이 구독과 종이 광고는 회사가 각주에 적는 분기도 있고 안 적는 "
            "분기도 있습니다. 그래서 '전체 - 디지털' 로 계산했고, 적혀 있는 모든 "
            "분기에서 계산이 공표값과 맞는 것을 확인했습니다. 다섯 갈래를 더하면 "
            "총매출이 되는 것도 모든 분기에서 확인했습니다.",
            "'제휴와 라이선스 등' 은 와이어커터 제휴 수수료와 콘텐츠 라이선스, "
            "기타 수입입니다. 생성형 AI 업체와의 라이선스 계약도 이 칸에 "
            "들어갑니다. 회사는 액수를 따로 밝히지 않습니다.",
            "계절성이 큽니다. 4분기에 광고가 몰려 매출이 한 해 중 가장 높고 "
            "1분기가 가장 낮습니다. 분기끼리 견주기보다 전년 같은 분기와 "
            "비교해야 합니다.",
            f"구간이 {f0.replace('-Q', '년 ')}분기에서 시작하는 것은 회사가 "
            "구독과 광고를 디지털과 종이로 나눠 공표한 때부터이기 때문입니다. "
            "그 전에는 종이 구독 매출을 가정배달과 가판으로 나누는 등 갈래가 "
            "달라 한 그림으로 잇기 어렵습니다.",
            SURVEY,
        ],
        "updated": now,
    }]

    # ── 새 차트: 분기 영업이익과 이익률
    op_q = [q for q in qs if q >= "2018-Q1"
            and "op_profit" in D[q] and "rev_total" in D[q]]
    lab5 = qlist(D, op_q[0], op_q[-1])
    prof = [round(D[q]["op_profit"], 1) for q in lab5]
    marg = [round(D[q]["op_profit"] / D[q]["rev_total"] * 100, 1) for q in lab5]
    worst = min(lab5, key=lambda q: D[q]["op_profit"] / D[q]["rev_total"])
    items.append({
        "slide": SL_OP, "category": "미디어와 저널리즘",
        "title": "뉴욕타임스 분기 영업이익과 이익률",
        "vizType": "combo", "unit": "100만 달러, %", "labels": lab5,
        "series": [prof, marg], "seriesNames": ["영업이익", "영업이익률"],
        "seriesKinds": ["bar", "line"], "seriesAxes": [0, 1],
        "seriesColors": [BLUE, RED],
        "source": ("뉴욕타임스 실적 발표(SEC 8-K). 영업이익은 100만 달러, "
                   "이익률은 총매출 대비 %."),
        "sourceUrl": SRC_URL,
        "notes": [
            f"{lab5[-1].replace('-Q', '년 ')}분기 영업이익 {prof[-1]:,.1f}백만 "
            f"달러, 이익률 {marg[-1]}% 입니다.",
            "계절성이 큽니다. 광고가 몰리는 4분기에 이익률이 가장 높고 1분기에 "
            "가장 낮습니다. 막대 높이를 분기끼리 견주면 실적이 들쭉날쭉해 "
            "보이지만, 전년 같은 분기와 비교하면 결이 보입니다.",
            f"가장 낮았던 분기는 {worst.replace('-Q', '년 ')}분기로 이익률 "
            f"{D[worst]['op_profit'] / D[worst]['rev_total'] * 100:.1f}% 였습니다.",
            "회사가 따로 내는 '조정 영업이익(adjusted operating profit)' 이 아니라 "
            "회계 기준 그대로의 영업이익입니다. 조정 영업이익은 감가상각과 "
            "무형자산 상각, 희망퇴직 비용, 생성형 AI 소송 비용 같은 특별 항목을 "
            "빼고 내는 수치여서 늘 더 큽니다. 회사가 스스로 고른 제외 항목이 "
            "들어가므로 이 차트에는 쓰지 않았습니다.",
            f"{lab5[0].replace('-Q', '년 ')}분기부터 그립니다. 2017년까지는 "
            "연금 회계 개정(ASU 2017-07)을 거꾸로 적용해 같은 분기의 영업이익이 "
            "공시마다 100만 달러 남짓 다릅니다. 그 구간을 이으면 어느 쪽을 "
            "골라도 끊긴 자리가 생깁니다.",
            "이익률은 영업이익을 총매출로 나눈 값이고, 회사가 공표하는 "
            "영업이익률과 모든 분기에서 맞는 것을 확인했습니다.",
            SURVEY,
        ],
        "updated": now,
    })

    # ── 새 차트: ARPU
    ar_q = [q for q in qs if "arpu_digital" in D[q]]
    lab6 = qlist(D, ar_q[0], ar_q[-1])
    arpu = [D[q]["arpu_digital"] for q in lab6]
    items.append({
        "slide": SL_ARPU, "category": "미디어와 저널리즘",
        "title": "뉴욕타임스 디지털 구독자당 매출",
        "vizType": "line", "unit": "달러", "labels": lab6,
        "series": [arpu], "seriesNames": ["디지털 전용 구독자당 매출(ARPU)"],
        "seriesColors": [BLUE], "yMin": 7,
        "source": ("뉴욕타임스 실적 발표(SEC 8-K). 디지털 전용 구독자당 28일 "
                   "과금 주기 기준 평균 매출. 단위: 달러."),
        "sourceUrl": SRC_URL,
        "notes": [
            f"{lab6[0].replace('-Q', '년 ')}분기 {arpu[0]}달러에서 "
            f"{lab6[-1].replace('-Q', '년 ')}분기 {arpu[-1]}달러입니다. "
            f"{len(lab6)}개 분기 동안 {arpu[-1] - arpu[0]:+.2f}달러 움직였습니다. "
            "구독자가 같은 기간 크게 늘어난 것에 비하면 단가는 거의 제자리입니다.",
            "회사가 정의한 ARPU 입니다. 분기 디지털 전용 구독 매출을 그 분기 "
            "평균 디지털 전용 구독자 수로 나누고, 28일 과금 주기에 맞춰 환산한 "
            "값입니다. 월 매출이 아닙니다.",
            f"2022년 무렵 한 번 내려앉습니다({min(arpu)}달러). 디 애슬레틱을 "
            "인수해 단가가 낮은 단품 구독자가 한꺼번에 들어온 시기이고, 할인 "
            "판촉으로 들어온 구독자 비중도 컸습니다.",
            "그 뒤 오르는 것은 할인으로 들어온 구독자가 정상가로 넘어가고 기존 "
            "구독자 요금을 올린 효과라고 회사가 설명합니다. 다만 번들 비중이 "
            "커지는 효과와 단품 비중이 커지는 효과가 반대로 작용해, 이 한 줄로 "
            "요금 인상 폭을 읽을 수는 없습니다.",
            "세로축은 0 이 아니라 7달러에서 끊었습니다. 0 부터 그리면 움직임이 "
            "거의 보이지 않습니다. 축을 끊은 만큼 등락이 실제보다 커 보입니다.",
            SURVEY,
        ],
        "updated": now,
    })

    print()
    for cid in (SUBS, ADDS):
        o = ov[cid]
        print(f"  {cid} {o['title']} — {len(o['labels'])}개 분기 "
              f"({o['labels'][0]}~{o['labels'][-1]}), 계열 {len(o['series'])}개")
    for it in items:
        print(f"  {it['slide']:28s} {it['title']} — {len(it['labels'])}개 분기 "
              f"({it['labels'][0]}~{it['labels'][-1]})")

    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 과 data/manual.json 에 씁니다)")
        return 0

    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    ids = json.load(open(os.path.join(DATA, "ids.json"), encoding="utf-8"))
    for item in items:
        cur = next((i for i in doc["items"] if i.get("slide") == item["slide"]), None)
        if cur and cur.get("id"):
            item["id"] = cur["id"]
        else:
            k = "S\x1f%s\x1f%s" % (item["slide"], item["title"])
            if ids.get(k):
                item["id"] = ids[k]
        if cur:
            doc["items"][doc["items"].index(cur)] = item
        else:
            doc["items"].append(item)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json, data/manual.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
