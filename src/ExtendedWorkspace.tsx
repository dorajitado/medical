/** Independent model comparison and prior-study review. The user explicitly
 * links lesions; missing geometry or a box-only result never becomes growth. */
import { useEffect, useState } from 'react';
import { Accordion, AccordionSummary, AccordionDetails, Alert, Button, Checkbox, FormControlLabel, LinearProgress, MenuItem, Select, Stack, TextField, Typography } from '@mui/material';
import { ExpandMore } from '@mui/icons-material';
import { request } from './api';
import { useIntake } from './IntakePanel';
type D=Record<string,any>;
const title=(r:D)=>`${r.model_id} · ${r.created_at} · ${r.id.slice(0,8)}`;
export default function ExtendedWorkspace({section}:{section?:'models'|'prior'|'evaluation'}){
  const {selectedStudy:study,selectedSeriesId:series,studies}=useIntake();
  const [runs,setRuns]=useState<D[]>([]),[left,setLeft]=useState(''),[right,setRight]=useState('');
  const [manualLeft,setManualLeft]=useState(''),[manualRight,setManualRight]=useState(''),[landmarks,setLandmarks]=useState('');
  const [modelHistory,setModelHistory]=useState<D[]>([]),[modelId,setModelId]=useState(''),[edges,setEdges]=useState<D[]>([]);
  const [priorStudy,setPriorStudy]=useState(''),[priorSeries,setPriorSeries]=useState<D[]>([]),[priorSeriesId,setPriorSeriesId]=useState(''),[priorRuns,setPriorRuns]=useState<D[]>([]);
  const [currentRun,setCurrentRun]=useState(''),[priorRun,setPriorRun]=useState(''),[currentFindings,setCurrentFindings]=useState<D[]>([]),[priorFindings,setPriorFindings]=useState<D[]>([]);
  const [currentFinding,setCurrentFinding]=useState(''),[priorFinding,setPriorFinding]=useState(''),[reason,setReason]=useState(''),[samePatient,setSamePatient]=useState(false),[priorHistory,setPriorHistory]=useState<D[]>([]);
  const [capabilities,setCapabilities]=useState<D[]>([]),[evaluation,setEvaluation]=useState<D|null>(null),[split,setSplit]=useState('test');
  const [patientGroup,setPatientGroup]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[refresh,setRefresh]=useState(0);
  const model=modelHistory.find(m=>m.id===modelId);
  /** Each effect is cancelled when its actual source ID changes. The component
   * is also keyed by study so a prior-study confirmation never carries over. */
  useEffect(()=>{const c=new AbortController();setRuns([]);setLeft('');setRight('');setCurrentRun('');if(series)request<D>(`series/${series}/analyses`,c.signal).then(r=>{if(!c.signal.aborted)setRuns(r.items.filter((r:D)=>r.status==='completed'));}).catch(e=>{if(!c.signal.aborted)setError(e.message);});return()=>c.abort();},[series,refresh]);
  useEffect(()=>{const c=new AbortController();if(study)Promise.all([request<D>(`studies/${study}/model-comparisons`,c.signal),request<D>(`studies/${study}/longitudinal`,c.signal),request<D>('capabilities',c.signal),request<D>('evaluation',c.signal)]).then(([m,p,cap,ev])=>{if(c.signal.aborted)return;setModelHistory(m.items);setModelId(v=>m.items.some((x:D)=>x.id===v)?v:m.items[0]?.id||'');setPriorHistory(p.items);setCapabilities(cap.items);setEvaluation(ev);}).catch(e=>{if(!c.signal.aborted)setError(e.message);});return()=>c.abort();},[study,refresh]);
  useEffect(()=>{setEdges(model?structuredClone(model.payload.edges):[]);},[model]);
  useEffect(()=>{const c=new AbortController();setPriorSeries([]);setPriorSeriesId('');setSamePatient(false);if(priorStudy)request<D>(`studies/${priorStudy}/series`,c.signal).then(r=>{if(!c.signal.aborted)setPriorSeries(r.items);}).catch(e=>{if(!c.signal.aborted)setError(e.message);});return()=>c.abort();},[priorStudy]);
  useEffect(()=>{const c=new AbortController();setPriorRuns([]);setPriorRun('');if(priorSeriesId)request<D>(`series/${priorSeriesId}/analyses`,c.signal).then(r=>{if(!c.signal.aborted)setPriorRuns(r.items.filter((x:D)=>x.status==='completed'));}).catch(e=>{if(!c.signal.aborted)setError(e.message);});return()=>c.abort();},[priorSeriesId]);
  useEffect(()=>{const c=new AbortController();setCurrentFindings([]);setCurrentFinding('');if(currentRun)request<D>(`analyses/${currentRun}/result`,c.signal).then(r=>{if(!c.signal.aborted)setCurrentFindings(r.findings);}).catch(e=>{if(!c.signal.aborted)setError(e.message);});return()=>c.abort();},[currentRun]);
  useEffect(()=>{const c=new AbortController();setPriorFindings([]);setPriorFinding('');if(priorRun)request<D>(`analyses/${priorRun}/result`,c.signal).then(r=>{if(!c.signal.aborted)setPriorFindings(r.findings);}).catch(e=>{if(!c.signal.aborted)setError(e.message);});return()=>c.abort();},[priorRun]);
  async function act(fn:()=>Promise<void>){setBusy(true);setError('');setMessage('');try{await fn();setRefresh(v=>v+1);}catch(e){setError(e instanceof Error?e.message:'처리 실패');}finally{setBusy(false);}}
  const runSelect=(label:string,value:string,set:(v:string)=>void,items:D[])=><Select displayEmpty disabled={busy||!items.length} value={value} onChange={e=>set(e.target.value)} inputProps={{'aria-label':label}}><MenuItem value="">{label}</MenuItem>{items.map(r=><MenuItem key={r.id} value={r.id}>{title(r)}</MenuItem>)}</Select>;
  return <Stack spacing={2} sx={{mt:2}}>
    {busy&&<LinearProgress aria-label="확장 검토 처리 중"/>}{error&&<Alert severity="error" action={<Button onClick={()=>setRefresh(v=>v+1)}>다시 조회</Button>}>{error}</Alert>}{message&&<Alert>{message}</Alert>}
    {(!section||section==='models')&&<Accordion key="models" defaultExpanded={!!section}><AccordionSummary expandIcon={<ExpandMore/>}><Typography>독립 결절 모델 비교</Typography></AccordionSummary><AccordionDetails><Stack spacing={2}>
      <Typography variant="body2">분할 모델과 MONAI 탐지상자를 독립적으로 검토합니다. 점수 평균·악성 확률·탐지상자 부피는 생성하지 않습니다.</Typography>
      {runSelect('분할 모델 실행',left,setLeft,runs.filter(r=>r.model_id==='lung_nodules'))}{runSelect('MONAI 모델 실행',right,setRight,runs.filter(r=>r.model_id==='monai_nodule'))}
      <Button disabled={busy||!left||!right} onClick={()=>act(async()=>{const r=await request<D>(`studies/${study}/model-comparisons`,undefined,{run_ids:[left,right]},'POST');setModelId(r.id);})}>동일 원본의 두 모델 비교</Button>
      {!!modelHistory.length&&<Select value={modelId} onChange={e=>setModelId(e.target.value)} inputProps={{'aria-label':'모델 대조 버전'}}>{modelHistory.map(m=><MenuItem key={m.id} value={m.id}>{m.created_at} · {m.id.slice(0,8)}</MenuItem>)}</Select>}
      {model&&<>{model.payload.groups.map((group:D[],index:number)=><Stack key={index}><Typography variant="subtitle2">{model.payload.runs[index].model_id} · 후보 {group.length}개</Typography>{group.map(f=><Typography key={f.ref} variant="body2">{f.title} · 점수 {f.score??'미제공'} · 장경 {f.diameter_mm??'측정 해당 없음'} · 부피 {f.volume_mm3??'측정 해당 없음'}</Typography>)}</Stack>)}
        <Typography variant="body2">자동 제안에 없는 후보도 직접 연결할 수 있습니다.</Typography>
        {[0,1].map((group:number)=><Select key={group} displayEmpty value={group===0?manualLeft:manualRight} onChange={e=>group===0?setManualLeft(e.target.value):setManualRight(e.target.value)} inputProps={{'aria-label':`수동 모델 후보 ${group+1}`}}><MenuItem value="">모델 {group+1} 후보 선택</MenuItem>{model.payload.groups[group].map((f:D)=><MenuItem key={f.ref} value={f.ref}>{f.title}</MenuItem>)}</Select>)}
        <Button disabled={!manualLeft||!manualRight||edges.some(e=>e.left===manualLeft&&e.right===manualRight)} onClick={()=>setEdges(old=>[...old,{left:manualLeft,right:manualRight,state:'proposed',reason:'사용자 수동 연결 — 원본 위치 확인 필요'}])}>수동 연결 후보 추가</Button>
        {edges.map((edge,index)=><Stack key={index} spacing={1}><Typography variant="caption" sx={{overflowWrap:'anywhere'}}>{edge.left} ↔ {edge.right} · {edge.distance_mm?.toFixed(2)??'수동'} mm</Typography><Select value={edge.state} onChange={e=>setEdges(old=>old.map((v,i)=>i===index?{...v,state:e.target.value}:v))} inputProps={{'aria-label':`모델 연결 ${index+1} 상태`}}><MenuItem value="proposed">연결 후보</MenuItem><MenuItem value="confirmed">사용자 확인</MenuItem><MenuItem value="rejected">연결 거절</MenuItem></Select><TextField label={`모델 연결 ${index+1} 근거`} value={edge.reason} onChange={e=>setEdges(old=>old.map((v,i)=>i===index?{...v,reason:e.target.value}:v))}/></Stack>)}
        <Button disabled={busy} onClick={()=>act(async()=>{const r=await request<D>(`model-comparisons/${model.id}/links`,undefined,{edges},'PUT');setModelId(r.id);})}>모델 연결 검토 새 버전 저장</Button>
        {model.payload.limitations.map((t:string)=><Typography variant="caption" key={t}>{t}</Typography>)}</>}
    </Stack></AccordionDetails></Accordion>}
    {(!section||section==='prior')&&<Accordion key="prior" defaultExpanded={!!section}><AccordionSummary expandIcon={<ExpandMore/>}><Typography>이전 CT · 병변 변화 검토</Typography></AccordionSummary><AccordionDetails><Stack spacing={2}>
      <Typography variant="body2">서로 다른 검사의 LPS 좌표만으로 같은 병변이라 가정하지 않습니다. 원본 영상에서 동일 환자·병변을 확인한 연결만 계산하며 자동 영상 정렬은 적용하지 않습니다.</Typography>
      <Select displayEmpty value={priorStudy} onChange={e=>setPriorStudy(e.target.value)} inputProps={{'aria-label':'이전 검사'}}><MenuItem value="">이전 검사 선택</MenuItem>{studies.filter(s=>s.id!==study).map(s=><MenuItem key={s.id} value={s.id}>{s.study_date||'날짜 미상'} · {s.description||s.id.slice(0,8)}</MenuItem>)}</Select>
      <Select displayEmpty value={priorSeriesId} onChange={e=>setPriorSeriesId(e.target.value)} inputProps={{'aria-label':'이전 시리즈'}}><MenuItem value="">이전 시리즈 선택</MenuItem>{priorSeries.map(s=><MenuItem key={s.id} value={s.id}>{s.description||s.id.slice(0,8)}</MenuItem>)}</Select>
      {runSelect('현재 검사 실행',currentRun,setCurrentRun,runs)}{runSelect('이전 검사 실행',priorRun,setPriorRun,priorRuns)}
      <Select displayEmpty value={currentFinding} onChange={e=>setCurrentFinding(e.target.value)} inputProps={{'aria-label':'현재 후보'}}><MenuItem value="">현재 병변 선택</MenuItem>{currentFindings.map(f=><MenuItem key={f.id} value={f.id}>{f.title}</MenuItem>)}</Select>
      <Select displayEmpty value={priorFinding} onChange={e=>setPriorFinding(e.target.value)} inputProps={{'aria-label':'이전 후보'}}><MenuItem value="">이전 병변 선택</MenuItem>{priorFindings.map(f=><MenuItem key={f.id} value={f.id}>{f.title}</MenuItem>)}</Select>
      <FormControlLabel control={<Checkbox checked={samePatient} onChange={e=>setSamePatient(e.target.checked)}/>} label="같은 환자의 이전 검사이며 선택한 두 후보가 동일 병변임을 원본 영상으로 확인했습니다"/>
      <TextField label="정합 기준점 (선택)" multiline minRows={3} value={landmarks} onChange={e=>setLandmarks(e.target.value)} helperText="한 줄에 현재 X Y Z, 이전 X Y Z (LPS mm) 6개를 입력. 3쌍 이상·비공선 기준점 필요. 미입력 시 정합 미확인으로 변화 계산 불가."/>
      <TextField label="이전·현재 병변 연결 근거" value={reason} onChange={e=>setReason(e.target.value)}/>
      <Button disabled={busy||!samePatient||!reason.trim()||!currentFinding||!priorFinding} onClick={()=>act(async()=>{await request(`studies/${study}/longitudinal`,undefined,{prior_study:priorStudy,current_run:currentRun,prior_run:priorRun,same_patient_confirmed:samePatient,landmarks:landmarks.trim()?landmarks.trim().split('\n').map(line=>{const n=line.trim().split(/[ ,]+/).map(Number);if(n.length!==6||n.some(v=>!Number.isFinite(v)))throw new Error('기준점은 한 줄에 유한한 수 6개를 입력해 주세요.');return [n.slice(0,3),n.slice(3)];}):[],links:[{current_ref:`${currentRun}/${currentFinding}`,prior_ref:`${priorRun}/${priorFinding}`,confirmed:true,reason}]},'POST');setMessage('이전 검사 연결·측정 변화 버전을 저장했습니다.');})}>확인한 병변 변화 저장</Button>
      {priorHistory.map(v=><Stack key={v.id}><Typography>{v.created_at} · {v.payload.days}일 간격 · {v.payload.registration.status} · 기준점 RMS {v.payload.registration.rms_mm??'미확인'} mm (영상에는 자동 적용하지 않음)</Typography>{v.payload.links.map((l:D,i:number)=><Stack key={i}>{Object.entries(l.changes).map(([k,value])=>{const m=value as D;return <Typography key={k} variant="body2">{k}: {m.prior??'미측정'} → {m.current??'미측정'} / {m.status==='comparable'?`차이 ${m.delta.toFixed(2)}, ${m.percent.toFixed(1)}%`:'비교 불가'} · 성장/악성 판정 아님</Typography>;})}</Stack>)}</Stack>)}
    </Stack></AccordionDetails></Accordion>}
    {(!section||section==='evaluation')&&<Accordion key="evaluation" defaultExpanded={!!section}><AccordionSummary expandIcon={<ExpandMore/>}><Typography>평가 사례 준비 · 지원 범위</Typography></AccordionSummary><AccordionDetails><Stack spacing={2}>
      <Alert severity="warning">전문 정답·검토자가 아직 없습니다. 사례 준비와 기능 시험은 진료 적용 성능 검증(VAL-05)이 아닙니다.</Alert>
      <Select value={split} onChange={e=>setSplit(e.target.value)} inputProps={{'aria-label':'평가 데이터 분할'}}><MenuItem value="development">개발</MenuItem><MenuItem value="validation">검증</MenuItem><MenuItem value="test">독립 테스트</MenuItem></Select>
      <TextField label="평가용 비식별 환자 그룹 (선택)" value={patientGroup} onChange={e=>setPatientGroup(e.target.value)} helperText="같은 환자의 여러 검사를 같은 그룹으로 관리합니다. 이름·주민번호를 쓰지 마세요."/>
      <Button disabled={busy||!study} onClick={()=>act(async()=>{await request(`studies/${study}/evaluation-cases`,undefined,{split,reference_source:'',reviewer:'',payload:{expert_reviewed:false,patient_group:patientGroup||null,counts:{},note:'전문 정답/검토자 확보 대기'}},'POST');setMessage('원본 해시와 연결한 준비 사례를 등록했습니다.');})}>선택 검사 평가 사례 준비</Button>
      <Typography>등록 버전 {evaluation?.cases.length??0}건 · 임상 인수 {evaluation?.clinical_acceptance||'미평가'}</Typography>
      <Button href="/api/evaluation/export">평가대장 JSON 저장</Button>
      {capabilities.map(c=><Stack key={c.id}><Typography variant="subtitle2">{c.id} · {c.name} · {c.status}</Typography><Typography variant="body2">{c.reason}</Typography><Typography variant="caption">선행 조건: {c.requirements.join(' / ')}</Typography><Button href={c.source} target="_blank" rel="noreferrer">모델·연구 출처</Button></Stack>)}
    </Stack></AccordionDetails></Accordion>}
  </Stack>;
}
