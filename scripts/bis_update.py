#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""국제결제은행(BIS) 통계를 차트에 붙인다.

등록부는 data/bis_map.json. 열쇠는 차트 id.

  {"c0671": {"flow": "WS_TC/2.0", "mode": "replace",
             "series": [{"key": "Q.KR.H.A.M.770.A", "name": "가계부채"},
                        {"key": "Q.KR.N.A.M.770.A", "name": "기업부채"}],
             "unit": "%", "source": "...", "sourceUrl": "..."}}

BIS 통계 포털의 SDMX API 에서 CSV 를 받아 TIME_PERIOD 를 그대로 라벨로 쓴다.
분기는 "YYYY-Q1", 연간은 "YYYY", 월간은 "YYYY-MM" 으로 내려와 차트 라벨과 같다.

기본은 '이어붙이기'다. 겹치는 구간이 어긋나면 그 차트는 건드리지 않는다.
BIS 는 과거까지 자주 고쳐 쓰므로, 같은 계열임을 확인한 차트에는
"mode": "replace" 로 통째로 갈아끼우는 쪽이 낫다.

쓸 만한 흐름(flow)과 열쇠:
  WS_TC/2.0        총신용. Q.<나라>.<차주>.<대출자>.<평가>.<단위>.<조정>
                   차주 H 가계 · N 기업 · G 정부 · P 민간 · C 비금융
                   단위 770 GDP 대비 % · 'A' 조정은 단절 보정
  WS_CREDIT_GAP/1.0  GDP 대비 신용 갭
  WS_DSR/1.0         원리금 상환 부담률

  python3 scripts/bis_update.py            미리보기
  python3 scripts/bis_update.py --apply
"""
import argparse, csv, datetime, io, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
BASE = "https://stats.bis.org/api/v2/data/dataflow/BIS"


def fetch(flow, key):
    """{"YYYY-Q1": 값}. 빈 관측치는 버린다."""
    url = f"{BASE}/{flow}/{key}?format=csv"
    req = urllib.request.Request(url, headers={"Accept": "text/csv"})
    with urllib.request.urlopen(req, timeout=120) as r:
        text = r.read().decode("utf-8-sig")
    if text.lstrip().startswith("<"):
        raise RuntimeError("CSV 가 아니라 오류 응답이 왔습니다")
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        t = (row.get("TIME_PERIOD") or "").strip()
        v = (row.get("OBS_VALUE") or "").strip()
        if t and v:
            out[t] = float(v)
    return out


def this_period(lab, now):
    """아직 끝나지 않은 구간. 라벨 꼴로 주기를 알아낸다."""
    if "-Q" in lab:
        return f"{now.year}-Q{(now.month - 1) // 3 + 1}"
    if "-" in lab:
        return now.strftime("%Y-%m")
    return str(now.year)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", help="이 차트 id 만")
    a = ap.parse_args()

    mp = os.path.join(DATA, "bis_map.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if a.only:
        mapping = {k: v for k, v in mapping.items() if k == a.only}
    if not mapping:
        print("data/bis_map.json 이 비어 있습니다."); return 0

    now = datetime.datetime.now(KST)
    stamp = now.strftime("%Y-%m-%d %H:%M")

    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in _items if it.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}

    plans, skips = [], []
    for cid, spec in mapping.items():
        it = items.get(cid)
        if not it:
            skips.append((cid, "차트를 찾지 못했습니다")); continue
        labels = [str(x) for x in it["labels"]]
        sers = spec.get("series") or []
        if len(sers) != len(it["series"]):
            skips.append((cid, f"등록 계열 {len(sers)}개 != 차트 계열 "
                               f"{len(it['series'])}개")); continue
        cut = this_period(labels[-1], now)
        mode = spec.get("mode", "append")
        tol = float(spec.get("tol", 1.0))

        got, err = [], None
        for s in sers:
            try:
                raw = fetch(s.get("flow", spec["flow"]), s["key"])
                sc = float(s.get("scale", spec.get("scale", 1)))
                rd = s.get("round", spec.get("round"))
                if sc != 1 or rd is not None:
                    raw = {k: (round(v * sc, rd) if rd is not None else v * sc)
                           for k, v in raw.items()}
                got.append(raw)
            except Exception as e:
                err = f"조회 실패: {e}"; break
        if err:
            skips.append((cid, err)); continue
        if not got[0]:
            skips.append((cid, "내려온 값이 없습니다")); continue

        if mode == "replace":
            keys = [k for k in sorted(got[0]) if k != cut
                    and all(d.get(k) is not None for d in got)]
            if not keys:
                skips.append((cid, "쓸 구간이 없습니다")); continue
            nl, ns = keys, [[d[k] for k in keys] for d in got]
            note = f"통째로 교체 ({len(keys)}개 구간, {keys[0]}~{keys[-1]})"
            if nl == labels and ns == it["series"]:
                skips.append((cid, "이미 최신")); continue
        else:
            bad, seen = [], 0
            for si, d in enumerate(got):
                for k, b0 in d.items():
                    if k not in labels:
                        continue
                    a0 = it["series"][si][labels.index(k)]
                    if a0 is None:
                        continue
                    seen += 1
                    if abs(a0 - b0) > tol:
                        bad.append((k, a0, b0))
            if seen < 6:
                skips.append((cid, f"대조할 구간이 부족합니다({seen}곳)")); continue
            if bad:
                skips.append((cid, f"겹치는 구간 {len(bad)}곳 불일치 "
                                   f"(예 {bad[0]})")); continue
            addk = [k for k in sorted(got[0]) if k > labels[-1] and k != cut
                    and all(d.get(k) is not None for d in got)]
            if not addk:
                skips.append((cid, "이미 최신")); continue
            nl = labels + addk
            ns = [list(s) + [d[k] for k in addk] for s, d in zip(it["series"], got)]
            note = f"{len(addk)}개 구간 추가"

        plans.append({"id": cid, "title": it["title"], "labels": nl, "series": ns,
                      "from": labels[-1], "to": nl[-1], "note": note,
                      "names": [s.get("name") for s in sers]})

    print(f"등록 {len(mapping)}건 · 고칠 것 {len(plans)}건 · 건너뜀 {len(skips)}건\n")
    for p in plans:
        print(f"  + {p['title'][:26]:28s} {p['from']} -> {p['to']}  {p['note']}")
    for cid, why in skips:
        print(f"  - {cid}: {why}")

    if a.apply and plans:
        for p in plans:
            spec = mapping[p["id"]]
            o = ov.setdefault(p["id"], {})
            o["id"] = p["id"]
            o["labels"] = p["labels"]; o["series"] = p["series"]
            if all(p["names"]):
                o["seriesNames"] = p["names"]
            for k in ("title", "source", "sourceUrl", "unit"):
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
