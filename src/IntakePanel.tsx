// IntakePanel.tsx — DICOM 등록, 시리즈 열람 제어, 판독소견서 관리 및 AI 모델 상태 컴포넌트
// 데이터 가져오기, 검사·시리즈 선택, 소견서 버전 관리, 모델 준비 상태를 모듈화하여 3단 레이아웃에 공급한다.

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  FormControl,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  CreateNewFolderOutlined,
  HistoryEduOutlined,
  PlayArrowOutlined,
  SaveOutlined,
  SmartToyOutlined,
  TuneOutlined,
  UploadFileOutlined,
} from '@mui/icons-material';
import {
  request,
  type Job,
  type Model,
  type Report,
  type Series,
  type Study,
} from './api';
import type { SelectedSeries } from './Viewer';

/** 가져오기 작업 상태 한글 라벨 맵핑 */
const jobLabels: Record<string, string> = {
  running: '등록 중',
  completed: '등록 처리 완료',
  cancelled: '등록 취소',
  interrupted: '서버 재시작으로 중단',
  failed: '실패',
};

/** 소견서 출처 한글 라벨 맵핑 */
const sourceLabels: Record<string, string> = {
  user_authored: '직접 작성한 소견',
  hospital_transcription: '병원 판독 전사 (사용자 입력)',
  personal_note: '개인 메모',
  document_ocr_unverified: '문서 추출·사용자 전사 확인 (의학 검증 전)',
};

/** Intake 컨텍스트 인터페이스 정의 */
interface IntakeContextType {
  connected: boolean;
  studies: Study[];
  selectedStudy: string;
  onStudySelected: (id: string) => void;
  onRefresh: () => void;
  selectedSeriesId: string;
  setSelectedSeriesId: (id: string) => void;
  series: Series[];
  reports: Report[];
  models: Model[];
  jobs: Job[];
  busy: boolean;
  saving: boolean;
  error: string;
  detailError: string;
  message: string;
  detailLoading: boolean;
  text: string;
  setText: (v: string) => void;
  source: string;
  setSource: (v: string) => void;
  importFiles: (files: File[]) => Promise<void>;
  saveReport: () => Promise<void>;
  cancelImport: () => void;
  openSeriesViewer: () => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  loadJobs: () => Promise<void>;
}

const IntakeContext = createContext<IntakeContextType | null>(null);

/** Intake 컨텍스트 커스텀 훅 */
export function useIntake() {
  const context = useContext(IntakeContext);
  if (!context) {
    throw new Error('useIntake must be used within an IntakeProvider');
  }
  return context;
}

/** IntakeProvider 속성 정의 */
interface IntakeProviderProps {
  children: ReactNode;
  connected: boolean;
  studies: Study[];
  selected: string;
  onStudySelected: (value: string) => void;
  onBusyChange: (value: boolean) => void;
  onRefresh: () => void;
  onSeriesSelected: (value: SelectedSeries | null) => void;
}

/**
 * IntakeProvider — DICOM 업로드, 시리즈 선택, 판독문 버전 관리의 상태 허브
 * 하위의 UploadCard, SeriesToolbar, ReportCard, ModelStatusCard에 일관된 상태와 액션을 제공한다.
 */
export function IntakeProvider({
  children,
  connected,
  studies,
  selected,
  onStudySelected,
  onBusyChange,
  onRefresh,
  onSeriesSelected,
}: IntakeProviderProps) {
  const [selectedSeriesId, setSelectedSeriesId] = useState('');
  const [series, setSeries] = useState<Series[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [detailError, setDetailError] = useState('');
  const [text, setText] = useState('');
  const [source, setSource] = useState('user_authored');
  const [message, setMessage] = useState('');
  const [detailLoading, setDetailLoading] = useState(false);

  const cancel = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const activeStudy = useRef(selected);
  activeStudy.current = selected;

  // 작업 상태(업로드 또는 저장 중)를 부모에 전달하여 불필요한 상태 변경 차단
  useEffect(() => {
    onBusyChange(busy || saving);
    return () => onBusyChange(false);
  }, [busy, saving, onBusyChange]);

  /** 최근 등록 작업 이력 조회 */
  async function loadJobs() {
    try {
      const result = await request<{ items: Job[] }>('imports');
      setJobs(result.items);
    } catch {
      // 이력 갱신 실패는 조용히 무시
    }
  }

  // 서버 연결 시 사용 가능한 AI 모델 및 가져오기 작업 이력 로드
  useEffect(() => {
    if (!connected) {
      setModels([]);
      setJobs([]);
      return;
    }
    const control = new AbortController();
    Promise.all([
      request<{ items: Model[] }>('models', control.signal),
      request<{ items: Job[] }>('imports', control.signal),
    ])
      .then(([m, j]) => {
        if (!control.signal.aborted) {
          setModels(m.items);
          setJobs(j.items);
        }
      })
      .catch((e) => {
        if (!control.signal.aborted) setError(e.message);
      });
    return () => control.abort();
  }, [connected]);

  // 선택된 검사가 변경되면 해당 검사의 시리즈 목록과 소견서 버전 이력 조회
  useEffect(() => {
    const control = new AbortController();
    setSeries([]);
    setReports([]);
    setText('');
    setMessage('');
    setDetailError('');
    setSource('user_authored');
    setSelectedSeriesId('');
    onSeriesSelected(null);

    if (!selected || !connected) {
      setDetailLoading(false);
      return;
    }

    setDetailLoading(true);
    Promise.all([
      request<{ items: Series[] }>(`studies/${selected}/series`, control.signal),
      request<{ items: Report[] }>(`studies/${selected}/reports`, control.signal),
    ])
      .then(([s, r]) => {
        if (!control.signal.aborted) {
          setSeries(s.items);
          setReports(r.items);
          // 시리즈가 1개뿐인 경우 사용 편의를 위해 자동 선택
          setSelectedSeriesId(s.items.length === 1 ? s.items[0].id : '');
        }
      })
      .catch((e) => {
        if (!control.signal.aborted) setDetailError(e.message);
      })
      .finally(() => {
        if (!control.signal.aborted) setDetailLoading(false);
      });

    return () => control.abort();
  }, [selected, connected, onSeriesSelected]);

  // Document transcripts append report versions without discarding a draft.
  useEffect(() => {
    const control = new AbortController();
    const reload = () => { if (selected && connected) request<{items: Report[]}>(`studies/${selected}/reports`, control.signal).then(r => { if(!control.signal.aborted) setReports(r.items); }).catch(e => {if(!control.signal.aborted) setDetailError(e.message);}); };
    window.addEventListener('review-updated', reload);
    return () => {control.abort();window.removeEventListener('review-updated', reload);};
  }, [selected, connected]);

  /** DICOM 폴더 또는 다중 파일 가져오기 실행 */
  async function importFiles(files: File[]) {
    if (!files.length || busy) return;
    setBusy(true);
    cancel.current = false;
    setError('');
    let jobId: string | null = null;
    try {
      jobId = (
        await request<{ id: string }>(
          'imports',
          undefined,
          { total: files.length },
          'POST',
        )
      ).id;
      await loadJobs();
      for (const file of files) {
        if (cancel.current) break;
        const response = await fetch(`/api/imports/${jobId}/files`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/octet-stream',
            'X-Workspace-Request': '1',
          },
          body: file,
        });
        if (!response.ok) {
          throw new Error(
            `파일 전송 실패 (${response.status}). 작업 이력을 확인해 주세요.`,
          );
        }
        await loadJobs();
      }
      await request(
        `imports/${jobId}/${cancel.current ? 'cancel' : 'finish'}`,
        undefined,
        {},
        'POST',
      );
      await loadJobs();
      onRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : '등록 중 오류가 발생했습니다.');
      if (jobId) {
        await request(`imports/${jobId}/cancel`, undefined, {}, 'POST').catch(
          () => undefined,
        );
        await loadJobs().catch(() => undefined);
      }
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  /** 판독소견서 새 버전 저장 */
  async function saveReport() {
    const studyId = selected;
    setSaving(true);
    setDetailError('');
    setMessage('');
    try {
      await request(
        `studies/${studyId}/reports`,
        undefined,
        { text, source },
        'POST',
      );
      const result = await request<{ items: Report[] }>(
        `studies/${studyId}/reports`,
      );
      if (activeStudy.current === studyId) {
        setReports(result.items);
        setText('');
        setMessage('새 버전으로 저장했습니다. 이전 입력은 보존됩니다.');
      }
    } catch (e) {
      setError(
        e instanceof Error ? e.message : '저장 실패. 입력 내용은 유지됩니다.',
      );
    } finally {
      setSaving(false);
    }
  }

  /** 시리즈 선택 후 영상 열기 트리거 */
  function openSeriesViewer() {
    const item = series.find((s) => s.id === selectedSeriesId);
    if (item) {
      onSeriesSelected({
        studyId: selected,
        seriesId: item.id,
        description: item.description || '시리즈 설명 미기재',
      });
    }
  }

  const contextValue: IntakeContextType = {
    connected,
    studies,
    selectedStudy: selected,
    onStudySelected,
    onRefresh,
    selectedSeriesId,
    // 사용자가 드롭다운 시리즈를 변경하는 즉시 이전 영상·마스크를 해제한다.
    // 새 시리즈는 사용자가 '영상 열기'로 확정한 뒤에만 열람/분석한다.
    setSelectedSeriesId: (id) => { setSelectedSeriesId(id); onSeriesSelected(null); },
    series,
    reports,
    models,
    jobs,
    busy,
    saving,
    error,
    detailError,
    message,
    detailLoading,
    text,
    setText,
    source,
    setSource,
    importFiles,
    saveReport,
    cancelImport: () => {
      cancel.current = true;
    },
    openSeriesViewer,
    inputRef,
    fileInputRef,
    loadJobs,
  };

  return (
    <IntakeContext.Provider value={contextValue}>
      {children}
    </IntakeContext.Provider>
  );
}

/**
 * UploadCard — DICOM 폴더 및 파일 등록 카드 (사이드바 배치용)
 * 로컬 PC 저장소로의 파일 복사 및 등록 진행률을 시각적으로 표시한다.
 */
export function UploadCard() {
  const {
    connected,
    busy,
    error,
    jobs,
    importFiles,
    cancelImport,
    inputRef,
    fileInputRef,
    loadJobs,
  } = useIntake();

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        bgcolor: '#ffffff',
        borderRadius: 2,
        border: '1px solid',
        borderColor: 'divider',
      }}
    >
      <Stack spacing={1.5}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <CreateNewFolderOutlined color="primary" sx={{ fontSize: 20 }} />
          <Typography variant="subtitle2" fontWeight={700}>
            CT 폴더 등록
          </Typography>
        </Stack>

        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.4 }}>
          선택한 파일은 이 PC의 저장소에 복사됩니다. 원본 폴더는 변경하지 않습니다.
        </Typography>

        {/* 숨김 처리된 파일 및 폴더 선택 인풋 엘리먼트 */}
        <input
          ref={inputRef}
          type="file"
          multiple
          hidden
          aria-label="DICOM 폴더 선택"
          {...({ webkitdirectory: '', directory: '' } as object)}
          onChange={(event) => {
            const files = Array.from(event.target.files || []);
            void importFiles(files);
          }}
        />
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          aria-label="DICOM 파일 선택"
          onChange={(event) => {
            void importFiles(Array.from(event.target.files || []));
          }}
        />

        {/* 업로드 실행 버튼 그룹 */}
        <Stack spacing={1}>
          <Button
            variant="contained"
            fullWidth
            startIcon={<CreateNewFolderOutlined />}
            disabled={!connected || busy}
            onClick={() => inputRef.current?.click()}
            size="small"
          >
            CT 폴더 선택
          </Button>
          <Button
            variant="outlined"
            fullWidth
            startIcon={<UploadFileOutlined />}
            disabled={!connected || busy}
            onClick={() => fileInputRef.current?.click()}
            size="small"
          >
            파일 선택
          </Button>
          {busy && (
            <Button
              color="warning"
              variant="text"
              size="small"
              onClick={cancelImport}
            >
              남은 등록 취소
            </Button>
          )}
        </Stack>

        {error && (
          <Alert severity="error" sx={{ mt: 1, py: 0.5, fontSize: '0.8rem' }}>
            {error}
          </Alert>
        )}

        {/* 최근 등록 작업 상태 및 프로그레스 바 (스크롤 가능하여 사이드바 비대화 방지) */}
        {jobs.length > 0 && (
          <Box sx={{ maxHeight: 180, overflowY: 'auto', pr: 0.5 }}>
            {jobs.slice(0, 3).map((job) => {
              const processed =
                job.imported + job.duplicates + job.excluded + job.failed;
              return (
                <Box
                  key={job.id}
                  sx={{
                    mt: 1,
                    p: 1.2,
                    bgcolor: '#f8fafc',
                    borderRadius: 1.5,
                    border: '1px solid #e2e8f0',
                  }}
                >
                  <Stack direction="row" spacing={0.8} alignItems="center" flexWrap="wrap">
                    <Chip
                      size="small"
                      label={jobLabels[job.status] || job.status}
                      color={job.status === 'completed' ? 'success' : 'default'}
                      sx={{ height: 20, fontSize: '0.72rem' }}
                    />
                    <Typography variant="caption" fontWeight={600}>
                      {processed}/{job.total}개 처리
                    </Typography>
                  </Stack>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: 'block', mt: 0.5, fontSize: '0.72rem' }}
                  >
                    {processed}/{job.total}개 처리 · 등록 {job.imported} · 중복 {job.duplicates} · 제외 {job.excluded} · 실패 {job.failed}
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(100, (processed / (job.total || 1)) * 100)}
                    aria-label="파일 등록 진행률"
                    sx={{ my: 0.8, height: 6, borderRadius: 3 }}
                  />
                  {job.status === 'running' && !busy && (
                    <Button
                      size="small"
                      variant="text"
                      sx={{ fontSize: '0.72rem', p: 0 }}
                      onClick={() => {
                        void request(`imports/${job.id}/cancel`, undefined, {}, 'POST')
                          .then(loadJobs);
                      }}
                    >
                      중단된 전송 취소
                    </Button>
                  )}
                  {job.last_issue && (
                    <Typography variant="caption" color="error" sx={{ display: 'block', fontSize: '0.7rem' }}>
                      {job.last_issue}
                    </Typography>
                  )}
                </Box>
              );
            })}
          </Box>
        )}

        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: 'block', fontSize: '0.72rem', lineHeight: 1.35 }}
        >
          지원: 비압축 단일 프레임 CT · 파일당 32MB · 영상 열기에서 픽셀·절편 간격·방향을 확인합니다.
        </Typography>
      </Stack>
    </Paper>
  );
}

/**
 * SeriesToolbar — 검사 및 시리즈 선택, 영상 열기 및 메타데이터 표시 툴바 (중앙 메인 영역 상단 배치)
 */
export function SeriesToolbar() {
  const {
    connected,
    studies,
    selectedStudy,
    onStudySelected,
    selectedSeriesId,
    setSelectedSeriesId,
    series,
    saving,
    busy,
    detailLoading,
    detailError,
    openSeriesViewer,
  } = useIntake();

  const selectedItem = series.find(
    (item) => !selectedSeriesId || item.id === selectedSeriesId,
  );

  return (
    <Paper
      variant="outlined"
      sx={{
        p: { xs: 2, md: 2.5 },
        mb: 2.5,
        borderRadius: 2.5,
        bgcolor: '#ffffff',
      }}
    >
      <Typography variant="h6" component="h2" sx={{ mb: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
        <TuneOutlined color="primary" sx={{ fontSize: 22 }} />
        CT 영상 및 시리즈 선택
      </Typography>

      <Stack spacing={2}>
        {/* 검사 선택 드롭다운 */}
        <FormControl fullWidth size="small" disabled={!connected || saving || busy}>
          <InputLabel id="study-choice">연결할 검사</InputLabel>
          <Select
            labelId="study-choice"
            label="연결할 검사"
            value={selectedStudy}
            onChange={(event) => onStudySelected(event.target.value)}
          >
            <MenuItem value="">검사를 선택해 주세요</MenuItem>
            {studies.map((study) => (
              <MenuItem key={study.id} value={study.id}>
                {study.study_date || '검사일 미기재'} · {study.description || '설명 미기재'} · {study.id.slice(0, 8)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {/* 시리즈 선택 드롭다운 및 영상 열기 액션 버튼 */}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems="center">
          <FormControl
            fullWidth
            size="small"
            disabled={!selectedStudy || detailLoading || !connected || busy}
          >
            <InputLabel id="series-choice">열람할 시리즈</InputLabel>
            <Select
              labelId="series-choice"
              label="열람할 시리즈"
              value={selectedSeriesId}
              onChange={(e) => setSelectedSeriesId(e.target.value)}
            >
              <MenuItem value="">시리즈를 선택해 주세요</MenuItem>
              {series.map((item) => (
                <MenuItem key={item.id} value={item.id}>
                  {item.description || '시리즈 설명 미기재'} · {item.instance_count}장
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <Button
            variant="contained"
            size="large"
            startIcon={<PlayArrowOutlined />}
            disabled={
              !connected ||
              !selectedSeriesId ||
              detailLoading ||
              busy ||
              !!detailError
            }
            sx={{
              minWidth: 150,
              height: 40,
              whiteSpace: 'nowrap',
              fontWeight: 700,
            }}
            onClick={openSeriesViewer}
          >
            영상 열기
          </Button>
        </Stack>

        {/* 안내 문구 */}
        {!selectedStudy && (
          <Typography variant="caption" color="text.secondary">
            왼쪽 등록된 검사 또는 위 목록에서 검사를 선택하세요.
          </Typography>
        )}
        {selectedStudy && series.length > 1 && !selectedSeriesId && (
          <Typography variant="caption" color="text.secondary">
            시리즈가 여러 개입니다. 열람할 시리즈를 먼저 선택하세요.
          </Typography>
        )}

        {detailLoading && (
          <LinearProgress aria-label="검사 상세 불러오는 중" sx={{ my: 1 }} />
        )}
        {detailError && (
          <Alert severity="error" sx={{ my: 1 }}>
            {detailError}
          </Alert>
        )}

        {/* 선택된 시리즈의 DICOM 촬영 및 재구성 태그 상세 정보 */}
        {selectedStudy && selectedItem && (
          <Box
            sx={{
              p: 1.5,
              bgcolor: '#f8fafc',
              borderRadius: 1.5,
              border: '1px solid #e2e8f0',
            }}
          >
            <Typography variant="body2" fontWeight={700} color="text.primary">
              {selectedItem.description || '시리즈 설명 미기재'} · {selectedItem.instance_count}장
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.3 }}>
              절편 {selectedItem.slice_thickness ? `${selectedItem.slice_thickness} mm` : '미기재'} · 조영 태그 {selectedItem.contrast_agent || '미기재'} · CTPA 여부 미확정
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.2 }}>
              재구성 커널 {selectedItem.convolution_kernel || '미기재'} · 영상 종류 {selectedItem.image_type?.join(' / ') || '미기재'} · 재구성 직경 {selectedItem.reconstruction_diameter ? `${selectedItem.reconstruction_diameter} mm` : '미기재'}
            </Typography>
          </Box>
        )}
      </Stack>
    </Paper>
  );
}

/**
 * ReportCard — 병원 판독소견서 직접 전사 및 개인 메모 작성 패널 (우측 패널 상단 배치)
 * CT 영상을 보면서 바로 오른쪽에 두고 실시간으로 내용을 대조할 수 있도록 지원한다.
 */
export function ReportCard() {
  const {
    selectedStudy,
    reports,
    text,
    setText,
    source,
    setSource,
    saveReport,
    saving,
    detailLoading,
    detailError,
    message,
  } = useIntake();

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2.5,
        mb: 2,
        bgcolor: '#ffffff',
        borderRadius: 2.5,
      }}
    >
      <Stack spacing={2}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <HistoryEduOutlined color="primary" sx={{ fontSize: 22 }} />
          <Typography variant="h6" component="h3">
            병원 판독소견서 입력
          </Typography>
        </Stack>

        {message && (
          <Alert severity="success" sx={{ py: 0.5, fontSize: '0.85rem' }}>
            {message}
          </Alert>
        )}

        {selectedStudy ? (
          <Stack spacing={2}>
            {/* 소견 입력 출처 선택 */}
            <FormControl size="small" fullWidth>
              <InputLabel id="report-source">입력 출처</InputLabel>
              <Select
                labelId="report-source"
                label="입력 출처"
                value={source}
                disabled={saving}
                onChange={(e) => setSource(e.target.value)}
              >
                <MenuItem value="user_authored">직접 작성한 소견</MenuItem>
                <MenuItem value="hospital_transcription">
                  병원 판독소견서 직접 옮겨 적기
                </MenuItem>
                <MenuItem value="personal_note">개인 메모</MenuItem>
              </Select>
            </FormControl>

            {/* 판독 내용 텍스트 입력창 */}
            <TextField
              label="직접 입력한 내용"
              multiline
              minRows={4}
              maxRows={10}
              value={text}
              disabled={saving || detailLoading || !!detailError}
              onChange={(e) => setText(e.target.value)}
              slotProps={{ htmlInput: { maxLength: 100000 } }}
              helperText="직접 입력한 내용은 인증된 병원 원본과 구별해 저장합니다. 검사일과 검사 연결을 확인해 주세요."
              fullWidth
            />

            {/* 새 버전 저장 실행 버튼 */}
            <Button
              startIcon={<SaveOutlined />}
              variant="contained"
              fullWidth
              onClick={() => void saveReport()}
              disabled={
                !text.trim() || saving || detailLoading || !!detailError
              }
            >
              {saving ? '저장 중' : '선택 검사에 새 버전 저장'}
            </Button>

            {/* 저장된 판독소견서 버전 히스토리 (스크롤 가능) */}
            {reports.length > 0 && (
              <Box sx={{ mt: 1 }}>
                <Divider sx={{ my: 1.5 }} />
                <Typography variant="subtitle2" sx={{ mb: 1, fontSize: '0.825rem', color: 'text.secondary' }}>
                  저장된 버전 이력 ({reports.length}개)
                </Typography>
                <Box sx={{ maxHeight: 240, overflowY: 'auto', pr: 0.5 }}>
                  <Stack spacing={1.5}>
                    {reports.map((report, index) => (
                      <Box
                        key={report.id}
                        sx={{
                          p: 1.5,
                          bgcolor: index === 0 ? '#f0fdf4' : '#f8fafc',
                          border: '1px solid',
                          borderColor: index === 0 ? '#bbf7d0' : '#e2e8f0',
                          borderRadius: 1.5,
                        }}
                      >
                        <Stack direction="row" justifyContent="space-between" alignItems="center">
                          <Typography variant="body2" fontWeight={700}>
                            {index === 0 ? '최근 입력' : '이전 입력'} · {sourceLabels[report.source] || '출처 확인 필요'}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {report.created_at} UTC
                          </Typography>
                        </Stack>
                        <Typography
                          sx={{
                            whiteSpace: 'pre-wrap',
                            overflowWrap: 'anywhere',
                            mt: 0.8,
                            fontSize: '0.84rem',
                            lineHeight: 1.5,
                          }}
                        >
                          {report.text}
                        </Typography>
                        <Button
                          size="small"
                          disabled={saving}
                          sx={{ mt: 0.5, p: 0, fontSize: '0.78rem' }}
                          onClick={() => {
                            setText(report.text);
                            setSource(report.source === 'document_ocr_unverified' ? 'user_authored' : report.source);
                          }}
                        >
                          이 내용을 새 버전으로 수정
                        </Button>
                      </Box>
                    ))}
                  </Stack>
                </Box>
              </Box>
            )}
          </Stack>
        ) : (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
            CT를 등록하고 검사를 선택하면 내용을 입력할 수 있습니다.
          </Typography>
        )}
      </Stack>
    </Paper>
  );
}

/**
 * ModelStatusCard — AI 분석 모델 준비 상태 카드 (사이드바 하단 배치)
 */
export function ModelStatusCard() {
  const { connected, models } = useIntake();

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        bgcolor: '#ffffff',
        borderRadius: 2,
        border: '1px solid',
        borderColor: 'divider',
      }}
    >
      <Stack spacing={1.5}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <SmartToyOutlined color="primary" sx={{ fontSize: 20 }} />
          <Typography variant="subtitle2" fontWeight={700}>
            분석 모델 준비 상태
          </Typography>
        </Stack>

        <Stack spacing={1.2}>
          {models.map((model) => (
            <Box
              key={model.id}
              sx={{
                p: 1,
                bgcolor: '#f8fafc',
                borderRadius: 1.2,
                border: '1px solid #e2e8f0',
              }}
            >
              <Stack
                direction="row"
                gap={0.8}
                alignItems="center"
                flexWrap="wrap"
                sx={{ mb: 0.3 }}
              >
                <Typography variant="caption" fontWeight={700}>
                  {model.target}
                </Typography>
                <Chip
                  variant="outlined"
                  size="small"
                  label={model.status === 'ready' ? '실행 준비됨' : model.status === 'not_installed' ? '미설치' : '설정 미완료'}
                  sx={{ height: 20, fontSize: '0.7rem' }}
                />
                <Chip
                  variant="outlined"
                  size="small"
                  label="성능 평가 전"
                  sx={{ height: 20, fontSize: '0.7rem' }}
                />
              </Stack>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: 'block', fontSize: '0.7rem', lineHeight: 1.3 }}
              >
                {model.name} · {model.limitation}
              </Typography>
            </Box>
          ))}
        </Stack>

        {!connected && (
          <Typography variant="caption" color="text.secondary">
            서버 연결 후 확인할 수 있습니다.
          </Typography>
        )}
      </Stack>
    </Paper>
  );
}
