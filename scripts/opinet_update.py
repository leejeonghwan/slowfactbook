#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""오피넷 일별 제품 평균가격을 이어붙인다.

오피넷은 조회 페이지가 자기 자신에게 POST 하고 결과를 표로 돌려준다(API 키 불필요).
  https://www.opinet.co.kr/user/dopospdrg/dopOsPdrgSelect.do

등록부는 data/opinet_map.json. 열쇠는 차트 id.
  {"c0850": {"codes": {"보통 휘발유.": "B027", "자동차용 경유.": "D047"}, "year": 2026}}

겹치는 날짜 값이 어긋나면 그 차트는 건드리지 않는다.

  python3 scripts/opinet_update.py --dry-run
  python3 scripts/opinet_update.py --apply
"""
import argparse, datetime, json, os, re, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

URL = "https://www.opinet.co.kr/user/dopospdrg/dopOsPdrgSelect.do"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
KST = datetime.timezone(datetime.timedelta(hours=9))
TOL = 0.01          # 원/리터. 소수 둘째자리까지 같아야 한다


def fetch(codes, d0, d1, term="D"):
    """{날짜: {코드이름: 값}} 을 돌려준다. term 은 'D'(일별) 또는 'M'(월별)."""
    q = {"TERM": term,
         "STA_Y": f"{d0.year}", "STA_M": f"{d0.month:02d}", "STA_D": f"{d0.day:02d}",
         "END_Y": f"{d1.year}", "END_M": f"{d1.month:02d}", "END_D": f"{d1.day:02d}",
         "chk_cnt": str(len(codes)), "all_chk_cnt": "5", "INIF_FLAG": "N", "equal": "Y"}
    for c in codes:
        q["OIL_CD_" + c] = "Y"
    req = urllib.request.Request(URL, data=urllib.parse.urlencode(q).encode(),
                                 headers={"User-Agent": UA,
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=45) as r:
        html = r.read().decode("utf-8", "replace")
    m = re.search(r"<table.*?</table>", html, re.S)
    if not m:
        raise RuntimeError("결과 표를 찾지 못했습니다")
    cells = [re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", c))
             for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", m.group(0), re.S)]
    # 머리글에서 열 순서를 읽는다
    out, cur = {}, None
    head = []
    for c in cells:
        if c in ("고급휘발유", "보통휘발유", "일반휘발유", "자동차용경유", "실내등유", "보일러등유"):
            head.append(c)
    vals = []
    for c in cells:
        dm = re.fullmatch(r"(\d{4})년(\d{2})월(?:(\d{2})일)?", c)
        if dm:
            if cur and vals:
                out[cur] = vals
            cur = "-".join(x for x in dm.groups() if x)
            vals = []
        elif cur is not None and re.fullmatch(r"-?[\d,]+(\.\d+)?", c):
            vals.append(float(c.replace(",", "")))
    if cur and vals:
        out[cur] = vals
    return head, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.apply:
        a.dry_run = True

    mp = os.path.join(DATA, "opinet_map.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if not mapping:
        print("data/opinet_map.json 이 비어 있습니다."); return 0

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
        term = spec.get("term", "D")
        labels = [str(x) for x in it["labels"]]
        want_re = r"\d{4}-\d{2}-\d{2}" if term == "D" else r"\d{4}-\d{2}"
        if not re.fullmatch(want_re, labels[-1]):
            skips.append((cid, f"라벨이 날짜 꼴이 아닙니다: {labels[-1]}")); continue
        if term == "D":
            last = datetime.date.fromisoformat(labels[-1])
            d0 = last - datetime.timedelta(days=20)   # 겹치는 20일로 대조
        else:
            y, mo = (int(x) for x in labels[-1].split("-"))
            d0 = datetime.date(y - 1, mo, 1)          # 겹치는 12개월로 대조
        codes = spec["codes"]                       # {계열이름: 코드}
        order = list(codes)
        try:
            head, rows = fetch([codes[k] for k in order], d0, today, term)
        except Exception as e:
            skips.append((cid, f"조회 실패: {e}")); continue
        # 머리글 순서대로 값이 들어오므로, 등록한 코드 순서와 맞춘다
        namemap = {"B034": "고급휘발유", "B027": "보통휘발유", "D047": "자동차용경유",
                   "C004": "실내등유", "C042": "보일러등유"}
        want = [namemap[codes[k]] for k in order]
        try:
            pos = [head.index(w) for w in want]
        except ValueError:
            skips.append((cid, f"열을 찾지 못했습니다 (받은 열 {head})")); continue

        bad = 0
        for d, vs in rows.items():
            if d in labels:
                i = labels.index(d)
                for k, p in zip(order, pos):
                    si = order.index(k)
                    a0 = it["series"][si][i]
                    if a0 is not None and p < len(vs) and abs(vs[p] - a0) > TOL:
                        bad += 1
        if bad:
            skips.append((cid, f"겹치는 구간 {bad}곳 불일치")); continue
        addd = [d for d in sorted(rows) if d > labels[-1]]
        if not addd:
            skips.append((cid, "이미 최신")); continue
        nl = labels + addd
        ns = []
        for si, k in enumerate(order):
            p = pos[si]
            ns.append(list(it["series"][si]) + [rows[d][p] if p < len(rows[d]) else None for d in addd])
        plans.append({"id": cid, "title": it["title"], "labels": nl, "series": ns,
                      "n": len(addd), "from": labels[-1], "to": nl[-1]})

    print(f"등록 {len(mapping)}건 · 이어붙일 것 {len(plans)}건 · 건너뜀 {len(skips)}건\n")
    for p in plans:
        print(f"  + {p['title'][:30]:32s} {p['from']} → {p['to']}  ({p['n']}개 추가)")
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
        print(f"\n→ data/overrides.json 에 {len(plans)}건 반영. 다음: python3 scripts/build.py")
    elif plans:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
