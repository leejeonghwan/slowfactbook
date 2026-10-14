#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""빈 출처를 메운다. 세 갈래로 쓴다.

  --restore   원본 덱(data/full.json)에 남아 있는 출처 문자열을 되살린다.
              단위를 따로 떼어 내던 과정에서 '단위: %, 고용노동부.' 같은 문자열이
              통째로 비워진 차트가 있다. 단위 토막을 뺀 나머지가 남으면 그것을
              출처로 돌려놓는다.
  --rules     data/source_rules.json 의 낱말 규칙을 적용한다.
              [{"cat": "출산", "title": "고용률", "source": "...", "sourceUrl": "..."}]
              cat 과 title 은 둘 다 선택이고, 있는 것만 맞으면 걸린다.
  --todo      아직 빈 차트를 data/_source_todo.tsv 로 뽑는다. 사람이 채운 뒤
              같은 파일을 --from-tsv 로 돌려주면 그대로 반영한다.
  --from-tsv  채워 온 TSV 를 읽어 반영한다.

어느 갈래든 --apply 없이는 미리보기만 한다. 이미 출처가 있는 차트는 건드리지
않는다. 덮어쓰는 일이 없어야 사람이 손으로 적어 둔 것이 살아남는다.
"""
import argparse, csv, datetime, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
TODO = os.path.join(DATA, "_source_todo.tsv")


def unit_stripped(s):
    """'단위: …' 토막을 뺀 나머지. 남는 말이 없으면 빈 문자열."""
    t = re.sub(r"단위\s*:?\s*[^.,]*[.,]?", "", str(s))
    t = re.sub(r"\s+", " ", t).strip(" .,·")
    return t


def load():
    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    cur = {it["id"]: it for it in items if it.get("id")}
    blank = {cid: it for cid, it in cur.items()
             if not str(it.get("source") or "").strip()}
    return cur, blank


def plan_restore(cur, blank):
    fp = os.path.join(DATA, "full.json")
    full = (json.load(open(fp, encoding="utf-8")) or {}).get("items", [])
    byid = {it["id"]: it for it in full if it.get("id")}
    byslide = {str(it.get("slide")): it for it in full}
    out = []
    for cid, it in blank.items():
        f = byid.get(cid) or byslide.get(str(it.get("slide")))
        txt = unit_stripped((f or {}).get("source") or "")
        # 슬라이드에 출처 대신 제목이 한 번 더 적혀 있던 경우가 있다. 제목을 출처
        # 칸에 옮겨 적으면 안 되므로 걸러낸다.
        norm = lambda x: re.sub(r"[\s.,·()]+", "", str(x or ""))
        if txt and norm(txt) and norm(txt) != norm(it.get("title")) \
                and norm(txt) not in norm(it.get("title")):
            out.append((cid, it.get("title"), txt, (f or {}).get("sourceUrl") or ""))
    return out


def plan_rules(cur, blank):
    rp = os.path.join(DATA, "source_rules.json")
    rules = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else []
    out = []
    for cid, it in blank.items():
        for r in rules:
            if r.get("cat") and r["cat"] != (it.get("category") or ""):
                continue
            if r.get("title") and not re.search(r["title"], str(it.get("title") or "")):
                continue
            out.append((cid, it.get("title"), r["source"], r.get("sourceUrl", "")))
            break
    return out


def plan_tsv(cur, blank):
    out = []
    with open(TODO, encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t"):
            if len(row) < 4 or row[0] == "id":
                continue
            cid, src, url = row[0].strip(), row[3].strip(), (row[4].strip() if len(row) > 4 else "")
            if cid in blank and src:
                out.append((cid, blank[cid].get("title"), src, url))
    return out


def write_todo(cur, blank):
    rows = sorted(blank.values(), key=lambda it: (it.get("category") or "", it["id"]))
    with open(TODO, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["id", "category", "title", "source", "sourceUrl", "chart_url"])
        for it in rows:
            w.writerow([it["id"], it.get("category") or "", it.get("title") or "", "", "",
                        "https://slownews.net/factbook/chart.html?id=" + it["id"]])
    print(f"data/_source_todo.tsv 에 {len(rows)}개를 적었습니다.")
    print("source 칸을 채운 뒤 --from-tsv --apply 로 돌려주십시오.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--rules", action="store_true")
    ap.add_argument("--todo", action="store_true")
    ap.add_argument("--from-tsv", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    cur, blank = load()
    print(f"차트 {len(cur)}개 · 출처 빈칸 {len(blank)}개\n")
    if a.todo:
        write_todo(cur, blank); return 0
    if not (a.restore or a.rules or a.from_tsv):
        print("무엇을 할지 골라 주십시오: --restore / --rules / --todo / --from-tsv")
        return 0

    plans = []
    if a.restore:
        plans += plan_restore(cur, blank)
    if a.rules:
        plans += plan_rules(cur, blank)
    if a.from_tsv:
        plans += plan_tsv(cur, blank)
    seen, uniq = set(), []
    for p in plans:
        if p[0] not in seen:
            seen.add(p[0]); uniq.append(p)

    print(f"메울 것 {len(uniq)}개\n")
    for cid, title, src, url in uniq[:60]:
        print(f"  {cid}  {str(title)[:24]:26s} <- {src[:46]}")
    if len(uniq) > 60:
        print(f"  … 그리고 {len(uniq)-60}개 더")

    if a.apply and uniq:
        ovp = os.path.join(DATA, "overrides.json")
        ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
        stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
        for cid, _t, src, url in uniq:
            o = ov.setdefault(cid, {})
            o["id"] = cid
            o["source"] = src
            if url and not o.get("sourceUrl"):
                o["sourceUrl"] = url
            o["revised"] = stamp          # 숫자가 아니라 표기만 고친 것이다
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n-> data/overrides.json 에 {len(uniq)}건 반영.")
    elif uniq:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
