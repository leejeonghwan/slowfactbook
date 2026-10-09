#!/usr/bin/env python3
"""
열쇠를 슬라이드 번호에서 차트 id(cNNNN)로 갈아끼운다. 한 번만 돌린다.

슬라이드 번호는 덱을 다시 내보낼 때마다 밀린다. 그런데 overrides.json(갱신·교정분)과
api_map_auto.json(자동 갱신 등록부)이 모두 그 번호를 열쇠로 쓰고 있었다. 덱이 바뀔 때마다
대응표를 만들어 옮기는 수고가 들고, 한 번 빠뜨리면 엉뚱한 차트에 값이 들어간다.

차트 id 는 한 번 발급되면 바뀌지 않는다(임베드 주소가 그것이다). 그러니 id 를 열쇠로 쓴다.
  · data/*.json 의 각 차트 항목에 "id" 를 박아 넣는다 — 차트가 자기 신분증을 들고 다닌다
  · overrides.json · api_map_auto.json · api_map.json 의 열쇠를 id 로 바꾼다

  python3 scripts/migrate_ids.py            미리보기
  python3 scripts/migrate_ids.py --apply
"""
import os, sys, json, glob, shutil, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SEP = "\x1f"
SKIP = {"overrides.json", "ids.json", "api_map_auto.json", "api_map.json",
        "kb_charts.json", "api_charts.json", "changelog.json", "versions.json",
        "registry.tsv"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    ids = json.load(open(os.path.join(DATA, "ids.json"), encoding="utf-8"))
    byst = {}
    for k, v in ids.items():
        p = k.split(SEP)
        if len(p) >= 3 and p[0] == "S":
            byst.setdefault((p[1], p[2]), v)

    stamped = {}          # slide -> [(title, id)]
    files = {}
    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        if os.path.basename(f).startswith("_") or os.path.basename(f) in SKIP:
            continue
        doc = json.load(open(f, encoding="utf-8"))
        if not (isinstance(doc, dict) and "items" in doc):
            continue
        n = 0
        for it in doc["items"]:
            if not it.get("vizType"):
                continue
            t = (it.get("title") or "").strip().rstrip(".")
            cid = byst.get((it.get("slide"), t))
            if cid:
                it["id"] = cid
                stamped.setdefault(it.get("slide"), []).append((t, cid))
                n += 1
        files[f] = (doc, n)
        print(f"  {os.path.basename(f):<22} 차트에 id 박음 {n}")

    # 슬라이드 → id (슬라이드에 차트가 하나일 때만 단순 치환이 안전하다)
    s2i, multi = {}, []
    for sl, lst in stamped.items():
        if len(lst) == 1:
            s2i[sl] = lst[0][1]
        else:
            multi.append((sl, lst))

    def rekey(name):
        p = os.path.join(DATA, name)
        d = json.load(open(p, encoding="utf-8"))
        out, left = {}, {}
        for k, v in d.items():
            if k in s2i:
                out[s2i[k]] = v
            elif k.startswith("c") and k[1:].isdigit():
                out[k] = v                       # 이미 id
            else:
                left[k] = v
        print(f"  {name:<22} 옮김 {len(out)} · 남음 {len(left)}")
        return p, out, left

    rk = [rekey("overrides.json"), rekey("api_map_auto.json"), rekey("api_map.json")]

    print(f"\n슬라이드 하나에 차트가 둘 이상인 곳 {len(multi)}건 — 열쇠를 단순 치환하지 않는다")
    for sl, lst in multi[:6]:
        print("   ", sl, [c for _, c in lst])

    if not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)")
        return 0

    bak = os.path.join(ROOT, ".cache", "migrate_ids_backup")
    os.makedirs(bak, exist_ok=True)
    for f, (doc, n) in files.items():
        shutil.copy(f, os.path.join(bak, os.path.basename(f)))
        json.dump(doc, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    for p, out, left in rk:
        shutil.copy(p, os.path.join(bak, os.path.basename(p)))
        json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if left:
            lp = p.replace(".json", "_legacy.json")
            json.dump(left, open(lp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"  옮기지 못한 열쇠 {len(left)}개 → {os.path.basename(lp)}")
    print(f"\n→ 반영 완료. 원본은 {os.path.relpath(bak, ROOT)} 에 있습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
