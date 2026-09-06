#!/usr/bin/env python3
"""
슬라이드 하나를 새 데이터로 갱신한다. 키노트는 건드리지 않는다.

  python3 scripts/set_data.py 964 새데이터.csv --url https://... --source "국가데이터처 인구동향조사"
  python3 scripts/set_data.py c0718 data.xlsx --sheet "아파트 매매평균가격"
  pbpaste | python3 scripts/set_data.py 964 -                       # 붙여넣은 표를 표준입력으로
  python3 scripts/set_data.py "합계출산율"  new.tsv                    # 제목으로 찾기 (후보가 여럿이면 목록만 보여준다)

기본은 미리보기다. 실제 반영은 --apply.

세 가지 방식
  append (기본)  겹치는 구간을 전부 대조해서 하나라도 어긋나면 건드리지 않는다. 뒤에만 이어붙인다.
  --revise       겹치는 구간의 값이 달라진 것(원자료 수정치)을 새 값으로 덮어쓴다. 뭐가 바뀌는지 한 점씩 보여준다.
  --replace      라벨·계열을 통째로 갈아끼운다. 비시계열(지역별·연령별)이나 계열 구성이 바뀔 때.

결과는 data/overrides.json (사이트가 읽는 것)과 data/changelog.json (키노트에 옮길 목록)에 적힌다.
차트 id(=임베드 주소)는 그대로다.
"""
import os, sys, json, re, datetime, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import generate_site as g       # noqa: E402
import tabledata as td          # noqa: E402

TOL = 0.005                     # 겹치는 구간 허용 오차 0.5%


def _norm(s):
    return re.sub(r"[\s·,()（）]", "", str(s or "")).lower()


def find_item(items, key):
    """'964' 'slide-964' 'c0718' 또는 제목 일부로 차트를 찾는다."""
    k = str(key).strip()
    if re.fullmatch(r"\d+", k):
        k = "slide-" + k
    if re.fullmatch(r"(slide|api)-\d+", k):
        hit = [it for it in items if it.get("slide") == k]
        return hit, "slide"
    if re.fullmatch(r"c\d{4}", k):
        hit = [it for it in items if it.get("id") == k]
        return hit, "id"
    nk = _norm(k)
    hit = [it for it in items if nk and nk in _norm(it["title"])]
    return hit, "title"


def map_series(item, new, force_order=False):
    """새 표의 계열을 기존 계열에 붙인다. 이름으로 맞추고, 안 되면 순서로."""
    old_names = item.get("seriesNames") or []
    cur = [n or f"계열{i+1}" for i, n in enumerate(old_names)]
    if len(cur) < len(item["series"]):
        cur += [f"계열{i+1}" for i in range(len(cur), len(item["series"]))]
    new_names = new["seriesNames"]
    by_name = {}
    for j, n in enumerate(new_names):
        for i, c in enumerate(cur):
            if _norm(n) == _norm(c) and i not in by_name.values():
                by_name[j] = i
                break
    if len(by_name) == len(new_names) and not force_order:
        return by_name, "이름"
    if len(new_names) == len(cur):
        return {j: j for j in range(len(cur))}, "순서"
    if len(by_name) == len(cur) and len(new_names) > len(cur):
        return by_name, "이름(여분 계열 무시)"
    return None, None


SCALES = [1, 0.1, 0.01, 0.001, 0.0001, 1e-5, 1e-6, 10, 100, 1000, 10000, 1e5, 1e6]


def _scaled(new, sc):
    if sc == 1:
        return new
    return {**new, "series": [[None if v is None else v * sc for v in s] for s in new["series"]]}


def align_auto(item, new, mapping, fixed=False):
    """배수를 모르면 10의 거듭제곱 범위에서 겹치는 구간이 맞아떨어지는 배수를 찾는다."""
    for sc in ([1] if fixed else SCALES):
        cand = _scaled(new, sc)
        kind, pairs, tail, before = align(item, cand, mapping)
        if kind is None:
            continue
        if kind == "값":
            return sc, cand, kind, pairs, tail, before
        # 시점·라벨로 맞춘 경우: 겹치는 값의 비율이 1에 가까운지 본다
        rr = []
        for j, i in mapping.items():
            for oi, nj in pairs:
                c, x = item["series"][i][oi], cand["series"][j][nj]
                if c not in (None, 0) and x not in (None, 0):
                    rr.append(c / x)
        if not rr:
            return sc, cand, kind, pairs, tail, before
        rr.sort()
        med = rr[len(rr) // 2]
        if abs(med - 1) <= 0.05:
            return sc, cand, kind, pairs, tail, before
        if sc == 1:
            first = (kind, pairs, tail, before, med)
    # 어느 배수로도 안 맞으면 배수 1 결과를 그대로 돌려준다 (어긋남으로 보고된다)
    if 'first' in locals():
        kind, pairs, tail, before, med = first
        return 1, new, kind, pairs, tail, before
    return None, new, None, [], [], 0


def align(item, new, mapping):
    """겹치는 구간을 찾는다. 시점 열쇠로 맞추고, 안 되면 값으로 맞춘다.
    돌려주는 것: kind, pairs[(old_idx, new_idx)], new_tail[new_idx...] (차트 뒤에 붙을 것), before(차트보다 앞선 새 시점 수)"""
    ok = [td.period_key(l) for l in item["labels"]]
    nk = [td.period_key(l) for l in new["labels"]]
    if all(ok) and all(nk) and len(set(ok)) == len(ok) and len(set(nk)) == len(nk):
        pos = {k: i for i, k in enumerate(ok)}
        pairs = [(pos[k], j) for j, k in enumerate(nk) if k in pos]
        last = ok[-1]
        tail = [j for j, k in enumerate(nk) if k > last and k not in pos]
        before = sum(1 for k in nk if k < ok[0] and k not in pos)
        return "시점", pairs, tail, before
    # 비시계열: 라벨 글자가 그대로 맞으면 그걸로
    if not all(ok) or not all(nk):
        pos = {_norm(l): i for i, l in enumerate(item["labels"])}
        pairs = [(pos[_norm(l)], j) for j, l in enumerate(new["labels"]) if _norm(l) in pos]
        if pairs and len(pairs) >= min(len(pos), 3):
            tail = [j for j, l in enumerate(new["labels"]) if _norm(l) not in pos]
            return "라벨", pairs, tail, 0
    # 값으로 맞춘다 (연도만 반복해 찍힌 월간 차트 등). 차트의 마지막 값을 새 표에서 찾아 앞으로 대조한다.
    j0 = next(iter(mapping))
    i0 = mapping[j0]
    cv, nv = item["series"][i0], new["series"][j0]
    anchor = next((i for i in range(len(cv) - 1, -1, -1) if cv[i] is not None), None)
    if anchor is None:
        return None, [], [], 0
    av = cv[anchor]
    for off in range(len(nv) - 1, -1, -1):              # 뒤에서부터: 마지막 값은 보통 표 끝쪽에 있다
        x = nv[off]
        if x is None or abs(av - x) / max(abs(x), 1e-9) > TOL:
            continue
        d = off - anchor                                 # new_idx = old_idx + d
        hits = tot = 0
        for i, c in enumerate(cv):
            j = i + d
            if c is None or j < 0 or j >= len(nv) or nv[j] is None:
                continue
            tot += 1
            hits += abs(c - nv[j]) / max(abs(nv[j]), 1e-9) <= TOL
        if (tot >= 3 and hits / tot >= 0.9) or (tot == 2 and hits == 2):
            pairs = [(i, i + d) for i in range(len(cv)) if 0 <= i + d < len(nv)]
            tail = list(range(len(cv) + d, len(nv))) if len(cv) + d < len(nv) else []
            before = max(0, d)                          # 차트 시작보다 앞선 새 시점 수
            return "값", pairs, tail, before
    return None, [], [], 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="슬라이드 번호 · slide-964 · c0718 · 제목 일부")
    ap.add_argument("data", nargs="?", help="CSV/TSV/XLSX/텍스트 파일. '-' 는 표준입력")
    ap.add_argument("--sheet", help="엑셀 시트 이름")
    ap.add_argument("--transpose", action="store_true", help="표 방향을 강제로 뒤집는다")
    ap.add_argument("--by-order", action="store_true", help="계열을 이름 대신 순서로 맞춘다")
    ap.add_argument("--scale", type=float, help="새 표 값에 곱할 배수 (예: 만원→억 원은 0.0001). 없으면 10의 거듭제곱 범위에서 스스로 찾는다")
    ap.add_argument("--revise", action="store_true", help="겹치는 구간의 달라진 값을 덮어쓴다")
    ap.add_argument("--replace", action="store_true", help="라벨·계열을 통째로 교체한다")
    ap.add_argument("--url", help="데이터 출처 URL (기록해 두면 다음 갱신·자동 갱신 후보에 쓴다)")
    ap.add_argument("--source", help="출처 표기 (예: '국가데이터처 인구동향조사')")
    ap.add_argument("--unit", help="단위 (예: '억 원', '%%')")
    ap.add_argument("--title", help="제목을 바꾼다 (주의: id=임베드 주소가 바뀐다)")
    ap.add_argument("--note", help="변경 메모 (changelog 에 남는다)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    hits, how = find_item(items, a.target)
    if not hits:
        print(f"'{a.target}' 에 해당하는 차트가 없습니다.")
        return 1
    if len(hits) > 1:
        print(f"'{a.target}' 후보가 {len(hits)}개입니다. 슬라이드 번호로 다시 지정하세요:")
        for it in hits[:30]:
            print(f"  {it['slide']:12s} {it['id']}  [{it['category']}] {it['title']}  ({it['labels'][0]}~{it['labels'][-1]}, {len(it['series'])}계열)")
        return 1
    it = hits[0]
    print(f"대상: {it['slide']} {it['id']} [{it['category']}] {it['title']}")
    print(f"  현재: {it['labels'][0]} ~ {it['labels'][-1]}  {len(it['labels'])}점 × {len(it['series'])}계열  "
          f"{it.get('seriesNames')}\n  출처: {it.get('source') or '(없음)'}  {it.get('sourceUrl') or ''}")

    if not a.data:
        # 메타데이터만 고치는 경우
        if not any([a.url, a.source, a.unit, a.title]):
            print("데이터 파일이 없습니다. (출처·URL만 고치려면 --url/--source/--unit 를 주세요)")
            return 1
        new = None
    else:
        text = sys.stdin.read() if a.data == "-" else None
        try:
            new = td.load(path=None if text is not None else a.data, text=text,
                          sheet=a.sheet, transpose=True if a.transpose else None)
        except Exception as e:
            print(f"표를 읽지 못했습니다: {e}")
            return 1
        print(f"  새 표: {new['labels'][0]} ~ {new['labels'][-1]}  {len(new['labels'])}점 × {len(new['series'])}계열  "
              f"{new['seriesNames']}" + ("  (뒤집어 읽음)" if new["transposed"] else ""))
        if a.scale:
            new["series"] = [[None if v is None else v * a.scale for v in s] for s in new["series"]]
            print(f"  배수 {a.scale} 적용")

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    o = dict(ov.get(it["slide"], {}))
    today = datetime.date.today().isoformat()
    change = {"date": today, "slide": it["slide"], "id": it["id"], "title": it["title"],
              "category": it["category"], "keynoteSynced": False}

    if new is not None:
        labels = list(map(str, it["labels"]))
        series = [list(s) for s in it["series"]]
        names = list(it.get("seriesNames") or [None] * len(series))
        if a.replace:
            labels, series, names = new["labels"], new["series"], new["seriesNames"]
            change.update(mode="replace", **{"from": f"{it['labels'][0]}~{it['labels'][-1]}",
                                              "to": f"{labels[0]}~{labels[-1]}", "n": len(labels)})
            print(f"  → 통째로 교체: {labels[0]} ~ {labels[-1]}  {len(labels)}점 × {len(series)}계열")
        else:
            mapping, mhow = map_series(it, new, a.by_order)
            if mapping is None:
                print(f"  계열을 맞추지 못했습니다. 기존 {names} ↔ 새 {new['seriesNames']}\n"
                      f"  계열 이름을 맞추거나 --by-order, 또는 --replace 를 쓰세요.")
                return 1
            print(f"  계열 대응({mhow}): " + ", ".join(f"{new['seriesNames'][j]}→{names[i]}" for j, i in mapping.items()))
            missing = [names[i] for i in range(len(series)) if i not in mapping.values()]
            if missing:
                print(f"  ! 새 표에 없는 계열 {missing} 은 새 시점이 빈칸으로 남습니다.")
            sc, new, kind, pairs, tail, before = align_auto(it, new, mapping, fixed=bool(a.scale))
            if sc not in (None, 1):
                print(f"  배수 {sc} 로 맞아떨어짐 (새 표 값 × {sc})")
                change["scale"] = sc
            if kind is None:
                print("  겹치는 구간을 찾지 못했습니다 (시점 라벨도, 값도 안 맞음). --replace 로 통째로 넣거나 표를 확인하세요.")
                return 1
            # 겹치는 구간 대조
            diffs = []
            for j, i in mapping.items():
                for oi, nj in pairs:
                    c, x = series[i][oi], new["series"][j][nj]
                    if c is None or x is None:
                        continue
                    if abs(c - x) / max(abs(x), 1e-9) > TOL:
                        diffs.append((names[i], labels[oi], c, x, i, oi, j, nj))
            print(f"  겹치는 구간({kind} 기준): {len(pairs)}점 대조, 어긋남 {len(diffs)}점" +
                  (f", 차트보다 앞선 새 시점 {before}점은 무시" if before else ""))
            for nm, lb, c, x, *_ in diffs[:20]:
                print(f"     {nm} {lb}: {c} → {x}")
            if len(diffs) > 20:
                print(f"     … 외 {len(diffs)-20}점")
            if diffs and not a.revise:
                print("  → 어긋나는 값이 있어 건드리지 않습니다. 원자료 수정치를 반영하려면 --revise, 통째로 바꾸려면 --replace.")
                return 1
            for nm, lb, c, x, i, oi, j, nj in diffs:
                series[i][oi] = round(x, 6)
            # 겹치는 구간에서 기존이 비어 있던 자리도 채운다
            filled = 0
            for j, i in mapping.items():
                for oi, nj in pairs:
                    if series[i][oi] is None and new["series"][j][nj] is not None:
                        series[i][oi] = round(new["series"][j][nj], 6); filled += 1
            # 뒤에 이어붙인다
            for nj in tail:
                if kind == "시점":
                    labels.append(td.like_label(labels[-1], td.period_key(new["labels"][nj])))
                elif kind == "값":
                    k = td.period_key(new["labels"][nj])
                    labels.append(td.like_label(labels[-1], k) if k else str(new["labels"][nj]))
                else:
                    labels.append(str(new["labels"][nj]))
                for i in range(len(series)):
                    j = next((jj for jj, ii in mapping.items() if ii == i), None)
                    v = new["series"][j][nj] if j is not None else None
                    series[i].append(None if v is None else round(v, 6))
            change.update(mode="revise" if a.revise else "append",
                          **{"from": str(it["labels"][-1]),
                             "to": str(new["labels"][tail[-1]]) if tail else labels[-1], "n": len(tail),
                             "revised": len(diffs), "filled": filled})
            msg = [f"이어붙임 {len(tail)}점 ({str(it['labels'][-1])} → {new['labels'][tail[-1]]})"] if tail else []
            if diffs: msg.append(f"수정 {len(diffs)}점")
            if filled: msg.append(f"빈칸 채움 {filled}점")
            print("  → " + (", ".join(msg) if msg else "바꿀 것 없음"))
            if not tail and not diffs and not filled:
                print("  이미 최신입니다. 바꿀 것이 없습니다.")
                if not any([a.url, a.source, a.unit, a.title]):
                    return 0
        o["labels"], o["series"] = labels, series
        if names != list(it.get("seriesNames") or []):
            o["seriesNames"] = names
        o["updated"] = today

    if a.url:
        o["sourceUrl"] = a.url; change["sourceUrl"] = a.url
    if a.source:
        src = a.source
        if a.unit and "단위" not in src:
            src = f"{src}, 단위: {a.unit}"
        o["source"] = src; change["source"] = src
    elif a.unit:
        o["unit"] = a.unit
        base = re.sub(r",?\s*단위\s*:.*$", "", it.get("source") or "").rstrip(". ")
        o["source"] = f"{base}, 단위: {a.unit}" if base else f"단위: {a.unit}"
    if a.title:
        o["title"] = a.title; change["newTitle"] = a.title
        print(f"  ! 제목 변경 → id 가 바뀝니다 (임베드 주소 갱신 필요): {it['title']} → {a.title}")
    if a.note:
        change["note"] = a.note
    if a.url and "kosis.kr" in a.url and "tblId=" in a.url:
        tbl = re.search(r"tblId=([A-Z0-9_]+)", a.url).group(1)
        change["kosisTbl"] = tbl
        print(f"  · KOSIS 표 {tbl} — 자동 갱신 후보. 등록: python3 scripts/register_auto.py {it['slide']} --tbl {tbl}")

    if not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)")
        return 0
    ov[it["slide"]] = o
    json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    clp = os.path.join(DATA, "changelog.json")
    cl = json.load(open(clp, encoding="utf-8")) if os.path.exists(clp) else []
    cl.append(change)
    json.dump(cl, open(clp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n→ data/overrides.json · data/changelog.json 반영. 다음: python3 scripts/build.py  (또는 ./update.sh)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
