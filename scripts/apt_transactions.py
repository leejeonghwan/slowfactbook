#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""아파트 매매 거래량. 전국(c0753)과 서울(c0752).

  python3 scripts/apt_transactions.py            # 미리보기
  python3 scripts/apt_transactions.py --apply

한국부동산원 '행정구역별 아파트매매거래현황'(408/DT_408_2006_S0064)을 쓴다.
월별로 2006년 1월부터 있고 단위는 호수다.

팩트북에 들어 있던 두 차트는 출처가 '부동산 통계 정보' 라고만 적혀 있고
URL 이 없어 어느 표인지 알 수 없었다. 이 표와 대조해 보니 겹치는 240달이
한 달도 빠짐없이 값까지 똑같아, 같은 통계로 보고 이 표로 이어 간다.

신고일 기준이다. 계약일이 아니라 신고가 들어온 날로 잡히고, 거래 신고
기한이 계약 뒤 30일이라 최근 한두 달은 뒤에 늘어난다. 그래서 받을 때마다
과거 값까지 덮는다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

ORG, TBL, ITM = "408", "DT_408_2006_S0064", "13103114448T1"
URL = ("https://kosis.kr/statHtml/statHtml.do?orgId=408&tblId=DT_408_2006_S0064")
AREA = {"전국": "13102114448A.0001", "서울": "13102114448A.0002"}
CHART = {"c0753": "전국", "c0752": "서울"}


def envkey(name):
    """환경변수를 먼저 보고 없으면 .env 를 읽는다. 액션에는 .env 가 없다."""
    v = os.environ.get(name)
    if v:
        return v.strip()
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit(f"{name} 가 필요합니다(환경변수 또는 .env).")


def fetch(key, obj):
    now = datetime.datetime.now(KST)
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
         f"&apiKey={key}&format=json&jsonVD=Y&orgId={ORG}&tblId={TBL}&prdSe=M"
         f"&startPrdDe=200601&endPrdDe={now.strftime('%Y%m')}&itmId={ITM}&objL1={obj}")
    r = subprocess.run(["curl", "-sS", "--max-time", "150", u], capture_output=True)
    if r.returncode:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    if not isinstance(d, list):
        raise SystemExit("KOSIS 응답이 표가 아닙니다: " + str(d)[:160])
    out = {}
    for x in d:
        if x.get("DT") in (None, "", "-"):
            continue
        p = x["PRD_DE"]
        out[f"{p[:4]}-{p[4:6]}"] = float(x["DT"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("KOSIS_API_KEY")

    got = {nm: fetch(key, obj) for nm, obj in AREA.items()}
    for nm, m in got.items():
        ks = sorted(m)
        if len(ks) < 200:
            raise SystemExit(f"{nm} 받은 달이 {len(ks)}개뿐입니다 — 쓰지 않습니다.")
        # 중간에 빠진 달이 없어야 한다.
        y, mo = int(ks[0][:4]), int(ks[0][5:])
        for k in ks:
            if k != f"{y:04d}-{mo:02d}":
                raise SystemExit(f"{nm} 에 빠진 달이 있습니다: {y:04d}-{mo:02d}")
            mo += 1
            if mo == 13:
                y, mo = y + 1, 1
        print(f"  {nm}: {len(ks)}달 {ks[0]}~{ks[-1]}")

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    base = {}
    for f in ("full.json", "manual.json"):
        for i in json.load(open(os.path.join(DATA, f), encoding="utf-8"))["items"]:
            if i.get("id"):
                base.setdefault(i["id"], {}).update(i)

    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    out = {}
    for cid, nm in CHART.items():
        c = {**base.get(cid, {}), **(ov.get(cid) or {})}
        lab = [str(x) for x in c["labels"]]
        s = c["series"][0]
        m = got[nm]
        # ── 검산. 겹치는 달이 한 곳도 어긋나면 안 된다.
        bad = [(lab[i], s[i], m[lab[i]]) for i in range(len(lab))
               if s[i] is not None and lab[i] in m and abs(s[i] - m[lab[i]]) > 0.5]
        seen = sum(1 for i in range(len(lab)) if s[i] is not None and lab[i] in m)
        if bad:
            raise SystemExit(f"{cid} 기존 값이 표와 어긋납니다({len(bad)}곳): {bad[:5]}")
        print(f"  {cid} {nm}: 겹치는 {seen}달 모두 일치, {lab[-1]} -> {sorted(m)[-1]}")
        ks = sorted(m)
        out[cid] = {"id": cid, "labels": ks, "series": [[m[k] for k in ks]],
                    "seriesNames": [nm], "unit": "호", "vizType": "line",
                    "title": f"아파트 매매 거래량({nm})",
                    "source": (f"한국부동산원 행정구역별 아파트매매거래현황. "
                               f"{ks[0]}~{ks[-1]}. 단위: 호."),
                    "sourceUrl": URL, "updated": now}

    peak = {cid: max(sorted(got[nm]), key=lambda k: got[nm][k]) for cid, nm in CHART.items()}
    for cid, nm in CHART.items():
        m = got[nm]; ks = sorted(m); last = ks[-1]
        import statistics
        y26 = [m[k] for k in ks if k.startswith("2026")]
        y25 = [m[k] for k in ks if k.startswith("2025")]
        out[cid]["notes"] = [
            f"{last.replace('-', '년 ')}월 {m[last]:,.0f}호입니다. 2026년 들어 "
            f"{len(y26)}달 평균 {statistics.fmean(y26):,.0f}호로 2025년 평균 "
            f"{statistics.fmean(y25):,.0f}호의 "
            f"{statistics.fmean(y26) / statistics.fmean(y25) * 100:.0f}% 입니다.",
            f"가장 많았던 달은 {peak[cid].replace('-', '년 ')}월의 "
            f"{m[peak[cid]]:,.0f}호입니다.",
            "신고일 기준입니다. 계약한 날이 아니라 신고가 들어온 날로 잡히고, "
            "거래 신고 기한이 계약 뒤 30일이라 가장 최근 한두 달은 뒤에 "
            "늘어납니다. 이 차트는 받을 때마다 과거 값까지 덮습니다.",
            "거래량은 가격보다 먼저 움직입니다. 살 사람이 줄면 거래가 먼저 "
            "마르고 가격은 뒤따라 내립니다. 다만 대출 규제나 세제 변경이 있는 "
            "달에는 신고가 한쪽으로 몰려 한 달치가 크게 튑니다.",
            "출처 표기가 '부동산 통계 정보' 뿐이고 URL 이 없던 차트였습니다. "
            f"한국부동산원 표와 겹치는 240달이 한 달도 빠짐없이 값까지 같아 "
            "같은 통계로 보고 이 표로 이어 갑니다.",
        ]

    for cid, o in out.items():
        print(f"  {cid} {o['title']:22s} {len(o['labels'])}달 {o['labels'][0]}~{o['labels'][-1]}")
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
