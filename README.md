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

## 알려진 보강 포인트

- 빌드 단계가 비연속적으로 흩어진 경우 `dedup_builds()`가 일부를 놓칠 수 있음 → 필요 시 제목+데이터 해시 기준 전역 중복 제거로 강화.
- 도넛이 .key 경로에서 실패하면 해당 슬라이드만 .pptx로 보강하거나 이미지+비전 처리.
