# 3주차 검증 — 해부학 분할·원본 격자 복원

날짜: 2026-11-15. 초기 목표: WEEK3_PROGRESS.md. 기준: REQUIREMENTS.md v0.5, WBS 2·4·9. Docker 사용 없음. 사용자 업데이트 3단 React/MUI UI를 보존했다. 사용자 원본 CT·소견서는 이번 모델 검증에 사용하지 않았다.

## 구현·지원 범위

- `backend/analysis_volume.py`: DICOM 물리 순서 XYZ, 슬라이스별 HU, padding=-1024, LPS→RAS affine·역행렬·UID/해시 기록, 최근접 라벨 복원, 원본 격자 부피/중심·경계 접촉.
- `backend/analysis.py`, `backend/inference_worker.py`, `backend/storage.py`: 영속 AnalysisRun, 단일 실행기/별도 GPU 프로세스, 대기/실행/완료/실패/취소·단계, 중복 차단, 취소 우선, 이전 실행 보존, 중단 복구. 단계의 임의 백분율 없음.
- `backend/analysis_runtime.py`, `backend/offline/sitecustomize.py`: 설치/가중치 확인·실행 전 SHA-256 검사, 별도 Python 환경. telemetry=false, 외부 Python TCP/DNS 차단이 Windows spawn 자식에도 적용. OS 방화벽 전체를 검증했다는 뜻은 아니다.
- `src/AnalysisPanel.tsx`: 실제 API 실행·버전·결과, 원본 격자 CT/마스크, 표시·구조·불투명도·창 설정·슬라이스. OHIF와 별도 탐색임을 명시. 시리즈 드롭다운 변경 즉시 이전 영상·분할 해제.
- 공개 `total` fast 3 mm의 8개 구조(5폐엽·기관·심장·대동맥)만 노출. 단일 프레임/비압축 지원 CT, 3절편 이상, 위치 affine 오차 0.01 mm 이하, 최대 160,000,000복셀. 나머지 task는 실행 불가 후보로 남김.

## 고정 환경·공식 근거

Python 3.10 / TotalSegmentator 2.18.0 / torch 2.7.1+cu128 / torchvision 0.22.1+cu128 / nnunetv2 2.8.1. 실제 `pip check` 통과. 전체 패키지는 backend/ai-requirements-lock.txt, API 환경은 backend/requirements-lock.txt. 가중치 Dataset297_TotalSegmentator_total_3mm_1559subj, v2.0.0-weights. 파일별 SHA-256은 ai-weights-lock.json, 집계 `1b29e88f59684931601ce38381b60fbbb2f4b864d93b084657066b5574467614`.

공식 [사용·라이선스·제한](https://github.com/wasserth/TotalSegmentator), [fast 3 mm 설정](https://github.com/wasserth/TotalSegmentator/blob/master/totalsegmentator/map_tasks_config.py), [공식 예제 CT](https://github.com/wasserth/TotalSegmentator/blob/master/tests/reference_files/example_ct_sm.nii.gz) 확인. 공개 total task Apache-2.0 범위. 공급자도 임상 용도로 검증된 완제품으로 제시하지 않는다.

## 합성 API·좌표 회귀

명령: `.venv/Scripts/python.exe -m unittest backend.test_app backend.test_intake backend.test_geometry backend.test_analysis -v`.

기존 26개 + 신규 13개 = 39개. 기존 검사는 초기/모델 설치 후 전체 실행에서 통과했고, 마지막 신규 좌표·검사 혼동 보강은 해당 테스트 모듈 재실행으로 확인했다.

허용오차를 테스트 작성 시 정의: 좌표 1e-4 mm, 복셀 수 정확 일치, 부피 1e-4 mm³. 사선·반전 방향, 뒤섞인 절편 등록, 비등방성 모델 격자, 평행 이동 출력, per-slice rescale/HU, 원본 해시·축 순서, 1복셀 12 mm³ 기준, 원본 인스턴스·YX 평탄화 확인. 물리 범위가 다른 마스크·소수/음수/NaN/알 수 없는 라벨 거부. 빈 마스크는 no_segment이며 정상 뜻이 아님. 지원 geometry 외 절편 위치 편차는 분석 차단.

작업 검사: 확인 없는 요청/미지원 task/임의 경로 거부, 중복 실행 차단, snapshot에 report_input=false, 취소 후 늦은 완료 차단, 재시작 running→failed/interrupted, 이전 완료 보존, 실행 파일 오류·OOM 응답, 실행 중 소유 프로세스 종료 호출, 미완료/다른 시리즈 결과 접근 차단. OOM은 실제 GPU를 고갈시키지 않고 워커 오류를 주입해 검증했다. 외부 DNS 연결은 새 자식 Python에서 차단됨.

## 실제 모델 통합

명령: `.venv/Scripts/python.exe -m backend.qa_week3`. 공식 공개 NIfTI(122×101×30, 3 mm; 483,312 bytes)를 QA DICOM으로 래핑해 운영 intake/API/queue/실제 GPU worker를 실행했다. 원본 예제 SHA-256: `e50c00b2914e2cac0aaee8e7f3b5f57d44d9f21bfd5c0577271c54c0cb49e9fb`.

- 결과 completed. 보존한 해부학 라벨 5,269복셀, 4개 구조에 비어 있지 않은 결과. 예제는 촬영 범위가 제한되어 전체 흉부 구조가 나오지 않는다.
- 모델 호출·복원 구간 24.766초. RTX 3080 10GB, torch CUDA peak allocated 2,455,137,792 bytes (2.29 GiB), reserved 3,110,076,416 bytes (2.90 GiB).
- 0/중간/마지막 3개 원본 HU 평면을 결과 API와 비교하여 1e-4 이내 일치.
- 로컬 증거: `data/qa-week3/last-run.json`, 해당 QA workspace의 analysis 결과·metrics·source. Git 제외.

이 수치는 작은 공개 예제의 기술 측정이다. 512×512 실제 흉부 CT의 처리시간/최대 시스템 RAM·GPU 전체 사용량을 보장하지 않으며, 해부학 정확도·임상 허용오차를 측정한 것이 아니다.

## 실제 Edge UI

`npm run build` 타입 검사·프로덕션 빌드 통과. 약 506 kB 번들 크기 안내는 있으나 빌드 오류는 없음.

`npx playwright test`: 기존 4개 통과. 사용자 UI에 맞춰 모델 준비 상태는 실제 API 기반으로 검사하고 등록 카운터의 중복 표시를 구별했다. 등록·소견 버전·연결 실패/재시도, 1280×720/1920×1080/390×844 가로 overflow, 실제 OHIF CT·MPR·거리/HU 확인.

`npx playwright test --config playwright.analysis.config.ts`: 실제 공개 예제 결과로 1개 통합 검사 통과. 픽셀 checksum으로 마스크/불투명도/구조 선택/창 설정이 실제 영상에 반영됨을 확인. 슬라이스·LPS 출처, 실행 전 확인, 실제 inference 단계 취소, 이전 완료 결과 유지·다시 선택, 검사 해제 시 이전 결과 제거, 브라우저 외부 HTTP 요청 0개. 캡처: `data/analysis-browser-results/public-anatomy-overlay.png`, `public-workspace.png` (Git 제외).

## 미완료·적용 한계

3D 표면(VIEW-05), 후보-CT-3D 동기화(VIEW-06), 결절/삼출(AI-03/04), 장경 등 측정(AI-05 일부), 다른 모델 입력/자원 검증(AI-07/NFR-04 일부), 소견 구조화/대조/정리본, 백업은 남음. 현재 마스크 뷰는 원본 격자 축상이며 OHIF MPR/도구와 자동 동기화하지 않는다. 강제 OS 종료 시 중단 상태는 복구하나 모든 네이티브 드라이버/OS 장애를 복구하는 것은 아니다.

VAL-01은 해부학 좌표·부피 부분을 보강했으나 전체 대상 소견 평가가 남음. VAL-03은 소견서 입력 분리를 구현했으나 학습/평가 자료 분리 설계 전체는 남음. VAL-05 임상 성능/진료 적용 평가는 수행하지 않았다.

## 실제 앱 반영 확인

로컬 API를 0.4.0으로 재시작한 뒤 /api/health, /api/models, 정적 화면 HTTP 200, 네이티브 영상 ready를 확인했다. 기존 검사 목록을 보존했고 total만 실행 준비, 결절/삼출 후보는 미설치 상태다. 사용자 CT 분석을 자동 실행하지 않았다. 3주차 UI는 화면을 새로고침한 뒤 영상 열기 → 중앙 CT 뷰어 아래 AI 해부학 분할에서 사용한다.
