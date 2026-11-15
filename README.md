# 흉부 CT 검토실

본인 PC에서 조영증강 흉부 CT와 병원 판독소견서를 검토하는 로컬 웹앱. React 19 / TypeScript / Material UI 7 / FastAPI / SQLite.

## 현재 구현

사용자 선택 DICOM 등록, 검사·시리즈·직접 입력 소견서 버전 저장, 시리즈 geometry/픽셀 검증, Windows 네이티브 Orthanc/OHIF CT 열람·MPR·거리/HU 도구를 구현했다. 해부학·폐결절·흉수/심낭삼출 분할, 원본 격자 마스크·정량화, 실제 3D 표면, CT 마스크 뷰/3D/선택 후보 상세 연결, 실행 이력·취소를 제공한다. 소견 구조화·사용자 정정, 원본 기반 AI 후보 대조/확인, 검토·질문/이력, 한글 PDF·JSON 정리본, 문서 업로드/로컬 OCR, 백업/오프라인 복원을 제공한다. 독립 MONAI 탐지와 모델별 연결 검토도 제공한다. 이전 CT 비교는 수동 기준점/측정 검토의 부분 구현이고, 로컬 언어모델은 확인 원문 문구의 순서 정리만 제공한다. 등록 성공·빈 목록·빈 분할·후보 없음은 정상 판정을 의미하지 않는다. Docker는 사용하지 않는다.

## 처음 설치

PowerShell에서 프로젝트 폴더로 이동한 뒤 실행한다. Python 3.10, Node 24에서 확인했다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-lock.txt
npm ci
npm run build
powershell -ExecutionPolicy Bypass -File .\setup-imaging.ps1
```

동일한 설치 작업은 `powershell -ExecutionPolicy Bypass -File .\setup.ps1`로 실행할 수 있다. Python·Node는 먼저 설치되어 있어야 한다.

## 실행 및 종료

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

[로컬 화면](http://127.0.0.1:8000)을 브라우저로 연다. `start.cmd`를 더블클릭해도 실행할 수 있다. run_local이 API와 네이티브 영상 프로세스를 시작하고 Ctrl+C 시 자신이 시작한 프로세스를 종료한다. 시스템 서비스는 설치하지 않는다. `data/workspace.sqlite3`, `data/originals/`, `data/imaging/`에 저장하며 모두 Git 제외다. 원본 폴더는 변경하지 않는다. 백업 도구는 후속 작업이다. 서버는 한 프로세스만 실행한다.

## 사용 흐름 및 현재 입력 한계

1. **CT 폴더 선택** 또는 **파일 선택**으로 등록한다. 폴더 하위 파일을 브라우저가 수집해 로컬 서버로 순차 전송한다.
2. 등록/중복/제외/실패 수를 확인하고 검사를 선택한다. 파일당 32MB, 배치당 100,000개 한도다.
3. **병원 판독소견서 직접 옮겨 적기** 또는 **개인 메모** 출처를 선택하고 저장한다. 수정은 새 버전으로 추가된다. 사용자 입력은 인증된 병원 원문이 아니다.
4. 초기 등록은 비압축 Little Endian 단일 프레임 CT Image Storage의 필수 메타데이터를 확인한다. 비CT·로컬라이저·Enhanced/다중프레임·압축·공간정보 누락은 제외한다. 조영 태그만으로 CTPA를 판정하지 않는다.
5. 시리즈의 **영상 열기**에서 원본 해시·픽셀·방향·간격·겹침/불규칙 간격을 검증하고 OHIF를 표시한다. 비평행/기울어진 geometry는 초기 지원에서 제외한다. 등록 성공과 열람 적합성은 구분한다. 조영 CT의 모델 입력 적합성/진단 성능은 별도 평가다.
6. 취소 시 이미 등록한 원본은 유지한다. 브라우저가 닫힌 후 남은 running 작업은 화면에서 취소할 수 있고, 서버 재시작 시 interrupted로 복구된다. 자동 파일 재전송은 하지 않는다.

암호화·계정별 인증·백업/삭제·AI 모델 설치와 추론은 후속 범위다. 현재 모델 목록은 후보 레지스트리이며 실행 가능한 모델을 뜻하지 않는다.

## 영상 조작

중앙 **CT 열람 · 판독소견서 입력**에서 검사와 시리즈를 선택한 뒤 파란 **영상 열기** 버튼을 누른다. 왼쪽 등록된 검사를 클릭해도 선택된다. 검사/시리즈가 각각 한 개면 자동 선택한다. 이전 화면이 열려 있으면 브라우저 Ctrl+R로 새 화면을 불러온다.

OHIF 초기 도구 안내를 닫고 사용한다. 휠/오른쪽 스크롤바로 절편을 탐색한다. Zoom/Pan/Window Level 도구는 선택 후 드래그한다. 영상에 초점을 두고 단축키 1은 연조직 창(400/40), 2는 폐창(1500/-600)이다. Change layout → MPR로 축상/관상/시상면을 열고 Crosshairs로 위치를 연결한다. 3절편 미만에서는 MPR을 사용하지 않는다. Length 및 Probe는 뷰어 도구 메뉴에 있다. **원본 복셀의 HU·거리 확인**은 0부터 시작하는 X열/Y행/Z정렬절편 인덱스를 입력하며 원본 HU·LPS 좌표·거리를 표시한다. 패딩 픽셀은 HU에서 제외한다.

OHIF 공급자의 연구용 안내는 그대로 표시한다. 이 통합의 기술 검증을 임상 성능 보증으로 사용하지 않는다. 좁은 화면에서는 **뷰어를 별도 창으로 열기**를 권한다. 창 수치의 별도 숫자 입력 UI는 없으며 직접 창 조절은 드래그 방식이다.

영상 서비스를 별도로 실행하려면 `start-imaging.ps1`을 사용한다. 설치된 바이너리 버전/해시는 imaging-runtime-lock.json에 기록한다. 영상 서비스 설치 단계에서는 모델 가중치를 설치하지 않는다.

## AI 설치·사용

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-ai.ps1
```

현재 PC에는 설치·GPU 실행 검증을 완료했다. 새 PC에서는 NVIDIA 드라이버·CUDA 대응 GPU가 필요하다. Python 3.10의 별도 `runtime/ai-venv`에 고정 의존성을 설치하고 공식 가중치를 `runtime/models`에 받는다. CUDA PyTorch 등 수 GB 다운로드와 충분한 디스크 공간이 필요하다. Docker·별도 CUDA Toolkit 설치는 사용하지 않는다. `backend/ai-requirements-lock.txt`, `ai-weights-lock.json`에 패키지·가중치 식별을 고정한다. 모델 설치와 환자 영상 처리는 분리하며 추론에서는 외부 Python 네트워크 접속·DNS를 차단한다.

앱을 다시 실행하고 **영상 열기 → 중앙 CT 뷰어 아래 ‘분석 모델’ 선택 → 시리즈/한계 확인 → 실행** 순서로 사용한다. 해부학 분할·폐결절 후보·흉수/심낭삼출 중 선택한다. 이전 실행은 모델별 선택 목록에 남고 재실행은 새 버전으로 보존된다. 서로 다른 모델 요청도 GPU에서 순차 처리하며 실행 중 취소할 수 있다. 실제 단계만 표시하고 임의 진행률을 생성하지 않는다.

초기 지원: 공개 `total` 3 mm fast의 폐엽 5개·기관·심장·대동맥, `lung_nodules`의 결절 라벨, `pleural_pericard_effusion`의 흉수/심낭삼출 라벨. 폐 보조 라벨을 결절로 세지 않는다. 부피는 원본 격자 복셀 수 × 복셀 부피이며 경계 접촉 시 부분 부피를 표시한다. 결절은 26연결 성분별 후보이고 삼출은 종류별 합산 영역이다. 소견서는 모델 입력에 포함하지 않는다.

후보 버튼을 선택하면 **CT 마스크 뷰의 대표 절편·위치, 오른쪽 3D 표식, 후보 상세**가 연결된다. 3D 표면 클릭으로도 후보를 고를 수 있다. 선택 해제는 AI 결과의 채택/제외가 아니며 검토 판단 저장은 후속 작업이다. 마스크 뷰와 OHIF의 탐색·창 설정은 독립적이다. 3D는 현재 선택한 실행의 실제 분할만 표시하며 서로 다른 모델 결과를 자동 합성하지 않는다. 구조 체크·윤곽선·불투명도·회전/확대·초기화를 사용할 수 있다.

장경은 원본 절편별 **복셀 외곽의 최대 2D Feret 중 최댓값**으로 계산한다. 사선 촬영이면 원본 촬영 평면 기준이며 환자 축상 MPR/임상 RECIST 측정이 아니다. 삼출 장경·탐지 점수·악성 확률은 제공하지 않는다. 대표 이동 위치는 실제 마스크 복셀이고, 장경을 구한 절편은 별도로 표시한다.

기술 검증은 진료 적용 성능 입증이 아니다. 3개 이상 연속 절편, 단일 affine에 대한 위치 편차 0.01 mm 이하, 최대 1억 6천만 복셀을 지원한다. 초기 앱 간격 제한은 결절 각 축 ≤3 mm, 삼출 각 축 ≤5 mm이며 임상 적합성 기준으로 해석하지 않는다. 메모리 부족은 실패로 남기고 GPU를 사용하는 다른 앱을 닫은 후 새 실행을 시작한다. 중단 작업은 재시작 시 실패/중단으로 복구한다. 원본과 이전 결과는 보존한다. 3D 표면은 캐시하며 복잡한 구조의 표시 한도 초과는 오류로 알리고 CT 마스크는 유지한다.

개발 중에는 API와 화면을 각각 실행할 수 있다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --no-access-log
# 별도 터미널
npm run dev
```

개발 화면은 http://127.0.0.1:5173 이며 `/api`를 로컬 서버에 전달한다. 빌드 후 API 재시작 시 8000에서 최신 정적 화면을 제공한다. 외부 폰트·CDN·환자 데이터 전송 API를 사용하지 않는다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_app backend.test_intake backend.test_geometry backend.test_analysis backend.test_findings -v
npm run build
npx playwright test
```

브라우저 검증은 설치된 Microsoft Edge를 사용한다. 임시 DB의 8001 포트에서 동작하며 운영 DB와 분리된다. 전체 브라우저 테스트 전에 별도 터미널에서 `.venv/Scripts/python.exe -m backend.run_imaging --qa`를 실행한다(종료 Ctrl+C). 합성 2×2/128×128 DICOM만 생성하며 결과는 Git 제외 `data/browser-results/`에 기록한다.

API 테스트는 임시 DB의 가상 자료만 사용한다. 실제 환자 자료를 테스트나 Git에 넣지 않는다.

선택적 실제 AI 검증은 공식 저장소의 `tests/reference_files/example_ct_sm.nii.gz`를 `data/qa-week3/`에 받은 뒤 `.venv/Scripts/python.exe -m backend.qa_week3`로 해부학 실행을 만든다. 이어 `.venv/Scripts/python.exe -m backend.qa_week4`로 결절/삼출 모델을 실제 실행한다. 예제 SHA-256과 QA 경로를 확인하며 운영 DB는 읽지 않는다. `npx playwright test --config playwright.analysis.config.ts`로 실제 결과를 검증한다. 별도 `npx playwright test --config playwright.findings.config.ts`는 8003 임시 DB에 명시적 합성 결절 두 개를 만들어 선택 이동·늦은 응답·오류 복구를 검증한다. 이 양성 fixture는 모델 출력/성능으로 집계하지 않는다. 테스트용 네이티브 영상 서비스가 필요하다. 증거: docs/verification/week3.md, week4.md.

## 프로젝트 문서

- [요구사항분석서](REQUIREMENTS.md)
- [요구사항 추적표](REQUIREMENTS_TRACKER.md)
- [개발계획·WBS](DEVELOPMENT_PLAN.md)
- [오늘 목표·달성률](DAILY_PROGRESS.md)
- [Day 1 검증 기록](docs/verification/day1.md)
- [1주차 목표·달성률](WEEK1_PROGRESS.md)
- [기술 설계](docs/ARCHITECTURE.md)
- [1주차 검증 기록](docs/verification/week1.md)
- [2주차 목표·달성률](WEEK2_PROGRESS.md)
- [2주차 검증 기록](docs/verification/week2.md)
- [3주차 목표·달성률](WEEK3_PROGRESS.md)
- [3주차 검증 기록](docs/verification/week3.md)
- [4주차 목표·달성률](WEEK4_PROGRESS.md)
- [4주차 검증 기록](docs/verification/week4.md)

## 메뉴별 사용

왼쪽 메뉴에서 **검사 등록 → CT 영상 열람 → AI 분석 · 3D → 판독소견 · 구조화 → 소견 · AI 대조 → 검토 · 정리본** 순서로 필요한 화면을 선택한다. 시리즈 선택 후 ‘영상 열기’로 열람/분석할 입력을 확정한다. 문서/OCR, 독립 모델 비교, 이전 CT, 평가/지원 범위, 백업/데이터 관리는 별도 메뉴다. PC 메뉴는 고정되고 모바일에서는 상단 메뉴 버튼으로 왼쪽 서랍을 연다. 기능을 모두 한 페이지 아래로 나열하지 않는다. 메뉴 이동 시 검사·열린 시리즈·초안·선택 후보를 보존한다.

선택적 추가 런타임은 `setup-ocr.ps1`, `setup-monai.ps1`, `setup-llm.ps1`로 설치한다. 각각 공식 고정 파일/커밋·크기·SHA를 검사한다. MONAI는 AI 가상환경 설치 후 실행한다. 문장 모델은 CPU 전용이며 사용자 확인 원문 인용만 입력한다. 설치 중 다운로드와 영상/문서 로컬 처리는 별개다.

- [문서·백업/복원·삭제 안내](docs/LOCAL_DATA_MANAGEMENT.md)
- [진료 적용 평가 준비 절차](docs/CLINICAL_EVALUATION.md)
- [현재 구현·메뉴 UI 검증과 미완료](docs/verification/remaining.md)
- [최초 통합 목표와 현재 달성률](REMAINING_PROGRESS.md)

현재는 API 0.6.0 기능 검토 버전이다. 사용자 요청으로 새 기능 확장을 멈추고 메뉴 UI를 우선했다. 최종 디자인 검토·완전한 새 PC AI/영상 재설치·대표 실제 조영 CT 성능, 이전 CT 전체 정합/자유 문장 재작성, 조건부 모듈과 임상 평가는 남아 있다. 평가자/정답 자료가 없는 VAL-05는 미완료다.

추가 검증: `npx playwright test -c playwright.remaining.config.ts`는 8004 임시 합성 DB에서 메뉴·구조화/대조/검토·문서·백업을 확인한다. `python -m backend.qa_monai`는 기존 공개 예제 QA 저장소에서 실제 두 번째 모델을 실행한다. `python -m backend.qa_performance`는 별도 512×512×128 합성 CT 자원 시험이며 정확도 시험이 아니다. 모든 QA는 운영 저장소와 분리한다.
