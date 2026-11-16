// AnalysisPanel.tsx — 선택 시리즈의 해부학 실행·버전·원본 격자 마스크 검토.
// OHIF의 영상 열람 기능을 유지하고 별도의 정확한 원본 격자 비교 화면을 제공한다.
// API에서 받은 실제 상태/마스크만 표시하며 미분석을 정상으로 표현하지 않는다.
import { useEffect, useRef, useState } from 'react';
import {
  Alert, Box, Button, Checkbox, Chip, FormControlLabel, LinearProgress,
  MenuItem, Paper, Select, Slider, Stack, TextField, Typography,
} from '@mui/material';
import { request } from './api';
import type { SelectedSeries } from './Viewer';
import { modelTitles, useAnalysisReview, type AnalysisResult as Result, type ModelId } from './AnalysisReview';

/** 진행률 대신 실제 작업 단계와 영속 상태를 보여준다. */
type Run = {
  id: string; series_id: string; model_id: ModelId; status: string; stage: string;
  error: string | null; created_at: string;
};
type Eligibility = { eligible: boolean; reasons: string[] };
type Structure = {
  label: number; title: string; color: string; voxel_count: number;
  volume_ml: number; touches_boundary: boolean;
};
type Slice = {
  width: number; height: number; z: number; hu: number[]; labels: number[];
  components?: number[] | null;
  spacing_xy: number[]; origin_lps_mm: number[];
  column_direction_lps: number[]; row_direction_lps: number[];
  source_instance: { id: string; sop_uid: string };
};
const statuses: Record<string, string> = {
  queued: '대기', running: '실행 중', completed: '분할 완료', failed: '실패', cancelled: '취소',
};
const stages: Record<string, string> = {
  queued: '순서 대기', converting: '원본 검증·HU 변환', inference: '모델 실행·원본 격자 복원',
  completed: '결과 저장 완료', failed: '실패', cancelled: '취소', interrupted: '중단',
};

/** 결과 1개에 고정된 뷰어. 실행 ID를 key로 사용해 이전 마스크를 재사용하지 않는다. */
function MaskView({ result }: { result: Result }) {
  const { selectedFinding } = useAnalysisReview();
  const [z, setZ] = useState(Math.floor(result.shape_xyz[2] / 2));
  const [slice, setSlice] = useState<Slice | null>(null);
  const [error, setError] = useState('');
  const [visible, setVisible] = useState(true);
  const [opacity, setOpacity] = useState(0.4);
  const [enabled, setEnabled] = useState(result.structures.map(s => s.label));
  const [width, setWidth] = useState(1500);
  const [level, setLevel] = useState(-600);
  const canvas = useRef<HTMLCanvasElement>(null);

  // The same representative voxel drives CT navigation, 3D marker and detail.
  // On manual slice navigation the selected candidate remains explicit; its
  // crosshair is drawn only on its actual representative source plane.
  useEffect(() => {
    if (selectedFinding) setZ(selectedFinding.representative_index_xyz[2]);
  }, [selectedFinding?.id]);

  // 슬라이스 전환 중 이전 프레임을 숨기고, 늦게 도착한 응답을 취소한다.
  useEffect(() => {
    const control = new AbortController();
    setSlice(null); setError('');
    request<Slice>(`analyses/${result.run_id}/slices/${z}`, control.signal)
      .then(value => { if (!control.signal.aborted) setSlice(value); })
      .catch(e => { if (!control.signal.aborted) setError(e.message); });
    return () => control.abort();
  }, [result.run_id, z]);

  // CT와 라벨 모두 동일한 YX 순서이다. 영상과 마스크를 따로 확대/뒤집지 않는다.
  useEffect(() => {
    const context = canvas.current?.getContext('2d');
    if (!slice || !context) return;
    const image = context.createImageData(slice.width, slice.height);
    const colors = new Map(result.structures.map(s => [s.label, s.color.match(/[a-f\d]{2}/gi)!.map(c => parseInt(c, 16))]));
    for (let i = 0; i < slice.hu.length; i++) {
      const grey = Math.round(Math.min(1, Math.max(0, (slice.hu[i] - (level - width / 2)) / Math.max(1, width))) * 255);
      const selectedVoxel = selectedFinding && slice.components?.[i] === selectedFinding.selection_label;
      const color = visible && enabled.includes(slice.labels[i]) ? (selectedVoxel ? [255, 235, 40] : colors.get(slice.labels[i])) : undefined;
      for (let channel = 0; channel < 3; channel++) {
        image.data[i * 4 + channel] = color ? Math.round(grey * (1 - opacity) + color[channel] * opacity) : grey;
      }
      image.data[i * 4 + 3] = 255;
    }
    context.putImageData(image, 0, 0);
    if(result.model_id==='monai_nodule')for(const finding of result.findings||[]){
      const bounds=finding.bounds_index_xyz;
      if(bounds&&visible&&bounds[0][2]<=slice.z&&slice.z<=bounds[1][2]){
        context.strokeStyle=selectedFinding?.id===finding.id?'#ffff33':finding.color;context.lineWidth=1;
        context.strokeRect(bounds[0][0],bounds[0][1],bounds[1][0]-bounds[0][0]+1,bounds[1][1]-bounds[0][1]+1);
      }
    }
    if (selectedFinding && selectedFinding.representative_index_xyz[2] === slice.z) {
      const [x, y] = selectedFinding.representative_index_xyz;
      context.strokeStyle = '#ffff33'; context.lineWidth = 1;
      context.beginPath(); context.moveTo(x - 4, y + .5); context.lineTo(x + 5, y + .5);
      context.moveTo(x + .5, y - 4); context.lineTo(x + .5, y + 5); context.stroke();
    }
  }, [slice, visible, enabled, opacity, width, level, result.structures, selectedFinding]);

  return <Stack spacing={1.5}>
    <Typography variant="subtitle2">{result.model_id==='monai_nodule'?'원본 CT 탐지상자 (분할 아님)':'원본 격자 AI 마스크'} · OHIF와 독립된 슬라이스 탐색</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    {!slice && !error && <LinearProgress aria-label="분할 슬라이스 불러오는 중" />}
    <Box sx={{ bgcolor: '#0b1219', minHeight: 200, display: 'flex', justifyContent: 'center', alignItems: 'center' }}
      onWheel={event => { setZ(previous => Math.max(0, Math.min(result.shape_xyz[2] - 1, previous + Math.sign(event.deltaY)))); }}>
      {slice && <canvas ref={canvas} width={slice.width} height={slice.height} aria-label={result.model_id==='monai_nodule'?'원본 CT와 AI 탐지상자':'원본 CT와 AI 분할 마스크'}
        style={{ display: 'block', maxWidth: '100%', width: 'min(100%, 640px)',
          aspectRatio: `${slice.width * slice.spacing_xy[0]} / ${slice.height * slice.spacing_xy[1]}` }} />}
    </Box>
    <Typography variant="body2">분할 슬라이스 {z + 1} / {result.shape_xyz[2]}</Typography>
    {selectedFinding && <Typography variant="caption" data-testid="ct-selected-candidate">CT 선택: {selectedFinding.title} · {selectedFinding.id} · 대표 절편 {selectedFinding.representative_index_xyz[2] + 1}</Typography>}
    <Slider aria-label="분할 슬라이스" min={0} max={result.shape_xyz[2] - 1} step={1} value={z}
      onChange={(_, value) => setZ(value as number)} />
    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
      <FormControlLabel control={<Checkbox checked={visible} onChange={(_, checked) => setVisible(checked)} />} label="AI 마스크 표시" />
      <Button size="small" onClick={() => { setWidth(1500); setLevel(-600); }}>폐창</Button>
      <Button size="small" onClick={() => { setWidth(400); setLevel(40); }}>종격동창</Button>
      <TextField label="마스크 뷰 창 너비" type="number" value={width} onChange={e => setWidth(Math.max(1, Number(e.target.value)))} sx={{ width: 140 }} />
      <TextField label="마스크 뷰 창 중심" type="number" value={level} onChange={e => setLevel(Number(e.target.value))} sx={{ width: 140 }} />
    </Stack>
    <Typography variant="caption">마스크 투명도: {Math.round(opacity * 100)}% 불투명</Typography>
    <Slider aria-label="마스크 불투명도" min={0} max={1} step={0.05} value={opacity} onChange={(_, value) => setOpacity(value as number)} />
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 0.5 }}>
      {result.structures.map(s => <FormControlLabel key={s.label} sx={{ alignItems: 'flex-start', m: 0 }}
        control={<Checkbox size="small" checked={enabled.includes(s.label)} onChange={(_, checked) => setEnabled(previous => checked ? [...previous, s.label] : previous.filter(v => v !== s.label))} sx={{ color: s.color, '&.Mui-checked': { color: s.color } }} />}
        label={<Typography variant="caption">{s.title} · {s.voxel_count ? `${s.volume_ml.toFixed(2)} mL${s.touches_boundary ? ' · 영상 경계 접촉' : ''}` : '영역 미생성 (정상 뜻 아님)'}</Typography>} />)}
    </Box>
    {slice && <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>
      절편 원점 LPS(mm): {slice.origin_lps_mm.map(v => v.toFixed(2)).join(', ')} ·
      열 방향 LPS: {slice.column_direction_lps.map(v => v.toFixed(2)).join(', ')} ·
      행 방향 LPS: {slice.row_direction_lps.map(v => v.toFixed(2)).join(', ')} · 원본 인스턴스: {slice.source_instance.id}
    </Typography>}
    <Typography variant="caption">{result.model_id==='monai_nodule'?'탐지상자는 위치 참조용이며 병변 분할·부피가 아닙니다.':'부피: 원본 격자의 라벨 복셀 수 × 복셀 부피. 영상 경계에 닿는 구조는 부분 부피일 수 있습니다.'}</Typography>
  </Stack>;
}

/** App에서 시리즈 ID를 key로 전달하므로 전환 시 이전 실행/결과/오류가 모두 해제된다. */
export default function AnalysisPanel({ selection, focusRequest }: { selection: SelectedSeries | null; focusRequest?: import('./AnalysisReview').FindingFocus | null }) {
  const { result, publishResult: setResult, selectCandidate, selectedFinding } = useAnalysisReview();
  const [modelId, setModelId] = useState<ModelId>(focusRequest && focusRequest.seriesId === selection?.seriesId ? focusRequest.modelId : 'total');
  const [eligibility, setEligibility] = useState<Eligibility | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [runId, setRunId] = useState(focusRequest && focusRequest.seriesId === selection?.seriesId ? focusRequest.runId : '');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const appliedFocus = useRef<number | null>(null);
  // Loading the exact requested model/run first prevents an automatic "latest"
  // result from substituting a different candidate under a summary card.
  useEffect(() => {
    if (!focusRequest || focusRequest.seriesId !== selection?.seriesId) return;
    setResult(null); setModelId(focusRequest.modelId); setRunId(focusRequest.runId);
    setRuns([]); setError(''); setEligibility(null); setRefresh(v => v + 1);
  }, [focusRequest?.nonce, selection?.seriesId, setResult]);
  useEffect(() => {
    if (!focusRequest || result?.run_id !== focusRequest.runId || appliedFocus.current === focusRequest.nonce) return;
    if (result.findings?.some(f => f.id === focusRequest.findingId)) {
      selectCandidate(focusRequest.findingId); appliedFocus.current = focusRequest.nonce;
    }
  }, [focusRequest, result, selectCandidate]);

  // 종료 시 타이머·요청을 취소한다. 통신 실패 시 완료 상태를 추측하지 않는다.
  useEffect(() => {
    if (!selection) return;
    const control = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let initial = true;
    const load = async () => {
      try {
        const [possible, history] = await Promise.all([
          // Geometry validation reads original pixels; do it once, not every poll.
          initial ? request<Eligibility>(`series/${selection.seriesId}/analysis-eligibility?model_id=${modelId}`, control.signal) : Promise.resolve(null),
          request<{ items: Run[] }>(`series/${selection.seriesId}/analyses`, control.signal),
        ]);
        if (!control.signal.aborted) {
          initial = false;
          if (possible) setEligibility(possible);
          const matching = history.items.filter(r => r.model_id === modelId);
          setRuns(matching); setError('');
          setRunId(previous => previous || matching.find(r => r.status === 'completed')?.id || '');
        }
      } catch (e) {
        if (!control.signal.aborted) { initial = true; setEligibility(null); setError(e instanceof Error ? e.message : '분석 상태 조회 실패'); }
      } finally {
        if (!control.signal.aborted) timer = setTimeout(load, 4000);
      }
    };
    void load();
    return () => { control.abort(); clearTimeout(timer); };
  }, [selection, refresh, modelId]);

  const selected = runs.find(r => r.id === runId);
  const selectedStatus = selected?.status;
  useEffect(() => {
    setResult(null); setLoading(false);
    if (!runId || selectedStatus !== 'completed') return;
    const control = new AbortController();
    setLoading(true);
    request<Result>(`analyses/${runId}/result`, control.signal)
      .then(value => { if (!control.signal.aborted && value.series_id === selection?.seriesId && value.model_id === modelId) setResult(value); })
      .catch(e => { if (!control.signal.aborted) setError(e.message); })
      .finally(() => { if (!control.signal.aborted) setLoading(false); });
    return () => control.abort();
  }, [runId, selectedStatus, selection, modelId, setResult]);

  async function action(id?: string) {
    if (!selection) return;
    setBusy(true); setError('');
    try {
      const run = id
        ? await request<Run>(`analyses/${id}/cancel`, undefined, {}, 'POST')
        : await request<Run>(`series/${selection.seriesId}/analyses`, undefined, { model_id: modelId, confirmed }, 'POST');
      if (mounted.current) { setRunId(run.id); setRefresh(v => v + 1); }
    } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : '분석 요청 실패'); }
    finally { if (mounted.current) setBusy(false); }
  }

  const active = runs.find(r => ['queued', 'running'].includes(r.status));
  return <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.5 }, mb: 2.5 }}>
    <Stack spacing={1.5}>
      <Typography variant="h6" component="h2">{modelId === 'total' ? 'AI 해부학 분할' : `${modelTitles[modelId]} 분석`}</Typography>
      <Select value={modelId} size="small" inputProps={{ 'aria-label': '분석 모델' }} disabled={busy}
        onChange={e => {
          // Invalidate every dependent panel synchronously on model selection.
          setResult(null); setRunId(''); setRuns([]); setEligibility(null); setError(''); setConfirmed(false);
          setModelId(e.target.value as ModelId);
        }}>
        {Object.entries(modelTitles).map(([id, title]) => <MenuItem key={id} value={id}>{title}</MenuItem>)}
      </Select>
      <Typography variant="body2" color="text.secondary">{modelId === 'total'
        ? 'TotalSegmentator · 3 mm · 폐엽 5개 / 기관 / 심장 / 대동맥. 해부학 분할이며 질환 판정이 아닙니다.'
        : modelId==='monai_nodule'?'MONAI 독립 탐지상자와 모델 점수입니다. 분할 크기/부피·악성 확률을 제공하지 않습니다.': '검토 전 AI 분할 후보입니다. 후보 없음은 질환 배제가 아니며 탐지 점수·악성 확률을 제공하지 않습니다.'}</Typography>
      {!selection ? <Alert severity="info">‘영상 열기’로 분석할 시리즈를 먼저 선택하세요.</Alert> : <>
        <Typography variant="body2">선택 시리즈: {selection.description || '설명 미기재'}</Typography>
        {error && <Alert severity="error" action={<Button onClick={() => setRefresh(v => v + 1)}>재시도</Button>}>{error}</Alert>}
        {!eligibility && !error && <LinearProgress aria-label="분석 가능 여부 확인 중" />}
        {eligibility?.reasons.map(reason => <Alert key={reason} severity="warning">{reason}</Alert>)}
        <FormControlLabel control={<Checkbox checked={confirmed} onChange={(_, checked) => setConfirmed(checked)} />}
          label={modelId === 'total' ? '선택 시리즈와 해부학 분할의 한계를 확인했습니다' : '선택한 흉부 시리즈와 후보 분석의 한계를 확인했습니다'} />
        <Stack direction="row" spacing={1}>
          <Button variant="contained" disabled={!eligibility?.eligible || !confirmed || busy || !!active || !!error} onClick={() => void action()}>
            {modelId === 'total' ? (runs.length ? '새 버전으로 해부학 분할' : '해부학 분할 실행') : `${modelTitles[modelId]} 분석 실행`}
          </Button>
          {active && <Button disabled={busy} color="warning" onClick={() => void action(active.id)}>분석 취소</Button>}
        </Stack>
        {active && <><Chip label={`${statuses[active.status]} · ${stages[active.stage] || active.stage}`} /><LinearProgress aria-label="해부학 분할 처리 중" /></>}
        {runs.length === 0 && <Typography variant="body2">분석 이력이 없습니다. 현재 상태로 정상 여부를 판단하지 않습니다.</Typography>}
        {runs.length > 0 && <Select size="small" displayEmpty value={runId} inputProps={{ 'aria-label': modelId === 'total' ? '해부학 분석 실행 버전' : '후보 분석 실행 버전' }} onChange={e => { setResult(null); setRunId(e.target.value); }}>
          <MenuItem value="">결과를 선택하세요</MenuItem>
          {runs.map(r => <MenuItem key={r.id} value={r.id}>{r.created_at} UTC · {statuses[r.status] || r.status} · {r.id.slice(0, 8)}</MenuItem>)}
        </Select>}
        {selected?.error && <Alert severity="error">{selected.error}</Alert>}
        {selected && selected.status !== 'completed' && <Typography variant="body2">{statuses[selected.status]} · 완료된 분할 결과가 없습니다.</Typography>}
        {loading && <LinearProgress aria-label="해부학 결과 불러오는 중" />}
        {result && <>
          <Typography variant="caption">{result.metrics.elapsed_seconds === null || result.metrics.cuda_peak_allocated_bytes === null
            ? '추론 실측값 없음 · 합성 검증 자료'
            : `실제 추론 ${result.metrics.elapsed_seconds.toFixed(1)}초 · CUDA 최대 할당 ${(result.metrics.cuda_peak_allocated_bytes / 1024 ** 3).toFixed(2)} GiB`}</Typography>
          {result.limitations.map(text => <Typography key={text} variant="caption" color="text.secondary">{text}</Typography>)}
          {result.model_id !== 'total' && <>
            <Typography variant="subtitle2">이번 실행의 AI 후보: {result.finding_count}개</Typography>
            {result.model_id === 'pleural_pericard_effusion' && <Typography variant="caption">삼출은 종류별 합산 영역입니다. 표시 개수는 독립 병변 개수가 아닙니다.</Typography>}
            {result.finding_status === 'no_candidates' && <Alert severity="info">후보 없음 · 이 모델에서 영역이 생성되지 않았습니다. 정상 판정·질환 배제가 아닙니다.</Alert>}
            <Stack direction="row" flexWrap="wrap" useFlexGap gap={1}>
              {result.findings?.map(finding => <Button key={finding.id} size="small" variant={selectedFinding?.id === finding.id ? 'contained' : 'outlined'}
                sx={selectedFinding?.id === finding.id ? { bgcolor: 'primary.dark', color: 'primary.contrastText' } : undefined}
                aria-pressed={selectedFinding?.id === finding.id} onClick={() => selectCandidate(finding.id)}>
                {finding.title}{finding.diameter_mm !== null ? ` · ${finding.diameter_mm.toFixed(2)} mm` : finding.volume_ml!==null?` · ${finding.volume_ml.toFixed(2)} mL`:` · 점수 ${finding.score?.toFixed(3)}`}
              </Button>)}
            </Stack>
            <Typography variant="caption">후보를 선택하면 아래 CT 마스크 뷰·오른쪽 3D 표식·상세가 연결됩니다. OHIF 탐색은 독립적입니다.</Typography>
          </>}
          <MaskView key={result.run_id} result={result} />
        </>}
      </>}
    </Stack>
  </Paper>;
}
