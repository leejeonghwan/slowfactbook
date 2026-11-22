#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""투자자예탁금(c0684) — 금융투자협회 FREESIS 증시자금추이.

한국은행 ECOS 에도 KOSIS 에도 없다. 금융투자협회 FREESIS 가 유일한
출처인데 화면이 프레임과 자바스크립트로 돼 있어 주소만 봐서는 자료를
못 받는다. 화면이 실제로 쓰는 POST 끝점을 그대로 쓴다.

  POST https://freesis.kofia.or.kr/meta/getMetaDataList.do
  {"dmSearch":{"tmpV40":"1000000","tmpV41":"1","tmpV1":"<D|M>",
               "tmpV45":"<시작>","tmpV46":"<끝>",
               "OBJ_NM":"STATSCU0100000060BO"}}

돌아오는 ds1 의 칸
  TMPV1 날짜, TMPV2 투자자예탁금(장내파생상품 거래예수금 제외),
  TMPV3 장내파생상품 거래예수금, TMPV4 대고객 RP 매도잔고,
  TMPV5 위탁매매 미수금, TMPV6 반대매매금액, TMPV7 반대매매비중
단위는 백만 원이다. 차트는 조 원이라 1,000,000 으로 나눈다.

c0684 가 TMPV2 라는 근거: 1998년 6월 1,804,736백만원이 차트의 첫 값
1.8047조와 같다. 겹치는 구간 전체를 대조해 확인한다.

섞으면 안 되는 것 — 화면 머리의 '투자자예탁금'과 다르다.
FREESIS 첫 화면에 뜨는 투자자예탁금은 날짜가 일간이고, 여기서 쓰는
것은 월말 값이다. 또 TMPV3(장내파생상품 거래예수금)을 더하면 다른
숫자가 된다. 차트 계열 이름에 '장내파생상품 거래예수금제외'라고
적혀 있는 이유다.
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

EP = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
OBJ = "STATSCU0100000060BO"
SITE = "https://freesis.kofia.or.kr/"
GATE_FIRST = ("1998-06", 1.8047)      # 차트의 첫 값


def fetch(cyc, s, e, tries=3):
    body = json.dumps({"dmSearch": {
        "tmpV40": "1000000", "tmpV41": "1", "tmpV1": cyc,
        "tmpV45": s, "tmpV46": e, "OBJ_NM": OBJ}}).encode()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(EP, data=body, headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/json",
                "Referer": "https://freesis.kofia.or.kr/stat/FreeSIS.do"})
            d = json.load(urllib.request.urlopen(req, timeout=90))
            rows = d.get("ds1") or []
            if not rows:
                raise RuntimeError("ds1 이 비었다")
            out = {}
            for r in rows:
                t = str(r.get("TMPV1") or "")
                v = r.get("TMPV2")
                if len(t) != 8 or v in (None, ""):
                    continue
                out[f"{t[:4]}-{t[4:6]}"] = round(float(v) / 1_000_000, 4)
            if out:
                return out
            raise RuntimeError("쓸 값이 없다")
        except Exception as ex:                      # noqa: BLE001
            last = ex
            time.sleep(3 + 3 * i)
    raise RuntimeError(f"FREESIS 를 받지 못했다: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    now = datetime.datetime.now(KST).strftime("%Y%m")

    d = fetch("M", "199801", now)
    ks = sorted(d)
    print(f"    받음: {len(ks)}개월 {ks[0]}~{ks[-1]}")

    if d.get(GATE_FIRST[0]) != GATE_FIRST[1]:
        print(f"  검산 실패: {GATE_FIRST[0]} 이 {d.get(GATE_FIRST[0])} 다 "
              f"(차트의 첫 값 {GATE_FIRST[1]})")
        return 1
    print(f"    검산 첫값: {GATE_FIRST[0]} {GATE_FIRST[1]}조로 차트와 일치")

    fp = os.path.join(DATA, "full.json")
    fl = json.load(open(fp, encoding="utf-8"))
    full = {i.get("id"): i for i in (fl.get("items") or fl)}
    ovp = os.path.join(DATA, "overrides.json")
    o = json.load(open(ovp, encoding="utf-8"))
    cur = dict(full.get("c0684") or {})
    cur.update(o.get("c0684") or {})
    old = dict(zip(cur.get("labels") or [], (cur.get("series") or [[]])[0]))

    ov = [k for k in ks if k in old]
    diff = [(k, old[k], d[k]) for k in ov
            if abs(d[k] - old[k]) > max(abs(old[k]) * 0.001, 0.01)]
    same = len(ov) - len(diff)
    if not ov or same / len(ov) < 0.95:
        print(f"  검산 실패: 겹친 {len(ov)}개월 중 {same}개만 일치 "
              f"{diff[:4]}")
        return 1
    print(f"    검산 대조: 겹친 {len(ov)}개월 중 {same}개 일치"
          + (f" (어긋남 {len(diff)}개: "
             f"{', '.join(f'{k} {a}->{b}' for k, a, b in diff[:3])})"
             if diff else ""))

    # 예탁금은 한 달에 크게 움직인다. 1999년 4월 코스닥 거품 때 67%
    # 늘었다. 실제 값이므로 막는 문턱은 100%로 두고, 40% 넘는 자리는
    # 막지 않고 세어서 알려만 준다. 단위가 바뀌는 사고는 백만 원과
    # 조 원 사이라 백만 배로 튀므로 이 문턱에 걸린다.
    big, huge = [], []
    for i in range(1, len(ks)):
        if not d[ks[i-1]]:
            continue
        r = abs(d[ks[i]] / d[ks[i-1]] - 1)
        if r > 1.0:
            huge.append((ks[i], round(r, 2)))
        elif r > 0.4:
            big.append((ks[i], round(r, 2)))
    if huge:
        print(f"  검산 실패: 한 달에 100% 넘게 튄 자리 {huge[:3]}")
        return 1
    print(f"    검산 연속: {len(ks)}개월 모두 전달 대비 100% 안 "
          f"(40% 넘는 달 {len(big)}개"
          + (f": {', '.join(k for k, _ in big[:4])})" if big else ")"))

    last, first = ks[-1], ks[0]
    pk = max(ks, key=lambda k: d[k])
    it = {
        "id": "c0684", "category": "주식",
        "title": "투자 예탁금.",
        "vizType": "line", "unit": "조 원",
        "labels": list(ks), "series": [[d[k] for k in ks]],
        "seriesNames": ["투자자예탁금 (장내파생상품 거래예수금제외)"],
        "hideLegend": True,
        "source": ("금융투자협회 FREESIS 증시자금추이. 월말 기준, "
                   f"{first}~{last}. 장내파생상품 거래예수금은 "
                   "뺀 값입니다. 단위: 조 원."),
        "sourceUrl": SITE,
        "notes": [
            f"{last} 기준 {d[last]:,.1f}조 원입니다. 가장 많았던 달은 "
            f"{pk}로 {d[pk]:,.1f}조 원입니다.",
            "증권 계좌에 들어와 있지만 아직 주식을 사지 않은 돈입니다. "
            "주식을 사면 예탁금에서 빠지므로, 늘었다고 반드시 주식을 "
            "더 사는 것은 아닙니다.",
            "장내파생상품 거래예수금은 뺀 값입니다. 그걸 더하면 숫자가 "
            "크게 달라집니다. FREESIS 첫 화면에 뜨는 일간 투자자예탁금과도 "
            "시점이 다릅니다.",
            "월말 기준입니다. 그달 마지막 거래일 값입니다.",
        ],
        "updated": ymd,
    }

    print(f"  c0684 {len(ks)}점 {first}~{last} 끝값 {d[last]:,.1f}조 "
          f"(전에는 {len(old)}점, {max(old) if old else '-'} 까지)")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    o.setdefault("c0684", {}).update(it)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))
    print("-> data/overrides.json 에 c0684 를 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
