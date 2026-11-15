# 1주차 기술 설계

## 2주차 확정 및 구현

사용자 제약에 따라 Docker를 사용하지 않는다. Windows Orthanc 1.13.0 + DICOMweb 1.24 + OHIF 플러그인 1.8을 프로젝트 runtime/에 설치한다. 공식 바이너리의 버전·URL·SHA-256은 imaging-runtime-lock.json으로 고정하고 setup-imaging.ps1에서 확인한다. 바이너리는 Git 제외이며 설치 스크립트로 복원한다. 기존 1주차 설명 중 영상 엔진 미연결 상태는 이 절로 갱신한다.

NativeImaging은 app의 관리 원본을 인증된 로컬 Orthanc에 복사하고 선택한 검사/시리즈 UID로 OHIF를 연다. React/MUI 안의 같은 출처 iframe으로 /imaging/ohif/viewer를 표시한다. API의 고정 대상 프록시는 OHIF와 읽기 전용 DICOMweb만 노출하며 Orthanc 관리 API/사용자 지정 URL은 허용하지 않는다. Orthanc 인증 토큰은 Git 제외 config에 생성되고 브라우저에 전달하지 않는다. RemoteAccessAllowed=false, DICOM 수신 비활성. COOP/COEP 헤더로 같은 출처 영상 WASM/볼륨 환경을 구성한다.

start.cmd → run_local이 API와 네이티브 영상 프로세스를 실행한다. 자신이 시작한 프로세스만 종료한다. QA는 별도 저장소/8043 포트, 운영은 8042 포트로 분리하며 API 프록시는 각각 8001/8000을 사용한다. 시스템 서비스나 Docker를 설치하지 않는다.

시리즈 geometry는 환자 LPS 좌표로 정렬하고 행/열 방향·크기·간격·중복 위치·불규칙 간격·gantry tilt·원본 해시·픽셀 디코딩을 확인한다. 등록 중인 시리즈는 열지 않는다. 초기 지원은 평행한 직교 단일 프레임 비압축 CT다. 단일/두 절편은 스택 확인만, MPR은 최소 3절편이다. 균일하게 누락된 절편이나 촬영 범위 밖 병변의 존재를 이 검사로 알아낼 수 있다고 주장하지 않는다.

HU 원본 확인은 실제 signed/unsigned 픽셀에 절편별 RescaleSlope/Intercept를 적용하며 패딩을 제외한다. 열 X·행 Y·정렬 Z 인덱스를 원본 인스턴스와 LPS 좌표에 연결한다. 거리 계산은 두 환자 좌표의 유클리드 거리다. OHIF의 화면 Length/Probe 및 MPR 조작과 API의 정확한 원본 복셀 확인을 함께 제공한다. 관상/시상 보간 픽셀을 원본 HU와 동일한 측정으로 표시하지 않는다. 측정/분할의 영속 보존은 후속 OUT/AI 범위로 남는다.

## 경계와 구현 순서

React 19/TypeScript/Material UI 7 화면이 같은 출처의 FastAPI에 연결한다. 원본 데이터는 data/ 아래, 상태와 관계는 SQLite에 저장한다. Node는 화면 빌드에만 필요하고 빌드한 앱은 Python 서버 하나로 실행한다. 기본 바인딩은 127.0.0.1이며 원격 환자 API는 없다.

사용자는 브라우저 폴더 선택기를 통해 DICOM 파일을 선택한다. 절대 경로를 API에 전달하지 않는다. 브라우저가 선택한 파일의 바이트만 로컬 서버로 전송한다. 파일명·상대 경로를 저장 경로로 사용하지 않고 서버가 UUID 파일명을 부여한다. 등록 성공한 원본을 보존하며 사용자 원본 폴더에는 쓰지 않는다. 등록 한도·실패·중복·취소를 표시한다.

판독소견서는 검사 선택 후 직접 입력한다. 입력 원문에 병원 판독 전사/개인 메모 출처를 명시하고 버전별 보존한다. 직접 입력은 인증된 병원 원본이 아니다. 추후 OCR은 선택 기능으로 추가한다. 문서 텍스트는 React 텍스트 노드로 출력하고 HTML로 실행하지 않는다.

OHIF와 Orthanc는 후속 영상 기능용이며 이번 단계에서 설치·연결했다고 표시하지 않는다. React/MUI는 검사·소견·대조 흐름의 외곽을 소유한다. OHIF는 별도 로컬 빌드와 extension/mode로 영상 뷰포트·측정·분할을 소유하며 DICOMweb을 통해 Orthanc에 연결한다. MUI와 OHIF 내부 상태를 직접 결합하지 않는다. 어댑터 계약은 study/series/instance UID와 환자 좌표계(mm), 선택 이벤트, 측정/분할 참조다. 웹 메시지 사용 시 같은 출처·메시지 스키마를 확인한다. 영상 엔진 선택·버전 고정과 실제 통합은 WBS 3에서 검증한다.

공식 근거: [OHIF 확장](https://docs.ohif.org/platform/extensions/), [Orthanc DICOMweb](https://orthanc.uclouvain.be/book/plugins/dicomweb.html). 이 설계는 도구의 자동 호환성을 보장하지 않는다.

## 데이터 소유권

Study → Series → Instance를 외래키로 연결한다. DICOM UID는 중복 식별, 서버 UUID는 URL 및 내부 경로에 사용한다. 파일 해시는 동일 UID/다른 바이트 충돌을 구분한다. 동일 UID의 다른 바이트를 조용히 덮어쓰지 않는다. 하나의 시리즈를 다른 검사로 재연결하지 않는다.

ReportVersion은 study_id·입력 출처·본문·생성 시각을 보존한다. 수정은 새 버전 추가이며 기존 원문을 덮어쓰지 않는다. 자동 소견 추출·대조는 아직 수행하지 않는다.

ImportJob은 등록 진행과 성공/중복/제외/실패 수를 저장한다. 상태는 running → completed/cancelled/failed. 재시작 시 남은 running은 interrupted로 변경한다. 끊긴 작업을 완료로 표시하지 않는다. 개별 파일은 staging 임시 파일 → 검사 → 원본 파일 이동 → DB 트랜잭션 순서다. DB 실패 시 새로 생성한 파일만 정리한다. 취소는 이미 등록한 성공 파일을 삭제하지 않고 남은 파일 전송을 중단한다.

모델 분석 AnalysisRun은 ImportJob과 다른 개체다. 3주차에 queued/running/completed/failed/cancelled 상태와 처리 단계·취소·재시작 interrupted 사유·설정 snapshot을 별도 테이블에 구현했다. 폴더 등록 작업 완료를 AI 분석 완료로 해석하지 않는다.

## 지원 입력과 미지원

초기 등록 대상은 Part 10 CT Image Storage의 단일 프레임 영상이다. 비CT·로컬라이저·Enhanced/다중프레임·압축·공간정보 누락은 제외하거나 시리즈 제한 사유를 표시한다. 간격/Rescale/방향/위치 정보와 검사/시리즈/SOP UID를 확인한다. 복수 CT 파일의 시리즈 단위 방향·크기·간격·절편 위치 검증은 WBS 3에서 이어진다. 메타데이터 등록이 픽셀 디코딩·측정 적합성 검증을 대신하지 않는다. 조영 관련 태그가 있어도 일반 조영 CT를 CTPA로 확정하지 않는다.

## 후보 모델과 설치 상태

TotalSegmentator total, lung_nodules, pleural_pericard_effusion을 첫 후보로 관리한다. 모델별 입력 범위와 한계를 화면에서 확인한다. 실행 패키지·가중치·설정 버전이 검증되기 전에는 실행 가능으로 표시하지 않는다. 설치 여부와 임상 검증 여부는 별도다. 가중치 파일의 해시와 버전을 실제 다운로드 후 기록한다.

RTX 3080 10GB에서는 추론을 순차 실행하고 패치/ROI 처리를 검토한다. 3주차 total fast 3 mm 공개 예제(122×101×30) 실측은 호출/복원 24.766초, torch CUDA peak allocated 2.29 GiB였다. 일반 CT의 처리시간이나 최대 입력 크기를 보장하지 않는다. 원본 512×512×1000의 float32 볼륨은 약 1GB이며 활성화·복사·분할 마스크 메모리는 별도다. 초기 분석 한도는 1억 6천만 복셀이며 대표 CT/다른 모델 프로파일은 남아 있다.

공식 모델 작업 목록: https://github.com/wasserth/TotalSegmentator#subtasks (2026-11-15 확인). 해부학 분할은 질환 진단을 의미하지 않는다. 결절 후보 점수는 악성 확률이 아니다.

## 검증 계획 및 임시 기준

- 모든 등록/문서/작업 API는 격리된 합성 자료에서 정상·잘못된 요청·중복·검사 혼동·경로 공격·중단 복구를 검사한다.
- 좌표/측정: 알려진 합성 geometry의 기하 계산 오차는 부동소수 계산 수준에서 확인. 리샘플링/모델 마스크 측정의 허용오차는 실제 방법 결정 후 별도로 정한다. 이를 임상 허용오차로 사용하지 않는다.
- UI 기준 해상도는 1280×720, 1920×1080, 좁은 창 390px. 브라우저 확인 전에는 검증 완료로 표시하지 않는다.
- 성능은 작업당 실제 읽은 파일 수/처리시간을 기록하고 진행률은 성공·제외·실패를 포함한 처리 파일 수/선택 수로 표시한다. API 반응과 영상/추론 시간은 별도 측정한다.
- 부정/의심/과거 소견 및 임상 성능 평가는 WBS 6~9에서 별도 자료로 확인한다.

## 보안·복구

로컬 Host/Origin과 변경 요청 헤더를 검사한다. 경로는 서버가 결정하고 요청 filename을 사용하지 않는다. 선택 파일 크기를 제한하고 UID·메타데이터 파싱 오류를 사용자에게 일반화해 반환한다. 로그에 문서 본문·환자명·원본 경로를 출력하지 않는다. SQLite 연결은 요청별로 닫고 트랜잭션을 사용한다. 원본 파일·문서와 데이터베이스는 Git에서 제외한다.

백업·복원·삭제 도구 및 임상 사용 평가는 WBS 10/별도 평가로 남긴다. 이번 단계의 로컬 요청 보호가 OS 계정 수준의 데이터 암호화·사용자 인증을 대체하지 않는다.

## 3주차 해부학 실행 경계 — 당시 구현 기록

`setup-ai.ps1`은 runtime/ai-venv와 runtime/models를 준비하며 영상 입력을 읽지 않는다. ai-requirements-lock.txt와 ai-weights-lock.json의 고정값을 사용한다. API는 무거운 torch를 import하지 않고 설치 manifest/파일과 실행 전 가중치 해시를 확인한다. total 이외 후보 task는 어댑터가 없어 실행 불가다.

분석 요청은 선택 Series와 model_id=total·확인 플래그만 받는다. 임의 파일 경로·모델 명령·소견서 텍스트를 받지 않는다. 단일 ThreadPool 실행기가 소유하는 별도 GPU Python 프로세스를 하나씩 실행한다. 취소/종료는 소유 PID와 자식 프로세스에만 적용한다. 완료 상태를 DB에 게시하기 전에 마스크·결과·실측 metrics가 모두 있어야 한다. 실패/취소/중단 파일을 완료 결과 API에서 열지 않는다.

DICOM을 정렬된 XYZ float32 HU로 변환한다. 슬라이스별 slope/intercept를 적용하고 padding만 -1024로 대체한다. 환자 LPS를 NIfTI RAS로 변환한 affine 및 역행렬, 원본 UID/해시/순서를 저장한다. 단일 affine로 표현할 수 없는 0.01 mm 초과 편차는 차단한다. TotalSegmentator 내부 3 mm 결과는 다시 원본 격자로 최근접 복원하고 지원 8개 라벨만 보존한다. 부피는 원본 격자 복셀 수 × affine 행렬식 절댓값이다. 원본/입력/예측/복원/실행 설정은 실행 UUID별로 보존한다.

별도 inference Python의 PYTHONPATH에 network guard를 넣어 외부 TCP/DNS를 차단하고 Windows spawn 자식에도 적용한다. loopback IPC는 허용한다. telemetry=false, HF_HUB_OFFLINE=1, nnUNet_compile=false. 네트워크 설치는 추론 전에 수행한다. OS 전체 네트워크 통제나 향후 모든 native library의 동작을 검증했다는 의미는 아니다.

원본 격자 마스크 뷰는 CT와 동일한 YX 평면을 같은 canvas에서 표시한다. 데이터 행/열을 뒤집지 않고 원점·행/열 LPS 방향을 제시하며 물리 픽셀 간격의 화면 비율을 적용한다. 이 뷰의 슬라이스/창 설정은 OHIF와 독립적이다. 검사/시리즈 변경 시 이전 결과 상태와 비동기 요청을 해제한다. 3D 표면과 OHIF MPR overlay 통합은 남아 있다. 증거: docs/verification/week3.md.

## 4주차 확장 — 현재 결절/삼출·3D 검토 경계

앞 절의 해부학 전용 어댑터를 total/lung_nodules/pleural_pericard_effusion의 허용 목록으로 확장했다. 모델별 가중치·crop 298 포함 설치를 독립 inventory/해시로 관리한다. API는 model_id와 사용자 확인만 받고 임의 CLI 옵션/경로/소견 텍스트를 받지 않는다. 같은 시리즈의 서로 다른 모델을 큐에 넣을 수 있지만 단일 GPU 실행기에서 순차 처리한다. 대기 중 가중치 식별/설정 변경을 차단한다.

원본 격자 복원 후 결절 라벨 2를 26연결 성분별로 분리한다. 삼출 라벨 2/3은 종류별 합산 영역이다. 보조 폐 라벨 1은 후보가 아니다. components.npy의 run-local selection_label과 후보 ID를 함께 저장하며 전체 식별은 run_id+candidate_id다. 대표 이동점은 중심에 가장 가까운 실제 마스크 복셀, 정량/경계/원본 인스턴스/LPS 출처를 보존한다. 장경은 전체 DICOM 평면 기저를 적용한 원본 촬영 절편별 외곽 Feret 최댓값이다. 임상 RECIST/환자 축상 MPR 측정은 아니다.

완료된 실행에서만 /surfaces를 제공한다. 원본 격자 labels/components 해시를 확인하고 marching cubes의 0.5 등가면을 생성해 LPS mm로 변환·캐시한다. 큰 구조는 표시 간격을 조정하고 복잡도 한도를 넘으면 명시적 3D 오류로 반환한다. 3D 오류가 완료된 마스크/정량값을 정상 결과나 빈 영역으로 덮어쓰지 않는다. 표면의 정점/부피로 정량값을 다시 계산하지 않는다.

AnalysisReviewProvider는 하나의 선택 실행/후보를 CT 마스크 뷰·SurfacePanel·CandidateDetail에 공급한다. 목록과 ray picking은 같은 selection API를 사용한다. 모델/실행/시리즈 변경에서 이전 결과·선택·비동기 요청을 해제한다. Three.js는 로컬 지연 로딩, LPS +Z를 카메라 up으로 사용한다. 회전/확대/구조·윤곽·불투명도/시점 초기화와 WebGL 연결 실패를 처리하며 unmount에서 geometry/material/renderer를 해제한다.

3D는 선택한 실행만 표시하며 모델 간 자동 마스크 합성은 제공하지 않는다. OHIF의 별도 탐색은 유지한다. 병원 소견 구조화/연결과 사용자 채택·제외/보류는 후속 REP/CMP 개체에서 원본 AI와 구별해 구현한다. 검증용 공개 모델 실행과 합성 양성 fixture는 운영 저장소와 분리한다. 세부 증거: docs/verification/week4.md.


## 2026-11-16 통합과 메뉴 구조

App의 허용된 UI hash 경로 11개로 화면을 분리한다. patient/study ID는 브라우저 주소에 넣지 않는다. IntakeProvider·AnalysisReviewProvider와 작업 편집기는 메뉴 전환 중 유지하고 실제 검사/시리즈가 바뀔 때 원본 경계를 해제한다. 메뉴별 visibility와 필요한 보조 패널만 바꾸며, 모바일 Drawer·PC 고정 탐색과 작업 영역 독립 스크롤을 사용한다. CSS 메뉴 강조 전환을 제거해 선택 순간의 대비도 유지한다.

SQLite의 extraction_versions, comparison_versions, review_versions, summary_versions와 audit_events가 원본 소견·기계 제안·사용자 해석·출력 스냅샷을 분리한다. source_documents는 원본 SHA/페이지·추출/실패 상태와 문서 전사 출처를 보존한다. model_comparison_versions와 longitudinal_versions는 독립 모델/이전 검사 연결 버전이며 원본 AI를 수정하지 않는다. evaluation_cases는 준비/전문가 등록 계수와 분할/출처를 보존하며 clinical_acceptance를 자동 승인하지 않는다.

영상 추론에는 보고서를 전달하지 않는다. MONAI는 고정 RetinaNet을 별도 GPU worker에서 실행하고 처리 격자/RAS→원본 인덱스/LPS로 8개 박스 꼭짓점을 변환한다. 박스는 wireframe/사각형으로 그리며 분할 부피·장경을 생성하지 않는다. 다른 모델과 점수를 융합하지 않는다. 문장 모델은 고정 CPU llama.cpp/Qwen을 인증된 loopback에서 잠깐 실행하고 ID 순열만 허용한다. 확인된 원문을 서버가 그대로 재구성하므로 모델이 쓴 의료 문장을 저장하지 않는다.

백업은 mutation 잠금·유휴 확인 후 SQLite online backup과 파일 해시 ZIP을 완성/검증한 뒤 공개한다. 복원은 종료된 서비스에서만 CLI로 수행하며 기존 데이터/캐시를 recovery에 이동하고 실패 시 되돌린다. 검사 삭제는 관리 경로 이동 저널→DB commit→파일 정리 순서이고 시작 시 commit 전 중단 이동을 복구한다. commit 후 잠긴 파일은 명시적 재시도 목록에 남는다. OCR와 로컬 문장 worker는 Windows kill-on-close Job으로 소유한다. 운영 자료의 자동 삭제/복원·자동 추론은 수행하지 않았다.

요구사항/보류/검증: docs/verification/remaining.md, docs/LOCAL_DATA_MANAGEMENT.md, docs/CLINICAL_EVALUATION.md. 과거 장의 ‘후속’ 표현은 해당 주차의 상태 기록이며 현재 추적표가 최신 상태다.
