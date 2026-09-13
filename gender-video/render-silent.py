from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import json,math,subprocess,functools,re,wave,sys
P=Path(__file__).resolve().parent
S=json.loads((P/'scenes.json').read_text());
for scene in S:
 scene['narration']=scene['narration'].replace('?', '.').replace('!', '.')
F={x['slide']:x for x in json.loads((P.parent/'data/full.json').read_text())['items']}
FF='/opt/homebrew/bin/ffmpeg'; FP='/opt/homebrew/bin/ffprobe'; SCALE=1.5; W,H=1920,1080; FPS=30
BG='#000000'; FG='#fdad00'; MUT='#fdad00'; TEAL='#fdad00'; BLUE='#916300'; GRID='#252015'; ORANGE='#fdad00'
@functools.lru_cache(None)
def font(size,bold=False): return ImageFont.truetype('/System/Library/Fonts/AppleSDGothicNeo.ttc',round(size*SCALE),index=6 if bold else 0)
def xy(v):return round(v*SCALE)
def text(d,x,y,s,size=24,color=FG,bold=False,anchor=None,punctuate=True):
 s=str(s).replace('−','-')
 if punctuate and any('가'<=c<='힣' for c in s) and not s.endswith('.'):
  s=s.rstrip('?!,')+'.'
 d.text((xy(x),xy(y)),s,font=font(size,bold),fill=FG,anchor=anchor)
def rect(d,box,color,r=0):
 b=tuple(xy(x) for x in box)
 if r:d.rounded_rectangle(b,radius=xy(r),fill=color)
 else:d.rectangle(b,fill=color)
def line(d,pts,color=GRID,width=2):d.line([(xy(x),xy(y)) for x,y in pts],fill=color,width=xy(width))
def ease(v):v=max(0,min(1,v));return 1-(1-v)**3
def wrap(s,n=43):
 words=s.split();rows=[];row=''
 for w in words:
  if len(row)+len(w)>n:rows.append(row);row=w
  else:row+=(' ' if row else '')+w
 if row:rows.append(row)
 return rows

def make_audio():
 start=0; pcm=[]
 for i,s in enumerate(S):
  src=P/'audio'/f'{i:02}.aiff'; dur=float(subprocess.check_output([FP,'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(src)]))
  s['speech_duration']=dur;s['duration']=math.ceil((dur+1.3)*FPS)/FPS;s['start']=start;start+=s['duration']
  data=subprocess.check_output([FF,'-v','error','-i',str(src),'-f','s16le','-ar','48000','-ac','1','pipe:1'])
  lead=b'\0'*int(.4*48000)*2;tail=b'\0'*(round(s['duration']*48000)*2-len(data)-len(lead));pcm.extend([lead,data,tail])
 with wave.open(str(P/'narration.wav'),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(48000);w.writeframes(b''.join(pcm))
 (P/'timeline.json').write_text(json.dumps(S,ensure_ascii=False,indent=2))
 print('Duration',round(start,2),flush=True)

def captions(s):
 chunks=[x.rstrip('?!')+'.' if not x.endswith('.') else x for x in re.split(r'(?<=[.!?])\s+',s['narration'])]
 weight=sum(len(x) for x in chunks);time=.4;out=[]
 for chunk in chunks:
  dur=s['speech_duration']*len(chunk)/weight;out.append((time,time+dur,chunk));time+=dur
 return out

def base(i):
 im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im);s=S[i]
 text(d,64,31,'slownews.',23,FG,True);text(d,1216,36,'DATA EXPLAINED   /   격차의 구조',14,MUT,False,'ra')
 for k in range(9):rect(d,(64+k*129,77,64+k*129+112,80),TEAL if k<i else GRID)
 text(d,64,110,s['chapter'],18,TEAL,True)
 if s['id']!='ending':text(d,64,146,s['title'],46,FG,True);text(d,65,211,s['subtitle'],21,MUT)
 line(d,[(64,635),(1216,635)],GRID,1)
 text(d,64,652,s['source'],13,MUT);text(d,64,678,s['note'],13,MUT)
 text(d,1216,678,f'{i+1:02} / 09',13,MUT,False,'ra')
 return im

def bar(d,label,value,maxv,y,color,p,unit='',x=180,width=760):
 text(d,64,y+9,label,24,color,True);rect(d,(x,y,x+width,y+46),GRID,4)
 rect(d,(x,y,x+max(1,width*value/maxv*p),y+46),color,4)
 text(d,x+width+25,y+6,f'{value:,.1f}'.replace('.0','')+unit,30,color,True)

def linechart(d,labels,series,names,cols,p,x=105,y=285,w=1000,h=240,maxv=100,minv=0,label_indices=None):
 for j in range(5):
  yy=y+h-j*h/4;line(d,[(x,yy),(x+w,yy)],GRID,1);text(d,x-15,yy-9,f'{minv+j*(maxv-minv)/4:g}',15,MUT,False,'ra')
 n=len(labels);idxs=label_indices or list(range(n))
 for j in idxs:text(d,x+j*w/(n-1),y+h+12,labels[j],16,MUT,False,'ma')
 for s,k in enumerate(series):
  full=p*(n-1);pts=[]
  for j,v in enumerate(k):
   if j>full:break
   pts.append((x+j*w/(n-1),y+h-(v-minv)/(maxv-minv)*h))
  j=int(full)
  if j<n-1:
   v=k[j]+(k[j+1]-k[j])*(full-j);pts.append((x+full*w/(n-1),y+h-(v-minv)/(maxv-minv)*h))
  if len(pts)>1:line(d,pts,cols[s],4)
  if pts:
   xx,yy=pts[-1];d.ellipse((xy(xx-5),xy(yy-5),xy(xx+5),xy(yy+5)),fill=cols[s])
  text(d,100+s*160,250,names[s],17,cols[s],True)

def frame(i,t):
 s=S[i];im=bases[i].copy();d=ImageDraw.Draw(im);p=ease((t-.4)/2.5);id=s['id']
 rect(d,(64+i*129,77,64+i*129+112*min(1,t/s['duration']),80),TEAL)
 if id=='opening':
  text(d,64,282,'남성',24,BLUE,True);text(d,64,309,'100',142,BLUE,True)
  text(d,515,345,':',76,MUT,True);text(d,660,282,'여성',24,TEAL,True);text(d,660,309,f'{70.9*p:.1f}',142,TEAL,True)
  rect(d,(64,495,564,514),BLUE,3);rect(d,(660,495,660+500*.709*p,514),TEAL,3)
  text(d,64,540,'남성 시간당 임금을 100으로 환산',20,MUT)
 elif id=='definitions':
  for j,(lab,val,sub) in enumerate([('OECD 중위임금',29.3,'2023 · 전일제'),('시간당 평균 임금',29.1,'2024 · 국내 조사'),('월평균 소득',34.6,'2024 · 일자리행정통계')]):
   x=64+j*395;v=ease((t-.7-j*.7)/1.4);rect(d,(x,278,x+365,526),GRID,7);text(d,x+24,301,lab,23,FG,True);text(d,x+24,353,f'{val*v:.1f}',74,TEAL,True);text(d,x+286,395,'%',29,TEAL);text(d,x+24,476,sub,18,MUT)
  text(d,64,549,'다른 조사 · 다른 대상 · 다른 계산법',23,BLUE,True)
 elif id=='hours':
  late=ease((t-s['duration']*.36)/1.8)
  text(d,64,264,'월 노동시간',22,FG,True)
  bar(d,'남성',153.8,180,305,BLUE,p,'시간',x=160,width=730);bar(d,'여성',137.4,180,368,TEAL,p,'시간',x=160,width=730)
  if late>0:
   text(d,64,454,'한 시간의 임금',22,FG,True);text(d,300,449,f'{28734*late:,.0f}원',38,BLUE,True);text(d,670,449,f'{20363*late:,.0f}원',38,TEAL,True);text(d,64,527,'시간을 나누어도 남는 격차',26,FG,True)
 elif id=='employment':
  vals=[499.6,354.1,237.1,148.9];labs=['정규직 남성','정규직 여성','비정규직 남성','비정규직 여성']
  for j,(v,lab) in enumerate(zip(vals,labs)):
   x=175+j*275;h=240*v/500*ease((t-.5-j*.25)/2);rect(d,(x,530-h,x+150,530),BLUE if j%2==0 else TEAL,5);text(d,x+75,535,lab,18,FG,False,'ma');text(d,x+75,530-h-38,f'{v:.1f}',30,BLUE if j%2==0 else TEAL,True,'ma')
  text(d,64,255,'단위: 만 원',16,MUT)
 elif id=='age':
  c=F['slide-225'];labels=['25–29','30–34','35–39','40–44','45–49','50–54','55–59'];vals=[a[2:9] for a in c['series']]
  linechart(d,labels,vals,['남성','여성'],[BLUE,TEAL],ease((t-.5)/5),maxv=100,minv=50)
  if t>6:
   line(d,[(624,325),(636,325),(636,438),(624,438)],FG,2);text(d,650,358,'23.4%p',29,FG,True);text(d,650,400,'40–44세',16,MUT)
 elif id=='birth':
  c=F['slide-202'];vals=c['series'][10];labels=['−360일' if j==0 else '출산일' if j==12 else '+480일' if j==28 else '+720일' if j==36 else '' for j in range(37)]
  linechart(d,labels,[vals],['어머니 취업비율'],[TEAL],ease((t-.5)/6),maxv=65,minv=45,label_indices=[0,12,28,36])
  for j,idx in enumerate([0,12,28]):
   if t>2+j*3:text(d,115+idx*1000/36,275+240-(vals[idx]-45)/20*240,f'{vals[idx]:.1f}%',24,FG,True)
 elif id=='factors':
  text(d,64,273,'관측 특성으로 설명',22,TEAL,True);text(d,1205,273,'미설명 부분',22,MUT,True,'ra')
  rect(d,(64,316,1216,405),GRID,5);rect(d,(64,316,64+1152*.531*p,405),TEAL,5)
  text(d,85,409,f'{53.1*p:.1f}%',32,FG,True);text(d,1150,323,f'{46.9*p:.1f}%',51,FG,True,'ra')
  text(d,64,455,'근속 18.6%   산업 17.1%   기타 관측 특성 17.4%',20,TEAL)
  if t>6:text(d,64,502,'미설명 부분 ≠ 차별의 크기',38,BLUE,True)
 elif id=='progress':
  c=F['slide-50'];m=c['series'][0]+[29411];f=c['series'][1]+[21164];gap=[(a-b)/a*100 for a,b in zip(m,f)];labels=c['labels']+['2025']
  linechart(d,labels,[gap],['남성 대비 격차 (%)'],[TEAL],ease((t-.4)/5),maxv=45,minv=0,label_indices=[0,4,9,14,19]);text(d,100,294,'39.4%',31,FG,True)
  if t>5:text(d,1085,315,'28.0%',47,TEAL,True)
 elif id=='ending':
  text(d,64,171,'얼마나 다른가에서,',61,FG,True);text(d,64,251,'왜 다른가로.',76,TEAL,True)
  for j,lab in enumerate(['임금','일자리','경력']):
   x=64+j*310;rect(d,(x,397,x+275,463),GRID,5);text(d,x+137,407,lab,31,FG,True,'ma')
  text(d,64,503,'격차의 구조 · 슬로우팩트북',25,FG,True);text(d,64,547,'slownews.kr/156679',22,MUT)
 # Recompose the chart area to leave a substantial illustration column.
 if id not in ['definitions','factors','ending']:
  plot=im.crop((0,xy(245),W,xy(578)))
  rect(d,(0,245,1280,580),BG)
  im.paste(plot.resize((xy(875),xy(333*875/1280)),Image.Resampling.LANCZOS),(0,xy(285)))
  subject={'opening':0,'hours':0,'employment':2,'age':2,'birth':1,'progress':2}[id]
  art,width,h=prepared_art(subject)
  offset=24*(1-ease(t/1.1))+3*math.sin(t*.7)
  im.paste(art,(xy(900+(330-width)/2+offset),xy(252+(315-h)/2)))
  d=ImageDraw.Draw(im)
 elif id=='ending':
  rect(d,(0,135,1280,578),BG)
  text(d,64,155,'얼마나 다른가에서.',49,FG,True)
  text(d,64,220,'왜 다른가로.',65,FG,True)
  art=END_ART
  im.paste(art,(xy(500),xy(80)));d=ImageDraw.Draw(im)
  text(d,64,365,'임금. 일자리. 경력.',27,FG,True)
  text(d,64,428,'격차의 구조 · 슬로우팩트북.',22,FG,True)
  text(d,64,472,'slownews.kr/156679',19,FG)
 fade=min(1,t/.25,(s['duration']-t)/.3)
 if fade<1:im=Image.blend(Image.new('RGB',(W,H),BG),im,max(0,fade))
 return im

ART=Image.open(P/'assets/work-care-career.png').convert('RGB')
ARTS=[ART.crop((0,165,545,865)),ART.crop((590,165,970,865)),ART.crop((995,165,1536,865))]

END_ART=ART.resize((xy(780),xy(520)),Image.Resampling.LANCZOS)
@functools.lru_cache(None)
def prepared_art(subject):
 art=ARTS[subject];width=min(330,300*art.width/art.height);h=width*art.height/art.width
 return art.resize((xy(width),xy(h)),Image.Resampling.LANCZOS),width,h

if __name__=='__main__':
 make_audio();bases=[base(i) for i in range(len(S))];caps=[captions(s) for s in S]
 def stamp(x):
  ms=round(x*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
 lines=[]
 for i,s in enumerate(S):
  for a,b,c in caps[i]:lines.append(f'{len(lines)+1}\n{stamp(s["start"]+a)} --> {stamp(s["start"]+b)}\n{c}\n')
 (P/'captions-v2.srt').write_text('\n'.join(lines))
 (P/'narration-v2.md').write_text('# 격차의 구조 — 내레이션\n\n'+ '\n\n'.join(f'## {s["chapter"]}\n\n{s["narration"]}\n\n출처: {s["source"]}' for s in S))
 thumbs=[]
 for i,s in enumerate(S):
  im=frame(i,min(s['duration']-.6,8));im.save(P/'frames'/f'{i:02}-silent.png');thumbs.append(im.resize((640,360)))
 sheet=Image.new('RGB',(1920,1080),BG)
 for i,im in enumerate(thumbs):sheet.paste(im,(i%3*640,i//3*360))
 sheet.save(P/'storyboard-silent.jpg',quality=92)
 if '--stills' in sys.argv:sys.exit()
 cmd=[FF,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(P/'gender-gap-silent.mp4')]
 with subprocess.Popen(cmd,stdin=subprocess.PIPE) as proc:
  for i,s in enumerate(S):
   print('Rendering',i,s['id'],s['duration'],flush=True)
   for k in range(round(s['duration']*FPS)):proc.stdin.write(frame(i,k/FPS).tobytes())
  proc.stdin.close();ret=proc.wait()
  if ret:raise RuntimeError(ret)
 print('Finished',flush=True)
