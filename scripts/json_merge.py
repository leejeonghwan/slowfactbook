#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""깃이 data/*.json 을 차트 단위로 합치게 하는 병합기.

왜 필요한가.
  overrides.json 에 1,950장이, manual.json 에 수백 장이 한 파일에 들어
  있다. 야간 작업(깃허브 액션)과 사람이 같은 날 다른 차트를 고쳐도 깃은
  글자 단위로만 보기 때문에 덩어리가 닿으면 충돌로 올린다. 같은 차트를
  양쪽에서 고친 경우도 사람이 손으로 풀어야 했다.

어떻게 푸는가.
  파일을 차트별로 쪼개서 본다. 한쪽에서만 바뀐 차트는 그대로 가져온다.
  양쪽에서 바뀐 차트는 updated 가 더 최근인 쪽을 쓴다. 어댑터는 출처에서
  다시 만들어 내므로 나중 것이 더 많은 시점을 담고 있다.
  updated 가 없거나 같은데 내용이 다르면 손대지 않고 충돌로 남긴다.
  짐작해서 고르지 않는다.

거는 법 (한 번만)
  git config merge.jsonchart.name "차트 JSON 병합"
  git config merge.jsonchart.driver "python3 scripts/json_merge.py %O %A %B %P"

  .gitattributes 에 어떤 파일에 쓸지 적어 둔다.

되돌리는 법
  git config --unset merge.jsonchart.driver
  그러면 깃이 평소처럼 글자 단위로 합치고 충돌을 올린다.
"""
import json
import os
import sys


def load(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:                                # noqa: BLE001
        return None


def dump(p, obj):
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def newer(a, b):
    """updated 가 더 최근인 쪽. 못 고르면 None."""
    ua = (a or {}).get("updated") if isinstance(a, dict) else None
    ub = (b or {}).get("updated") if isinstance(b, dict) else None
    if ua and ub and ua != ub:
        return a if ua > ub else b
    return None


def merge_map(base, ours, theirs, clash):
    base = base if isinstance(base, dict) else {}
    out = {}
    for k in list(ours) + [k for k in theirs if k not in ours]:
        o, t, b = ours.get(k), theirs.get(k), base.get(k)
        if o == t:
            out[k] = o if k in ours else t
        elif k not in theirs:
            out[k] = o
        elif k not in ours:
            out[k] = t
        elif o == b:
            out[k] = t
        elif t == b:
            out[k] = o
        else:
            pick = newer(o, t)
            if pick is None:
                clash.append(k)
                out[k] = o
            else:
                out[k] = pick
    return out


def keyof(it, i):
    if isinstance(it, dict):
        return it.get("slide") or it.get("id") or f"#{i}"
    return f"#{i}"


def merge_items(base, ours, theirs, clash):
    """{"items": [...]} 꼴. slide 로 묶어 합치고 차례를 지킨다."""
    def idx(doc):
        xs = (doc or {}).get("items") or []
        return {keyof(x, i): x for i, x in enumerate(xs)}
    bo, oo, to = idx(base), idx(ours), idx(theirs)
    merged = merge_map(bo, oo, to, clash)
    order = [keyof(x, i) for i, x in enumerate((ours or {}).get("items")
                                               or [])]
    order += [k for k in to if k not in merged or k not in order]
    seen, items = set(), []
    for k in order:
        if k in merged and k not in seen:
            seen.add(k)
            items.append(merged[k])
    for k in merged:
        if k not in seen:
            seen.add(k)
            items.append(merged[k])
    out = dict(ours or {})
    out["items"] = items
    return out


def merge_log(base, ours, theirs):
    """덧붙이기만 하는 목록. 양쪽에서 새로 붙은 것을 모두 남긴다."""
    def sig(x):
        return json.dumps(x, ensure_ascii=False, sort_keys=True)
    bs = {sig(x) for x in (base or [])}
    out, seen = list(base or []), set(bs)
    for src in (ours or [], theirs or []):
        for x in src:
            s = sig(x)
            if s not in seen:
                seen.add(s)
                out.append(x)
    return out


def main(argv):
    if len(argv) < 4:
        return 1
    anc, cur, oth = argv[1], argv[2], argv[3]
    name = argv[4] if len(argv) > 4 else cur
    base, ours, theirs = load(anc), load(cur), load(oth)
    if ours is None or theirs is None:
        return 1                                     # 깃에게 맡긴다
    clash = []
    if isinstance(ours, list) and isinstance(theirs, list):
        out = merge_log(base, ours, theirs)
    elif isinstance(ours, dict) and "items" in ours:
        out = merge_items(base, ours, theirs, clash)
    elif isinstance(ours, dict):
        out = merge_map(base, ours, theirs, clash)
    else:
        return 1
    if clash:
        sys.stderr.write(
            f"{name}: 양쪽에서 바뀌었는데 어느 쪽이 나중인지 알 수 없는 "
            f"것 {len(clash)}개 — {', '.join(clash[:6])}\n")
        return 1
    dump(cur, out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
