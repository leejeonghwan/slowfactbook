#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""통신 3사 분기 실적. SK텔레콤, KT, LG유플러스의 연결 매출과 영업이익.

  python3 scripts/telecom_results.py            # 미리보기
  python3 scripts/telecom_results.py --apply

원천은 금융감독원 전자공시(DART) 오픈API 다. 두 군데를 쓴다.

  1) 단일회사 주요계정(fnlttSinglAcnt). 분기·반기보고서의 '당기금액' 이
     그 분기 석 달치다. 4분기는 사업보고서의 연간값에서 3분기 누계를 뺀다.
     이 API 는 2016년부터 받을 수 있다.
  2) 「연결재무제표기준 영업(잠정)실적(공정공시)」. 분기보고서는 분기 끝난
     뒤 45일까지 내면 되므로, 실적 발표는 났는데 보고서는 아직인 구간이
     생긴다. 그 한 분기를 잠정 공시에서 메운다.

잠정 공시에는 직전 분기 실적이 같이 적혀 있다. 그 값이 이미 확정된
분기보고서 값과 맞는지 보고, 어긋나면 쓰지 않는다. 숫자를 잘못 읽었는지
가려내는 가장 확실한 방법이다.

연결 기준이다. SK텔레콤에는 SK브로드밴드가, KT 에는 BC카드와 케이뱅크 등이,
LG유플러스에는 미디어로그 등이 들어 있다. 통신 본업만의 실적이 아니다.
"""
import argparse, datetime, html, json, os, re, subprocess, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "dart_cache.json")
KST = datetime.timezone(datetime.timedelta(hours=9))

CO = [("SK텔레콤", "00159023", "#c0322f"),
      ("KT", "00190321", "#2f5e8e"),
      ("LG유플러스", "00231363", "#e8820c")]
FIRST = 2016
RC = {1: "11013", 2: "11012", 3: "11014", 4: "11011"}
SALES = ("매출액", "수익(매출액)", "영업수익", "매출")
PROFIT = ("영업이익", "영업이익(손실)")
SLIDE_S = "manual-telecom-sales"
SLIDE_P = "manual-telecom-profit"
SLIDE_M = "manual-telecom-margin"
URL = "https://dart.fss.or.kr/"


def envkey(name):
    """환경변수를 먼저 보고 없으면 .env 를 읽는다.

    깃허브 액션은 secrets 를 환경변수로 넘기고 .env 는 저장소에 없다.
    맥에서 손으로 돌릴 때는 .env 에 들어 있다. 둘 다 되게 한다.
    """
    v = os.environ.get(name)
    if v:
        return v.strip()
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit(f"{name} 가 필요합니다(환경변수 또는 .env).")


def key():
    return envkey("DART_API_KEY")


def get(url, out=None):
    cmd = ["curl", "-sS", "--max-time", "90"]
    if out:
        cmd += ["-o", out]
    r = subprocess.run(cmd + [url], capture_output=True)
    if r.returncode:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    return r.stdout


def won(s):
    if s in (None, "", "-"):
        return None
    s = str(s).replace(",", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def acnt(K, cc, y, rc):
    """{'매출_당기','매출_누계','이익_당기','이익_누계'} — 억 원."""
    u = ("https://opendart.fss.or.kr/api/fnlttSinglAcnt.json?crtfc_key=" + K +
         f"&corp_code={cc}&bsns_year={y}&reprt_code={rc}&fs_div=CFS")
    d = json.loads(get(u).decode("utf-8", "replace"))
    if d.get("status") != "000":
        return None
    out = {}
    for it in d.get("list") or []:
        if it.get("sj_div") != "IS" and it.get("sj_nm") not in ("손익계산서", "포괄손익계산서"):
            continue
        nm = (it.get("account_nm") or "").strip()
        tag = "매출" if nm in SALES else ("이익" if nm in PROFIT else None)
        if not tag:
            continue
        a, b = won(it.get("thstrm_amount")), won(it.get("thstrm_add_amount"))
        if a is not None:
            out.setdefault(tag + "_당기", a / 1e8)
        if b is not None:
            out.setdefault(tag + "_누계", b / 1e8)
    return out or None


def provisional(K, cc):
    """가장 최근 「연결재무제표기준 영업(잠정)실적」에서 분기 실적을 읽는다."""
    end = datetime.datetime.now(KST).strftime("%Y%m%d")
    bgn = (datetime.datetime.now(KST) - datetime.timedelta(days=150)).strftime("%Y%m%d")
    u = ("https://opendart.fss.or.kr/api/list.json?crtfc_key=" + K +
         f"&corp_code={cc}&bgn_de={bgn}&end_de={end}&page_count=100")
    d = json.loads(get(u).decode("utf-8", "replace"))
    hits = [x for x in (d.get("list") or [])
            if "연결재무제표기준영업(잠정)실적" in x["report_nm"].replace(" ", "")]
    if not hits:
        return None
    rc = sorted(hits, key=lambda x: x["rcept_dt"])[-1]["rcept_no"]
    p = f"/tmp/dart_{rc}.zip"
    get("https://opendart.fss.or.kr/api/document.xml?crtfc_key=" + K +
        f"&rcept_no={rc}", out=p)
    try:
        z = zipfile.ZipFile(p)
    except zipfile.BadZipFile:
        return None
    raw = z.read(z.namelist()[0])
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            t = raw.decode(enc)
            break
        except Exception:
            t = None
    if t is None:
        return None
    t = re.sub(r"<(script|style).*?</\1>", "", t, flags=re.S | re.I)
    x = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    L, prev = [], None
    for l in (l.strip() for l in x.split("\n")):
        if l and l != prev:
            L.append(l)
            prev = l
    # 머리글에서 당기와 전기가 몇 년 몇 분기인지 읽는다. 회사마다 표기가
    # 달라 '(2026년 3분기 )', "('26.3분기)", "('26.3Q)" 를 모두 받는다.
    blob = "\n".join(L)
    qs = [(y if len(y) == 4 else "20" + y, q) for y, q in
          re.findall(r"\(\s*'?(\d{2,4})\s*(?:년|\.)\s*([1-4])\s*(?:분기|Q)", blob)]
    if len(qs) < 2:
        return None
    cur, prv = qs[0], qs[1]
    out = {}
    for tag, names in (("매출", SALES), ("이익", PROFIT)):
        i = next((k for k, l in enumerate(L) if l in names), None)
        if i is None:
            continue
        seg = L[i:i + 8]
        j = next((k for k, l in enumerate(seg) if l == "당해실적"), None)
        if j is None:
            continue
        nums = [won(v) for v in seg[j + 1:j + 4]]
        nums = [v for v in nums if v is not None]
        if len(nums) >= 2:
            out[tag] = (nums[0], nums[1])      # 당기, 직전 분기 — 억 원
    if len(out) < 2:
        return None
    return {"cur": f"{cur[0]}-Q{cur[1]}", "prev": f"{prv[0]}-Q{prv[1]}", "v": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--refetch", action="store_true")
    a = ap.parse_args()
    K = key()
    now = datetime.datetime.now(KST)

    cache = json.load(open(CACHE, encoding="utf-8")) if (
        os.path.exists(CACHE) and not a.refetch) else {}
    Q = {}          # 회사 -> {'2026-Q2': {'매출':..,'이익':..}}
    prov = {}
    for nm, cc, _ in CO:
        Q[nm] = {}
        for y in range(FIRST, now.year + 1):
            ck = f"{cc}:{y}"
            # 지난 해는 한 번 받으면 다시 받지 않는다. 올해와 지난해는 늘 받는다.
            if ck in cache and y < now.year - 1:
                rows = cache[ck]
            else:
                rows = {}
                for q, rc in RC.items():
                    r = acnt(K, cc, y, rc)
                    if r:
                        rows[str(q)] = r
                    time.sleep(0.12)
                cache[ck] = rows
            acc = {}
            for q in (1, 2, 3):
                r = rows.get(str(q))
                if not r:
                    continue
                if "매출_당기" in r and "이익_당기" in r:
                    acc[f"{y}-Q{q}"] = {"매출": r["매출_당기"], "이익": r["이익_당기"]}
                    continue
                # 보고서에 따라 '당기금액' 칸이 비고 누계만 들어오는 해가 있다.
                # 그럴 때는 누계끼리 빼서 그 분기 석 달치를 만든다.
                prev_acc = rows.get(str(q - 1)) if q > 1 else None
                got = {}
                for tag in ("매출", "이익"):
                    cum = r.get(tag + "_누계")
                    if cum is None:
                        break
                    before = 0.0 if q == 1 else (prev_acc or {}).get(tag + "_누계")
                    if before is None:
                        break
                    got[tag] = cum - before
                if len(got) == 2:
                    acc[f"{y}-Q{q}"] = got
            r4, r3 = rows.get("4"), rows.get("3")
            if r4 and r3 and "매출_누계" in r3 and "이익_누계" in r3:
                acc[f"{y}-Q4"] = {"매출": r4["매출_당기"] - r3["매출_누계"],
                                  "이익": r4["이익_당기"] - r3["이익_누계"]}
            # 검산: 네 분기의 합이 연간과 맞아야 한다.
            if r4 and all(f"{y}-Q{q}" in acc for q in (1, 2, 3, 4)):
                for tag in ("매출", "이익"):
                    s = sum(acc[f"{y}-Q{q}"][tag] for q in (1, 2, 3, 4))
                    t = r4[tag + "_당기"]
                    if abs(s - t) > max(2.0, abs(t) * 0.002):
                        raise SystemExit(f"{nm} {y}년 {tag} 네 분기 합 {s:.0f} 과 "
                                         f"연간 {t:.0f} 이 어긋납니다.")
            Q[nm].update(acc)
        p = provisional(K, cc)
        if p:
            prov[nm] = p
    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")

    # ── 잠정 공시 검증과 반영
    prov_used = {}
    for nm, _, _ in CO:
        p = prov.get(nm)
        if not p:
            continue
        # 잠정 공시에 적힌 직전 분기가 확정값과 맞아야 한다.
        ok = True
        for tag in ("매출", "이익"):
            have = Q[nm].get(p["prev"], {}).get(tag)
            said = p["v"].get(tag, (None, None))[1]
            if have is None or said is None:
                continue
            if abs(have - said) > max(3.0, abs(have) * 0.004):
                print(f"  ※ {nm} 잠정 공시의 {p['prev']} {tag} {said:.0f}억이 "
                      f"확정값 {have:.0f}억과 어긋납니다 — 잠정치를 쓰지 않습니다.")
                ok = False
        if ok and p["cur"] not in Q[nm]:
            Q[nm][p["cur"]] = {"매출": p["v"]["매출"][0], "이익": p["v"]["이익"][0]}
            prov_used[nm] = p["cur"]
    print(f"DART 전자공시 — 확정 분기보고서 {FIRST}년부터")
    for nm, _, _ in CO:
        ks = sorted(Q[nm])
        print(f"  {nm:8s} {len(ks)}개 분기 {ks[0]}~{ks[-1]}"
              + (f"  (마지막은 잠정 공시)" if prov_used.get(nm) else ""))

    # 세 회사가 다 갖춘 분기 가운데, 마지막까지 끊기지 않고 이어지는 구간만
    # 쓴다. 2016년 3분기 보고서처럼 주요계정이 반쪽만 들어오는 해가 있어,
    # 그대로 두면 선 가운데 구멍이 뚫린다.
    def step(q):
        y, k = int(q[:4]), int(q[-1])
        return f"{y + 1}-Q1" if k == 4 else f"{y}-Q{k + 1}"
    full = sorted(q for q in set().union(*[set(Q[nm]) for nm, _, _ in CO])
                  if all(q in Q[nm] for nm, _, _ in CO))
    if not full:
        raise SystemExit("세 회사가 함께 있는 분기가 없습니다.")
    lab = [full[-1]]
    while True:
        prev = next((q for q in full if step(q) == lab[0]), None)
        if prev is None:
            break
        lab.insert(0, prev)
    dropped = [q for q in full if q not in lab]
    if dropped:
        print(f"  앞쪽 {len(dropped)}개 분기는 세 회사가 다 갖추지 못해 뺐습니다: "
              f"{dropped[0]}~{dropped[-1]}")
    last = lab[-1]
    print(f"  공통 구간 {lab[0]}~{last} ({len(lab)}개 분기)")
    for nm, _, _ in CO:
        v = Q[nm][last]
        print(f"    {nm:8s} {last} 매출 {v['매출']:,.0f}억  영업이익 {v['이익']:,.0f}억  "
              f"이익률 {v['이익'] / v['매출'] * 100:.1f}%")

    now_s = now.strftime("%Y-%m-%d %H:%M")
    pv = ", ".join(f"{n}({q})" for n, q in prov_used.items())
    SRC = ("금융감독원 전자공시(DART). 연결재무제표 기준 분기 실적. "
           f"{lab[0].replace('-Q', '년 ')}분기~{last.replace('-Q', '년 ')}분기.")
    BASIS = ("연결 기준이라 통신 본업만의 실적이 아닙니다. SK텔레콤에는 "
             "SK브로드밴드가, KT 에는 BC카드와 케이뱅크 등이, LG유플러스에는 "
             "미디어로그 등이 들어 있습니다. 세 회사의 자회사 구성이 달라 "
             "매출 규모를 그대로 견주면 통신 점유율과는 다른 그림이 됩니다.")
    PROV = (f"가장 최근 분기({last.replace('-Q', '년 ')}분기)는 잠정치입니다. "
            "분기보고서는 분기가 끝난 뒤 45일까지 내면 되기 때문에, 실적 발표는 "
            "났는데 보고서는 아직인 구간이 생깁니다. 회사가 낸 "
            "「연결재무제표기준 영업(잠정)실적」 공시에서 가져왔고, 보고서가 "
            "올라오면 확정치로 바뀝니다.") if prov_used else ""
    Q4 = ("4분기는 사업보고서의 연간값에서 3분기 누계를 뺀 값입니다. 회사가 "
          "4분기만 따로 공표하지 않기 때문입니다. 네 분기를 더하면 연간과 "
          "맞는 것을 모든 해에서 확인했습니다.")

    def series(tag, f=lambda v: v):
        return [[round(f(Q[nm][q][tag]), 2) for q in lab] for nm, _, _ in CO]

    names = [nm for nm, _, _ in CO]
    colors = [c for _, _, c in CO]
    items = []

    items.append({
        "slide": SLIDE_S, "category": "기업과 산업",
        "title": "통신 3사 분기 매출", "vizType": "line", "unit": "조 원",
        "labels": lab, "series": series("매출", lambda v: v / 10000),
        "seriesNames": names, "seriesColors": colors,
        "source": SRC + " 단위: 조 원.", "sourceUrl": URL,
        "notes": [
            f"{last.replace('-Q', '년 ')}분기 매출은 "
            + ", ".join(f"{nm} {Q[nm][last]['매출'] / 10000:.2f}조 원"
                        for nm, _, _ in CO) + " 입니다.",
            BASIS,
            "분기마다 오르내리는 것이 계절성입니다. 단말기 판매가 몰리는 분기에 "
            "매출이 커집니다. 단말기는 사서 되파는 것이라 매출은 늘려도 이익에는 "
            "거의 보탬이 되지 않습니다. 매출보다 영업이익 쪽을 보는 편이 낫습니다.",
            Q4, PROV,
            "DART 가 주요계정 API 로 주는 구간이 2016년부터입니다. 더 거슬러 "
            "가려면 각 사 IR 자료를 따로 긁어야 합니다.",
        ],
        "updated": now_s,
    })

    items.append({
        "slide": SLIDE_P, "category": "기업과 산업",
        "title": "통신 3사 분기 영업이익", "vizType": "line", "unit": "억 원",
        "labels": lab, "series": series("이익"),
        "seriesNames": names, "seriesColors": colors,
        "source": SRC + " 단위: 억 원.", "sourceUrl": URL,
        "notes": [
            f"{last.replace('-Q', '년 ')}분기 영업이익은 "
            + ", ".join(f"{nm} {Q[nm][last]['이익']:,.0f}억 원"
                        for nm, _, _ in CO) + " 입니다.",
            "전년 같은 분기와 견주는 편이 낫습니다. 분기끼리 견주면 계절성과 "
            "일회성 비용에 묻힙니다. 희망퇴직 비용이 한 분기에 몰리거나 부동산을 "
            "팔아 이익이 잡히는 해가 있습니다.",
            BASIS, Q4, PROV,
        ],
        "updated": now_s,
    })

    items.append({
        "slide": SLIDE_M, "category": "기업과 산업",
        "title": "통신 3사 분기 영업이익률", "vizType": "line", "unit": "%",
        "labels": lab,
        "series": [[round(Q[nm][q]["이익"] / Q[nm][q]["매출"] * 100, 2) for q in lab]
                   for nm, _, _ in CO],
        "seriesNames": names, "seriesColors": colors,
        "source": SRC + " 영업이익을 매출로 나눈 값. 단위: %.", "sourceUrl": URL,
        "notes": [
            f"{last.replace('-Q', '년 ')}분기 영업이익률은 "
            + ", ".join(f"{nm} {Q[nm][last]['이익'] / Q[nm][last]['매출'] * 100:.1f}%"
                        for nm, _, _ in CO) + " 입니다.",
            "매출 규모가 다른 세 회사를 견주기에는 이익률이 낫습니다. 다만 연결 "
            "기준이라 자회사 구성이 이익률을 끌어내리기도 합니다. 단말기 유통이나 "
            "카드업처럼 매출은 크고 마진이 얇은 사업을 품으면 이익률이 낮게 "
            "나옵니다.",
            BASIS, Q4, PROV,
        ],
        "updated": now_s,
    })

    for it in items:
        print(f"  {it['slide']:24s} {it['title']:18s} {len(it['labels'])}개 분기")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0

    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    ids = json.load(open(os.path.join(DATA, "ids.json"), encoding="utf-8"))
    for item in items:
        item["notes"] = [n for n in item["notes"] if n]
        cur = next((i for i in doc["items"] if i.get("slide") == item["slide"]), None)
        if cur and cur.get("id"):
            item["id"] = cur["id"]
        else:
            k = "S\x1f%s\x1f%s" % (item["slide"], item["title"])
            if ids.get(k):
                item["id"] = ids[k]
        if cur:
            doc["items"][doc["items"].index(cur)] = item
        else:
            doc["items"].append(item)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/manual.json 에 반영했습니다." + (f" 잠정: {pv}" if pv else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
