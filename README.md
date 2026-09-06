# 슬로우팩트북 (Slow Factbook)

Keynote/PowerPoint로 만든 데이터 인포그래픽(약 2,000페이지)을 **검색 가능한 인터랙티브 웹사이트**로 변환하는 파이프라인.

```
source/*.pptx (또는 *.key)  ──►  data/*.json  ──►  site/index.html
        원본 덱                  구조화 데이터        정적 사이트
```

## 빠른 시작

```bash
pip install -r requirements.txt
# 원본 덱을 source/ 에 넣는다 (카테고리별 분할 권장: 02_노동.pptx 등)
python3 scripts/build.py
# 결과: site/index.html  (브라우저로 열기)
```

## 포맷: PowerPoint(.pptx) 권장

세 가지 추출 경로를 비교한 결과 **.pptx 가 가장 우수**하다.

| 경로 | 차트 데이터 | 원형(도넛) | 풀 데이터 | 비고 |
|---|---|---|---|---|
| **PPTX** (`python-pptx`) | 정확 | ✅ 복구 | ✅ | 빌드 애니메이션이 슬라이드로 복제됨 → `dedup_builds()`가 정리 |
| .key (`keynote-parser`) | 정확 | ❌ 역직렬화 실패 | ✅ | 도넛만 별도 보강 필요 |
| Keynote "HTML 출판" | ❌ 이미지로 굽힘 | — | ❌ | 수치 없음, 페이지마다 폴더 난립. 비추천 |

Keynote에서 `파일 > 내보내기 > PowerPoint`로 저장해 `source/`에 넣으면 된다.
`.key`를 직접 쓰려면 같은 파일명으로 넣으면 `build.py`가 자동으로 `keynote-parser`를 쓴다.

## 파일 구성

- `scripts/extract_pptx.py` — .pptx → JSON (차트 타입·시리즈·라벨·수치 추출, 빌드 중복 제거)
- `scripts/extract_keynote.py` — .key → JSON (대안 경로)
- `scripts/generate_site.py` — `data/*.json` → `site/index.html` (타입별 차트 렌더러 + 검색·카테고리 필터)
- `scripts/build.py` — 전체 오케스트레이터. `data/_report.json`에 보강 필요 슬라이드 기록
- `categories.json` — 원본 파일명 → 카테고리 매핑 (21개 대분류)

## 명명 규칙

```
source/02_노동.pptx        # "NN_" 접두사는 표시에서 제거, 카테고리는 categories.json 참조
```

## 업데이트 방식 (2,000페이지)

1. **카테고리별로 분할**해 관리한다 (단일 거대 파일 금지: 편집 무겁고 오류 전파 위험).
2. Keynote에서 수정 → 해당 카테고리만 .pptx 재내보내기 → `source/`에 덮어쓰기.
3. `python3 scripts/build.py` 실행.
4. `git diff data/`로 **바뀐 수치를 리뷰**(예: `5.5 → 5.7`). 텍스트 JSON이라 변경 이력이 그대로 남는다.
5. 커밋 → push → GitHub Actions가 자동으로 사이트 빌드·배포(GitHub Pages).

> 원칙: **.key/.pptx(바이너리)가 아니라 `data/`의 JSON을 버전 관리**한다. 그래야 데이터 변경 이력이 diff로 남는다. 원본 덱을 깃에 넣고 싶으면 `.gitattributes`의 Git LFS 설정을 사용.

## 배포

`.github/workflows/build.yml`이 `main` push마다 빌드 후 GitHub Pages로 배포한다.
저장소 Settings → Pages → Source를 "GitHub Actions"로 설정하면 끝.

## 차트 임베드 (외부 사이트에 삽입)

각 차트는 고유 URL을 가진다.

```
https://<사용자>.github.io/slowfactbook/embed.html?id=c0001
```

사이트의 각 카드 오른쪽 위 **"임베드"** 버튼을 누르면 iframe 코드가 클립보드에 복사된다. 블로그·기사·노션 등에 붙이면 그 차트만 그려진다.

```html
<iframe src="https://<사용자>.github.io/slowfactbook/embed.html?id=c0001"
        style="border:0;width:100%;max-width:680px;aspect-ratio:16/10" loading="lazy"></iframe>
```

- 차트 id는 `data/ids.json`에 **영구 저장**되며 `카테고리+제목` 기준으로 부여된다. 따라서 **숫자를 고쳐도 id(=임베드 URL)는 그대로** 유지된다. 제목이나 카테고리를 바꿀 때만 id가 바뀐다.
- 빌드 시 `site/embed.html`(플레이어 1개)와 `site/embed/<id>.json`(차트당 데이터 1개)이 생성된다.

## 수정·업데이트 반영

최신 데이터가 나오거나 숫자를 고칠 때:

1. Keynote(또는 .pptx)에서 해당 차트의 데이터를 수정한다.
2. 그 카테고리 .pptx만 다시 내보내 `source/`에 덮어쓴다.
3. `python3 scripts/build.py` 실행.
4. `git diff data/` 로 **무엇이 바뀌었는지 숫자 단위로 확인**한다 (예: `5.5 → 5.7`).
5. `git commit` & `git push` → GitHub Actions가 사이트와 모든 임베드를 자동 재배포한다.

> 임베드 URL이 안정적이므로, **한 번 고쳐 push하면 그 차트를 삽입한 모든 외부 페이지가 자동으로 갱신**된다. 새 항목을 추가하면 새 id가 발급되고, 기존 항목 id는 보존된다.

## 팩트북이 정본이다 — 갱신·추가·키노트 동기화

원본 덱을 매번 다시 내보내 추출하는 경로(`source/` → `build.py`)는 남겨 두되, 일상 갱신은 팩트북 쪽에서 한다.
키노트는 팩트북에서 바뀐 것을 가져다 맞추는 쪽(팩트북 → 키노트)이다. 세 가지 경로가 있다.

| 경로 | 스크립트 | 언제 |
|---|---|---|
| 자동 갱신 | `refresh_charts.py` (KOSIS 확정 매칭) · `build_api_charts.py` (API 트랙) · `kb_update.py` (KB 엑셀) | 매일 05:00 빌드가 KOSIS 매칭분을 이어붙이고 `data/`에 커밋한다 |
| 슬라이드 갱신 | `set_data.py` | "슬라이드 N 을 이 데이터로" — CSV·TSV·엑셀·붙여넣은 표 |
| 슬라이드 추가 | `add_chart.py` | "이 데이터(URL)로 차트 하나" — `data/manual.json` 에 들어가고 새 id 를 받는다 |

```bash
# 갱신: 겹치는 구간을 대조해 어긋나면 멈춘다. 뒤에만 이어붙인다. 기본은 미리보기.
python3 scripts/set_data.py 964 새데이터.xlsx --sheet "아파트 매매평균가격" --url https://... --source "KB부동산 데이터허브" --unit "억 원"
pbpaste | python3 scripts/set_data.py 122 -             # 붙여넣은 표
python3 scripts/set_data.py 122 new.csv --revise --apply # 원자료 수정치까지 덮어쓰기
python3 scripts/set_data.py 55  new.csv --replace --apply # 비시계열·계열 구성 변경은 통째로

# 추가
python3 scripts/add_chart.py 표.csv --title "…" --category "노동" --source "…" --unit "%" --url https://... --apply

# KOSIS 표 URL 을 줬다면 한 번 등록해 두면 그 뒤로는 매일 자동으로 잇는다
KOSIS_API_KEY=… python3 scripts/register_auto.py 122 --url "https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=DT_118N_MON051" --apply

# 키노트에 옮길 것 — 바뀐 차트 목록 + 붙여넣을 TSV(latest/keynote/)
python3 scripts/keynote_sync.py
python3 scripts/keynote_sync.py --done c0718,c2031   # 옮긴 뒤 표시

./update.sh   # 빌드 → 커밋 → push
```

- 표는 방향(시점이 행인지 열인지)·구분자·단위 배수(만원↔억 원 등 10의 거듭제곱)를 스스로 맞춘다. 안 맞으면 `--transpose` `--scale` `--by-order`.
- 모든 변경은 `data/changelog.json` 에 남고(자동 갱신 포함), `keynote_sync.py` 가 그걸 읽어 아직 키노트에 안 옮긴 것만 보여준다.
- 차트 id(=임베드 주소)는 갱신해도 그대로다. 제목을 바꿀 때만 바뀐다.

## 알려진 보강 포인트

- 빌드 단계가 비연속적으로 흩어진 경우 `dedup_builds()`가 일부를 놓칠 수 있음 → 필요 시 제목+데이터 해시 기준 전역 중복 제거로 강화.
- 도넛이 .key 경로에서 실패하면 해당 슬라이드만 .pptx로 보강하거나 이미지+비전 처리.
