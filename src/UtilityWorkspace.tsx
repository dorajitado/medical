/** Local document and workspace tools. All rows come from persisted APIs; the
 * typed deletion phrase is supplied by a scope preview rather than guessed. */
import { useEffect, useRef, useState } from 'react';
import { Accordion, AccordionSummary, AccordionDetails, Alert, Box, Button, Checkbox, FormControlLabel, LinearProgress, Stack, TextField, Typography } from '@mui/material';
import { ExpandMore } from '@mui/icons-material';
import { request } from './api';
import { useIntake } from './IntakePanel';
type Row = Record<string, any>;
export default function UtilityWorkspace({section}:{section?:'documents'|'maintenance'}) {
  const { selectedStudy, connected, onRefresh } = useIntake();
  const [docs,setDocs]=useState<Row[]>([]), [backups,setBackups]=useState<Row[]>([]);
  const [chosen,setChosen]=useState(''),[text,setText]=useState(''),[confirmed,setConfirmed]=useState(false);
  const [pending,setPending]=useState<Row[]>([]);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const [preview,setPreview]=useState<Row|null>(null),[phrase,setPhrase]=useState('');
  const alive=useRef(true);
  const doc=docs.find(d=>d.id===chosen);
  /** Each mounted study owns its response state. Old requests cannot populate a
   * newly selected study, and a failed upload retains the selected document. */
  async function load(signal?:AbortSignal) {
    const [d,b,p]=await Promise.all([selectedStudy?request<{items:Row[]}>(`studies/${selectedStudy}/documents`,signal):Promise.resolve({items:[]}),request<{items:Row[]}>('maintenance/backups',signal),request<{items:Row[]}>('maintenance/pending-cleanup',signal)]);
    if(alive.current&&!signal?.aborted){setDocs(d.items);setBackups(b.items);setPending(p.items);}
  }
  useEffect(()=>{alive.current=true;const c=new AbortController();if(connected)load(c.signal).catch(e=>{if(!c.signal.aborted)setError(e.message);});return()=>{alive.current=false;c.abort();};},[selectedStudy,connected]);
  async function act(work:()=>Promise<void>){setBusy(true);setError('');setMessage('');try{await work();if(alive.current)await load();}catch(e){if(alive.current)setError(e instanceof Error?e.message:'처리 실패');}finally{if(alive.current)setBusy(false);}}
  function choose(d:Row){setChosen(d.id);setText(d.pages.map((p:Row)=>p.text).join('\n\n'));setConfirmed(false);}
  return <Stack spacing={2} sx={{mt:2}}>
    {busy&&<LinearProgress aria-label="로컬 문서·저장소 처리 중"/>}
    {error&&<Alert severity="error" action={<Button onClick={()=>act(async()=>{})}>재시도</Button>}>{error}</Alert>}
    {message&&<Alert severity="info">{message}</Alert>}
    {(!section||section==='documents')&&<Accordion key="documents" defaultExpanded={!!section}><AccordionSummary expandIcon={<ExpandMore/>}><Typography>병원 문서 · 로컬 OCR</Typography></AccordionSummary><AccordionDetails><Stack spacing={2}>
      <Typography variant="body2">PDF·PNG·JPEG 원본과 페이지를 보존합니다. 추출 문장은 원문과 대조하고 수정한 뒤 소견 버전으로 저장하세요.</Typography>
      <Button component="label" disabled={!selectedStudy||busy||!connected}>문서 선택 (32 MiB 이하)<input hidden type="file" accept="application/pdf,image/png,image/jpeg" onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;if(file.size>32*1024**2){setError('문서당 32 MiB 한도입니다.');return;}void act(async()=>{const response=await fetch(`/api/studies/${selectedStudy}/documents`,{method:'POST',headers:{'Content-Type':file.type,'x-workspace-request':'1'},body:file});const body=await response.json();if(!response.ok)throw new Error(body.detail||'문서 처리 실패');if(alive.current){choose(body);setMessage(body.status==='extracted'?'원문과 추출 텍스트를 확인하세요.':'문서 추출 실패: 원본은 보존됩니다.');}});}}/></Button>
      {!docs.length&&<Typography color="text.secondary">등록한 문서가 없습니다.</Typography>}
      {docs.map(d=><Button key={d.id} onClick={()=>choose(d)} variant={chosen===d.id?'contained':'outlined'}>{d.created_at} · {d.status} · {d.pages.length}쪽</Button>)}
      {doc&&<><Typography variant="caption" sx={{overflowWrap:'anywhere'}}>문서 {doc.id} · SHA-256 {doc.sha256}</Typography><Button href={`/api/documents/${doc.id}/original`}>보존 원본 다운로드</Button>
        {doc.error&&<Alert severity="error">{doc.error}</Alert>}
        {doc.pages.map((p:Row)=><Box key={p.page}><Typography>{p.page}쪽 · {p.method} · 인식 신뢰도 {p.confidence??'제공 없음'}</Typography><Box component="img" src={`/api/documents/${doc.id}/page/${p.page}`} alt={`보존 문서 ${p.page}쪽`} sx={{maxWidth:'100%',maxHeight:400,objectFit:'contain'}}/></Box>)}
        <TextField label="원문 대조·수정한 전사 텍스트" multiline minRows={5} value={text} onChange={e=>{setText(e.target.value);setConfirmed(false);}}/>
        <FormControlLabel control={<Checkbox checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>} label="선택한 검사와 문서가 일치하고 전사 내용을 확인했습니다"/>
        <Button disabled={busy||!confirmed||!text.trim()||doc.status!=='extracted'} onClick={()=>act(async()=>{await request(`documents/${doc.id}/accept`,undefined,{text,confirmed},'POST');window.dispatchEvent(new Event('review-updated'));setMessage('문서 추출 출처의 새 소견 버전을 저장했습니다.');})}>문서 출처로 소견 저장</Button></>}
    </Stack></AccordionDetails></Accordion>}
    {(!section||section==='maintenance')&&<Accordion key="maintenance" defaultExpanded={!!section}><AccordionSummary expandIcon={<ExpandMore/>}><Typography>백업 · 무결성 검증 · 검사 삭제</Typography></AccordionSummary><AccordionDetails><Stack spacing={2}>
      <Typography variant="body2">백업: 앱 원본 복사본·분석·문서·검토 DB. 모델과 영상 캐시는 제외됩니다. 복원은 앱/영상 서비스를 종료한 뒤 Windows 복원 명령으로 실행합니다.</Typography>
      <Button disabled={busy||!connected} onClick={()=>act(async()=>{await request('maintenance/backups',undefined,{},'POST');setMessage('백업을 생성했습니다. 다운로드와 무결성 검증을 진행할 수 있습니다.');})}>현재 작업 공간 백업</Button>
      {backups.map(b=><Stack key={b.id} direction="row" spacing={1} flexWrap="wrap"><Typography variant="caption" sx={{overflowWrap:'anywhere'}}>{b.id} · {(b.bytes/1024**2).toFixed(1)} MiB</Typography><Button href={`/api/maintenance/backups/${b.id}/download`}>다운로드</Button><Button disabled={busy} onClick={()=>act(async()=>{const v=await request<Row>(`maintenance/backups/${b.id}/verify`,undefined,{},'POST');setMessage(`${v.restore_instruction} / ${v.scope}`);})}>검증·복원 안내</Button></Stack>)}
      {pending.map(p=><Button key={p.id} disabled={busy} onClick={()=>act(async()=>{await request(`maintenance/pending-cleanup/${p.id}`,undefined,{},'POST');setMessage('남아 있던 앱 관리 파일을 정리했습니다.');})}>잠긴 삭제 파일 정리 재시도 · {p.id.slice(0,8)}</Button>)}
      <Button color="error" disabled={busy||!selectedStudy} onClick={()=>act(async()=>{setPreview(await request<Row>(`maintenance/studies/${selectedStudy}/delete-preview`));setPhrase('');})}>선택 검사 삭제 범위 확인</Button>
      {preview&&<><Alert severity="warning">{preview.scope} 원본 {preview.original_instances}개, 분석 {preview.analysis_runs}건. 실행하려면 {preview.confirmation} 입력.</Alert><TextField label="삭제 확인 문구" value={phrase} onChange={e=>setPhrase(e.target.value)}/><Button color="error" disabled={busy||phrase!==preview.confirmation} onClick={()=>act(async()=>{const r=await request<Row>(`maintenance/studies/${selectedStudy}/delete`,undefined,{confirmation:phrase},'POST');setMessage(r.status);setPreview(null);onRefresh();})}>확인한 검사 삭제 실행</Button></>}
    </Stack></AccordionDetails></Accordion>}
  </Stack>;
}
