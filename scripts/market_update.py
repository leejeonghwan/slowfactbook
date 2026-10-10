#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""지수·시세 차트를 야후 파이낸스에서 이어붙인다.

등록부는 data/market_map.json. 열쇠는 차트 id.

  {"c0496": {"symbol": "^GSPC", "interval": "1mo",
             "note": "S&P 500 월말 종가", "sourceUrl": "..."}}

규칙
  1. 겹치는 구간 값이 어긋나면 그 차트는 건드리지 않는다(마지막 한 점만 예외).
     마지막 저장값은 달이 끝나기 전에 긁은 값일 수 있어 바로잡는 걸 허용한다.
  2. 아직 끝나지 않은 기간(이번 달/이번 주)은 붙이지 않는다.
  3. 결과는 data/overrides.json(labels/series/updated) + data/changelog.json.

  python3 scripts/market_update.py --dry-run
  python3 scripts/market_update.py --apply
"""
import argparse, datetime, json, os, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

TOL = 0.005          # 겹치는 구간 허용 오차 0.5%
CHECK = 120          # 대조할 뒤쪽 점 개수
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
KST = datetime.timezone(datetime.timedelta(hours=9))


def fetch(symbol, interval, years=20):
    """야후 차트 API.

    interval=1mo 에 range=max 를 주면 조용히 분기 값을 돌려준다(169점). 그래서
    범위는 period1/period2 로 못박는다. 한 번에 돌려주는 줄 수에도 상한이 있어
    필요한 뒤쪽 구간만 가져온다 — 이어붙이기와 대조에는 그걸로 충분하다.
    """
    now = int(time.time())
    p1 = max(0, now - int(years * 366 * 86400))
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(symbol, safe="")
           + f"?interval={interval}&period1={p1}&period2={now + 86400}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                doc = json.load(r)
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 + attempt * 3)
    res = doc["chart"]["result"][0]
    off = res["meta"].get("gmtoffset") or 0
    ts = res["timestamp"]
    close = res["indicators"]["quote"][0]["close"]
    out = {}
    for t, c in zip(ts, close):
        if c is None:
            continue
        d = datetime.datetime.fromtimestamp(t + off, datetime.timezone.utc)
        out[key_of(d, interval)] = round(c, 2)
    return out


def key_of(d, interval):
    if interval == "1mo":
        return d.strftime("%Y-%m")
    if interval == "1wk":
        return d.strftime("%Y-%m-%d")
    if interval in ("3mo",):
        return f"{d.year} {(d.month - 1) // 3 + 1}Q"
    return d.strftime("%Y-%m-%d")


def open_period(interval, now=None):
    """아직 끝나지 않은 기간의 열쇠 — 이건 붙이지 않는다."""
    now = now or datetime.datetime.now(KST)
    if interval == "1mo":
        return now.strftime("%Y-%m")
    if interval == "3mo":
        return f"{now.year} {(now.month - 1) // 3 + 1}Q"
    if interval == "1wk":
        monday = now - datetime.timedelta(days=now.weekday())
        return monday.strftime("%Y-%m-%d")
    return now.strftime("%Y-%m-%d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="차트 id 하나만")
    a = ap.parse_args()
    if not a.apply:
        a.dry_run = True

    mp = os.path.join(DATA, "market_map.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if not mapping:
        print("data/market_map.json 이 비어 있습니다."); return 0

    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in _items if it.get("id")}

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    today = datetime.date.today().isoformat()
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    plans, skips = [], []
    for cid, spec in mapping.items():
        if a.only and cid != a.only:
            continue
        it = items.get(cid)
        if not it:
            skips.append((cid, "차트를 찾지 못했습니다")); continue
        if len(it["series"]) != 1:
            skips.append((cid, f"계열 {len(it['series'])}개 — 단일 계열만 지원")); continue
        interval = spec.get("interval", "1mo")
        try:
            remote = fetch(spec["symbol"], interval, float(spec.get("years", 20)))
            start = spec.get("start")
            if start:
                remote = {k: v for k, v in remote.items() if k >= start}
        except Exception as e:
            skips.append((cid, f"조회 실패: {e}")); continue

        labels = [str(x) for x in it["labels"]]
        vals = list(it["series"][0])
        bad, seen = [], 0
        for lab, v in list(zip(labels, vals))[-CHECK:]:
            r = remote.get(lab)
            if r is None or v is None:
                continue
            seen += 1
            if abs(r - v) / max(abs(v), 1e-9) > TOL:
                bad.append((lab, v, r))
        if seen < 6:
            skips.append((cid, f"대조할 점이 {seen}개뿐 — 라벨 형식을 확인하세요")); continue
        # 마지막 한 점은 달이 끝나기 전 값일 수 있어 바로잡기를 허용한다
        tail_fix = None
        if bad and len(bad) == 1 and bad[0][0] == labels[-1]:
            tail_fix = bad[0]; bad = []
        if bad:
            skips.append((cid, f"겹치는 구간 {len(bad)}곳 불일치 (예 {bad[0][0]}: 저장 {bad[0][1]} / 원본 {bad[0][2]})"))
            continue

        cut = open_period(interval)
        addk = [k for k in sorted(remote) if k > labels[-1] and k != cut]
        if not addk and not tail_fix:
            skips.append((cid, "이미 최신")); continue
        nl = labels + addk
        nv = vals + [remote[k] for k in addk]
        if tail_fix:
            nv[len(labels) - 1] = tail_fix[2]
        plans.append({"id": cid, "title": it["title"], "category": it["category"],
                      "labels": nl, "series": [nv], "n": len(addk),
                      "from": labels[-1], "to": nl[-1], "tail_fix": tail_fix,
                      "sourceUrl": spec.get("sourceUrl", ""), "slide": it.get("slide")})

    print(f"등록 {len(mapping)}건 · 이어붙일 것 {len(plans)}건 · 건너뜀 {len(skips)}건\n")
    for p in plans:
        line = f"  + {p['title'][:30]:32s} {p['from']} → {p['to']}  ({p['n']}점 추가"
        if p["tail_fix"]:
            line += f", 마지막 점 {p['tail_fix'][1]}→{p['tail_fix'][2]} 보정"
        print(line + ")")
    for cid, why in skips:
        print(f"  - {cid}: {why}")

    if a.apply and plans:
        for p in plans:
            o = ov.setdefault(p["id"], {})
            o["labels"] = p["labels"]
            o["series"] = p["series"]
            o["updated"] = stamp
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        clp = os.path.join(DATA, "changelog.json")
        cl = json.load(open(clp, encoding="utf-8")) if os.path.exists(clp) else []
        for p in plans:
            cl.append({"date": today, "slide": p["slide"], "id": p["id"], "title": p["title"],
                       "category": p["category"], "mode": "auto",
                       "from": p["from"], "to": p["to"], "n": p["n"],
                       "sourceUrl": p["sourceUrl"], "keynoteSynced": False,
                       "note": ("마지막 점 보정 " + str(p["tail_fix"][1]) + "→" + str(p["tail_fix"][2])) if p["tail_fix"] else ""})
        json.dump(cl, open(clp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n→ data/overrides.json 에 {len(plans)}건 반영. 다음: python3 scripts/build.py")
    elif plans:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
