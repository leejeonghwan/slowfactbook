#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KRX 오픈API 로 시가총액 차트를 갱신한다.

  https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd?basDd=YYYYMMDD
  헤더 AUTH_KEY 에 .env 의 KRX_API_KEY. 2010년 1월 4일 자료부터 제공된다.

호출 단위가 '하루치 전 종목'이다. 한 번 부르면 그날 유가증권 전 종목의
시가총액이 통째로 오므로, 필요한 종목 몇 개와 시장 전체 합계를 한꺼번에
뽑아 data/krx_cache.json 에 달별로 쟁여 둔다. 같은 달을 두 번 부르지 않는다.

등록부는 data/krx_map.json. 계열 순서는 차트와 같아야 한다.

  {"c1083": {"fold": "last", "from": "2010-01",
             "series": [{"isu": "000660", "field": "MKTCAP", "scale": 1e-12},
                        {"isu": "005930", "field": "MKTCAP", "scale": 1e-12}]}}

  fold  "last" 는 그달 마지막 거래일(한 달에 호출 1번),
        "mean" 은 그달 거래일 평균(한 달에 20번쯤).
  from  이 달부터만 손댄다. 2010년 이전은 KRX 가 안 주므로 기존 값을 남긴다.
  isu   "005930" 같은 6자리. 전 종목 합계는 "*" 로 적는다(비중 차트용).
  field MKTCAP(시가총액)·TDD_CLSPRC(종가)·LIST_SHRS(상장주식수).
  scale 곱할 배수. 원 단위 시가총액을 조 원으로 보려면 1e-12.

겹치는 달이 어긋나면 그 차트는 건드리지 않는다. 다만 "mode": "replace" 면
from 이후 구간을 통째로 다시 깐다(겹치는 구간이 대체로 맞을 때만).
"""
import argparse, calendar, datetime, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
API = "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"
FIRST = "2010-01"                      # KRX 가 제공하는 첫 달
CACHE = os.path.join(DATA, "krx_cache.json")
FIELDS = ("MKTCAP", "TDD_CLSPRC", "LIST_SHRS")


def auth():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if ln.startswith("KRX_API_KEY="):
                return ln.split("=", 1)[1].strip()
    return os.environ.get("KRX_API_KEY", "")


def call(day, key):
    """하루치를 부른다. 휴장일이면 빈 목록이 온다."""
    r = subprocess.run(["curl", "-sSL", "--max-time", "60", "-H", f"AUTH_KEY: {key}",
                        f"{API}?basDd={day}"], capture_output=True, text=True, timeout=90).stdout
    d = json.loads(r)
    if d.get("respMsg"):
        raise RuntimeError(f"{day}: {d['respMsg']} — 활용신청이 되어 있는지 보세요")
    return d.get("OutBlock_1") or []


def digest(rows, want):
    """필요한 종목과 전 종목 합계만 남긴다."""
    def num(x):
        try:
            return float(str(x).replace(",", ""))
        except (TypeError, ValueError):
            return None
    out, total = {}, 0.0
    for r in rows:
        # 종목코드가 "005930" 으로 올 수도, "KR7005930003" 으로 올 수도 있다.
        code = str(r.get("ISU_CD", "")).strip()
        short = code[3:9] if len(code) == 12 else code
        m = num(r.get("MKTCAP"))
        if m:
            total += m
        if short in want:
            out[short] = {f: num(r.get(f)) for f in FIELDS}
    out["*"] = {"MKTCAP": total, "TDD_CLSPRC": None, "LIST_SHRS": None}
    return out


def days_of(ym, fold):
    """부를 날짜들. last 는 월말부터 거꾸로, mean 은 그 달 전부."""
    y, m = int(ym[:4]), int(ym[5:7])
    last = calendar.monthrange(y, m)[1]
    ds = [f"{y}{m:02d}{d:02d}" for d in range(1, last + 1)]
    return list(reversed(ds)) if fold == "last" else ds


def month_data(ym, fold, want, key, cache, budget):
    """한 달치를 쟁여 둔 것에서 꺼내거나, 없으면 부른다."""
    ck = f"{ym}|{fold}"
    if ck in cache:
        return cache[ck], 0
    got, used = [], 0
    for day in days_of(ym, fold):
        if budget is not None and used >= budget:
            break
        rows = call(day, key)
        used += 1
        if not rows:
            continue                   # 휴장일
        got.append(digest(rows, want))
        if fold == "last":
            break                      # 마지막 거래일 하나면 된다
    if not got:
        return None, used
    if fold == "last":
        cache[ck] = got[0]
    else:
        acc = {}
        for k in set().union(*[set(d) for d in got]):
            for f in FIELDS:
                vs = [d[k][f] for d in got if k in d and d[k].get(f) is not None]
                acc.setdefault(k, {})[f] = round(sum(vs) / len(vs), 4) if vs else None
        cache[ck] = acc
    return cache[ck], used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", help="이 차트 id 만")
    ap.add_argument("--max-calls", type=int, default=60,
                    help="이번 실행에서 쓸 최대 호출 수 (백필은 여러 번 나눠 돌린다)")
    a = ap.parse_args()

    key = auth()
    if not key:
        print(".env 에 KRX_API_KEY 가 없습니다."); return 1
    mp = os.path.join(DATA, "krx_map.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if a.only:
        mapping = {k: v for k, v in mapping.items() if k == a.only}
    if not mapping:
        print("data/krx_map.json 이 비어 있습니다."); return 0

    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    before = len(cache)
    now = datetime.datetime.now(KST)
    cut = now.strftime("%Y-%m")        # 이번 달은 아직 안 끝났다

    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in _items if it.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    stamp = now.strftime("%Y-%m-%d %H:%M")

    budget = a.max_calls
    plans, skips = [], []
    for cid, spec in mapping.items():
        it = items.get(cid)
        if not it:
            skips.append((cid, "차트를 찾지 못했습니다")); continue
        labels = [str(x) for x in it["labels"]]
        if not re.fullmatch(r"\d{4}-\d{2}", labels[-1]):
            skips.append((cid, f"라벨이 월 꼴이 아닙니다: {labels[-1]}")); continue
        sers = spec.get("series") or []
        if len(sers) != len(it["series"]):
            skips.append((cid, f"등록 계열 {len(sers)}개 != 차트 계열 {len(it['series'])}개")); continue

        fold = spec.get("fold", "last")
        lo = max(spec.get("from", FIRST), FIRST)
        want = {s["isu"] for s in sers if s["isu"] != "*"}
        tol = float(spec.get("tol", 0.5))

        # 손댈 달: 차트에 이미 있는 달 중 from 이후 + 차트 뒤로 새로 붙일 달
        have = [k for k in labels if k >= lo and k < cut]
        y, m = int(labels[-1][:4]), int(labels[-1][5:7])
        nxt = []
        while True:
            m += 1
            if m == 13:
                y, m = y + 1, 1
            k = f"{y}-{m:02d}"
            if k >= cut:
                break
            nxt.append(k)
        todo = [k for k in have + nxt if f"{k}|{fold}" not in cache]
        if budget is not None and len(todo) > budget and fold == "mean":
            todo = todo[-budget:]

        err = None
        for k in have + nxt:
            if budget is not None and budget <= 0:
                break
            try:
                _, used = month_data(k, fold, want, key, cache, budget)
                if budget is not None:
                    budget -= used
            except Exception as e:
                err = str(e); break
        if err:
            skips.append((cid, err)); continue

        def val(k, s):
            """한 달치에서 계열 하나의 값을 꺼낸다.

            SHARE 는 유가증권 전체 시가총액 대비 비중(%), SHARE_REST 는 minus 에
            적은 종목들을 뺀 나머지의 비중이다. 전체 합계는 하루치를 받을 때
            같이 계산해 두므로 추가 호출이 없다.
            """
            d = cache.get(f"{k}|{fold}")
            if not d:
                return None
            f = s.get("field", "MKTCAP")
            tot = (d.get("*") or {}).get("MKTCAP")
            if f in ("SHARE", "SHARE_REST"):
                if not tot:
                    return None
                if f == "SHARE":
                    m = (d.get(s["isu"]) or {}).get("MKTCAP")
                    return None if m is None else round(m / tot * 100, 4)
                mine = [(d.get(x) or {}).get("MKTCAP") for x in s.get("minus", [])]
                if any(x is None for x in mine):
                    return None
                return round((tot - sum(mine)) / tot * 100, 4)
            if s["isu"] not in d:
                return None
            v = d[s["isu"]].get(f)
            if v is None:
                return None
            # plus 에 적은 종목을 더한다. 우선주를 포함한 시가총액이 그런 경우다
            # (삼성전자 005930 + 삼성전자우 005935).
            for x in s.get("plus", []):
                w = (d.get(x) or {}).get(f)
                if w is None:
                    return None
                v += w
            return round(v * float(s.get("scale", 1)), 4)

        # 겹치는 달 대조
        bad, seen = [], 0
        for i, k in enumerate(labels):
            if k < lo:
                continue
            for si, s in enumerate(sers):
                a0, b0 = it["series"][si][i], val(k, s)
                if a0 is None or b0 is None:
                    continue
                seen += 1
                if abs(a0 - b0) > max(tol, abs(b0) * 0.01):
                    bad.append((k, s["isu"], a0, b0))
        if seen < 6:
            skips.append((cid, f"대조할 달이 부족합니다({seen}곳)")); continue

        if spec.get("mode") == "replace":
            ks = [k for k in sorted({*labels, *nxt}) if k >= lo
                  and all(val(k, s) is not None for s in sers)]
            keep = [k for k in labels if k < lo]
            nl = keep + ks
            ns = [[it["series"][si][labels.index(k)] for k in keep] + [val(k, s) for k in ks]
                  for si, s in enumerate(sers)]
            if nl == labels and all(ns[i] == it["series"][i] for i in range(len(ns))):
                skips.append((cid, "이미 최신")); continue
            plans.append({"id": cid, "title": it["title"], "labels": nl, "series": ns,
                          "from": labels[-1], "to": nl[-1],
                          "note": f"{lo} 이후 교체 {len(bad)}곳 수정"})
            continue

        if bad:
            skips.append((cid, f"겹치는 구간 {len(bad)}곳 불일치 (예 {bad[0]})")); continue
        addk = [k for k in nxt if all(val(k, s) is not None for s in sers)]
        if not addk:
            skips.append((cid, "이미 최신")); continue
        plans.append({"id": cid, "title": it["title"], "labels": labels + addk,
                      "series": [list(s) + [val(k, sp) for k in addk]
                                 for s, sp in zip(it["series"], sers)],
                      "from": labels[-1], "to": addk[-1],
                      "note": f"({len(addk)}개월 추가)"})

    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"등록 {len(mapping)}건 · 고칠 것 {len(plans)}건 · 건너뜀 {len(skips)}건"
          f" · 새로 받은 달 {len(cache)-before}개 · 남은 호출 {budget}\n")
    for p in plans:
        print(f"  + {p['title'][:30]:32s} {p['from']} -> {p['to']}  {p['note']}")
    for cid, why in skips:
        print(f"  - {cid}: {why}")

    if a.apply and plans:
        for p in plans:
            o = ov.setdefault(p["id"], {})
            o["id"] = p["id"]
            o["labels"] = p["labels"]; o["series"] = p["series"]; o["updated"] = stamp
            u = (mapping.get(p["id"]) or {}).get("sourceUrl")
            if u:
                o["sourceUrl"] = u
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n-> data/overrides.json 에 {len(plans)}건 반영.")
    elif plans:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
