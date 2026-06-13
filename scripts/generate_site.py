#!/usr/bin/env python3
"""
data/*.json (extractor output) -> self-contained interactive site/index.html

Usage:
  python3 generate_site.py <data_dir> <out_html>

Each json in <data_dir> is one extractor output. Its category is taken from
the json's top-level "category" field (set by build.py) or, failing that,
from the filename.
"""
import sys, os, json, glob

CATEGORIES = [
    "한눈에 보는 한국","노동, 비정규직, 산업재해","인구 구조, 출산","물가와 생활",
    "수출과 무역","젠더와 격차","복지와 사회 안전망","사회","조세와 재정",
    "세계 경제, 식량","정치","금융, 주식, 부동산","복지","기후와 에너지",
    "소비와 물가","지속가능한 성장","기업과 산업","재벌","TMI","미디어와 저널리즘","슬로우팩트북은…"
]

def clean(values):
    return [None if v is None else round(float(v), 4) for v in values]

def load_items(data_dir):
    items = []
    seen = set()  # drop exact-duplicate charts (same title + data), even non-adjacent
    for f in sorted(glob.glob(os.path.join(data_dir, "*.json"))):
        doc = json.load(open(f, encoding="utf-8"))
        fallback = doc.get("category") or os.path.splitext(os.path.basename(f))[0]
        for it in doc.get("items", []):
            cat = it.get("category") or fallback
            if not it.get("vizType"):
                continue
            labels = it.get("labels") or []
            if len(labels) < 2:
                continue
            series = [clean(s) for s in (it.get("series") or []) if any(v is not None for v in s)]
            if not series:
                continue
            names = it.get("seriesNames") or []
            names = (names + [None] * len(series))[:len(series)]
            title = it["title"].strip().rstrip(".")
            sig = (title, it["vizType"], len(labels), repr(series))
            if sig in seen:
                continue
            seen.add(sig)
            items.append({
                "category": cat, "title": title,
                "source": it.get("source", ""), "sourceUrl": it.get("sourceUrl", ""),
                "vizType": it["vizType"], "labels": labels,
                "seriesNames": names, "series": series, "slide": it.get("slide"),
            })
    return items

def assign_ids(items, idpath):
    """Assign each chart a stable id (c0001, ...), persisted in ids.json and
    keyed on category+title so ids survive data fixes. Only renaming a chart
    (or category) changes its id — and thus its embed URL."""
    m = json.load(open(idpath, encoding="utf-8")) if os.path.exists(idpath) else {}
    nums = [int(v[1:]) for v in m.values() if v[1:].isdigit()]
    cnt = max(nums) if nums else 0
    used = {}
    for it in items:
        base = it["category"] + "" + it["title"]
        key, k = base, 2
        while key in used:                      # same title twice in one build
            key = base + "" + str(k); k += 1
        used[key] = 1
        if key not in m:
            cnt += 1
            m[key] = f"c{cnt:04d}"
        it["id"] = m[key]
    json.dump(m, open(idpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def build(data_dir, outp):
    items = load_items(data_dir)
    assign_ids(items, os.path.join(data_dir, "ids.json"))
    # category nav follows the deck's own section order (first appearance)
    cats = []
    for it in items:
        if it["category"] and it["category"] not in cats:
            cats.append(it["category"])
    if not cats:
        cats = CATEGORIES
    site_dir = os.path.dirname(outp) or "."
    os.makedirs(site_dir, exist_ok=True)
    html = TEMPLATE.replace("__CORE__", CORE_JS) \
                   .replace("__DATA__", json.dumps(items, ensure_ascii=False)) \
                   .replace("__CATS__", json.dumps(cats, ensure_ascii=False))
    open(outp, "w", encoding="utf-8").write(html)
    # embeddable single-chart player + one small JSON per chart
    open(os.path.join(site_dir, "embed.html"), "w", encoding="utf-8").write(
        EMBED_TEMPLATE.replace("__CORE__", CORE_JS))
    embdir = os.path.join(site_dir, "embed")
    os.makedirs(embdir, exist_ok=True)
    for it in items:
        json.dump(it, open(os.path.join(embdir, it["id"] + ".json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
    print(f"items={len(items)} -> {outp}  (+{len(items)} embed pages)")
    return items

TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>슬로우팩트북</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--blue:#2f5e8e;--red:#c0322f;--gray:#b3b3b3;--orange:#f5a623;--ink:#1a1a1a;--line:#e6e6e6;}
*{box-sizing:border-box;} body{margin:0;font-family:"Pretendard","Apple SD Gothic Neo","Malgun Gothic",-apple-system,sans-serif;color:var(--ink);background:#fafafa;}
header{padding:22px 28px;border-bottom:1px solid var(--line);background:#fff;display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;}
header h1{font-size:24px;margin:0;font-weight:800;letter-spacing:-.5px;}
header .sub{color:#888;font-size:13px;}
.layout{display:flex;min-height:calc(100vh - 67px);}
aside{width:240px;flex-shrink:0;border-right:1px solid var(--line);background:#fff;padding:16px 0;overflow-y:auto;position:sticky;top:0;height:calc(100vh - 67px);}
aside .cat{padding:9px 22px;font-size:14px;cursor:pointer;color:#444;border-left:3px solid transparent;}
aside .cat:hover{background:#f2f5f9;}
aside .cat.active{border-left-color:var(--blue);color:var(--blue);font-weight:700;background:#f2f5f9;}
aside .cat .cnt{color:#bbb;font-size:12px;float:right;} aside .cat.empty{color:#c8c8c8;}
main{flex:1;padding:24px 28px;}
.toolbar{display:flex;gap:12px;align-items:center;margin-bottom:20px;flex-wrap:wrap;}
#search{flex:1;min-width:220px;padding:10px 14px;border:1px solid #ddd;border-radius:8px;font-size:14px;outline:none;}
#search:focus{border-color:var(--blue);} .count{color:#999;font-size:13px;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(440px,1fr));gap:20px;}
.card{position:relative;background:#fff;border:1px solid var(--line);border-radius:12px;padding:20px 22px 18px;box-shadow:0 1px 3px rgba(0,0,0,.03);}
.embed-btn{position:absolute;top:16px;right:16px;font-size:11px;color:#999;background:#f4f4f4;border:1px solid #e4e4e4;border-radius:6px;padding:3px 9px;cursor:pointer;}
.embed-btn:hover{color:var(--blue);border-color:var(--blue);}
#toast{position:fixed;bottom:26px;left:50%;transform:translateX(-50%);background:#222;color:#fff;padding:9px 18px;border-radius:8px;font-size:13px;opacity:0;pointer-events:none;transition:opacity .2s;z-index:50;}
#toast.show{opacity:.95;}
.card h2{font-size:20px;margin:0 0 2px;font-weight:800;letter-spacing:-.4px;}
.card .meta{font-size:12px;color:#999;margin-bottom:14px;}
.card .tag{display:inline-block;font-size:11px;color:var(--blue);background:#eaf1f9;padding:2px 8px;border-radius:20px;margin-bottom:10px;}
.chartbox{position:relative;width:100%;aspect-ratio:16/9;}
.legendbar{display:flex;flex-wrap:wrap;justify-content:flex-end;align-items:center;gap:3px 12px;height:22px;overflow:hidden;margin:2px 0 6px;}
.legendbar .lg{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:#555;white-space:nowrap;}
.legendbar .lg i{width:11px;height:11px;border-radius:2px;flex:0 0 auto;}
.empty-state{color:#aaa;padding:60px;text-align:center;font-size:15px;}
footer{padding:18px 28px;color:#aaa;font-size:12px;border-top:1px solid var(--line);background:#fff;}
</style></head><body>
<header><h1>슬로우팩트북<span style="color:var(--blue)">.</span></h1>
<span class="sub">데이터 인포그래픽 · 검색 가능한 인터랙티브 아카이브</span></header>
<div class="layout"><aside id="sidebar"></aside>
<main><div class="toolbar"><input id="search" type="text" placeholder="제목·출처로 검색"><span class="count" id="count"></span></div>
<div class="grid" id="grid"></div></main></div>
<footer id="foot"></footer>
<script>
const ITEMS = __DATA__;
const CATEGORIES = __CATS__;
__CORE__
let activeCat=null,query="",charts=[];
const grid=document.getElementById("grid"),sidebar=document.getElementById("sidebar"),
      countEl=document.getElementById("count"),searchEl=document.getElementById("search");
function filtered(){return ITEMS.filter(it=>(!activeCat||it.category===activeCat)&&(!query||(it.title+it.category+it.source).toLowerCase().includes(query.toLowerCase())));}
function renderSidebar(){
  sidebar.innerHTML="";
  const all=document.createElement("div");all.className="cat"+(activeCat===null?" active":"");
  all.innerHTML=`전체 <span class="cnt">${ITEMS.length}</span>`;all.onclick=()=>{activeCat=null;render();};sidebar.appendChild(all);
  CATEGORIES.forEach(c=>{const n=ITEMS.filter(it=>it.category===c).length;const el=document.createElement("div");
    el.className="cat"+(activeCat===c?" active":"")+(n===0?" empty":"");
    el.innerHTML=`${dot(c)} <span class="cnt">${n||""}</span>`;el.onclick=()=>{activeCat=c;render();};sidebar.appendChild(el);});
}
let observer=null;
function render(){
  charts.forEach(c=>c.destroy());charts=[];
  if(observer)observer.disconnect();
  renderSidebar();
  const items=filtered();countEl.textContent=`${items.length}개 항목`;grid.innerHTML="";
  if(!items.length){grid.innerHTML='<div class="empty-state">해당 조건의 항목이 없습니다.</div>';return;}
  // lazy render: only build a chart when its card scrolls near the viewport
  observer=new IntersectionObserver((entries)=>{
    entries.forEach(e=>{
      if(!e.isIntersecting)return;
      const cv=e.target.querySelector("canvas");
      if(cv && !cv.dataset.done){cv.dataset.done="1";
        try{charts.push(buildChart(cv,items[+cv.dataset.idx]));}catch(err){console.error(err);}}
      observer.unobserve(e.target);
    });
  },{rootMargin:"300px"});
  items.forEach((it,i)=>{
    const card=document.createElement("div");card.className="card";
    const meta=[it.source,it.slide].filter(Boolean).join(" · ");
    card.innerHTML=`<button class="embed-btn" onclick="copyEmbed('${it.id}')">임베드</button><div class="tag">${dot(it.category)}</div><h2>${dot(it.title)}</h2><div class="meta">${meta}</div><div class="legendbar">${legendHTML(it)}</div><div class="chartbox"><canvas data-idx="${i}"></canvas></div>`;
    grid.appendChild(card);observer.observe(card);
  });
}
function toast(m){let t=document.getElementById("toast");if(!t){t=document.createElement("div");t.id="toast";document.body.appendChild(t);}t.textContent=m;t.className="show";clearTimeout(t._t);t._t=setTimeout(()=>t.className="",1800);}
function copyEmbed(id){
  const url=new URL("embed.html?id="+id, location.href).href;
  const code=`<iframe src="${url}" style="border:0;width:100%;max-width:680px;aspect-ratio:16/10" loading="lazy"></iframe>`;
  (navigator.clipboard?navigator.clipboard.writeText(code):Promise.reject())
    .then(()=>toast("임베드 코드가 복사되었습니다"))
    .catch(()=>{window.prompt("임베드 코드:",code);});
}
searchEl.addEventListener("input",e=>{query=e.target.value;render();});
document.getElementById("foot").textContent=`총 ${ITEMS.length}개 인포그래픽 · ${CATEGORIES.length}개 카테고리`;
render();
</script></body></html>"""

# ---- shared chart-rendering core, injected into both the site and embed pages ----
CORE_JS = r"""
const PALETTE = ["#2f5e8e","#c0322f","#f5a623","#1f8fd6","#6e6e6e","#7aa86f","#9a6fb0"];
function hexA(h,a){const n=parseInt(h.slice(1),16);return `rgba(${(n>>16)&255},${(n>>8)&255},${n&255},${a})`;}
function dot(s){s=String(s==null?"":s).trim();return (s===""||s.endsWith(".")||s.endsWith("…"))?s:s+".";}
function legendHTML(it){
  let entries=[];
  if(it.vizType==="pie"){entries=it.labels.map((l,i)=>[l,PALETTE[i%PALETTE.length]]);}
  else if(it.series.length>1){entries=it.seriesNames.map((n,i)=>[n||("계열 "+(i+1)),PALETTE[i%PALETTE.length]]);}
  return entries.map(([l,c])=>`<span class="lg"><i style="background:${c}"></i>${dot(l)}</span>`).join("");
}
function sparseTick(it){return function(val,index){const L=it.labels;
  const cur=(L[index]==null?"":String(L[index]));
  const prev=index>0?(L[index-1]==null?"":String(L[index-1])):null;
  return (cur!==prev)?cur:"";};}
function buildChart(canvas,it){
  const t=it.vizType,labels=it.labels.map(x=>x==null?"":String(x));
  const ds=it.series.map((vals,i)=>({label:it.seriesNames[i]||("계열 "+(i+1)),data:vals,backgroundColor:PALETTE[i%PALETTE.length],borderColor:PALETTE[i%PALETTE.length]}));
  const unit=(it.source.match(/단위:\s*([^,.]+)/)||[])[1]||"";
  const tip={callbacks:{label:c=>(ds.length>1?`${c.dataset.label}: `:"")+`${c.formattedValue} ${unit}`.trim()}};
  const interaction={mode:"index",intersect:false};
  const multi=ds.length>1;
  if(t==="line"||t==="area"||t==="two_axis"){
    const isArea=(t==="area");
    ds.forEach((d,i)=>{const col=PALETTE[i%PALETTE.length];
      d.borderColor=col;d.borderWidth=isArea?1.5:2;d.pointRadius=0;d.pointHoverRadius=4;d.tension=.25;
      d.backgroundColor=isArea?hexA(col,0.55):col;
      d.fill=isArea?(i===0?"origin":"-1"):false;});
    const stackY=isArea&&multi;
    return new Chart(canvas,{type:"line",data:{labels,datasets:ds},
      options:{responsive:true,maintainAspectRatio:false,interaction,plugins:{legend:{display:false},tooltip:tip},
        scales:{x:{grid:{display:false},ticks:{autoSkip:true,autoSkipPadding:6,maxRotation:0,callback:sparseTick(it),font:{size:10}}},y:{stacked:stackY,ticks:{font:{size:10}}}}}});
  }
  if(t==="bar"){ds.forEach(d=>d.borderWidth=0);
    return new Chart(canvas,{type:"bar",data:{labels,datasets:ds},
      options:{indexAxis:"y",responsive:true,maintainAspectRatio:false,interaction:{mode:"nearest",intersect:true},plugins:{legend:{display:false},tooltip:tip},
        scales:{x:{ticks:{font:{size:10}}},y:{grid:{display:false},ticks:{font:{size:9},autoSkip:false}}}}});
  }
  if(t==="pie"){
    const pieTip={callbacks:{label:c=>`${c.label}: ${c.formattedValue} ${unit}`.trim()}};
    return new Chart(canvas,{type:"doughnut",data:{labels,datasets:[{data:it.series[0],backgroundColor:labels.map((_,i)=>PALETTE[i%PALETTE.length]),borderColor:"#fff",borderWidth:1}]},
      options:{responsive:true,maintainAspectRatio:false,cutout:"60%",plugins:{legend:{display:false},tooltip:pieTip}}});
  }
  const stacked=(t==="stacked_bar");ds.forEach(d=>d.borderWidth=0);
  return new Chart(canvas,{type:"bar",data:{labels,datasets:ds},
    options:{responsive:true,maintainAspectRatio:false,interaction,plugins:{legend:{display:false},tooltip:tip},
      scales:{x:{stacked,grid:{display:false},ticks:{autoSkip:true,autoSkipPadding:6,maxRotation:0,callback:sparseTick(it),font:{size:9}}},y:{stacked,ticks:{font:{size:10}}}}}});
}
"""

EMBED_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>슬로우팩트북 차트</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
html,body{margin:0;height:100%;background:transparent;
  font-family:"Pretendard","Apple SD Gothic Neo","Malgun Gothic",-apple-system,sans-serif;color:#1a1a1a;}
#wrap{display:flex;flex-direction:column;height:100%;padding:12px 14px;box-sizing:border-box;}
#title{font-size:17px;font-weight:800;margin:0 0 1px;letter-spacing:-.3px;}
#meta{font-size:11px;color:#999;margin-bottom:6px;}
.legendbar{display:flex;flex-wrap:wrap;justify-content:flex-end;align-items:center;gap:3px 12px;height:22px;overflow:hidden;margin:0 0 4px;}
.legendbar .lg{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:#555;white-space:nowrap;}
.legendbar .lg i{width:11px;height:11px;border-radius:2px;flex:0 0 auto;}
.chartbox{position:relative;flex:1;min-height:0;}
#credit{font-size:10px;color:#bbb;text-align:right;margin-top:4px;}
#credit a{color:#bbb;text-decoration:none;}
</style></head><body>
<div id="wrap">
  <h2 id="title"></h2><div id="meta"></div>
  <div class="legendbar" id="legend"></div>
  <div class="chartbox"><canvas id="cv"></canvas></div>
  <div id="credit">슬로우팩트북</div>
</div>
<script>
__CORE__
const id=new URLSearchParams(location.search).get("id");
fetch("embed/"+id+".json").then(r=>r.json()).then(it=>{
  document.getElementById("title").textContent=dot(it.title);
  document.getElementById("meta").textContent=it.source||"";
  document.getElementById("legend").innerHTML=legendHTML(it);
  buildChart(document.getElementById("cv"),it);
  document.title=it.title+" — 슬로우팩트북";
}).catch(()=>{document.getElementById("title").textContent="차트를 불러올 수 없습니다.";});
</script></body></html>"""

if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
