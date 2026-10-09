#!/usr/bin/env python3
"""
새로 내보낸 덱(.pptx 추출 JSON)을 기존 data/full.json 자리에 갈아끼운다.

슬라이드 번호는 덱이 바뀔 때마다 밀린다. 그런데 차트 id(=임베드 주소)와
overrides.json(자동 갱신·수동 교정분)이 모두 슬라이드 번호를 열쇠로 쓴다.
그래서 번호가 아니라 '내용'으로 옛 슬라이드 ↔ 새 슬라이드 대응표를 만들고,
그 표로 ids.json·overrides.json 의 열쇠를 옮긴 뒤에 full.json 을 교체한다.

  python3 scripts/import_deck.py 새덱추출.json              # 리포트만
  python3 scripts/import_deck.py 새덱추출.json --apply      # 실제 반영

매칭 단계 (앞 단계에서 유일하게 정해지면 거기서 확정)
  1) 제목 + 차트종류 + 라벨수 + 계열수 + 값지문
  2) 제목 + 차트종류 + 라벨수 + 계열수
  3) 제목 + 차트종류
  4) 제목
같은 제목이 여럿이면 각 단계에서 '후보 수가 양쪽 다 1' 일 때만 확정하고,
수가 같으면 덱 안의 등장 순서대로 짝짓는다(--pair-by-order, 기본 켜짐).
그래도 안 갈리면 보류하고 리포트에 찍는다 — 사람이 판단할 몫이다.
"""
import os, sys, json, argparse, datetime
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SEP = "\x1f"


def norm_title(t):
    return (t or "").strip().rstrip(".").strip()


def shape(it):
    return (it.get("vizType"), len(it.get("labels") or []), len(it.get("series") or []))


def vsig(it):
    return repr(it.get("series"))


def load(path):
    d = json.load(open(path, encoding="utf-8"))
    return d, [i for i in d.get("items", [])]


def group(items, keyf):
    g = defaultdict(list)
    for i, it in enumerate(items):
        g[keyf(it)].append((i, it))
    return g


def match(old, new, pair_by_order=True, aliases=None):
    """old/new: items 리스트. 반환 (pairs, ambiguous, old_only, new_only)"""
    pairs = {}                      # old index -> new index
    used_new, used_old = set(), set()
    # 손으로 이어준 것(제목이 바뀐 차트)을 먼저 확정한다.
    for os_, ns_ in (aliases or {}).items():
        oi = [i for i, it in enumerate(old) if it.get("slide") == os_]
        nj = [j for j, it in enumerate(new) if it.get("slide") == ns_]
        for i, j in zip(oi, nj):
            pairs[i] = j; used_old.add(i); used_new.add(j)
    levels = [
        lambda it: (norm_title(it["title"]), shape(it), repr(it.get("labels")), vsig(it)),
        lambda it: (norm_title(it["title"]), shape(it), vsig(it)),
        lambda it: (norm_title(it["title"]), shape(it)),
        lambda it: (norm_title(it["title"]), it.get("vizType")),
        lambda it: (norm_title(it["title"]),),
    ]
    for keyf in levels:
        go = group([it for it in old], keyf)
        gn = group([it for it in new], keyf)
        for k, olds in go.items():
            olds = [(i, it) for i, it in olds if i not in used_old]
            news = [(j, it) for j, it in gn.get(k, []) if j not in used_new]
            if not olds or not news:
                continue
            if len(olds) == 1 and len(news) == 1:
                pairs[olds[0][0]] = news[0][0]
                used_old.add(olds[0][0]); used_new.add(news[0][0])
            elif pair_by_order and len(olds) == len(news):
                for (i, _), (j, _) in zip(olds, news):
                    pairs[i] = j
                    used_old.add(i); used_new.add(j)
    # 단계 매칭으로 안 갈린 것은 점수로 고른다. 계열 이름·첫 라벨·첫 값이
    # 그대로인 쪽이 '같은 차트가 자리만 옮긴 것'이다. 1등이 2등보다 확실히
    # 높을 때만 확정하고, 동점이면 덱에서 먼저 나오는 쪽을 쓴다
    # (빌드가 같은 내용 중복을 앞의 것만 남기므로 결과가 일치한다).
    def first_val(it):
        for ser in (it.get("series") or []):
            for v in (ser or []):
                if v is not None:
                    return round(float(v), 2)
        return None

    def score(o, n):
        sc = 0.0
        if (o.get("seriesNames") or []) == (n.get("seriesNames") or []): sc += 4
        ol, nl = o.get("labels") or [], n.get("labels") or []
        if ol and nl and ol[0] == nl[0]: sc += 3
        if first_val(o) is not None and first_val(o) == first_val(n): sc += 3
        if len(o.get("series") or []) == len(n.get("series") or []): sc += 2
        return sc - abs(len(nl) - len(ol)) * 0.01

    leftover_o = defaultdict(list); leftover_n = defaultdict(list)
    for i in range(len(old)):
        if i not in used_old: leftover_o[norm_title(old[i]["title"])].append(i)
    for j in range(len(new)):
        if j not in used_new: leftover_n[norm_title(new[j]["title"])].append(j)
    scored = {}
    for t, ois in leftover_o.items():
        njs = leftover_n.get(t) or []
        if not t or not njs:
            continue
        for i in ois:
            cands = sorted(((score(old[i], new[j]), -j, j) for j in njs if j not in used_new),
                           reverse=True)
            if not cands:
                continue
            if len(cands) == 1 or cands[0][0] > cands[1][0] or \
               repr(new[cands[0][2]].get("series")) == repr(new[cands[1][2]].get("series")):
                j = cands[0][2]
                pairs[i] = j; used_old.add(i); used_new.add(j)
                scored[old[i].get("slide")] = {
                    "title": t, "new": new[j].get("slide"), "score": cands[0][0],
                    "tie": len(cands) > 1 and cands[0][0] == cands[1][0],
                    "others": [new[c[2]].get("slide") for c in cands[1:]]}

    old_only = [i for i in range(len(old)) if i not in used_old]
    new_only = [j for j in range(len(new)) if j not in used_new]
    # 보류: 제목은 양쪽에 있는데 짝을 못 지은 것
    # 차트가 아닌 슬라이드(vizType 없음)와 제목 없는 슬라이드는 id·overrides 와
    # 무관하므로 보류 대상에서 뺀다. 짝이 안 지어져도 잃을 것이 없다.
    def real(it):
        return bool(it.get("vizType")) and bool(norm_title(it.get("title")))
    ot = defaultdict(list); nt = defaultdict(list)
    for i in old_only:
        if real(old[i]): ot[norm_title(old[i]["title"])].append(i)
    for j in new_only:
        if real(new[j]): nt[norm_title(new[j]["title"])].append(j)
    ambiguous = {t: (ot[t], nt[t]) for t in ot if t in nt}
    return pairs, ambiguous, old_only, new_only, scored


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("new_json")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-pair-by-order", action="store_true")
    ap.add_argument("--alias", action="append", default=[],
                    help="제목이 바뀐 차트를 손으로 이어준다: --alias slide-71=slide-80 (여러 번 가능)")
    ap.add_argument("--report", default=os.path.join(DATA, "_deck_import.json"))
    a = ap.parse_args()

    olddoc, old = load(os.path.join(DATA, "full.json"))
    newdoc, new = load(a.new_json)
    aliases = {}
    for spec in a.alias:
        k, _, v = spec.partition("=")
        aliases[k.strip()] = v.strip()
    pairs, amb, old_only, new_only, scored = match(old, new, not a.no_pair_by_order, aliases)
    if aliases:
        print(f"손으로 이어준 것 {len(aliases)}건: " +
              ", ".join(f"{k}→{v}" for k, v in aliases.items()))

    oslide = [it.get("slide") for it in old]
    nslide = [it.get("slide") for it in new]
    slide_map = {oslide[i]: nslide[j] for i, j in pairs.items()}

    ids = json.load(open(os.path.join(DATA, "ids.json"), encoding="utf-8"))
    ov = json.load(open(os.path.join(DATA, "overrides.json"), encoding="utf-8"))

    # 옮겨질 것 / 갈 곳 없는 것 세기
    ov_moved = {k: slide_map[k] for k in ov if k in slide_map}
    ov_lost = [k for k in ov if k not in slide_map and k.startswith("slide-")]
    # ids.json 열쇠는 "S|슬라이드|제목"(겹치면 |2,|3…)이다. 제목이 바뀐 차트는
    # 슬라이드만 바꿔서는 빌드가 만드는 열쇠와 어긋나 id 가 새로 발급된다.
    # 그래서 항목 단위 대응표로 슬라이드와 제목을 함께 갈아끼운다.
    def bkey(it):
        return "S" + SEP + str(it.get("slide")) + SEP + (it["title"].strip().rstrip("."))

    keymap = {}
    for i, j in pairs.items():
        keymap[bkey(old[i])] = bkey(new[j])
    id_new, id_lost = 0, 0
    newids = {}
    for k, v in ids.items():
        parts = k.split(SEP)
        base = SEP.join(parts[:3])
        suffix = parts[3:]
        if base in keymap:
            nk = SEP.join([keymap[base]] + suffix)
            newids[nk] = v
            id_new += 1
        else:
            newids[k] = v
            if len(parts) >= 3 and parts[0] == "S" and parts[1].startswith("slide-"):
                id_lost += 1

    amb_titles = sorted(amb)
    new_titles = sorted({norm_title(new[j]["title"]) for j in new_only
                         if norm_title(new[j]["title"]) not in amb})
    gone_titles = sorted({norm_title(old[i]["title"]) for i in old_only
                          if norm_title(old[i]["title"]) not in amb})

    print(f"기존 {len(old)}항목 / 새 덱 {len(new)}항목")
    print(f"  이어짐      : {len(pairs)}")
    print(f"  새 항목     : {len(new_only)}  (제목 기준 {len(new_titles)}종)")
    print(f"  사라진 항목 : {len(old_only)}  (제목 기준 {len(gone_titles)}종)")
    print(f"  보류(모호)  : 제목 {len(amb_titles)}종")
    print(f"  overrides   : 옮김 {len(ov_moved)} / 갈 곳 없음 {len(ov_lost)}")
    print(f"  ids         : 옮김 {id_new} / 그대로(=차트 사라짐) {id_lost}")

    if scored:
        print(f"\n── 점수로 고른 것 {len(scored)}건 (같은 제목이 새 덱에 여럿) ──")
        for o, v in sorted(scored.items()):
            mark = " [동점—덱 안 중복, 빌드가 앞의 것만 남긴다]" if v["tie"] else ""
            print(f"  {v['title'][:46]}")
            print(f"    {o} → {v['new']}  (점수 {v['score']:.2f}, 다른 후보 {', '.join(v['others'])}){mark}")

    if amb_titles:
        print("\n── 보류: 같은 제목이 여럿이라 짝을 못 지은 것 ──")
        for t in amb_titles:
            oi, nj = amb[t]
            print(f"  {t or '(제목 없음)'}")
            for i in oi:
                print(f"    기존 {old[i].get('slide'):>10}  {shape(old[i])}")
            for j in nj:
                print(f"    신규 {new[j].get('slide'):>10}  {shape(new[j])}")

    if new_titles:
        print(f"\n── 새 차트 {len(new_titles)}종 ──")
        for t in new_titles:
            print("  +", t[:70])
    if gone_titles:
        print(f"\n── 새 덱에 없는 차트 {len(gone_titles)}종 (id 는 남는다) ──")
        for t in gone_titles:
            print("  -", t[:70])

    rep = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
           "source": os.path.basename(a.new_json),
           "paired": len(pairs), "slide_map": slide_map,
           "ambiguous": {t: {"old": [old[i].get("slide") for i in amb[t][0]],
                             "new": [new[j].get("slide") for j in amb[t][1]]} for t in amb_titles},
           "scored": scored, "new_titles": new_titles, "gone_titles": gone_titles,
           "overrides_moved": len(ov_moved), "overrides_lost": ov_lost}
    json.dump(rep, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n리포트: {os.path.relpath(a.report, ROOT)}")

    if not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)")
        return 0

    if amb_titles:
        print("\n보류 항목이 있어 반영하지 않았습니다. 먼저 제목을 구분해 주세요.")
        return 1

    newov = {}
    for k, v in ov.items():
        newov[slide_map.get(k, k)] = v
    # 자동 갱신 등록부도 슬라이드 번호를 열쇠로 쓴다. 같이 옮기지 않으면
    # 봇이 엉뚱한 차트에 KOSIS 값을 덮어쓴다.
    for fn in ("api_map_auto.json", "api_map.json"):
        fp = os.path.join(DATA, fn)
        if not os.path.exists(fp):
            continue
        m = json.load(open(fp, encoding="utf-8"))
        moved = sum(1 for k in m if k in slide_map)
        json.dump({slide_map.get(k, k): v for k, v in m.items()},
                  open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  {fn}: {moved}/{len(m)} 옮김")
    newdoc["category"] = olddoc.get("category", "full")
    for it in new:
        pass
    json.dump(newids, open(os.path.join(DATA, "ids.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(newov, open(os.path.join(DATA, "overrides.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(newdoc, open(os.path.join(DATA, "full.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\n→ ids.json · overrides.json · full.json 갱신. 다음: python3 scripts/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
