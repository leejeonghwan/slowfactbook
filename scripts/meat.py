#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1인당 육류 소비량(c0342)과 쌀과 육류 소비 비교(c0346)의 육류 쪽.

  python3 scripts/meat.py            # 미리보기
  python3 scripts/meat.py --apply

한국육류유통수출협회의 소비현황 표를 그대로 읽는다. 표 한 줄은
  연도 | 전체소비량(톤) 우육·돈육·계육·계 | 1인당(kg) 우육·돈육·계육·계
아홉 칸이다. 이 어댑터는 뒤쪽 1인당 네 칸을 쓴다.

손으로 넣던 차트였고 값이 어긋나 있었다. 2022년 우육이 차트 13.8 / 표 14.90,
2023년 돈육이 차트 30.1 / 표 29.60 이었다. 협회가 뒤에 고쳤거나 다른 시점
자료를 옮겨 적은 것으로 보인다. 그래서 겹치는 구간을 덮고 1980년부터 다시
세운다.

c0346 은 쌀과 육류를 한 그림에 올린 차트다. 육류 계열만 이 표의 '계' 로
맞추고 쌀 계열은 건드리지 않는다.
"""
import argparse, collections, datetime, io, json, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

URL = "https://www.kmta.or.kr/kr/data/stats_spend.php"
MEAT, MIX = "c0342", "c0346"
NAMES = ["우육", "돈육", "계육"]


def pull():
    r = subprocess.run(["curl", "-sS", "--max-time", "60", URL],
                       capture_output=True)
    if r.returncode != 0:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    s = r.stdout.decode("euc-kr", "replace")
    out = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", s, re.S | re.I):
        tds = [re.sub(r"<[^>]+>", "", t).replace("\xa0", " ").strip()
               for t in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
        if len(tds) != 9 or not re.fullmatch(r"(19|20)\d\d", tds[0] or ""):
            continue
        try:
            v = [float(x.replace(",", "")) for x in tds[5:9]]
        except ValueError:
            continue
        out[tds[0]] = v          # 우육, 돈육, 계육, 계
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    raw = pull()
    if len(raw) < 30:
        raise SystemExit(f"받은 해가 {len(raw)}개뿐입니다 — 쓰지 않습니다.")
    years = sorted(raw)
    # 세 고기를 더하면 표의 '계' 와 맞아야 한다.
    bad = [(y, round(sum(raw[y][:3]), 2), raw[y][3]) for y in years
           if abs(sum(raw[y][:3]) - raw[y][3]) > 0.06]
    if bad:
        raise SystemExit(f"세 고기 합이 계와 어긋납니다: {bad[:5]}")
    print(f"한국육류유통수출협회 {years[0]} ~ {years[-1]} ({len(years)}개 해) — 합계 대조 일치")

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    full = {}
    for f in ("full.json", "manual.json"):
        for i in json.load(open(os.path.join(DATA, f), encoding="utf-8"))["items"]:
            if i.get("id"):
                full.setdefault(i["id"], {}).update(i)

    def cur(c):
        return {**full.get(c, {}), **(ov.get(c) or {})}

    # ── c0342 세 계열
    c = cur(MEAT)
    old = {str(L): [s[i] for s in c["series"]]
           for i, L in enumerate([])}  # 자리만 잡는다
    lab = [str(x) for x in (c.get("labels") or [])]
    moved = []
    for i, y in enumerate(lab):
        if y not in raw:
            continue
        for j in range(3):
            o = c["series"][j][i]
            if o is not None and round(o, 2) != round(raw[y][j], 2):
                moved.append((y, NAMES[j], o, raw[y][j]))
    print(f"  c0342 기존 {len(lab)}개 해({lab[0] if lab else '-'}~{lab[-1] if lab else '-'})"
          f" 가운데 고쳐질 값 {len(moved)}곳")
    for y, n, o, v in moved[:12]:
        print(f"    {y} {n}: {o} -> {v}")

    # ── c0346 육류 계열
    m = cur(MIX)
    mlab = [str(x) for x in m["labels"]]
    mnames = [str(n).strip().rstrip(".") for n in m["seriesNames"]]
    mi = mnames.index("육류")
    mmoved = [(y, m["series"][mi][i], raw[y][3]) for i, y in enumerate(mlab)
              if y in raw and m["series"][mi][i] is not None
              and round(m["series"][mi][i], 2) != round(raw[y][3], 2)]
    print(f"  c0346 육류 계열에서 고쳐질 값 {len(mmoved)}곳")
    for y, o, v in mmoved[:12]:
        print(f"    {y}: {o} -> {v}")
    add = [y for y in years if y > (mlab[-1] if mlab else "")]
    print(f"    새로 붙을 해: {add}")

    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
        return 0

    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    src = ("한국육류유통수출협회 소비현황. 1인당 소비량, "
           f"{years[0]}~{years[-1]}년. 단위: kg.")

    o = ov.setdefault(MEAT, {})
    o["id"] = MEAT
    o["title"] = "1인당 육류 소비량"
    o["labels"] = years
    o["series"] = [[raw[y][j] for y in years] for j in range(3)]
    o["seriesNames"] = ["쇠고기", "돼지고기", "닭고기"]
    o["unit"] = "kg"
    o["source"] = src
    o["sourceUrl"] = URL
    o["notes"] = [
        "한국육류유통수출협회가 내는 소비현황 표의 1인당 소비량입니다. "
        "협회는 전체 소비량(톤)도 같이 내는데, 그것을 인구로 나눈 값입니다.",
        "세 고기를 쌓은 그림이라 맨 위 높이가 육류 전체 소비량입니다. 세 값을 "
        f"더하면 협회가 공표하는 '계' 와 맞는 것을 {len(years)}개 해 모두에서 "
        "확인했습니다.",
        "먹은 양이 아니라 공급된 양에 가깝습니다. 생산과 수입에서 수출과 "
        "재고를 뺀 물량을 인구로 나누는 방식이라, 버려지는 몫과 외식업 "
        "손실분이 들어 있습니다.",
        f"{years[-1]}년 1인당 {raw[years[-1]][3]}kg 으로 1980년 "
        f"{raw[years[0]][3]}kg 의 다섯 배가 넘습니다. 돼지고기가 늘 가장 "
        "많고, 2010년대 들어 닭고기가 쇠고기를 앞질렀습니다.",
        "2020년에 한 번 꺾인 것은 코로나로 외식이 줄어든 해이기 때문입니다. "
        "이듬해 바로 회복했습니다.",
        "손으로 넣던 값에 협회 표와 어긋나는 곳이 있어 전부 다시 받았습니다. "
        "협회가 지난 해 수치를 뒤에 고치는 일이 있어, 이 차트는 받을 때마다 "
        "과거 값까지 덮습니다.",
    ]
    o["updated"] = now

    p = ov.setdefault(MIX, {})
    p["id"] = MIX
    # 기간은 늘리지 않는다. 협회 자료는 1980년부터지만 쌀 조사는 그만큼
    # 거슬러 가지 않아, 늘리면 육류 선만 혼자 길어진다.
    ml = list(mlab)
    rice = dict(zip(mlab, m["series"][1 - mi]))
    p["labels"] = ml
    meat_s = [raw[y][3] if y in raw else None for y in ml]
    rice_s = [rice.get(y) for y in ml]
    p["series"] = [rice_s, meat_s] if mi == 1 else [meat_s, rice_s]
    p["seriesNames"] = ["쌀", "육류"] if mi == 1 else ["육류", "쌀"]
    p["unit"] = "kg"
    p["source"] = ("육류는 한국육류유통수출협회 소비현황, 쌀은 국가데이터처 "
                   "양곡소비량조사. 1인당 연간 소비량. 단위: kg.")
    p["sourceUrl"] = URL
    p["notes"] = [
        "육류는 한국육류유통수출협회, 쌀은 국가데이터처 양곡소비량조사입니다. "
        "기관도 조사 방식도 달라 같은 잣대로 잰 값이 아닙니다.",
        "쌀은 가구 조사로 실제 먹은 양을 묻고, 육류는 공급량을 인구로 나눕니다. "
        "그래서 육류 쪽에 버려지는 몫과 외식업 손실분이 들어 있습니다. "
        "두 선이 교차하는 시점을 '고기가 쌀을 앞질렀다'로 읽을 때는 이 차이를 "
        "감안해야 합니다.",
        "육류는 세 고기(쇠고기, 돼지고기, 닭고기)를 더한 값입니다. 오리와 "
        "양고기 등은 들어 있지 않습니다.",
    ]
    p["updated"] = now

    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
