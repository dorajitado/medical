import { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Chip, Divider, FormControl, InputLabel, LinearProgress, MenuItem, Paper, Select, Stack, TextField, Typography } from '@mui/material';
import { CreateNewFolderOutlined, SaveOutlined } from '@mui/icons-material';
import { request, type Study } from './api';
import type { SelectedSeries } from './Viewer';

type Job = { id: string; status: string; total: number; imported: number; duplicates: number; excluded: number; failed: number; last_issue: string | null };
type Series = { id: string; description: string | null; instance_count: number; slice_thickness: string | null; contrast_agent: string | null; validation: string; ctpa: string; convolution_kernel: string|null; image_type: string[]; reconstruction_diameter: string|null };
type Report = { id: string; text: string; source: string; created_at: string };
type Model = { id: string; name: string; target: string; status: string; limitation: string; package_version: string | null; weights_sha256: string | null; validation_status: string };
const jobLabels: Record<string, string> = { running: '등록 중', completed: '등록 처리 완료', cancelled: '등록 취소', interrupted: '서버 재시작으로 중단', failed: '실패' };
const sourceLabels: Record<string, string> = { user_authored: '직접 작성한 소견', hospital_transcription: '병원 판독 전사 (사용자 입력)', personal_note: '개인 메모' };

export default function IntakePanel({ connected, studies, selected, onStudySelected, onBusyChange, onRefresh, onSeriesSelected }: { connected: boolean; studies: Study[]; selected:string; onStudySelected:(value:string)=>void; onBusyChange:(value:boolean)=>void; onRefresh: () => void; onSeriesSelected: (value:SelectedSeries|null)=>void }) {
  const [selectedSeriesId,setSelectedSeriesId]=useState('');
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
  const input = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const activeStudy=useRef(selected);
  activeStudy.current=selected;
  useEffect(()=>{onBusyChange(busy||saving);return()=>onBusyChange(false);},[busy,saving,onBusyChange]);
  async function loadJobs() { const result = await request<{ items: Job[] }>('imports'); setJobs(result.items); }
  useEffect(() => {
    if (!connected) { setModels([]); setJobs([]); return; }
    const control = new AbortController();
    Promise.all([request<{ items: Model[] }>('models', control.signal), request<{ items: Job[] }>('imports', control.signal)])
      .then(([m, j]) => { if (!control.signal.aborted) { setModels(m.items); setJobs(j.items); } })
      .catch(e => { if (!control.signal.aborted) setError(e.message); });
    return () => control.abort();
  }, [connected]);
  useEffect(() => {
    const control = new AbortController();
    setSeries([]); setReports([]); setText(''); setMessage(''); setDetailError(''); setSource('user_authored');
    setSelectedSeriesId('');
    onSeriesSelected(null);
    if (!selected || !connected) { setDetailLoading(false); return; }
    setDetailLoading(true);
    Promise.all([request<{ items: Series[] }>(`studies/${selected}/series`, control.signal), request<{ items: Report[] }>(`studies/${selected}/reports`, control.signal)])
      .then(([s, r]) => { if (!control.signal.aborted) { setSeries(s.items); setReports(r.items); setSelectedSeriesId(s.items.length===1?s.items[0].id:''); } })
      .catch(e => { if (!control.signal.aborted) setDetailError(e.message); })
      .finally(() => { if (!control.signal.aborted) setDetailLoading(false); });
    return () => control.abort();
  }, [selected, connected, onSeriesSelected]);

  async function importFiles(files: File[]) {
    if (!files.length || busy) return;
    setBusy(true); cancel.current = false; setError('');
    let jobId: string | null = null;
    try {
      jobId = (await request<{ id: string }>('imports', undefined, { total: files.length }, 'POST')).id;
      await loadJobs();
      for (const file of files) {
        if (cancel.current) break;
        const response = await fetch(`/api/imports/${jobId}/files`, { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-Workspace-Request': '1' }, body: file });
        if (!response.ok) throw new Error(`파일 전송 실패 (${response.status}). 작업 이력을 확인해 주세요.`);
        await loadJobs();
      }
      await request(`imports/${jobId}/${cancel.current ? 'cancel' : 'finish'}`, undefined, {}, 'POST');
      await loadJobs();
      onRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : '등록 중 오류가 발생했습니다.');
      if (jobId) {
        await request(`imports/${jobId}/cancel`, undefined, {}, 'POST').catch(() => undefined);
        await loadJobs().catch(() => undefined);
      }
    } finally { setBusy(false); if (input.current) input.current.value = ''; if (fileInput.current) fileInput.current.value = ''; }
  }
  async function saveReport() {
    const studyId = selected;
    setSaving(true); setDetailError(''); setMessage('');
    try {
      await request(`studies/${studyId}/reports`, undefined, { text, source }, 'POST');
      const result = await request<{ items: Report[] }>(`studies/${studyId}/reports`);
      if(activeStudy.current===studyId){setReports(result.items); setText(''); setMessage('새 버전으로 저장했습니다. 이전 입력은 보존됩니다.');}
    } catch (e) { setError(e instanceof Error ? e.message : '저장 실패. 입력 내용은 유지됩니다.'); }
    finally { setSaving(false); }
  }
  return <Stack spacing={2} sx={{ mb: 3 }}>
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={2}>
        <Box><Typography variant="h6">CT 폴더 등록</Typography><Typography variant="body2" color="text.secondary">선택한 파일은 이 PC의 저장소에 복사됩니다. 원본 폴더는 변경하지 않습니다.</Typography></Box>
        <Stack direction="row" spacing={1}>
          <input ref={input} type="file" multiple hidden aria-label="DICOM 폴더 선택" {...({ webkitdirectory: '', directory: '' } as object)} onChange={event => { const files = Array.from(event.target.files || []); void importFiles(files); }}/>
          <input ref={fileInput} type="file" multiple hidden aria-label="DICOM 파일 선택" onChange={event => { void importFiles(Array.from(event.target.files || [])); }}/>
          <Button variant="contained" startIcon={<CreateNewFolderOutlined/>} disabled={!connected || busy} onClick={() => input.current?.click()}>CT 폴더 선택</Button>
          <Button disabled={!connected || busy} onClick={() => fileInput.current?.click()}>파일 선택</Button>
          {busy && <Button onClick={() => { cancel.current = true; }}>남은 등록 취소</Button>}
        </Stack>
      </Stack>
      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      {jobs.slice(0, 3).map(job => {
        const processed = job.imported + job.duplicates + job.excluded + job.failed;
        return <Box key={job.id} sx={{ mt: 2 }}><Stack direction="row" gap={1} flexWrap="wrap"><Chip label={jobLabels[job.status] || job.status}/><Typography variant="body2">{processed}/{job.total}개 처리 · 등록 {job.imported} · 중복 {job.duplicates} · 제외 {job.excluded} · 실패 {job.failed}</Typography>{job.status === 'running' && !busy && <Button size="small" onClick={() => { void request(`imports/${job.id}/cancel`, undefined, {}, 'POST').then(loadJobs).catch(e => setError(e.message)); }}>중단된 전송 취소</Button>}</Stack><LinearProgress variant="determinate" value={Math.min(100, processed / job.total * 100)} aria-label="파일 등록 진행률" sx={{ my: 1 }}/>{job.last_issue && <Typography variant="caption" color="text.secondary">{job.last_issue}</Typography>}</Box>;
      })}
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>지원: 비압축 단일 프레임 CT · 파일당 32MB · 영상 열기에서 픽셀·절편 간격·방향을 확인합니다.</Typography>
    </Paper>
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>CT 열람 · 판독소견서 입력</Typography>
      <FormControl fullWidth size="small" disabled={!connected || saving || busy}><InputLabel id="study-choice">연결할 검사</InputLabel><Select labelId="study-choice" label="연결할 검사" value={selected} onChange={event => { onStudySelected(event.target.value); }}><MenuItem value="">검사를 선택해 주세요</MenuItem>{studies.map(study => <MenuItem key={study.id} value={study.id}>{study.study_date || '검사일 미기재'} · {study.description || '설명 미기재'} · {study.id.slice(0,8)}</MenuItem>)}</Select></FormControl>
      <Stack direction={{xs:'column',sm:'row'}} spacing={1.5} sx={{mt:2}}>
        <FormControl fullWidth size="small" disabled={!selected||detailLoading||!connected||busy}><InputLabel id="series-choice">열람할 시리즈</InputLabel><Select labelId="series-choice" label="열람할 시리즈" value={selectedSeriesId} onChange={e=>{setSelectedSeriesId(e.target.value);onSeriesSelected(null);}}><MenuItem value="">시리즈를 선택해 주세요</MenuItem>{series.map(item=><MenuItem key={item.id} value={item.id}>{item.description||'시리즈 설명 미기재'} · {item.instance_count}장</MenuItem>)}</Select></FormControl>
        <Button variant="contained" size="large" disabled={!connected||!selectedSeriesId||detailLoading||busy||!!detailError} sx={{minWidth:150,whiteSpace:'nowrap'}} onClick={()=>{const item=series.find(s=>s.id===selectedSeriesId);if(item)onSeriesSelected({studyId:selected,seriesId:item.id,description:item.description||'시리즈 설명 미기재'});}}>영상 열기</Button>
      </Stack>
      {!selected&&<Typography variant="caption" color="text.secondary" sx={{display:'block',mt:1}}>왼쪽 등록된 검사 또는 위 목록에서 검사를 선택하세요.</Typography>}
      {selected&&series.length>1&&!selectedSeriesId&&<Typography variant="caption" color="text.secondary" sx={{display:'block',mt:1}}>시리즈가 여러 개입니다. 열람할 시리즈를 먼저 선택하세요.</Typography>}
      {detailLoading && <LinearProgress aria-label="검사 상세 불러오는 중" sx={{ mt: 2 }}/ >}
      {detailError && <Alert severity="error" sx={{ mt: 2 }}>{detailError}</Alert>}
      {message && <Alert severity="success" sx={{ mt: 2 }}>{message}</Alert>}
      {selected && <Stack spacing={2} sx={{ mt: 2 }}>
        {series.filter(item=>!selectedSeriesId||item.id===selectedSeriesId).map(item => <Box key={item.id}><Typography variant="body2" fontWeight={600}>{item.description || '시리즈 설명 미기재'} · {item.instance_count}장</Typography><Typography variant="caption" color="text.secondary">절편 {item.slice_thickness ? `${item.slice_thickness} mm` : '미기재'} · 조영 태그 {item.contrast_agent || '미기재'} · CTPA 여부 미확정</Typography><Typography variant="caption" color="text.secondary" sx={{display:'block'}}>재구성 커널 {item.convolution_kernel||'미기재'} · 영상 종류 {item.image_type?.join(' / ')||'미기재'} · 재구성 직경 {item.reconstruction_diameter?`${item.reconstruction_diameter} mm`:'미기재'}</Typography></Box>)}
        <Divider/>
        <FormControl size="small"><InputLabel id="report-source">입력 출처</InputLabel><Select labelId="report-source" label="입력 출처" value={source} disabled={saving} onChange={e => setSource(e.target.value)}><MenuItem value="user_authored">직접 작성한 소견</MenuItem><MenuItem value="hospital_transcription">병원 판독소견서 직접 옮겨 적기</MenuItem><MenuItem value="personal_note">개인 메모</MenuItem></Select></FormControl>
        <TextField label="직접 입력한 내용" multiline minRows={5} value={text} disabled={saving || detailLoading || !!detailError} onChange={e => setText(e.target.value)} slotProps={{ htmlInput: { maxLength: 100000 } }} helperText="직접 입력한 내용은 인증된 병원 원본과 구별해 저장합니다. 검사일과 검사 연결을 확인해 주세요."/>
        <Button startIcon={<SaveOutlined/>} variant="contained" onClick={() => void saveReport()} disabled={!text.trim() || saving || detailLoading || !!detailError}>{saving ? '저장 중' : '선택 검사에 새 버전 저장'}</Button>
        {reports.map((report, index) => <Box key={report.id}><Typography variant="body2" fontWeight={600}>{index === 0 ? '최근 입력' : '이전 입력'} · {sourceLabels[report.source] || '출처 확인 필요'}</Typography><Typography variant="caption" color="text.secondary">{report.created_at} UTC</Typography><Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', mt: .5 }}>{report.text}</Typography><Button size="small" disabled={saving} onClick={() => { setText(report.text); setSource(report.source); }}>이 내용을 새 버전으로 수정</Button></Box>)}
      </Stack>}
      {!selected && <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>CT를 등록하고 검사를 선택하면 내용을 입력할 수 있습니다.</Typography>}
    </Paper>
    <Paper variant="outlined" sx={{ p: 2.5 }}><Typography variant="h6">분석 모델 준비 상태</Typography><Stack spacing={1.5} sx={{ mt: 2 }}>{models.map(model => <Box key={model.id}><Stack direction="row" gap={1} alignItems="center" flexWrap="wrap"><Typography variant="body2" fontWeight={600}>{model.target}</Typography><Chip variant="outlined" label={model.status === 'not_installed' ? '미설치' : '설정 미완료'}/><Chip variant="outlined" label="성능 평가 전"/></Stack><Typography variant="caption" color="text.secondary">{model.name} · {model.limitation}</Typography></Box>)}</Stack>{!connected && <Typography variant="body2" color="text.secondary">서버 연결 후 확인할 수 있습니다.</Typography>}</Paper>
  </Stack>;
}
