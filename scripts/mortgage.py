#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""주택담보대출 — 한국은행 가계신용 용도별.

ECOS 151Y005 예금취급기관 가계대출(용도별, 월)
     151Y004 가계신용(용도별, 분기)

'주택담보대출이 얼마냐'는 질문에 답이 하나가 아니다. 어디까지 세느냐에
따라 2026년 3분기 기준으로 787조(예금은행), 938조(예금취급기관),
1,202조(전 금융권)가 모두 맞는 말이다. 그래서 세 겹을 한 장에 같이
그린다. 숫자 하나만 들고 다니면 서로 다른 기준끼리 싸우게 된다.

c0673 의 정체를 되짚은 기록.
  차트의 2008년 1월 값 291.6233 이 151Y005 의 주택관련대출-예금취급기관
  (11100A0) 과 소수점 넷째 자리까지 같았다. 그래서 c0673 은 이 계열이다.
  다만 최근 달은 한국은행이 개정해서 차트의 2026년 2월 912.6341 이
  지금은 914.5702 다. 개정분을 따라가는 게 맞으므로 덮어쓴다.

c0742 '부동산 담보 대출'은 손대지 않았다.
  2004년 1분기 258.965, 2025년 3분기 1003.8381 인데 ECOS 의 가계신용,
  가계대출, 주택관련대출 어느 항목과도 맞지 않는다. 계열 이름은
  '가계 신용'인데 제목은 '부동산 담보 대출'이라 기준이 섞여 있다.
  무엇인지 모르는 채로 덮어쓰지 않는다.
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

SRC = "한국은행 ECOS 가계신용(용도별)"
URL = "https://ecos.bok.or.kr/"
LAYERS = [("전 금융권", "11000A0", "#c0322f"),
          ("예금취급기관", "11100A0", "#e8820c"),
          ("예금은행", "11110A0", "#2a5ca8")]
# c0673 이 이 계열임을 확인한 값. 바뀌면 기준이 바뀐 것이니 멈춘다.
GATE_0673 = ("2008-01", 291.6233)


def envkey(k):
    v = os.environ.get(k)
    if v:
        return v
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.startswith(k + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def pull(key, code, item, cyc, s, e, tries=3):
    u = (f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/4000/"
         f"{code}/{cyc}/{s}/{e}/{item}")
    last = None
    for i in range(tries):
        try:
            d = json.load(urllib.request.urlopen(u, timeout=90))
            if "StatisticSearch" not in d:
                raise RuntimeError(str(d)[:160])
            rows = d["StatisticSearch"].get("row") or []
            out = {}
            for x in rows:
                v = x.get("DATA_VALUE")
                if v in (None, "", "-"):
                    continue
                out[x["TIME"]] = round(float(v) / 1000, 4)   # 십억 -> 조
            if out:
                return out
            raise RuntimeError("빈 응답")
        except Exception as ex:                      # noqa: BLE001
            last = ex
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"{code}/{item} 를 받지 못했다: {last}")


def mlab(t):
    return f"{t[:4]}-{t[4:]}"


def qlab(t):
    return f"{t[:4]}-{t[4:]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("ECOS_API_KEY")
    if not key:
        print("ECOS_API_KEY 가 없다")
        return 2
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    now = datetime.datetime.now(KST)
    endm = now.strftime("%Y%m")
    endq = f"{now.year}Q4"

    # ── 1 c0673 월간, 예금취급기관
    mon = pull(key, "151Y005", "11100A0", "M", "200712", endm)
    mk = sorted(mon)
    if mon.get("200801") != GATE_0673[1]:
        print(f"  검산 실패: 2008-01 이 {mon.get('200801')} 다 "
              f"(c0673 의 {GATE_0673[1]} 와 달라 같은 계열이 아니다)")
        return 1
    print(f"    검산 계열: 2008-01 {GATE_0673[1]} 로 c0673 과 일치 "
          "(= c0673 은 예금취급기관 주택관련대출)")
    if not all(mon[k] > 0 for k in mk):
        print("  검산 실패: 0 이하 값이 있다")
        return 1
    drops = [(mk[i], round(mon[mk[i]] / mon[mk[i-1]] - 1, 4))
             for i in range(1, len(mk))
             if abs(mon[mk[i]] / mon[mk[i-1]] - 1) > 0.05]
    if drops:
        print(f"  검산 실패: 한 달에 5% 넘게 튄 자리 {drops[:3]}")
        return 1
    print(f"    검산 연속: {len(mk)}개월 모두 전달 대비 5% 안")

    m_lab = [mlab(k) for k in mk]
    m_val = [mon[k] for k in mk]
    ovr = {"c0673": {
        "id": "c0673", "category": "금융",
        "title": "주택 담보 대출.",
        "vizType": "line", "unit": "조 원",
        "labels": m_lab, "series": [m_val],
        "seriesNames": ["예금취급기관 주택관련대출"],
        "seriesColors": ["#e8820c"], "hideLegend": True,
        "source": (f"{SRC}, 예금취급기관 가계대출 용도별(ECOS 151Y005). "
                   f"{m_lab[0]}~{m_lab[-1]}. 은행과 비은행 예금취급기관의 "
                   "주택관련대출 잔액. 단위: 조 원."),
        "sourceUrl": URL,
        "notes": [
            f"{m_lab[-1]} 기준 {m_val[-1]:,.1f}조 원입니다. "
            f"{m_lab[0]} {m_val[0]:,.1f}조 원에서 "
            f"{m_val[-1]/m_val[0]:.1f}배가 됐습니다.",
            "예금취급기관 기준입니다. 보험사와 여신전문금융회사 같은 "
            "기타금융기관은 빠져 있습니다. 그쪽까지 넣은 전 금융권 "
            "기준은 「주택담보대출 잔액, 어디까지 세느냐」를 보십시오.",
            "주택'담보'대출이 아니라 주택'관련'대출입니다. 한국은행 "
            "분류가 그렇고, 주택담보대출에 더해 주택 관련 신용대출 등이 "
            "들어갑니다.",
            "한국은행이 최근 달을 뒤에 고칩니다. 전에는 2026년 2월이 "
            "912.6341조로 적혀 있었는데 지금 값은 914.5702조입니다. "
            "개정된 값을 따릅니다.",
        ],
        "updated": ymd,
    }}

    # ── 2 포괄 범위별(분기)
    qs, lay = {}, {}
    for nm, item, _c in LAYERS:
        lay[nm] = pull(key, "151Y004", item, "Q", "2005Q1", endq)
        qs |= {k: 1 for k in lay[nm]}
    qk = sorted(qs)
    # 검산: 전 금융권 >= 예금취급기관 >= 예금은행
    bad = []
    for k in qk:
        a_, b_, c_ = (lay["전 금융권"].get(k), lay["예금취급기관"].get(k),
                      lay["예금은행"].get(k))
        if None in (a_, b_, c_):
            continue
        if not a_ >= b_ >= c_:
            bad.append((k, a_, b_, c_))
    if bad:
        print(f"  검산 실패: 포괄 범위 순서가 뒤집힌 분기 {bad[:3]}")
        return 1
    n = sum(1 for k in qk if all(lay[x].get(k) for x, _, _ in LAYERS))
    print(f"    검산 포괄: {n}개 분기 모두 전 금융권 >= 예금취급기관 "
          ">= 예금은행")

    last = qk[-1]
    out = [{
        "slide": "manual-mortgage-scope", "category": "금융",
        "title": "주택담보대출 잔액, 어디까지 세느냐",
        "vizType": "line", "unit": "조 원",
        "labels": [qlab(k) for k in qk],
        "series": [[lay[nm].get(k) for k in qk] for nm, _, _ in LAYERS],
        "seriesNames": [nm for nm, _, _ in LAYERS],
        "seriesColors": [c for _, _, c in LAYERS],
        "source": (f"{SRC}(ECOS 151Y004). {qlab(qk[0])}~{qlab(last)}. "
                   "주택관련대출 잔액. 단위: 조 원."),
        "sourceUrl": URL,
        "notes": [
            (f"{qlab(last)} 기준으로 예금은행만 세면 "
             f"{lay['예금은행'][last]:,.0f}조, 비은행까지 넣은 "
             f"예금취급기관은 {lay['예금취급기관'][last]:,.0f}조, "
             f"보험사와 여신전문금융회사까지 넣은 전 금융권은 "
             f"{lay['전 금융권'][last]:,.0f}조입니다. 셋 다 맞는 "
             "말입니다."),
            (f"가장 넓은 기준과 가장 좁은 기준의 차이가 "
             f"{lay['전 금융권'][last]-lay['예금은행'][last]:,.0f}조 "
             "원입니다. 기사에서 주택담보대출 액수를 볼 때 어느 기준인지 "
             "먼저 봐야 하는 이유입니다."),
            "세 선의 간격이 벌어지면 은행 밖에서 돈이 더 늘었다는 "
            "뜻입니다. 규제가 은행에 먼저 걸릴 때 나타나는 모양입니다.",
            "한국은행 가계신용 통계의 '주택관련대출'입니다. 주택담보대출에 "
            "주택 관련 신용대출 등이 함께 들어갑니다.",
        ],
        "updated": ymd,
    }]

    print(f"  c0673 {len(m_lab)}점 {m_lab[0]}~{m_lab[-1]} "
          f"끝값 {m_val[-1]:,.1f}조 (overrides)")
    for it in out:
        print(f"  {it['title'][:26]:28s} {len(it['labels'])}점 "
              f"{it['labels'][0]}~{it['labels'][-1]}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    ovp = os.path.join(DATA, "overrides.json")
    o = json.load(open(ovp, encoding="utf-8"))
    for k, v in ovr.items():
        o.setdefault(k, {}).update(v)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))
    print(f"-> data/overrides.json 에 {', '.join(ovr)} 를 반영했습니다.")

    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    idx = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for it in out:
        old = idx.get(it["slide"])
        if old:
            keep = {k: old[k] for k in ("id",) if k in old}
            old.clear()
            old.update(it)
            old.update(keep)
        else:
            doc["items"].append(it)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(p, encoding="utf-8"))
    print(f"-> data/manual.json 에 {len(out)}장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
