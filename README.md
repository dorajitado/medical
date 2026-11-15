# 흉부 CT 검토실

본인 PC에서 조영증강 흉부 CT와 병원 판독소견서를 검토하는 로컬 웹앱. React 19 / TypeScript / Material UI 7 / FastAPI / SQLite.

## 현재 구현

사용자 선택 DICOM 등록, 검사·시리즈·직접 입력 소견서 버전 저장, 시리즈 geometry/픽셀 검증, Windows 네이티브 Orthanc/OHIF CT 열람·MPR·거리/HU 도구를 구현했다. 해부학 3D·AI 실행·소견 자동 구조화·대조는 미연결이다. 등록 성공·빈 목록은 진단 결과를 의미하지 않는다. Docker는 사용하지 않는다.

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

영상 서비스를 별도로 실행하려면 `start-imaging.ps1`을 사용한다. 설치된 바이너리 버전/해시는 imaging-runtime-lock.json에 기록한다. 모델 가중치는 설치하지 않는다.

개발 중에는 API와 화면을 각각 실행할 수 있다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --no-access-log
# 별도 터미널
npm run dev
```

개발 화면은 http://127.0.0.1:5173 이며 `/api`를 로컬 서버에 전달한다. 빌드 후 API 재시작 시 8000에서 최신 정적 화면을 제공한다. 외부 폰트·CDN·환자 데이터 전송 API를 사용하지 않는다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_app backend.test_intake backend.test_geometry -v
npm run build
npx playwright test
```

브라우저 검증은 설치된 Microsoft Edge를 사용한다. 임시 DB의 8001 포트에서 동작하며 운영 DB와 분리된다. 전체 브라우저 테스트 전에 별도 터미널에서 `.venv/Scripts/python.exe -m backend.run_imaging --qa`를 실행한다(종료 Ctrl+C). 합성 2×2/128×128 DICOM만 생성하며 결과는 Git 제외 `data/browser-results/`에 기록한다.

API 테스트는 임시 DB의 가상 자료만 사용한다. 실제 환자 자료를 테스트나 Git에 넣지 않는다.

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
