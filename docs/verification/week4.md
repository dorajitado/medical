# 4주차 검증 — 결절·삼출 후보, 정량화, 실제 3D

날짜: 2026-11-15. 기준: WEEK4_PROGRESS.md의 착수 시 6개 완료 기준, REQUIREMENTS.md v0.6, WBS 4·5·9. Docker 사용 없음. 사용자 UI와 기존 결과 보존. 사용자 CT/소견서를 이번 모델 검증에 자동 사용하지 않았다.

## 구현 및 데이터 경계

- `backend/analysis_runtime.py`, `backend/setup_ai.py`, `backend/models.py`: total/lung_nodules/pleural_pericard_effusion의 독립 설정·설치 상태·고정 가중치. 결절/삼출 crop에 필요한 6 mm task 298도 설치 단계에서 준비. 추론 중 다운로드/원격 API 없음.
- `backend/analysis.py`, `backend/inference_worker.py`: 시리즈·모델별 대기/실행·버전, 모든 모델 GPU 순차 실행. 대기 중 가중치 변경 차단, 워커 설정 snapshot 일치 확인. 취소/실패/중단 상태와 이전 결과 보존.
- `backend/analysis_volume.py`: task별 라벨 검증, 원본 HU·환자 좌표·격자 복원. lung_nodules의 보조 lung 라벨 1 및 삼출 task의 보조 lung_pleural 라벨 1은 후보에서 제외.
- `backend/findings.py`: 결절은 3D 26연결 성분별 후보. 흉수/심낭삼출은 각각 한 합산 영역(독립 병변 수가 아님). 실제 마스크 복셀 대표 위치, 원본 인스턴스·LPS·부피·경계·점수 없음 보존.
- `backend/surfaces.py`: 실제 분할에서 0.5 등가면 marching cubes, 환자 LPS mm 변환. 원본 마스크/선택맵 해시 확인 후 캐시. 작은 후보 step=1, 큰 구조는 표시 간격 조정. 구조당 150,000면·전체 600,000면 초과 시 3D 오류 표시. 정량값은 원본 복셀에서 계산.
- `src/AnalysisReview.tsx`, `AnalysisPanel.tsx`, `SurfacePanel.tsx`, `CandidateDetail.tsx`: 모델/실행 선택, 실제 후보 목록·카운트, CT 마스크 뷰 이동·강조, 3D 표식/표면 선택, 오른쪽 동일 후보 상세. 전환 즉시 선택 해제 및 이전 요청 취소. 원문/사용자 판단을 수정하지 않음.

3D는 선택한 실행의 분할만 표시한다. 서로 다른 모델 실행을 자동 합성하지 않는다. 후보에 연결되는 CT는 원본 격자의 분석 마스크 뷰이며 OHIF/MPR 탐색은 독립적이다. 이 경계는 착수 시 명시했다.

## 입력 조건과 측정 정의

공통: 초기 지원 비압축 단일 프레임 CT, 검증된 연속 3절편 이상, 위치 affine 편차 ≤0.01 mm, ≤160,000,000복셀. 결절은 각 축 간격 ≤3 mm, 삼출은 ≤5 mm인 초기 앱 범위다. 임상 촬영 적합성/최적 절편 두께를 입증하는 기준이 아니다. 사용자가 흉부 시리즈를 최종 확인한다. 조영 태그만으로 CTPA라고 판정하지 않는다.

부피 = 원본 라벨 복셀 수 × abs(det(원본 환자좌표 affine)). 1000 mm³=1 mL. 결절 장경 = 원본 촬영 절편마다 복셀 외곽 모서리의 2D Feret 최댓값을 계산한 뒤 절편 전체에서 최댓값 선택. DICOM 열/행의 전체 물리 기저를 사용해 방향 벡터 반올림도 반영한다. 사선 촬영에서는 원본 촬영 평면 기준이고 환자 축상 MPR/임상 RECIST가 아니다. 대표 이동 절편과 장경 산출 절편은 다를 수 있어 각각 제공한다.

삼출 장경은 해당 없음(null). 모델이 제공하지 않는 탐지 점수·악성 확률도 null이며 생성하지 않는다. 후보 없음/미실행/실패/취소/미지원은 정상 판정과 구별한다. 경계 접촉은 부분 부피 가능성을 표시한다.

## 모델·패키지 재현성 및 공식 근거

TotalSegmentator 2.18.0 / torch 2.7.1+cu128 / nnunetv2 2.8.1, RTX 3080 10GB. scikit-image 0.25.2, three/@types/three 0.182.0. API/AI 각각 pip check 통과. 전체 Python·Node 고정 버전은 backend/requirements-lock.txt, backend/ai-requirements-lock.txt, package-lock.json에 기록.

ai-weights-lock.json의 task별 집계 SHA-256:

| task | 실제 가중치 | 집계 |
|---|---|---|
| total | 297 / v2.0.0-weights | `1b29e88f59684931601ce38381b60fbbb2f4b864d93b084657066b5574467614` |
| lung_nodules | 913 / v2.5.0-weights + crop 298 | `0994b3906e80a6edece97910942d5583d1a01e5fe55cbc57cf1af1990b2b162b` |
| pleural_pericard_effusion | 315 / v2.0.0-weights + crop 298 | `dd54209e20153ad3e74d49ca445bc078a19144d59867caf1c007ee3cdb66fcd3` |

공식 [TotalSegmentator task·라이선스·한계](https://github.com/wasserth/TotalSegmentator), 설치 패키지 map_tasks_config.py/map_to_binary.py를 대조했다. 해당 공개 task Apache-2.0. [marching cubes](https://scikit-image.org/docs/stable/api/skimage.measure.html#skimage.measure.marching_cubes), [OrbitControls](https://threejs.org/docs/pages/OrbitControls.html), [Raycaster](https://threejs.org/docs/pages/Raycaster.html)를 참고했다. 3D 시점 초기화는 컨트롤의 saveState/reset을 사용한다.

의존성 설치 중 기존 Vite 7.2.2 개발 서버 보안 권고를 확인해 호환 수정 버전 7.3.8로 고정했다. 설치 후 npm audit 보고 취약점 0개. 이는 모델 정확도 평가와 무관하다. 프로덕션 빌드 통과, JS 약 512/516 kB 청크 크기 안내만 남으며 로컬 3D 번들은 지연 로딩한다.

## 실제 GPU 실행 — 공개 예제, 사용자 영상 아님

명령: `.venv/Scripts/python.exe -m backend.qa_week4` (먼저 week3 공개 예제 workspace 필요). 예제 122×101×30, 3 mm, SHA-256 `e50c00b2914e2cac0aaee8e7f3b5f57d44d9f21bfd5c0577271c54c0cb49e9fb`. 출처: [공식 공개 CT 예제](https://github.com/wasserth/TotalSegmentator/blob/master/tests/reference_files/example_ct_sm.nii.gz).

| 모델 | 상태 | 실제 호출·복원·정량화 | torch CUDA peak allocated | reserved | 해당 예제 출력 |
|---|---|---:|---:|---:|---|
| lung_nodules | completed | 37.875초 | 4,308,877,312 bytes (4.01 GiB) | 4,481,613,824 bytes | 후보 없음, 빈 3D 상태 |
| pleural_pericard_effusion | completed | 30.484초 | 1,829,972,992 bytes (1.70 GiB) | 1,906,311,168 bytes | 후보 영역 1종, 실제 3D 표면 |

결절과 삼출은 동일 API 실행기에서 순차 실행됐다. 이전 실제 해부학 결과도 재추론 없이 4개 비어 있지 않은 구조의 3D를 생성했다. 로컬 증거는 data/qa-week4/last-run.json 및 해당 QA run/source/result/metrics/worker 파일이며 Git 제외다. 작은 예제의 결과를 정답/민감도·특이도/임상 검출 성능으로 해석하지 않는다. 전체 흉부가 포함된 대표 CT의 처리시간·시스템 RAM·허용 대기는 NFR-04/07에서 남겨 둔다.

## 합성 좌표·측정 및 API 검증

명령: `.venv/Scripts/python.exe -m unittest backend.test_app backend.test_intake backend.test_geometry backend.test_analysis backend.test_findings -v`.

기존 39개 + 3D API/캐시 무결성 2개 + 후보 정량화 8개 = 49개 항목. 통합 검사와 후속 방향 기저 보강 모듈 재검사로 확인했다. 사전 오차: 원본 좌표·장경 1e-4 mm, 부피 1e-4 mm³, 복셀/후보 수 정확 일치. 반올림 방향 기저 별도 기준 1e-6 mm. 3D JSON 렌더링 좌표 0.002 mm. 임상 허용오차가 아니다.

검사 내용: 분리 결절·26연결·구멍 난 후보의 실제 마스크 대표 위치, 사선/반전·비등방/이동 격자, 복셀 외곽 단일/다중 크기·부피, 최대 절편 선택, 삼출 종류별 분리/합산·장경 null, 보조 폐 라벨 제외, 빈 후보, 미지원 라벨/격자 차단, 모델별 간격 제한. 기준 예: 2×3×4 mm 복셀 2개 부피 48 mm³, 원본 평면 2복셀 직사각형 장경 5 mm.

3D 원점·표면 범위·삼각형 인덱스·후보 ID/LPS, 완료 상태에서만 접근, 캐시 재사용 및 라벨/선택맵 변조 차단. 시리즈·모델별 중복/버전 독립, 대기 중 가중치 변경 실패, 취소 우선/재시작/이전 결과·OOM 오류 응답, 외부 Python TCP/DNS 차단 회귀를 확인했다. OOM은 실제 GPU 고갈 없이 워커 응답을 주입했다.

## Edge 통합 및 시각 검토

- `npm run build`: TypeScript/프로덕션 빌드 통과.
- `npx playwright test`: 기존 4개 통과. DICOM 등록·소견 버전·연결 오류/재시도·3종 해상도·실제 OHIF CT/MPR/거리/HU 보존.
- `npx playwright test --config playwright.analysis.config.ts`: 실제 공개 모델 결과 2개 통과. 해부학 마스크·취소/버전, 실제 결절 후보 없음·삼출 후보 양성 상태, CT/3D/상세 동일 후보, WebGL 회전·확대·윤곽·불투명도·구조 선택·표면 ray picking, 모델 전환 해제·외부 HTTP 요청 0. 시점 복원 이미지는 안티앨리어싱 반올림을 고려해 평균 채널 오차 <1/255 기준.
- `npx playwright test --config playwright.findings.config.ts`: 격리 양성 합성 자료 2개 통과. 결절 2개를 번갈아 골라 CT 절편/LPS·3D 표식·상세 일치, 늦은 응답/모델·시리즈 전환 이전 결과 차단, 1280×720/390×844 overflow, 3D API 실패 표시·재시도 복구.

합성 양성 자료는 임시 DB, SYNTHETIC 명칭·‘실제 AI 출력 아님’ 표시·실측 null을 사용한다. 운영 앱에 seed/import되지 않는다. 실제 모델의 후보 개수나 정확도에 합산하지 않는다.

캡처를 직접 확인했다: data/analysis-browser-results/public-effusion-3d.png, public-candidate-workspace.png 및 data/findings-browser-results/synthetic-linked-review.png. 모두 Git 제외.

## 인수와 남은 기준

AI-03/04/05/07, VIEW-05/06, VAL-01을 초기 명시 지원 범위에서 인수한다. 기존 DCM-05·AI-01/06 등의 증거를 새 task까지 보강한다. 주간 목표와 전체 P0율은 WEEK4_PROGRESS.md/REQUIREMENTS_TRACKER.md에서 별도 집계한다.

NFR-04/07은 작은 예제 자원 실측까지이고 대표 전체 CT 기준은 남음. NFR-05 새 PC 전체 설치 인수, 전체 파이프라인 오류·백업도 남아 있다. REP-04/05 소견 구조화/정정, CMP 대조·검토 판단 저장, 내보내기 및 VAL-02/03 전체 평가·VAL-05 진료 적용 평가는 미완료다. 임상 장경/경계 오차·탐지 성능을 검증했다고 보고하지 않는다.

## 실제 앱 반영 확인

로컬 API 0.5.0 재시작 후 health·세 모델 모두 ready/executable·정적 화면 HTTP 200·네이티브 영상 ready 확인. 운영 검사 목록 보존, 사용자 CT 자동 추론 없음. 테스트 영상 서비스는 종료했다. 브라우저에서 새로고침 → 영상 열기 → 중앙 분석 모델 선택 → 시리즈/한계 확인 → 실행 → 후보 선택으로 사용한다.
