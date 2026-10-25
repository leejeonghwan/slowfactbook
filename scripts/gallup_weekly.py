#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국갤럽 데일리 오피니언 주간 호 → 대통령 직무 수행 평가 주간 시계열(c2040).

  python3 scripts/gallup_weekly.py            # 미리보기
  python3 scripts/gallup_weekly.py --apply

gallup_update.py 는 달마다 한 번 나오는 '월별 통합표'를 읽는다. 이 스크립트는
주마다 나오는 호 자체를 읽는다. 둘은 보는 표가 달라서 따로 둔다.

각 호 PDF 의 '대통령 직무 수행 평가 표준오차' 표에 전체 응답자의 긍정률과
부정률이 한 줄씩 적혀 있다. 본문 그래프 대신 이 표를 읽는 이유는, 표가
숫자만 세로로 늘어서 있어 pdftotext -layout 으로 자리가 흔들리지 않아서다.

등록부는 data/gallup_weekly.json. lastNo 는 차트에 이미 담긴 마지막 호다.
새 호를 붙이기 전에 lastNo 호를 다시 받아 차트의 마지막 값과 맞는지 본다.
어긋나면 붙이지 않고 멈춘다 — 양식이 바뀌었을 때 조용히 틀린 값이 들어가는
것이 가장 나쁘기 때문이다.
"""
import argparse, collections, datetime, json, os, re, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, ".cache", "gallup")
sys.path.insert(0, HERE)
import generate_site as g

LIST = "https://www.gallup.co.kr/gallupdb/report.asp"
CONTENT = "https://www.gallup.co.kr/gallupdb/reportContent.asp?seqNo=%s&bType=8"
PDF_RE = re.compile(r"https://www\.gallup\.co\.kr/dir/GallupKoreaDaily/"
                    r"GallupKoreaDailyOpinion_(\d+)\((\d{8})\)\.pdf")
# '전체   1,001  잘하고 있다  40%' / 다음 줄 '잘못하고 있다  50%'
POS_RE = re.compile(r"전체\s+[\d,]+\s+잘하고 있다\s+(\d+)%")
NEG_RE = re.compile(r"잘못하고 있다\s+(\d+)%")
KST = datetime.timezone(datetime.timedelta(hours=9))


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 slowfactbook"})
    return urllib.request.urlopen(req, timeout=60).read()


def issues():
    """목록에 걸린 데일리 오피니언 호를 {호번호: (발표일, pdf 주소)} 로."""
    html = _get(LIST).decode("euc-kr", "replace")
    out = {}
    for seq, title in re.findall(r"fn_viewContents\('(\d+)'\);[^>]*>(.*?)</a>", html, re.S):
        if "데일리 오피니언" not in re.sub("<[^>]+>", "", title):
            continue
        page = _get(CONTENT % seq).decode("euc-kr", "replace")
        m = PDF_RE.search(page)
        if m:
            out[int(m.group(1))] = (m.group(2), m.group(0))
    return out


def rates(no, date, url):
    """한 호의 전체 긍정률과 부정률."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"GallupKoreaDailyOpinion_{no}({date}).pdf")
    if not os.path.exists(path):
        open(path, "wb").write(_get(url))
    txt = subprocess.run(["pdftotext", "-layout", path, "-"],
                         capture_output=True, text=True, timeout=180).stdout
    mp = POS_RE.search(txt)
    if not mp:
        raise RuntimeError(f"{no}호: 전체 긍정률을 찾지 못했습니다")
    mn = NEG_RE.search(txt, mp.end())
    if not mn:
        raise RuntimeError(f"{no}호: 전체 부정률을 찾지 못했습니다")
    return float(mp.group(1)), float(mn.group(1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    mp = os.path.join(DATA, "gallup_weekly.json")
    mapping = json.load(open(mp, encoding="utf-8"))
    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in items if it.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    found = issues()
    if not found:
        print("목록에서 데일리 오피니언 호를 찾지 못했습니다."); return 1
    print(f"목록에 걸린 호: {min(found)}~{max(found)}")

    changed = False
    for cid, spec in mapping.items():
        it = items.get(cid)
        if not it:
            print(f"  - {cid}: 차트를 찾지 못했습니다"); continue
        last = int(spec["lastNo"])
        title = it.get("title") or cid

        # 대조. 차트에 담긴 마지막 호를 다시 받아 값이 같은지 본다.
        if last not in found:
            print(f"  - {cid} {title}: 마지막 호({last})가 목록에서 내려가 대조할 수 없습니다")
            continue
        try:
            pos, neg = rates(last, *found[last])
        except Exception as e:
            print(f"  - {cid} {title}: {e}"); continue
        have = (it["series"][0][-1], it["series"][1][-1])
        if (pos, neg) != have:
            print(f"  - {cid} {title}: {last}호 대조 어긋남 "
                  f"차트 {have} vs 원문 ({pos}, {neg}) — 손대지 않습니다")
            continue

        new = sorted(n for n in found if n > last)
        if not new:
            print(f"  · {cid} {title}: 이미 최신 ({last}호, {len(it['labels'])}점)")
            continue

        labels = [str(x) for x in it["labels"]]
        series = [list(s) for s in it["series"]]
        added = []
        for n in new:
            date, url = found[n]
            try:
                p, q = rates(n, date, url)
            except Exception as e:
                print(f"  - {cid} {title}: {e} — 여기서 멈춥니다"); break
            labels.append(f"{date[:4]}-{date[4:6]}")
            series[0].append(p); series[1].append(q)
            added.append((n, date, p, q))
            last = n
        if not added:
            continue
        for n, d, p, q in added:
            print(f"  + {cid} {title}: {n}호({d[:4]}-{d[4:6]}-{d[6:]}) 긍정 {p:.0f} 부정 {q:.0f}")
        if a.apply:
            o = ov.setdefault(cid, {}); o["id"] = cid
            o["labels"] = labels; o["series"] = series; o["updated"] = stamp
            spec["lastNo"] = last
            changed = True

    if a.apply and changed:
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        open(ovp, "a", encoding="utf-8").write("\n")
        json.dump(mapping, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        open(mp, "a", encoding="utf-8").write("\n")
        print("-> data/overrides.json 에 반영했습니다.")
    elif not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
