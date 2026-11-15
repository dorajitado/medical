// Viewer.tsx — CT 영상 열람 및 원본 복셀 정밀 측정 컴포넌트
// OHIF DICOM 뷰어 iframe을 임베드하고, 백엔드 기하학(Geometry) 검증 및 원본 HU·거리 측정을 제공한다.

import { useEffect, useRef, useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  ExpandMoreOutlined,
  OpenInNewOutlined,
  StraightenOutlined,
  VisibilityOutlined,
} from '@mui/icons-material';
import { request } from './api';

/** 선택된 시리즈 정보 타입 */
export type SelectedSeries = {
  studyId: string;
  seriesId: string;
  description: string;
};

/** 백엔드 기하학 검증 결과 타입 */
type Geometry = {
  supported: boolean;
  reasons?: string[];
  shape_xyz?: number[];
  spacing_xyz?: (number | null)[];
  warnings?: string[];
};

/** 원본 복셀 샘플링 결과 타입 (HU 및 LPS 물리 좌표) */
type Probe = {
  hu: number | null;
  patient_lps_mm: number[];
  padding: boolean;
  source_instance_id: string;
};

/**
 * CT 영상 뷰어 컴포넌트
 * - 선택된 시리즈의 기하학적 유효성을 먼저 확인
 * - 로컬 웹 뷰어(OHIF) URL을 발급받아 화면 가득 표시
 * - 정밀 좌표(XYZ) 기반 원본 복셀 HU 및 3D 물리 거리 측정 기능 제공 (기본 펼쳐짐 접이식 아코디언)
 */
export default function Viewer({ selection }: { selection: SelectedSeries | null }) {
  // OHIF 뷰어 임베드용 URL
  const [url, setUrl] = useState('');
  // 시리즈 공간 기하학 검증 정보
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  // 오류 메시지
  const [error, setError] = useState('');
  // 뷰어 및 메타데이터 로딩 상태
  const [busy, setBusy] = useState(false);
  // 수동 재시도 카운터
  const [retry, setRetry] = useState(0);

  // 정밀 측정용 시작점 및 끝점 인덱스 좌표 (열 X, 행 Y, 정렬 절편 Z)
  const [point, setPoint] = useState([0, 0, 0]);
  const [end, setEnd] = useState([0, 0, 0]);
  // 샘플링된 복셀 정보 및 두 점 사이의 물리적 거리(mm)
  const [sample, setSample] = useState<Probe | null>(null);
  const [length, setLength] = useState<number | null>(null);
  // 측정 API 호출 중 여부
  const [measuring, setMeasuring] = useState(false);

  // 비동기 경쟁 상태(Race condition) 방지용 세대 식별자
  const generation = useRef(0);

  // 시리즈가 변경되거나 재시도 요청 시 뷰어 연결 초기화 및 재조회
  useEffect(() => {
    generation.current += 1;
    const abort = new AbortController();
    setUrl('');
    setGeometry(null);
    setError('');
    setSample(null);
    setLength(null);
    setPoint([0, 0, 0]);
    setEnd([0, 0, 0]);

    if (!selection) {
      setBusy(false);
      return;
    }

    setBusy(true);
    // 1단계: 시리즈 공간 정합성(절편 간격, 방향 등) 검증
    request<Geometry>(`series/${selection.seriesId}/geometry`, abort.signal)
      .then(async (geo) => {
        if (abort.signal.aborted) return;
        setGeometry(geo);
        if (!geo.supported) return;

        // 2단계: 유효한 시리즈인 경우 로컬 OHIF 뷰어 세션 열기
        const result = await request<{ url: string }>(
          `series/${selection.seriesId}/open`,
          abort.signal,
          {},
          'POST',
        );
        if (!abort.signal.aborted) {
          setUrl(result.url);
        }
      })
      .catch((e) => {
        if (!abort.signal.aborted) {
          setError(e.message);
        }
      })
      .finally(() => {
        if (!abort.signal.aborted) {
          setBusy(false);
        }
      });

    return () => abort.abort();
  }, [selection, retry]);

  /** 원본 복셀의 HU 값 및 두 좌표 간 물리 거리(mm) 측정 요청 */
  async function measure() {
    if (!selection) return;
    const current = generation.current;
    setMeasuring(true);
    setError('');
    setSample(null);
    setLength(null);

    try {
      const [probe, distance] = await Promise.all([
        request<Probe>(
          `series/${selection.seriesId}/probe`,
          undefined,
          { x: point[0], y: point[1], z: point[2] },
          'POST',
        ),
        request<{ distance_mm: number }>(
          `series/${selection.seriesId}/distance`,
          undefined,
          { start: point, end },
          'POST',
        ),
      ]);
      if (current === generation.current) {
        setSample(probe);
        setLength(distance.distance_mm);
      }
    } catch (e) {
      if (current === generation.current) {
        setError(e instanceof Error ? e.message : '측정 실패');
      }
    } finally {
      if (current === generation.current) {
        setMeasuring(false);
      }
    }
  }

  return (
    <Paper
      variant="outlined"
      sx={{
        p: { xs: 2, md: 2.5 },
        mb: 2.5,
        minWidth: 0,
        bgcolor: 'background.paper',
        borderRadius: 2.5,
      }}
    >
      {/* 뷰어 상단 헤더: 제목 및 현재 열람 중인 시리즈명 배지 */}
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        gap={1}
        flexWrap="wrap"
        sx={{ mb: 1.5 }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <VisibilityOutlined color="primary" sx={{ fontSize: 22 }} />
          <Typography variant="h6" component="h2">
            CT 영상 열람
          </Typography>
        </Stack>
        <Chip
          variant="outlined"
          label={selection ? selection.description : '시리즈 선택 전'}
          color={selection ? 'primary' : 'default'}
          sx={{ fontWeight: 600 }}
        />
      </Stack>

      {/* 시리즈 미선택 상태 안내 */}
      {!selection && (
        <Box
          sx={{
            py: 7,
            px: 2,
            textAlign: 'center',
            bgcolor: '#f8fafc',
            borderRadius: 2,
            border: '1px dashed #cbd5e1',
          }}
        >
          <Typography variant="body2" color="text.secondary">
            검사를 선택한 뒤 시리즈의 ‘영상 열기’를 눌러 주세요.
          </Typography>
        </Box>
      )}

      {/* 뷰어 로딩 진행 상태 */}
      {busy && (
        <Stack
          direction="row"
          spacing={1.5}
          alignItems="center"
          sx={{ my: 2, p: 2, bgcolor: '#f0f7ff', borderRadius: 2 }}
        >
          <CircularProgress size={20} color="primary" />
          <Typography variant="body2" color="primary.main" fontWeight={600}>
            원본 픽셀·절편 좌표 확인 및 로컬 뷰어 연결 중
          </Typography>
        </Stack>
      )}

      {/* 기하학적 미지원 사유 경고 */}
      {geometry && !geometry.supported && (
        <Alert severity="warning" sx={{ my: 2 }}>
          {geometry.reasons?.join(' ')}
        </Alert>
      )}

      {/* 기하학 경고 메시지 목록 */}
      {geometry?.warnings?.map((w) => (
        <Alert key={w} severity="info" sx={{ my: 1 }}>
          {w}
        </Alert>
      ))}

      {/* 에러 발생 시 재시도 안내 */}
      {error && (
        <Alert
          severity="error"
          sx={{ my: 2 }}
          action={
            <Button color="inherit" size="small" disabled={busy} onClick={() => setRetry((n) => n + 1)}>
              다시 연결
            </Button>
          }
        >
          {error}
        </Alert>
      )}

      {/* OHIF 뷰어 임베드 및 제어 툴바 */}
      {url && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5, fontSize: '0.825rem' }}>
            OHIF 도구에서 창 조절·확대·이동·거리·Probe를 사용할 수 있습니다. MPR은 3개 이상 절편에서 선택하세요.
          </Typography>

          {/* OHIF 임베드 iframe: 안정적인 화면 비율과 시인성을 보장 */}
          <Box
            component="iframe"
            title="OHIF CT 영상 뷰어"
            src={url}
            sx={{
              width: '100%',
              height: 'min(760px, 75vh)',
              minHeight: 480,
              border: 0,
              borderRadius: 2,
              bgcolor: '#111b24',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.08)',
              display: 'block',
            }}
          />

          <Stack direction="row" justifyContent="flex-end" sx={{ mt: 1 }}>
            <Button
              href={url}
              target="_blank"
              rel="noopener"
              startIcon={<OpenInNewOutlined />}
              size="small"
              sx={{ color: 'text.secondary' }}
            >
              뷰어를 별도 창으로 열기
            </Button>
          </Stack>
        </Box>
      )}

      {/* 정밀 복셀 HU 및 3D 물리 거리 측정 도구 — Accordion(기본 펼쳐짐)으로 정돈하여 기능 유지와 깔끔한 UI를 동시 충족 */}
      {geometry?.supported && (
        <Box sx={{ mt: 2.5 }}>
          <Accordion
            defaultExpanded
            disableGutters
            variant="outlined"
            sx={{
              borderRadius: 2,
              '&:before': { display: 'none' },
              borderColor: '#e2e8f0',
              bgcolor: '#f8fafc',
            }}
          >
            <AccordionSummary expandIcon={<ExpandMoreOutlined />}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <StraightenOutlined sx={{ fontSize: 18, color: 'secondary.main' }} />
                <Typography variant="subtitle2" component="h3">
                  원본 복셀의 HU·거리 확인
                </Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails sx={{ pt: 0, pb: 2 }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
                0부터 시작하는 열 X·행 Y·정렬 절편 Z 인덱스. 환자 좌표는 DICOM LPS(mm)입니다. 화면 보간값과 구분합니다.
              </Typography>

              {/* 시작점 및 끝점 좌표 입력 필드 */}
              <Stack spacing={1.2}>
                {[
                  { label: '시작점', values: point, set: setPoint },
                  { label: '끝점', values: end, set: setEnd },
                ].map((group) => (
                  <Stack
                    key={group.label}
                    direction="row"
                    spacing={1}
                    alignItems="center"
                    sx={{ flexWrap: 'wrap', rowGap: 1 }}
                  >
                    <Typography sx={{ minWidth: 50, fontSize: '0.85rem', fontWeight: 600 }}>
                      {group.label}
                    </Typography>
                    {group.values.map((value, axis) => (
                      <TextField
                        key={axis}
                        size="small"
                        type="number"
                        label={`${group.label} ${'XYZ'[axis]}`}
                        value={value}
                        disabled={measuring}
                        onChange={(e) => {
                          const next = [...group.values];
                          next[axis] = Number(e.target.value);
                          group.set(next);
                          setSample(null);
                          setLength(null);
                        }}
                        slotProps={{
                          htmlInput: {
                            min: 0,
                            max: (geometry.shape_xyz?.[axis] ?? 1) - 1,
                            step: 1,
                          },
                        }}
                        sx={{ width: 100 }}
                      />
                    ))}
                  </Stack>
                ))}
              </Stack>

              <Stack direction="row" alignItems="center" spacing={2} sx={{ mt: 1.5 }}>
                <Button
                  onClick={() => void measure()}
                  disabled={measuring || busy}
                  variant="outlined"
                  size="small"
                >
                  원본 HU·거리 계산
                </Button>
              </Stack>

              {/* 측정 결과 출력 영역 */}
              <Box aria-live="polite" sx={{ mt: 1.5, p: 1.2, bgcolor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 1.5 }}>
                {sample && (
                  <Typography variant="body2" sx={{ fontSize: '0.84rem' }}>
                    원본 HU:{' '}
                    {sample.hu === null ? '패딩 픽셀 (측정 제외)' : sample.hu.toFixed(3)} · LPS:{' '}
                    {sample.patient_lps_mm.map((v) => v.toFixed(3)).join(', ')} mm
                  </Typography>
                )}
                {length !== null && (
                  <Typography variant="body2" fontWeight={600} color="primary.main" sx={{ fontSize: '0.84rem', mt: 0.3 }}>
                    거리: {length.toFixed(3)} mm
                  </Typography>
                )}
              </Box>
            </AccordionDetails>
          </Accordion>
        </Box>
      )}
    </Paper>
  );
}
