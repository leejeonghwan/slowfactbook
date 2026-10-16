#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국은행 ECOS 월별 시계열을 차트에 붙인다.

등록부는 data/ecos_map.json. 열쇠는 차트 id, 계열 순서는 차트와 같아야 한다.

  {"c0828": {"stat": "731Y004", "cycle": "M", "from": "198201",
             "mode": "replace",
             "series": [{"items": ["0000001", "0000100"], "name": "원-달러 환율"}],
             "source": "한국은행 ECOS. ...",
             "sourceUrl": "https://ecos.bok.or.kr/..."}}

기본은 '이어붙이기'다. 겹치는 달이 어긋나면 그 차트는 건드리지 않는다.
표가 바뀐 게 아니라 다른 계열을 붙이려 한 것일 수 있어서다.

계열마다 "stat"/"cycle"/"from" 을 따로 적으면 한 차트에 다른 표를 섞을 수 있다.
연간 값을 분기 차트에 얹을 때는 "asQuarter": 4, "roll": 11 은 가운데 맞춘 11구간 평균이다.
그 계열이 띄엄띄엄이면
"sparse": true 를 붙인다(라벨을 고를 때 이 계열은 세지 않는다).

"slots": [0, 1] 은 차트의 몇 번째 계열만 손댈지 고른다. 나머지 계열은
그대로 둔다. 한 차트에 다른 출처의 계열이 섞여 있을 때 쓴다.

"mode": "replace" 는 겹치는 구간을 대조하지 않고 ECOS 값으로 통째로 바꾼다.
출처가 없거나 어디서 왔는지 모르는 숫자를 한국은행 값으로 갈아끼울 때만 쓴다.

  ECOS_API_KEY=... python3 scripts/ecos_update.py            미리보기
  ECOS_API_KEY=... python3 scripts/ecos_update.py --apply
"""
import argparse, datetime, json, os, re, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
KEY = os.environ.get("ECOS_API_KEY", "")
BASE = "https://ecos.bok.or.kr/api/StatisticSearch"


def fetch(stat, cycle, start, end, items):
    """{"YYYY-MM": 값}. items 는 1~3단 항목 코드."""
    parts = [stat, cycle, start, end] + list(items)
    url = BASE + "/" + KEY + "/json/kr/1/100000/" + "/".join(
        urllib.parse.quote(str(p), safe="") for p in parts)
    with urllib.request.urlopen(url, timeout=90) as r:
        d = json.loads(r.read().decode("utf-8"))
    if "RESULT" in d:
        code = d["RESULT"].get("CODE", "")
        if code == "INFO-200":
            return {}
        raise RuntimeError(f"{code} {d['RESULT'].get('MESSAGE','')[:80]}")
    out = {}
    for r in d.get("StatisticSearch", {}).get("row", []):
        v = r.get("DATA_VALUE")
        t = str(r.get("TIME", "")).strip()
        if v in (None, "", "."):
            continue
        k = stamp_of(t, cycle)
        if k:
            out[k] = float(v)
    return out


def stamp_of(t, cycle):
    """ECOS 시점 문자열을 차트 라벨 꼴로. 주기마다 다르게 온다."""
    if cycle == "M" and re.fullmatch(r"\d{6}", t):
        return f"{t[:4]}-{t[4:6]}"
    if cycle == "Q":
        m = re.fullmatch(r"(\d{4})(?:Q)?([1-4])", t)
        if m:
            return f"{m.group(1)}-Q{m.group(2)}"
    if cycle == "A" and re.fullmatch(r"\d{4}", t):
        return t
    if cycle == "D" and re.fullmatch(r"\d{8}", t):
        return f"{t[:4]}-{t[4:6]}-{t[6:8]}"
    return None


def ratio(m, lag):
    """{시점: 수준} 을 lag 구간 전 대비 등락률(%)로. 시점 순서로 센다."""
    ks = sorted(m)
    out = {}
    for i, k in enumerate(ks):
        if i >= lag and m[ks[i - lag]]:
            out[k] = round(100 * (m[k] / m[ks[i - lag]] - 1), 1)
    return out


def roll(m, n, nd=2):
    """{시점: 값} 을 가운데 맞춘 n구간 평균으로. 창이 모자라는 양끝은 버린다."""
    ks = sorted(m)
    h = n // 2
    out = {}
    for i in range(h, len(ks) - h):
        out[ks[i]] = round(sum(m[ks[j]] for j in range(i - h, i + h + 1)) / n, nd)
    return out


def label_ok(lab, cycle):
    pat = {"M": r"\d{4}-\d{2}", "Q": r"\d{4}-Q[1-4]",
           "A": r"\d{4}", "D": r"\d{4}-\d{2}-\d{2}"}.get(cycle)
    return bool(pat and re.fullmatch(pat, lab))


def this_period(cycle, now):
    """아직 끝나지 않은 구간. 이건 붙이지 않는다."""
    if cycle == "M":
        return now.strftime("%Y-%m")
    if cycle == "Q":
        return f"{now.year}-Q{(now.month - 1) // 3 + 1}"
    if cycle == "A":
        return str(now.year)
    return now.strftime("%Y-%m-%d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", help="이 차트 id 만")
    a = ap.parse_args()
    if not KEY:
        print("ECOS_API_KEY 가 없습니다."); return 1

    mp = os.path.join(DATA, "ecos_map.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if a.only:
        mapping = {k: v for k, v in mapping.items() if k == a.only}
    if not mapping:
        print("data/ecos_map.json 이 비어 있습니다."); return 0

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
        cyc = spec.get("cycle", "M")
        cut = this_period(cyc, now)
        if not label_ok(labels[-1], cyc):
            skips.append((cid, f"라벨이 {cyc} 주기 꼴이 아닙니다: {labels[-1]}")); continue
        sers = spec.get("series") or []
        nser = len(it["series"])
        slots = spec.get("slots")
        if slots is None:
            want_n = 2 if spec.get("split") == "updown" else len(sers)
            if want_n != nser:
                skips.append((cid, f"등록 계열 {want_n}개 != 차트 계열 {nser}개"))
                continue
            slots = list(range(len(sers)))
        else:
            # 고른 자리만 손대는 차트. split 과는 같이 쓸 수 없다.
            if spec.get("split") or len(slots) != len(sers):
                skips.append((cid, "slots 설정이 series 와 맞지 않습니다")); continue
            if any(not isinstance(x, int) or not 0 <= x < nser for x in slots):
                skips.append((cid, f"slots 가 차트 계열 {nser}개 범위를 벗어납니다")); continue
        at = {j: i for i, j in enumerate(slots)}
        mode = spec.get("mode", "append")
        tol = float(spec.get("tol", 0.6))
        def end_of(c):
            return spec.get("to") or {"Q": f"{now.year+1}Q4", "A": str(now.year + 1),
                                      "D": f"{now.year+1}1231"}.get(c, (now.year + 1) * 100)

        got, err = [], None
        for s in sers:
            try:
                # ECOS 단위와 차트 단위가 다를 때가 많다(천 달러 ↔ 억 달러 등).
                sc = float(s.get("scale", spec.get("scale", 1)))
                rd = s.get("round", spec.get("round"))
                sc_cyc = s.get("cycle", cyc)
                raw = fetch(s.get("stat", spec["stat"]), sc_cyc,
                            s.get("from", spec.get("from", "1900")),
                            str(end_of(sc_cyc)), s["items"])
                # 전년 같은 구간 대비 등락률. ECOS 가 지수만 줄 때 쓴다.
                tr = s.get("transform") or spec.get("transform")
                if tr == "yoy":
                    raw = ratio(raw, 4 if cyc == "Q" else (12 if cyc == "M" else 1))
                elif tr == "qoq":
                    raw = ratio(raw, 1)
                # 가운데 맞춘 이동평균. 장기 추세를 그리는 차트에 쓴다.
                rl = s.get("roll") or spec.get("roll")
                if rl:
                    raw = roll(raw, int(rl), 2 if rd is None else rd)
                # 연간 값을 분기 라벨 한 칸에 얹는다.
                if s.get("asQuarter"):
                    raw = {f"{k}-Q{s['asQuarter']}": v for k, v in raw.items()}
                if sc != 1 or rd is not None:
                    raw = {k: (round(v * sc, rd) if rd is not None else v * sc)
                           for k, v in raw.items()}
                got.append(raw)
            except Exception as e:
                err = f"조회 실패: {e}"; break
        if err:
            skips.append((cid, err)); continue
        # 띄엄띄엄한 계열은 라벨을 고를 때 세지 않는다.
        need = [i for i, s in enumerate(sers) if not s.get("sparse")] or [0]
        if not got[need[0]]:
            skips.append((cid, "내려온 값이 없습니다")); continue

        if mode == "replace":
            keys = [k for k in sorted(got[need[0]]) if k != cut
                    and all(got[i].get(k) is not None for i in need)]
            if not keys:
                skips.append((cid, "쓸 달이 없습니다")); continue
            nl = keys
            old = {lab: i for i, lab in enumerate(labels)}
            ns = [[got[at[j]].get(k) for k in keys] if j in at
                  else [it["series"][j][old[k]] if k in old else None for k in keys]
                  for j in range(nser)]
            # 증가는 파랑, 감소는 빨강으로 갈라 그리는 차트가 있다.
            if spec.get("split") == "updown":
                v = ns[0]
                ns = [[x if (x is not None and x >= 0) else None for x in v],
                      [x if (x is not None and x < 0) else None for x in v]]
            note = f"통째로 교체 ({len(keys)}개 구간, {keys[0]}~{keys[-1]})"
            if nl == labels and ns == it["series"]:
                skips.append((cid, "이미 최신")); continue
        else:
            bad, seen = [], 0
            for si, d in enumerate(got):
                for k, b0 in d.items():
                    if k not in labels:
                        continue
                    a0 = it["series"][slots[si]][labels.index(k)]
                    if a0 is None:
                        continue
                    seen += 1
                    if abs(a0 - b0) > tol:
                        bad.append((k, a0, b0))
            if seen < 6:
                skips.append((cid, f"대조할 달이 부족합니다({seen}곳)")); continue
            if bad:
                skips.append((cid, f"겹치는 구간 {len(bad)}곳 불일치 (예 {bad[0]})")); continue
            addk = [k for k in sorted(got[need[0]]) if k > labels[-1] and k != cut
                    and all(got[i].get(k) is not None for i in need)]
            if not addk:
                skips.append((cid, "이미 최신")); continue
            nl = labels + addk
            ns = [list(it["series"][j]) + ([got[at[j]].get(k) for k in addk]
                                           if j in at else [None] * len(addk))
                  for j in range(nser)]
            note = f"{len(addk)}개월 추가"

        plans.append({"id": cid, "title": it["title"], "labels": nl, "series": ns,
                      "from": labels[-1], "to": nl[-1], "note": note,
                      "names": [s.get("name") for s in sers], "slots": slots,
                      "was": list(it.get("seriesNames") or [None] * nser)})

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
                nm = list(o.get("seriesNames") or p["was"])
                while len(nm) < len(p["series"]):
                    nm.append(None)
                for j, n in zip(p["slots"], p["names"]):
                    nm[j] = n
                if all(nm):
                    o["seriesNames"] = nm
            for k in ("source", "sourceUrl", "unit"):
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
