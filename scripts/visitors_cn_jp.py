#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""중국과 일본 관광객 수(c1332). 월별.

  python3 scripts/visitors_cn_jp.py            # 미리보기
  python3 scripts/visitors_cn_jp.py --apply

한국문화관광연구원 관광지식정보시스템의 「외래객 입국 성별/국적별」 에서 받는다.
국가데이터처 포털에 올라와 있고 표가 둘로 갈려 있다. 분류 차수가 바뀌면서
옛 표가 2021년 12월에서 끊기고 새 표가 2022년 1월부터 시작한다.

  314/DT_SEX_ENT_AGG_MONTH       2003.01~2021.12
  314/DT_TRD_SEX_ENT_AGG_MONTH   2022.01~

둘을 이어 붙인다. 같은 기관의 같은 통계이고 차수만 다르다. 이어 붙인 자리에
구멍이나 겹침이 없는지, 그리고 차트에 이미 들어 있던 값이 원천과 맞는지
본다. 어긋나면 쓰지 않는다.

원천 단위는 명이고 차트는 만 명이다. 차트에 있던 값은 만 명 단위로 반올림된
정수였다. 다시 세우면서 소수 첫째 자리까지 살린다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=314&tblId=DT_TRD_SEX_ENT_AGG_MONTH"
OLD = ("DT_SEX_ENT_AGG_MONTH", "13103314001T01",
       {"중국": "13102314001A.2002", "일본": "13102314001A.2003",
        "전체": "13102314001A.1"}, 200301, 202112)
NEW = ("DT_TRD_SEX_ENT_AGG_MONTH", "13103314421T01",
       {"중국": "13102314421A.2002", "일본": "13102314421A.2003",
        "전체": "13102314421A.1"}, 202201, None)


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


KEY = None


def pull(tbl, itm, obj, s, e):
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
         f"&apiKey={KEY}&format=json&jsonVD=Y&orgId=314&tblId={tbl}&prdSe=M"
         f"&startPrdDe={s}&endPrdDe={e}&itmId={itm}&objL1={obj}")
    r = subprocess.run(["curl", "-sS", "--max-time", "170", u], capture_output=True)
    if r.returncode:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    if not isinstance(d, list):
        raise SystemExit(f"{tbl} {obj} 응답이 표가 아닙니다: {str(d)[:160]}")
    if d and d[0].get("UNIT_NM") != "명":
        raise SystemExit(f"{tbl} 단위가 '명' 이 아닙니다: {d[0].get('UNIT_NM')!r}")
    out = {}
    for x in d:
        if x.get("DT") in (None, "", "-"):
            continue
        p = str(x["PRD_DE"])
        out[f"{p[:4]}-{p[4:6]}"] = float(x["DT"])
    if not out:
        raise SystemExit(f"{tbl} {obj} 가 비었습니다.")
    return out


def main():
    global KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    KEY = envkey("KOSIS_API_KEY")
    now = datetime.datetime.now(KST)
    ymd = now.strftime("%Y-%m-%d %H:%M")

    got = {}
    for nm in ("중국", "일본", "전체"):
        old = pull(OLD[0], OLD[1], OLD[2][nm], OLD[3], OLD[4])
        new = pull(NEW[0], NEW[1], NEW[2][nm], NEW[3], f"{now.year}12")
        both = set(old) & set(new)
        if both:
            raise SystemExit(f"{nm}: 두 표가 겹치는 달이 있습니다: {sorted(both)[:5]}")
        got[nm] = {**old, **new}
        print(f"  {nm}: 옛 표 {len(old)}달, 새 표 {len(new)}달, 합쳐 {len(got[nm])}달")

    ms = sorted(set(got["중국"]) & set(got["일본"]))
    y, m = int(ms[0][:4]), int(ms[0][5:])
    for k in ms:
        if k != f"{y:04d}-{m:02d}":
            raise SystemExit(f"빠진 달이 있습니다: {y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    print(f"    검산 이음새: {ms[0]}~{ms[-1]} {len(ms)}달, 구멍도 겹침도 없음")

    # 검산. 중국과 일본을 더한 값이 전체를 넘지 않아야 한다.
    over = [k for k in ms if got["중국"][k] + got["일본"][k] > got["전체"][k] + 1]
    if over:
        raise SystemExit(f"중국과 일본의 합이 전체를 넘는 달: {over[:5]}")
    sh = {k: (got["중국"][k] + got["일본"][k]) / got["전체"][k] * 100 for k in ms}
    print(f"    검산 합계: 중국과 일본의 합이 {len(ms)}달 모두 전체 이하 "
          f"(비중 {min(sh.values()):.0f}~{max(sh.values()):.0f}%)")

    # 차트에 있던 값과 대조. 옛 값은 만 명 단위로 반올림된 정수다.
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
    cur = {**base.get("c1332", {}), **(ov.get("c1332") or {})}
    if cur.get("seriesNames") != ["중국", "일본"]:
        raise SystemExit(f"계열 이름이 바뀌었습니다: {cur.get('seriesNames')}")
    bad, seen = [], 0
    for nm, ser in zip(cur["seriesNames"], cur["series"]):
        for lb, v in zip([str(x) for x in cur["labels"]], ser):
            if v is None or lb not in got[nm]:
                continue
            seen += 1
            if abs(round(got[nm][lb] / 1e4) - v) > 0.51:
                bad.append((nm, lb, v, round(got[nm][lb] / 1e4, 1)))
    if seen < 400:
        raise SystemExit(f"대조한 칸이 {seen}개뿐입니다.")
    if len(bad) > seen * 0.02:
        raise SystemExit(f"기존 값이 원천과 어긋납니다({len(bad)}/{seen}): {bad[:6]}")
    if bad:
        print(f"    대조 {seen}칸 중 {len(bad)}칸 차이(반올림 경계): {bad[:3]}")
    print(f"    검산 기존 값: {seen}칸 중 {seen - len(bad)}칸 일치")

    ser = [[round(got[nm][k] / 1e4, 1) for k in ms] for nm in ("중국", "일본")]
    last = ms[-1]
    cn, jp = got["중국"], got["일본"]
    pkc = max((k for k in ms), key=lambda k: cn[k])
    pkj = max((k for k in ms), key=lambda k: jp[k])
    out = {
        "c1332": {
            "id": "c1332",
            "title": "중국과 일본 관광객 수.",
            "vizType": "line", "unit": "만 명",
            "labels": ms, "series": ser,
            "seriesNames": ["중국", "일본"],
            "seriesColors": ["#e8820c", "#c0322f"],
            "source": (f"한국문화관광연구원 관광지식정보시스템 외래객 입국 국적별. "
                       f"{ms[0]}~{last}. 단위: 만 명."),
            "sourceUrl": URL,
            "notes": [
                f"{last.replace('-', '년 ')}월 중국 {cn[last] / 1e4:,.1f}만 명, 일본 "
                f"{jp[last] / 1e4:,.1f}만 명입니다. 가장 많았던 달은 중국이 "
                f"{pkc.replace('-', '년 ')}월 {cn[pkc] / 1e4:,.1f}만 명, 일본이 "
                f"{pkj.replace('-', '년 ')}월 {jp[pkj] / 1e4:,.1f}만 명입니다.",
                "관광객이 아니라 입국자입니다. 상용과 유학연수, 그 밖의 목적이 모두 "
                "들어 있습니다. 승무원은 빠집니다. 순수한 관광 목적만 보려면 "
                "목적별 표를 따로 봐야 합니다.",
                "달마다 크게 흔들립니다. 명절과 방학, 연휴가 겹치는 달에 몰립니다. "
                "추세를 보려면 전년 같은 달과 견주는 편이 낫습니다.",
                "분류 차수가 바뀌면서 원천 표가 둘로 갈려 있습니다. 2021년 12월까지와 "
                "2022년 1월부터가 서로 다른 표입니다. 같은 기관의 같은 통계라 이어 "
                "붙였고, 이음새에 구멍이나 겹침이 없는 것을 확인했습니다.",
                "전에는 만 명 단위로 반올림한 정수만 들어 있었습니다. 원천에서 다시 "
                "받아 소수 첫째 자리까지 살렸습니다. 그래서 예전에 보던 값과 "
                "0.5만 명 안에서 다를 수 있습니다.",
            ],
            "updated": ymd,
        }
    }
    tot = got["전체"]
    pkt = max(ms, key=lambda k: tot[k])
    yr = {}
    for k in ms:
        yr.setdefault(int(k[:4]), []).append(tot[k])
    full = {y: sum(v) for y, v in yr.items() if len(v) == 12}
    py = max(full, key=full.get) if full else None
    manual = {
        "slide": "manual-visitors-total",
        "category": "TMI",
        "title": "외국인 입국자 수(월별)",
        "vizType": "line", "unit": "만 명",
        "labels": ms, "series": [[round(tot[k] / 1e4, 1) for k in ms]],
        "seriesNames": ["외국인 입국자"],
        "seriesColors": ["#2a5ca8"],
        "source": (f"한국문화관광연구원 관광지식정보시스템 외래객 입국. "
                   f"{ms[0]}~{last}. 단위: 만 명."),
        "sourceUrl": URL,
        "notes": [
            f"{last.replace('-', '년 ')}월 {tot[last] / 1e4:,.1f}만 명입니다. "
            f"가장 많았던 달은 {pkt.replace('-', '년 ')}월 "
            f"{tot[pkt] / 1e4:,.1f}만 명입니다."
            + (f" 해로 묶으면 {py}년 {full[py] / 1e4:,.0f}만 명이 가장 많습니다."
               if py else ""),
            "2020년 2월부터 2022년 상반기까지 바닥에 붙어 있는 구간이 코로나 "
            "유행기입니다. 입국 제한과 격리 때문이고 수요가 사라진 것과는 다릅니다.",
            "관광객이 아니라 입국자입니다. 상용과 유학연수, 그 밖의 목적이 모두 "
            "들어 있습니다. 승무원은 빠집니다.",
            "나라별로는 c1332 에 중국과 일본이 있습니다.",
            "분류 차수가 바뀌면서 원천 표가 둘로 갈려 있습니다. 2021년 12월까지와 "
            "2022년 1월부터가 서로 다른 표입니다. 이음새에 구멍이나 겹침이 없는 "
            "것을 확인했습니다.",
        ],
        "updated": ymd,
    }
    print(f"\n  외국인 입국자 수(월별) {len(ms)}달 {ms[0]}~{last}  끝 "
          f"{manual['series'][0][-1]}")
    print(f"\n  c1332 {len(ms)}달 {ms[0]}~{last}")
    for nm, s in zip(("중국", "일본"), ser):
        print(f"    {nm} {s[0]} ... {s[-1]}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
        return 0
    for cid, o in out.items():
        ov.setdefault(cid, {}).update(o)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8"))
    by = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    o = by.get(manual["slide"])
    if o:
        keep = {k: o[k] for k in ("id",) if k in o}
        o.clear(); o.update(manual); o.update(keep)
    else:
        doc["items"].append(manual)
    with open(mp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 과 data/manual.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
