#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""인천국제공항 월별 통계(운항·여객·화물)를 이어붙인다.

조회 페이지는 조건을 base64(enc) 로 감싸 넘긴다. 그 enc 를 직접 만들어 표를 받는다.
  https://www.airport.kr/co_ko/651/subview.do?enc=...

등록부는 data/airport_map.json. 열쇠는 차트 id.
  {"c1354": {"col": "여객-합계", "scale": 0.0001}}
  col 은 운항/여객/화물 × 도착/출발/합계 중 하나.

겹치는 달의 값이 하나라도 어긋나면 그 차트는 건드리지 않는다.
"""
import argparse, base64, datetime, json, os, re, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
GROUPS = ["운항", "여객", "화물"]
SUBS = ["도착", "출발", "합계"]


def fetch(y0, m0, y1, m1):
    inner = ("/fsmFsn/co_ko/statisticCategoryOfTimeSeries.do?firstYn=1&nvgSe=&arplnSe=&routeSe="
             f"&bag=&terminalId=&pas=&stYear={y0}&stMonth={m0:02d}&edYear={y1}&edMonth={m1:02d}&tmType=TM_A&")
    enc = base64.b64encode(("fnct1|@@|" + urllib.parse.quote(inner, safe="")).encode()).decode()
    url = "https://www.airport.kr/co_ko/651/subview.do?enc=" + urllib.parse.quote(enc, safe="")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    m = re.search(r"<table.*?</table>", html, re.S)
    if not m:
        raise RuntimeError("결과 표를 찾지 못했습니다")
    cells = [re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", c))
             for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", m.group(0), re.S)]
    # 머리글 14칸(년·월 + 3그룹×3칸 + 그룹명 3칸)을 지나면 11칸씩 한 줄이다
    body = cells[14:]
    out = {}
    for i in range(0, len(body) - 10, 11):
        row = body[i:i + 11]
        if not (re.fullmatch(r"\d{4}", row[0]) and re.fullmatch(r"\d{1,2}", row[1])):
            continue
        key = f"{row[0]}-{int(row[1]):02d}"
        vals = {}
        for gi, grp in enumerate(GROUPS):
            for si, sub in enumerate(SUBS):
                v = row[2 + gi * 3 + si].replace(",", "")
                vals[f"{grp}-{sub}"] = float(v) if re.fullmatch(r"-?\d+(\.\d+)?", v) else None
        out[key] = vals
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.apply:
        a.dry_run = True

    mp = os.path.join(DATA, "airport_map.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if not mapping:
        print("data/airport_map.json 이 비어 있습니다."); return 0

    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in _items if it.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    today = datetime.datetime.now(KST).date()

    plans, skips = [], []
    for cid, spec in mapping.items():
        it = items.get(cid)
        if not it:
            skips.append((cid, "차트를 찾지 못했습니다")); continue
        labels = [str(x) for x in it["labels"]]
        if not re.fullmatch(r"\d{4}-\d{2}", labels[-1]):
            skips.append((cid, f"라벨이 월 꼴이 아닙니다: {labels[-1]}")); continue
        last = labels[-1]
        y0, m0 = int(last[:4]), int(last[5:])
        y0 -= 1                                   # 대조할 겹침을 1년 확보한다
        try:
            rows = fetch(y0, m0, today.year, today.month)
        except Exception as e:
            skips.append((cid, f"조회 실패: {e}")); continue
        col, sc = spec["col"], float(spec.get("scale", 1))
        cur = it["series"][0]
        bad = []
        for k, v in rows.items():
            if k in labels and v.get(col) is not None:
                a0 = cur[labels.index(k)]
                b0 = round(v[col] * sc, 4)
                if a0 is not None and abs(a0 - b0) > max(0.01, abs(b0) * 0.001):
                    bad.append((k, a0, b0))
        if bad:
            skips.append((cid, f"겹치는 구간 {len(bad)}곳 불일치 (예 {bad[0]})")); continue
        addk = [k for k in sorted(rows) if k > last and rows[k].get(col) is not None]
        if not addk:
            skips.append((cid, "이미 최신")); continue
        nl = labels + addk
        nv = list(cur) + [round(rows[k][col] * sc, 4) for k in addk]
        plans.append({"id": cid, "title": it["title"], "labels": nl, "series": [nv],
                      "n": len(addk), "from": last, "to": nl[-1]})

    print(f"등록 {len(mapping)}건 · 이어붙일 것 {len(plans)}건 · 건너뜀 {len(skips)}건\n")
    for p in plans:
        print(f"  + {p['title'][:30]:32s} {p['from']} → {p['to']}  ({p['n']}개월 추가)")
    for cid, why in skips:
        print(f"  - {cid}: {why}")

    if a.apply and plans:
        for p in plans:
            o = ov.setdefault(p["id"], {})
            o["labels"] = p["labels"]; o["series"] = p["series"]; o["updated"] = stamp
            # 자동 갱신에 쓴 참조 주소를 차트에 남긴다 (차트 페이지의 '출처 링크' 버튼).
            u = (mapping.get(p["id"]) or {}).get("sourceUrl")
            if u:
                o["sourceUrl"] = u
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n→ data/overrides.json 에 {len(plans)}건 반영.")
    elif plans:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
