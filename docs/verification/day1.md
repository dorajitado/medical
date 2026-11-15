# Day 1 개발 기반 검증 기록

날짜: 2026-11-15 / 범위: DAY1-01~05 / 기준: REQUIREMENTS.md v0.2

## 실행 결과

| 검사 | 실행 및 결과 |
|---|---|
| 원격 연결 | origin = https://github.com/dorajitado/medical.git. 기존 main b30e3cb에서 연결. 원격 기존 파일은 README.md |
| 개발 환경 | Node v24.15.0, npm 11.12.1, Python 3.10, 프로젝트 전용 .venv |
| 프런트엔드 | `npm run build` 종료 코드 0. TypeScript 검사 통과, Vite 빌드 성공 |
| 백엔드 | `.venv/Scripts/python.exe -m unittest backend.test_app -v` : 6 tests, OK |
| 로컬 실행 | uvicorn loopback 127.0.0.1:8000에서 시작, SQLite 초기화 성공 |
| 실제 HTTP | `/`, `/api/health`, `/api/studies`, `/api/preferences` 모두 200 |
| 빈 데이터 | `/api/studies` = items 빈 배열. health의 imaging/analysis = not_connected |
| Git 제외 | data/, .venv/, node_modules/, dist/, DICOM·NIfTI·DB·로그 제외 규칙 추가. 실제 DB 제외 확인은 최종 문서 정합 확인과 함께 수행 |

## API 테스트 내용

1. 빈 검사 목록과 분석 미연결을 구별한다.
2. 격리한 DB에 넣은 검사만 조회되고 누락 날짜는 null을 유지한다.
3. 화면 구조 영역 설정이 앱 인스턴스 재생성 후에도 보존된다.
4. 허용하지 않은 Host/Origin/cross-site 요청을 거부한다.
5. 변경 요청 헤더가 없거나 bool 스키마가 틀린 설정 변경을 거부한다.
6. 검사 응답에 no-store를 적용한다.

## 검증 한계와 후속

- 브라우저 패널 열기를 요청했으나 도구 결과는 queued다. 화면 렌더링·실제 클릭·해상도별 시각 검증을 수행했다고 주장하지 않는다.
- 설치된 Starlette의 TestClient에서 httpx 사용 중단 예정 경고가 나왔으나 테스트는 통과했다. 테스트 의존성 갱신 때 추적한다.
- 샌드박스 테스트 프로세스가 대기하여 종료하고 권한이 허용된 실행에서 재실행, 6개 통과를 확인했다.
- 실제 DICOM·병원 문서·AI 가중치가 없으며 영상·측정·AI·OCR 성능은 검증하지 않았다.
- 종속 패키지는 package-lock.json 및 backend/requirements-lock.txt로 기록했다. 새 PC 재설치 검증은 아직 수행하지 않았다.
- 원격 push는 수행하지 않았다. 이 문서의 저장소 연결은 원격 이력 확인과 로컬 origin 설정을 의미한다.
