#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""코스피와 S&P 500 비교 차트(c0495, c1051)를 이미 갱신되는 차트에서 다시 세운다.

  python3 scripts/kospi_sp500.py            # 미리보기
  python3 scripts/kospi_sp500.py --apply

두 비교 차트는 어댑터가 없어 2026년 5월에 멈춰 있었고 값도 틀렸다. 2026년 5월
코스피 월말 종가가 8,476.15인데 c0495 에는 7,320, c1051 에는 7,339 로 적혀
있었다. 키노트에서 옮길 때 눈금에서 읽은 값으로 보인다.

새로 받아오지 않는다. 이미 자동 갱신되는 두 차트에서 가져다 붙인다.

  코스피      c0494  국가데이터처 증권·파생상품시장통계, 1981년 5월부터 월말 종가
  S&P 500   c0496  야후 파이낸스, 1970년 2월부터 월말 종가

검산은 셋이다. 두 계열의 달이 구멍 없이 겹치는지, 코스피가 다른 출처의 같은
계열(c2206, 야후)과 겹치는 구간에서 맞는지, S&P 500 이 c2215 와 맞는지 본다.
한 곳이라도 어긋나면 쓰지 않는다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
KOSPI, SP = "c0494", "c0496"
CHECK = {"S&P 500": ("c2215", SP)}
KOSIS = ("343", "DT_343_2010_S0029", "13103792816T1", "KOSPI")   # 월말 종가, 2004.01~


def envkey(name):
    v = os.environ.get(name)
    if v:
        return v.strip()
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit(f"{name} 가 필요합니다(환경변수 또는 .env).")


def kosis_kospi():
    """국가데이터처에서 코스피 월말 종가를 받는다. 2004년 1월부터 있다."""
    key = envkey("KOSIS_API_KEY")
    org, tbl, itm, want = KOSIS
    y1 = datetime.datetime.now(KST).year
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
         f"&apiKey={key}&format=json&jsonVD=Y&orgId={org}&tblId={tbl}&prdSe=M"
         f"&startPrdDe=200401&endPrdDe={y1}12&itmId={itm}&objL1=ALL")
    r = subprocess.run(["curl", "-sS", "--max-time", "170", u], capture_output=True)
    if r.returncode:
        raise SystemExit("코스피 내려받기 실패: " + r.stderr.decode()[:120])
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    if not isinstance(d, list):
        raise SystemExit(f"코스피 응답이 표가 아닙니다: {str(d)[:160]}")
    out = {}
    for x in d:
        if x.get("C1_NM") != want or x.get("DT") in (None, "", "-"):
            continue
        p = str(x["PRD_DE"])
        out[f"{p[:4]}-{p[4:6]}"] = float(x["DT"])
    if len(out) < 200:
        raise SystemExit(f"코스피 받은 달이 {len(out)}개뿐입니다.")
    return out


def load():
    base = {}
    for f in ("full.json", "manual.json", "api.json"):
        p = os.path.join(DATA, f)
        if not os.path.exists(p):
            continue
        for i in json.load(open(p, encoding="utf-8"))["items"]:
            if i.get("id"):
                base.setdefault(i["id"], {}).update(i)
    ov = json.load(open(os.path.join(DATA, "overrides.json"), encoding="utf-8"))
    return base, ov


def series(base, ov, cid):
    c = {**base.get(cid, {}), **(ov.get(cid) or {})}
    if not c.get("labels"):
        raise SystemExit(f"{cid} 를 못 읽었습니다.")
    return {str(l): v for l, v in zip(c["labels"], c["series"][0]) if v is not None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    base, ov = load()

    k = series(base, ov, KOSPI)
    s = series(base, ov, SP)

    # 코스피는 원천에서 다시 받아 2004년 이후를 통째로 맞춘다. refresh_charts 는
    # 뒤에 이어붙이기만 해서 한 번 잘못 들어간 값이 그대로 남는다.
    src = kosis_kospi()
    fixed = [(x, k[x], src[x]) for x in sorted(src)
             if x in k and abs(k[x] - src[x]) > max(0.05, src[x] * 0.001)]
    added = [x for x in sorted(src) if x not in k]
    k.update(src)
    if fixed:
        print(f"    코스피 바로잡음 {len(fixed)}달: "
              + ", ".join(f"{x} {a:,.2f}->{b:,.2f}" for x, a, b in fixed[:5]))
    if added:
        print(f"    코스피 새로 붙임: {added}")
    if not fixed and not added:
        print("    코스피: 원천과 이미 같습니다")

    # 2004년 이전은 원천이 없어 그대로 둔다. 야후 월간(c2206)과 겹치는 구간에서
    # 크게 벌어지지 않는지만 본다. 옛 구간은 지수 소급 개정 때문에 조금씩 다르다.
    yah = series(base, ov, "c2206")
    old_both = sorted(x for x in (set(yah) & set(k)) if x < "2004-01")
    far = [(x, k[x], yah[x]) for x in old_both if abs(k[x] - yah[x]) > yah[x] * 0.06]
    if far:
        raise SystemExit(f"2004년 이전 코스피가 야후와 6% 넘게 벌어집니다: {far[:4]}")
    print(f"    검산 2004년 이전: 야후와 겹치는 {len(old_both)}달 모두 6% 안")

    # 검산 1. 다른 출처의 같은 계열과 맞는가
    for nm, (other, mine) in CHECK.items():
        o = series(base, ov, other)
        m = k if mine == KOSPI else s
        both = sorted(set(o) & set(m))
        if len(both) < 60:
            raise SystemExit(f"{nm}: {other} 와 겹치는 달이 {len(both)}개뿐입니다.")
        bad = [(x, m[x], o[x]) for x in both if abs(m[x] - o[x]) > max(0.5, o[x] * 0.005)]
        if bad:
            raise SystemExit(f"{nm} 이 {other} 와 어긋납니다({len(bad)}/{len(both)}): {bad[:4]}")
        print(f"    검산 {nm}: {other} 와 겹치는 {len(both)}달 모두 일치")

    ms = sorted(set(k) & set(s))
    y, mo = int(ms[0][:4]), int(ms[0][5:])
    for x in ms:
        if x != f"{y:04d}-{mo:02d}":
            raise SystemExit(f"빠진 달: {y:04d}-{mo:02d}")
        mo += 1
        if mo == 13:
            y, mo = y + 1, 1
    print(f"    검산 겹침: {ms[0]}~{ms[-1]} {len(ms)}달, 구멍 없음")

    last = ms[-1]
    out = {}
    for cid, start, title in ((("c0495"), ms[0], "코스피 지수와 S&P 500 지수."),
                              (("c1051"), "2020-01", "코스피 지수와 S&P 500 지수.")):
        sel = [x for x in ms if x >= start]
        kk = [round(k[x], 2) for x in sel]
        ss = [round(s[x], 2) for x in sel]
        out[cid] = {
            "id": cid, "title": title, "vizType": "line", "unit": "",
            "labels": sel, "series": [kk, ss],
            "seriesNames": ["코스피", "S&P 500"],
            "seriesColors": ["#2a5ca8", "#c0322f"],
            "source": (f"코스피는 국가데이터처 증권·파생상품시장통계, S&P 500 은 "
                       f"야후 파이낸스. {sel[0]}~{sel[-1]} 월말 종가."),
            "sourceUrl": "https://kosis.kr/statHtml/statHtml.do?orgId=343&tblId=DT_343_2010_S0029",
            "notes": [
                f"{last.replace('-', '년 ')}월 코스피 {k[last]:,.2f}, S&P 500 "
                f"{s[last]:,.2f} 입니다. {sel[0].replace('-', '년 ')}월에는 각각 "
                f"{k[sel[0]]:,.2f}와 {s[sel[0]]:,.2f} 였습니다.",
                "두 지수는 기준시점과 산출 방식이 다릅니다. 코스피는 1980년 1월 4일을 "
                "100으로, S&P 500 은 1941년부터 1943년 평균을 10으로 둡니다. 숫자가 "
                "비슷해 보이는 것은 우연이고 어느 쪽이 더 비싸다는 뜻이 아닙니다. "
                "견줄 것은 수준이 아니라 기울기입니다.",
                "원화와 달러로 각각 표시된 지수입니다. 환율은 반영되지 않았습니다. "
                "달러로 바꿔 보면 코스피의 상승 폭은 이보다 작아집니다.",
                "월말 종가입니다. 달 안의 등락은 보이지 않습니다.",
                "전에 실려 있던 값이 틀려 다시 세웠습니다. 2026년 5월 코스피 월말 "
                "종가가 8,476.15인데 7,320으로 적혀 있었습니다. 지금은 자동 갱신되는 "
                "c0494 와 c0496 에서 가져다 쓰고, 두 차트가 다른 출처의 같은 계열과 "
                "맞는지 쓸 때마다 대조합니다.",
            ],
            "updated": ymd,
        }
    # 짧고 틀린 판본 둘은 내린다
    for cid, why in (("c1048", "코스피 지수"), ("c0686", "종합주가지수")):
        out[cid] = {
            "id": cid, "drop": True,
            "dropNote": (f"c0494 와 같은 계열인데 더 짧고 값이 틀렸습니다. 2026년 "
                         f"5월 코스피 월말 종가가 8,476.15인데 7,456(c1048)과 "
                         f"8,864(c0686, 6월)로 적혀 있었습니다. c0494 를 보세요."),
            "updated": ymd,
        }

    out[KOSPI] = {"id": KOSPI, "labels": sorted(k), "series": [[k[x] for x in sorted(k)]],
                  "updated": ymd}

    for cid, o in out.items():
        if o.get("drop"):
            print(f"  {cid} 내립니다.")
        elif cid == KOSPI:
            print(f"  {cid} 코스피 {len(o['labels'])}달 {o['labels'][0]}~{o['labels'][-1]} "
                  f"끝 {o['series'][0][-1]:,.2f}")
        else:
            print(f"  {cid} {len(o['labels'])}달 {o['labels'][0]}~{o['labels'][-1]} "
                  f"코스피 {o['series'][0][-1]:,.2f} / S&P {o['series'][1][-1]:,.2f}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
        return 0
    p = os.path.join(DATA, "overrides.json")
    cur = json.load(open(p, encoding="utf-8"))
    for cid, o in out.items():
        cur.setdefault(cid, {}).update(o)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(cur, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
