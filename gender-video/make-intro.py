from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import subprocess,re
P=Path(__file__).resolve().parent
W,H,FPS=1920,1080,30
FF='/opt/homebrew/bin/ffmpeg'
fontpath='/System/Library/Fonts/AppleSDGothicNeo.ttc'
fonts={s:ImageFont.truetype(fontpath,s,index=6) for s in [30,44,155,200]}
DURATION=6
cmd=[FF,'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(P/'title-intro.mp4')]
proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
for k in range(DURATION*FPS):
 t=k/FPS;im=Image.new('RGB',(W,H),'black');d=ImageDraw.Draw(im)
 d.text((100,70),'slownews.',font=fonts[44],fill='#fdad00')
 for j,(label,size,y) in enumerate([('한국 여성은 왜',155,240),('30%를 덜 받고',200,415),('일하나.',200,640)]):
  progress=max(0,min(1,(t-j*.45)/.7));ease=1-(1-progress)**3
  layer=Image.new('RGBA',(W,H));ld=ImageDraw.Draw(layer)
  ld.text((100,y+35*(1-ease)),label,font=fonts[size],fill=(253,173,0,round(255*ease)))
  im.paste(layer,(0,0),layer)
 if t>1.9:
  d=ImageDraw.Draw(im);d.text((106,962),'격차의 구조.  /  슬로우팩트북.',font=fonts[30],fill='#fdad00')
 if t>5.5:im=Image.blend(im,Image.new('RGB',(W,H)),(t-5.5)/.5)
 if k==100:im.save(P/'title-intro.png')
 proc.stdin.write(im.tobytes())
proc.stdin.close()
assert proc.wait()==0
subprocess.run([FF,'-v','error','-y','-i',str(P/'title-intro.mp4'),'-i',str(P/'gender-gap-silent.mp4'),'-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-an','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(P/'gender-gap-with-intro.mp4')],check=True)
s=(P/'captions-v2.srt').read_text()
def shift(m):
 h,mi,se,ms=map(int,m.groups());n=((h*60+mi)*60+se)*1000+ms+6000
 return f'{n//3600000:02}:{n//60000%60:02}:{n//1000%60:02},{n%1000:03}'
s=re.sub(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})',shift,s)
(P/'captions-with-intro.srt').write_text(s)
print('Intro and full video created; captions shifted by 6 seconds.')
