#!/usr/bin/env python3
"""
정부 데이터 API로 차트를 자동 갱신한다.

  data/api_map.json  (차트 ↔ 통계표 매핑)
        │
        ├─ KOSIS 파라미터 API / 한국은행 ECOS API 호출
        │
        ▼
  data/overrides.json  (slide id → {labels, series} 패치)
        │
        ▼
  scripts/build.py → site/  (기존 파이프라인 그대로)

핵심: 키노트 원본은 건드리지 않는다. generate_site.load_items()가 이미 지원하는
overrides.json 훅에 최신 수치를 얹는 방식이라, 차트 id(=임베드 URL)도 그대로 유지된다.

사용:
  KOSIS_API_KEY=... python3 scripts/refresh_api.py            # 갱신 + 리포트
  KOSIS_API_KEY=... python3 scripts/refresh_api.py --dry-run  # 뭐가 바뀔지만 출력
"""
import re, os, sys, json, time, datetime, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
MAP = os.path.join(DATA, "api_map.json")
OVR = os.path.join(DATA, "overrides.json")
REPORT = os.path.join(DATA, "_api_refresh.json")

KOSIS_KEY = os.environ.get("KOSIS_API_KEY", "")
ECOS_KEY = os.environ.get("ECOS_API_KEY", "")


def _get(url, tries=5):
    last = None
    for t in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(2 + t * 2)
    raise RuntimeError(f"fetch failed: {last}")


def fetch_kosis(spec):
    """spec: {orgId, tblId, itmId, objL1..objL4, prdSe, startPrdDe, endPrdDe}"""
    q = {
        "method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
        "orgId": spec.get("orgId", "101"), "tblId": spec["tblId"],
        "itmId": spec.get("itmId", "T1+"), "prdSe": spec.get("prdSe", "Y"),
        "startPrdDe": str(spec["startPrdDe"]), "endPrdDe": str(spec["endPrdDe"]),
    }
    for i in range(1, 5):
        k = f"objL{i}"
        if spec.get(k):
            q[k] = spec[k]
    url = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
           + "&".join(f"{k}={urllib.parse.quote(str(v), safe='+')}" for k, v in q.items()))
    rows = _get(url)
    if isinstance(rows, dict):
        raise RuntimeError(f"KOSIS error: {rows}")
    return rows


def fetch_ecos(spec):
    """spec: {statCode, itemCode, cycle, start, end} — scripts/ecos.py 어댑터를 쓴다."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import ecos
    ser = ecos.search(spec["statCode"], spec.get("cycle", "A"),
                      spec["start"], spec["end"], spec.get("itemCode"))
    return [{"TIME": p, "DATA_VALUE": v} for p, v in ser]


def to_series(rows, spec):
    """API 응답을 (labels, series, 계열이름) 으로 정규화.

    objL1 에 분류 코드를 여럿 적으면(예 "20+91+") 한 시점에 행이 여럿 온다.
    예전에는 시점이 겹친다고 뒤엣것을 버려서, 두 분류 가운데 그때그때
    작은 값만 남은 잡종 계열이 만들어졌다. 분류마다 계열을 따로 만든다.
    """
    prov = spec.get("provider", "kosis")
    scale = float(spec.get("scale", 1))
    nd = spec.get("round", 3)

    # 어느 칸이 분류인지 찾는다. objL1 → C1, objL2 → C2 …
    grp = None
    if prov == "kosis":
        for i in range(1, 5):
            v = str(spec.get(f"objL{i}") or "")
            if len([x for x in v.replace("+", " ").split() if x]) > 1:
                grp = f"C{i}"
                break
        # 분류가 하나뿐인데 항목(itmId)을 여럿 부른 표도 있다. 그때는 항목으로 가른다.
        # 안 그러면 한 시점에 행이 여럿 와서 뒤엣것이 버려진다.
        nitm = len([x for x in str(spec.get("itmId") or "").replace("+", " ").split() if x])
        if grp is None and nitm > 1:
            grp = "ITM_ID"
        # 항목과 분류를 동시에 여럿 부르는 차트가 있다(성별 × 정규직·비정규직).
        # "cross": true 를 적으면 (항목, 분류) 짝마다 계열을 만든다. 항목이 바깥이다.
        elif grp and nitm > 1 and spec.get("cross"):
            grp = ("ITM_ID", grp)

    def norm(p, v):
        return (p, round(float(v) * scale, nd))

    buckets = {}        # 분류코드 -> {시점: 값}
    names = {}
    order = []
    # 한 해에 조사가 두 번 있는 표가 있다(근로형태별 부가조사는 3월·8월).
    # "keepMonth": "08" 을 적으면 그 달 조사만 쓴다.
    keep = str(spec.get("keepMonth") or "")
    for r in rows:
        if prov == "kosis":
            p, v = r.get("PRD_DE"), r.get("DT")
        else:
            p, v = r.get("TIME"), r.get("DATA_VALUE")
        if v in (None, ""):
            continue
        if keep and str(p)[4:6] != keep:
            continue
        if isinstance(grp, tuple):
            key = tuple(r.get(x) or "" for x in grp)
        else:
            key = (r.get(grp) or "") if grp else ""
        if key not in buckets:
            buckets[key] = {}
            if isinstance(grp, tuple):
                nm = [(r.get("ITM_NM") if x == "ITM_ID" else r.get(x + "_NM")) or ""
                      for x in grp]
                names[key] = " ".join(y for y in nm if y)
            else:
                nmk = "ITM_NM" if grp == "ITM_ID" else (grp + "_NM" if grp else None)
                names[key] = (r.get(nmk) if nmk else "") or ""
            order.append(key)
        pp, vv = norm(p, v)
        buckets[key].setdefault(pp, vv)

    # 등록부에 적힌 순서대로 세운다. 색과 범례가 적을 때마다 뒤바뀌지 않게.
    def codes(src):
        return [x for x in str(src).replace("+", " ").split() if x]

    # 두 항목의 비(比)를 내는 차트가 있다(연령대별 비정규직 비율 = 비정규직/임금근로자).
    # "ratio": {"num": "T03", "den": "T01"} 을 적으면 분류마다 한 계열로 줄인다.
    rt = spec.get("ratio")
    if rt and isinstance(grp, tuple):
        num, den = rt["num"], rt["den"]
        mul = float(rt.get("mul", 100))
        rnd = int(rt.get("round", 1))
        nb, nn, no = {}, {}, []
        for cls in codes(spec.get("objL" + grp[1][1:])):
            a_, b_ = buckets.get((num, cls)), buckets.get((den, cls))
            if not a_ or not b_:
                continue
            nb[cls] = {k: round(a_[k] / b_[k] * mul, rnd)
                       for k in a_ if b_.get(k)}
            nn[cls] = names.get((num, cls), "").replace(
                names.get((num, cls), "").split(" ")[0], "", 1).strip() or cls
            no.append(cls)
        buckets, names, order, grp = nb, nn, no, grp[1]

    if isinstance(grp, tuple):
        wi = codes(spec.get("itmId"))
        wo = codes(spec.get("objL" + grp[1][1:]))
        want = [(a, b) for a in wi for b in wo]
        order = [k for k in want if k in buckets] + [k for k in order if k not in want]
    elif grp:
        src = spec.get("itmId") if grp == "ITM_ID" else spec.get("objL" + grp[1:])
        want = codes(src)
        order = [k for k in want if k in buckets] + [k for k in order if k not in want]

    ps = spec.get("prdSe", "Y")
    # 수준을 전년 같은 구간 대비 등락률(%)로. 등록부의 "transform": "yoy".
    if spec.get("transform") == "yoy":
        lag = {"M": 12, "Q": 4}.get(ps, 1)
        for key, bb in list(buckets.items()):
            ks = sorted(bb)
            buckets[key] = {ks[i]: round(100 * (bb[ks[i]] / bb[ks[i - lag]] - 1), 1)
                            for i in range(lag, len(ks)) if bb[ks[i - lag]]}
    keys = sorted({p for b in buckets.values() for p in b})
    # 원본 표에 아예 빠진 해가 있는 통계가 있다(국민연금 추납보험료는 2020년과 2021년이 없다).
    # 그냥 두면 빠진 해가 눈에 안 보이게 접혀서 2019년 다음 칸이 2022년이 된다.
    # "fillYears": true 를 적으면 처음부터 끝까지 모든 해를 깔고 없는 해는 빈 값으로 둔다.
    if ps == "Y" and spec.get("fillYears") and keys and all(len(str(k)) == 4 for k in keys):
        ys = [int(k) for k in keys]
        keys = [str(y) for y in range(min(ys), max(ys) + 1)]
    if ps == "Y":
        labels = [p[:4] for p in keys]
    elif ps == "M":
        # 199001 → 1990-01. 차트 가로축이 월을 알아보려면 이 꼴이어야 한다.
        labels = [(f"{p[:4]}-{p[4:6]}" if len(p) >= 6 and p[4:6].isdigit() else p)
                  for p in keys]
    else:
        labels = list(keys)
    series = [[buckets[k].get(p) for p in keys] for k in order]
    snames = [re.sub(r"\s+", " ", names[k]).strip() for k in order] if grp else []

    # 장래추계처럼 실적과 전망이 한 계열에 이어진 표가 있다. 가른 해를 적으면
    # 분류마다 '실적'과 '전망' 두 계열로 쪼갠다. 가른 해는 양쪽에 모두 넣어
    # 선이 끊기지 않게 한다. 등록부의 "splitAt": "2022".
    cutp = spec.get("splitAt")
    if cutp:
        cutp = str(cutp)
        tags = spec.get("splitNames") or ["실적", "전망"]
        ns, nn = [], []
        for si, vals in enumerate(series):
            base = snames[si] if si < len(snames) else ""
            ns.append([v if keys[i] <= cutp else None for i, v in enumerate(vals)])
            ns.append([v if keys[i] >= cutp else None for i, v in enumerate(vals)])
            nn.append(f"{base} {tags[0]}".strip())
            nn.append(f"{base} {tags[1]}".strip())
        series, snames = ns, nn
    return labels, series, snames


def main():
    dry = "--dry-run" in sys.argv
    if not os.path.exists(MAP):
        print(f"매핑 파일이 없습니다: {MAP}")
        return 1
    mapping = json.load(open(MAP, encoding="utf-8"))
    overrides = json.load(open(OVR, encoding="utf-8")) if os.path.exists(OVR) else {}
    # 현재 차트 상태 (비교용)
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import generate_site as g
    # 등록부(api_map)의 열쇠는 이제 차트 id 다. 옛 슬라이드 열쇠도 받아준다.
    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))
    cur = {it["slide"]: it for it in _items}
    cur.update({it["id"]: it for it in _items if it.get("id")})

    report, changed = [], 0
    for slide, spec in mapping.items():
        if spec.get("disabled"):
            continue
        try:
            rows = fetch_kosis(spec) if spec.get("provider", "kosis") == "kosis" else fetch_ecos(spec)
            labels, series, snames = to_series(rows, spec)
        except Exception as e:
            report.append({"slide": slide, "status": "error", "detail": str(e)[:200]})
            print(f"  ✗ {slide}  {spec.get('label','')}: {e}")
            continue
        old = cur.get(slide)
        old_last = (old["labels"][-1], old["series"][0][-1]) if old and old["labels"] else None
        new_last = (labels[-1], series[0][-1]) if labels else None
        # 마지막 점만 보면 과거 값이 수정된 경우를 놓친다. 라벨·값 전체를 본다.
        diff = not (old
                    and [str(x) for x in old["labels"]] == [str(x) for x in labels]
                    and old["series"] == series)
        report.append({"slide": slide, "label": spec.get("label", ""),
                       "status": "changed" if diff else "same",
                       "old_last": old_last, "new_last": new_last,
                       "n_old": len(old["labels"]) if old else 0, "n_new": len(labels)})
        mark = "●" if diff else "·"
        print(f"  {mark} {slide}  {spec.get('label','')}: {old_last} → {new_last}  (n {len(old['labels']) if old else 0}→{len(labels)})")
        if diff:
            changed += 1
        if not dry:
            key = (old or {}).get("id") or slide     # overrides 의 열쇠는 차트 id 다
            ov = overrides.get(key, overrides.get(slide, {}))
            ov.update({"labels": labels, "series": series,
                       "source": spec.get("source", ov.get("source", "")),
                       "sourceUrl": spec.get("sourceUrl", ov.get("sourceUrl", ""))})
            # 분류를 여럿 부른 차트는 계열 이름도 붙여 준다(등록부의 names 가 우선).
            nm = spec.get("names") or snames
            if len(series) > 1 and len(nm) == len(series) and all(nm):
                ov["seriesNames"] = nm
            # 값이 그대로면 updated 를 다시 찍지 않는다 — '최근 업데이트'가 오염된다.
            if diff:
                ov["updated"] = datetime.datetime.now(
                    datetime.timezone(datetime.timedelta(hours=9))
                ).strftime("%Y-%m-%d %H:%M")
            overrides[key] = ov

    if not dry:
        json.dump(overrides, open(OVR, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(report, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n{'[dry-run] ' if dry else ''}대상 {len(mapping)}건 · 값이 바뀐 차트 {changed}건")
    print("다음: python3 scripts/build.py && git diff data/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
