#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IMF World Economic Outlook 연간 지표를 차트에 붙인다.

데이터매퍼 API 는 키가 필요 없다.
  https://www.imf.org/external/datamapper/api/v1/<지표>/<나라코드>

등록부는 data/imf_map.json. 열쇠는 차트 id.
  {"c0669": {"indicator": "GGXWDG_NGDP", "country": "KOR", "split": 2024,
             "sourceUrl": "https://www.imf.org/external/datamapper/GGXWDG_NGDP/KOR"}}

split 을 적으면 그 해까지는 실적(첫 계열), 그 해부터는 전망(둘째 계열)으로
나눠 넣는다. 전망선이 실적선에서 이어지도록 split 해는 양쪽에 다 넣는다.
split 이 없으면 계열 하나에 통째로 넣는다.

WEO 는 판본이 바뀔 때마다 과거 수치까지 손본다. 그래서 겹치는 구간을
대조해 막지 않고, 받아온 값으로 덮어쓴다(mode 는 늘 replace 다). 다만
데이터매퍼가 주지 않는 옛 연도는 차트에 있던 값을 그대로 둔다.

  python3 scripts/imf_update.py            미리보기
  python3 scripts/imf_update.py --apply
"""
import argparse, datetime, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
API = "https://www.imf.org/external/datamapper/api/v1/{ind}/{cty}"


def fetch(ind, cty):
    """{"YYYY": 값}. urllib 이 자주 막혀 curl 로 받는다."""
    url = API.format(ind=ind, cty=cty)
    out = subprocess.run(["curl", "-sS", "--compressed", "--max-time", "60", url],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:120])
    d = json.loads(out.stdout)
    vals = (d.get("values") or {}).get(ind, {}).get(cty)
    if not vals:
        raise RuntimeError(f"{ind}/{cty}: 값이 비었습니다")
    return {str(k): float(v) for k, v in vals.items() if v is not None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()

    mp = os.path.join(DATA, "imf_map.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if a.only:
        mapping = {k: v for k, v in mapping.items() if k == a.only}
    if not mapping:
        print("data/imf_map.json 이 비어 있습니다."); return 0

    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in _items if it.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    plans, skips = [], []
    for cid, spec in mapping.items():
        it = items.get(cid)
        if not it:
            skips.append((cid, "차트를 찾지 못했습니다")); continue
        labels = [str(x) for x in it["labels"]]
        # series 를 적으면 나라마다 한 계열씩 만든다.
        multi = spec.get("series")
        if multi:
            try:
                ms = [fetch(spec["indicator"], x["country"]) for x in multi]
            except Exception as e:
                skips.append((cid, f"조회 실패: {e}")); continue
            if len(ms) != len(it["series"]):
                skips.append((cid, f"계열 {len(ms)}개 != 차트 {len(it['series'])}개")); continue
            yrs = sorted({y for d in ms for y in d if y.isdigit()}, key=int)
            lo = str(spec.get("from", yrs[0]))
            nl = [y for y in sorted(set(labels) | set(yrs), key=int) if y >= lo]
            ns = [[d.get(y) for y in nl] for d in ms]
            if nl == labels and ns == it["series"]:
                skips.append((cid, "이미 최신")); continue
            plans.append({"id": cid, "title": it["title"], "labels": nl, "series": ns,
                          "from": labels[-1], "to": nl[-1], "n": len(yrs)})
            continue
        try:
            m = fetch(spec["indicator"], spec.get("country", "KOR"))
        except Exception as e:
            skips.append((cid, f"조회 실패: {e}")); continue

        split = spec.get("split")
        nl = sorted(set(labels) | {y for y in m if y.isdigit()}, key=int)
        old = {y: [s[labels.index(y)] if y in labels else None for s in it["series"]]
               for y in nl}
        if split is None:
            ns = [[m.get(y, old[y][0]) for y in nl]]
        else:
            s0 = [m[y] if (y in m and int(y) <= split) else
                  (old[y][0] if int(y) <= split else None) for y in nl]
            s1 = [m[y] if (y in m and int(y) >= split) else None for y in nl]
            ns = [s0, s1]
        if len(ns) != len(it["series"]):
            skips.append((cid, f"계열 {len(ns)}개 != 차트 {len(it['series'])}개")); continue
        if nl == labels and ns == it["series"]:
            skips.append((cid, "이미 최신")); continue
        plans.append({"id": cid, "title": it["title"], "labels": nl, "series": ns,
                      "from": labels[-1], "to": nl[-1], "n": len(m)})

    print(f"등록 {len(mapping)}건 · 고칠 것 {len(plans)}건 · 건너뜀 {len(skips)}건\n")
    for p in plans:
        print(f"  + {p['title'][:26]:28s} {p['from']} -> {p['to']}  (IMF {p['n']}개 해)")
    for cid, why in skips:
        print(f"  - {cid}: {why}")

    if a.apply and plans:
        for p in plans:
            spec = mapping[p["id"]]
            o = ov.setdefault(p["id"], {})
            o["id"] = p["id"]
            o["labels"] = p["labels"]; o["series"] = p["series"]
            for k in ("source", "sourceUrl", "unit", "seriesNames"):
                if spec.get(k):
                    o[k] = spec[k]
            o["updated"] = stamp
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n-> data/overrides.json 에 {len(plans)}건 반영.")
    elif plans:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
