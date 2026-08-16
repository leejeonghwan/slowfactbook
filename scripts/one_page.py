#!/usr/bin/env python3
"""
지금까지 만든 것을 페이지 하나로 합친다.

여기저기 흩어진 JSON·CSV·HTML을 다 열어볼 필요 없이, 이 파일 하나만 보면 된다.
  - 어떤 차트가 어느 통계표에서 왔나
  - 지금 데이터가 언제까지인가, 원본은 어디까지 나와 있나
  - 갱신하려면 어느 TSV를 받아 키노트에 붙이면 되나

  python3 scripts/one_page.py
"""
import os, sys, json, html, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "슬로우팩트북_현황.html")


def load(name, default):
    p = os.path.join(DATA, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


ver = load("versions.json", {})
rev = load("_match_review.json", []) + load("_ecos_review.json", [])
refine = load("_source_refine.json", [])
titles = load("_title_review.json", [])

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import generate_site as g
items = g.load_items(DATA)
g.assign_ids(items, os.path.join(DATA, "ids.json"))
by = {it["slide"]: it for it in items}

FREQ = {"Y": "연간", "Q": "분기", "M": "월간", "H": "반기"}


def pp(t, f):
    """202605 → 2026-05 · 20262 → 2026 2Q"""
    t = str(t or "")
    if f == "M" and len(t) == 6:
        return f"{t[:4]}-{t[4:]}"
    if f == "Q" and len(t) > 4:
        return f"{t[:4]} {t[4:].lstrip('0') or '1'}Q"
    if f == "H" and len(t) > 4:
        return f"{t[:4]} {'상반기' if t[4:].lstrip('0') in ('1','') else '하반기'}"
    return t[:4]
rows = list(ver.values())
stale = [r for r in rows if r.get("state") == "stale"]
cur = [r for r in rows if r.get("state") == "current"]

# ── 갱신 대상 표 ───────────────────────────────────────────
def tr(r):
    tsv = (f"<button class=dl data-id='{r['id']}'>내려받기</button>"
           f"<button class=cp data-id='{r['id']}'>복사</button>") if r.get("tsv") else ""
    sc = r.get("scale", 1) or 1
    return (f"<tr><td class=id>{r['id']}</td>"
            f"<td>{html.escape(r['title'])}<div class=sub>{html.escape(r['category'])} · "
            f"{html.escape(str(r.get('statNm') or ''))} <span class=tbl>{r.get('tblId','')}</span></div></td>"
            f"<td class=n>{pp(r.get('chartLast'), r.get('prdSe'))}</td>"
            f"<td class=n><b>{pp(r.get('apiLast'), r.get('prdSe'))}</b></td>"
            f"<td class=n>{FREQ.get(r.get('prdSe'),'')}</td>"
            f"<td class=n>{'' if sc == 1 else f'×{sc:g}'}</td><td>{tsv}</td></tr>")


stale_rows = "".join(tr(r) for r in sorted(stale, key=lambda x: str(x.get("apiLast")), reverse=True))
cur_rows = "".join(tr(r) for r in sorted(cur, key=lambda x: x["category"]))

# ── 미매칭 상위 ────────────────────────────────────────────
mrows = ""
for r in sorted(rev, key=lambda x: -(x.get("best_score") or 0))[:60]:
    it = by.get(r["slide"])
    c = (r.get("cands") or [{}])[0]
    mrows += (f"<tr><td class=id>{it['id'] if it else ''}</td>"
              f"<td>{html.escape(r.get('title',''))}<div class=sub>{html.escape(r.get('category',''))}</div></td>"
              f"<td class=n>{FREQ.get(r.get('freq'),'')}</td>"
              f"<td class=n>{r.get('best_score') or 0:.2f}</td>"
              f"<td>{html.escape(str(c.get('statNm') or c.get('statName') or c.get('tblNm') or c.get('why') or ''))[:44]}"
              f" <span class=tbl>{c.get('tblId') or c.get('statCode') or ''}</span></td></tr>")

srows = "".join(
    f"<tr><td>{html.escape(r['title'])}<div class=sub>{html.escape(r['category'])}</div></td>"
    f"<td>{html.escape(r['current'] or '(없음)')}</td><td><b>{html.escape(r['suggest'])}</b></td></tr>"
    for r in refine)

# TSV 내용을 페이지 안에 넣어 파일 하나로 동작하게 한다
TSVDIR = os.path.join(ROOT, "latest", "tsv")
blob = {}
for r in rows:
    fn = r.get("tsv")
    if not fn:
        continue
    fp = os.path.join(TSVDIR, fn)
    if os.path.exists(fp):
        blob[r["id"]] = {"name": fn, "text": open(fp, encoding="utf-8-sig").read()}

empty_titles = [it for it in items if len(it["title"].strip()) < 3]

HTML = f"""<!DOCTYPE html><html lang=ko><meta charset=utf-8>
<title>슬로우팩트북 현황</title><style>
body{{font:14px/1.6 system-ui,-apple-system,"Apple SD Gothic Neo",sans-serif;background:#f7f7f5;color:#1a1a1a;margin:0}}
.w{{max-width:1000px;margin:0 auto;padding:30px 20px 80px}}
h1{{font-size:24px;margin:0 0 6px;letter-spacing:-.02em}}
h2{{font-size:17px;margin:38px 0 6px;letter-spacing:-.01em}}
p.s{{color:#666;font-size:13px;margin:0 0 14px;max-width:720px}}
.kpi{{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0 8px}}
.kpi div{{background:#fff;border:1px solid #e5e5e2;border-radius:11px;padding:13px 17px;min-width:112px}}
.kpi b{{display:block;font-size:23px;letter-spacing:-.02em}} .kpi span{{font-size:12px;color:#666}}
.kpi .hot b{{color:#c0322f}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e5e2;border-radius:11px;overflow:hidden;margin-bottom:6px}}
th{{text-align:left;font-size:11.5px;color:#555;background:#f2f2ef;padding:8px 10px;border-bottom:1px solid #e5e5e2;font-weight:600}}
td{{padding:9px 10px;border-bottom:1px solid #f2f2ef;font-size:13.5px;vertical-align:top}}
td.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
td.id{{color:#999;font-size:11.5px;font-variant-numeric:tabular-nums}}
.sub{{color:#999;font-size:11.5px;margin-top:2px}}
.tbl{{color:#bbb;font-size:10.5px}}
button.dl,button.cp{{font:inherit;font-size:11.5px;border:0;border-radius:99px;padding:4px 11px;cursor:pointer;white-space:nowrap}}
button.dl{{background:#2f5e8e;color:#fff;margin-right:4px}}
button.cp{{background:#ececea;color:#333}}
button.dl:hover{{background:#24486d}} button.cp:hover{{background:#e0e0dd}}
button.ok{{background:#0ca30c!important;color:#fff!important}}
b{{color:#c0322f}}
details{{margin-top:8px}} summary{{cursor:pointer;color:#2f5e8e;font-size:13px;padding:6px 0}}
.box{{background:#fff;border:1px solid #e5e5e2;border-radius:11px;padding:16px 18px;margin-bottom:8px}}
.box ol{{margin:6px 0 0;padding-left:20px}} .box li{{margin-bottom:7px}}
code{{background:#f2f2ef;padding:1px 5px;border-radius:4px;font-size:12.5px}}
.note{{color:#666;font-size:12.5px;margin-top:6px}}
</style><div class=w>

<h1>슬로우팩트북 현황</h1>
<p class=s>이 페이지 하나만 보시면 됩니다. 다른 파일은 안 열어도 됩니다.</p>

<div class=kpi>
 <div><b>{len(items):,}</b><span>전체 차트</span></div>
 <div><b>{len(rows)}</b><span>통계표 연결됨</span></div>
 <div class=hot><b>{len(stale)}</b><span>갱신 필요</span></div>
 <div><b>{len(rev)}</b><span>연결 못 함</span></div>
</div>

<h2>1. 지금 갱신할 것 — {len(stale)}건</h2>
<p class=s>원본에 새 데이터가 나와 있는 차트입니다. TSV를 받아 키노트에 붙여넣으면 됩니다.
<b>복사</b>를 누르면 클립보드에 들어가니 키노트·넘버스에 바로 붙여넣으시면 됩니다.
데이터에는 <b>차트단위</b> 칸이 있어서 지금 쓰시는 만·억·조 단위 그대로 쓰시면 됩니다.</p>
<table><thead><tr><th>ID</th><th>차트 / 출처</th><th>지금</th><th>원본</th><th>주기</th><th>단위배수</th><th></th></tr></thead>
<tbody>{stale_rows}</tbody></table>

<h2>2. 이미 최신인 것 — {len(cur)}건</h2>
<details><summary>펼쳐 보기</summary>
<table><thead><tr><th>ID</th><th>차트 / 출처</th><th>지금</th><th>원본</th><th>주기</th><th>단위배수</th><th></th></tr></thead>
<tbody>{cur_rows}</tbody></table></details>

<h2>3. 출처 표기 고칠 것 — {len(refine)}건</h2>
<p class=s>조사명이 실제와 다른 차트입니다. 나머지 1,358건(단위 분리·기관명 통일)은 이미 자동 반영했습니다.</p>
<table><thead><tr><th>차트</th><th>현재 표기</th><th>맞는 출처</th></tr></thead><tbody>{srows}</tbody></table>

<h2>4. 아직 연결 못 한 것 — {len(rev)}건</h2>
<p class=s>제목이 통계 용어와 달라 검색이 안 됐거나, KOSIS에 없는 데이터(민간 조사·언론사 자체 집계)입니다.
일치도가 높은 순으로 60건만 보여줍니다 — 위쪽은 통계표는 맞고 분류만 어긋난 경우가 많습니다.</p>
<details><summary>펼쳐 보기</summary>
<table><thead><tr><th>ID</th><th>차트</th><th>주기</th><th>일치도</th><th>가장 가까운 후보</th></tr></thead>
<tbody>{mrows}</tbody></table></details>

<h2>5. 저장소에서 먼저 고칠 것</h2>
<div class=box><ol>
<li><b>임베드 URL이 뒤바뀔 수 있음</b> — 제목이 겹치는 차트 274개의 id가 빌드 순서로 정해집니다.
    <code>assign_ids()</code>의 키를 <code>slide</code> 기준으로 바꾸면 끝납니다. 30분.</li>
<li><b>Chart.js가 CDN 한 곳에만 의존</b> — 막히면 차트 1,658개가 전부 빈 화면이 됩니다. 자체 호스팅 15분.</li>
<li><b>source 없이 build.py를 돌리면 검수 목록이 지워짐</b> — <code>update.sh</code>가 그대로 커밋합니다. 5분.</li>
<li><b>빈 제목 {len(empty_titles)}개</b>가 사이트에 그대로 노출됩니다. <code>_title_review.json</code>에 목록이 있습니다.</li>
</ol></div>

<h2>6. 갱신할 때 이 순서로</h2>
<div class=box><ol>
<li>위 1번 표에서 TSV 받기</li>
<li>키노트에서 해당 차트 데이터 교체 (차트단위 칸 복사)</li>
<li>키노트 → PowerPoint 내보내기 → <code>source/</code>에 덮어쓰기</li>
<li><code>python3 scripts/build.py</code></li>
<li><code>python3 scripts/export_latest.py</code> → 이 페이지가 갱신되고, 반영된 차트는 1번 표에서 사라집니다</li>
</ol>
<p class=note>키노트가 정본입니다. 이 도구는 “원본에 새 데이터 나왔다”고 알려줄 뿐 키노트를 건드리지 않습니다.</p>
</div>

</div></html>"""

JS = r"""
<script type="application/json" id="tsvdata">__TSVBLOB__</script>
<script>
const TSV = JSON.parse(document.getElementById('tsvdata').textContent);
document.addEventListener('click', function (e) {
  var b = e.target.closest('button.dl, button.cp');
  if (!b) return;
  var d = TSV[b.dataset.id];
  if (!d) return;
  if (b.classList.contains('dl')) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['\ufeff' + d.text], {type: 'text/tab-separated-values'}));
    a.download = d.name; a.style.display = 'none';
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 800);
  } else {
    var body = d.text.split('\n').filter(function (l) { return l.indexOf('#') !== 0; }).join('\n');
    navigator.clipboard.writeText(body).then(function () {
      var t = b.textContent; b.textContent = '\uBCF5\uC0AC\uB428'; b.classList.add('ok');
      setTimeout(function () { b.textContent = t; b.classList.remove('ok'); }, 1400);
    });
  }
});
</script>
"""
HTML = HTML.replace("</div></html>", JS.replace("__TSVBLOB__", json.dumps(blob, ensure_ascii=False).replace("</", "<\\/")) + "</div></html>")

open(OUT, "w", encoding="utf-8").write(HTML)
print(f"→ {OUT}")
print(f"연결 {len(rows)} · 갱신 필요 {len(stale)} · 최신 {len(cur)} · 미연결 {len(rev)} · 출처 수정 {len(refine)}")
