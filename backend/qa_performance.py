"""512x512x128 analytic phantom stress test, separated from clinical accuracy.

Limits are written before execution: 600 s/model, sampled process-tree RSS
32 GiB, torch reserved peak 9 GiB. Sampling may miss short peaks; measurements
do not establish performance on a real thin-slice full chest examination.
"""
import json
from pathlib import Path
import time
from uuid import uuid4
import numpy as np
import psutil
from fastapi.testclient import TestClient
from pydicom.uid import generate_uid
from .analysis_runtime import ROOT
from .app import create_app
from .test_intake import ct_bytes,HEADERS


def main():
    home=ROOT/'data'/'qa-remaining';home.mkdir(exist_ok=True)
    criteria={'schema':'ct-resource-qa-1','input':'analytic phantom; not patient CT or accuracy data','shape_xyz':[512,512,128],
              'spacing_xyz':[1.,1.,2.],'seconds_per_model':600,'sampled_tree_rss_bytes':32*1024**3,'cuda_reserved_bytes':9*1024**3,'clinical_accuracy':'not_evaluated'}
    (home/'performance-criteria.json').write_text(json.dumps(criteria,indent=2),encoding='utf-8')
    root=home/('performance-'+str(uuid4()));study,series=generate_uid(),generate_uid()
    x,y=np.meshgrid(np.arange(512),np.arange(512),indexing='xy')
    body=((x-256)/190)**2+((y-256)/145)**2<1
    lungs=(((x-190)/58)**2+((y-240)/90)**2<1)|(((x-320)/58)**2+((y-240)/90)**2<1)
    base=np.full((512,512),-1000,dtype='<i2');base[body]=30;base[lungs]=-800
    process=psutil.Process();results={}
    with TestClient(create_app(root),base_url='http://127.0.0.1:8000') as client:
        job=client.post('/api/imports',headers=HEADERS,json={'total':128}).json()['id']
        for z in range(128):
            voxels=base.copy()
            if abs(z-64)<=2:voxels[(x-190)**2+(y-240)**2<=16]=80
            data=ct_bytes(study,series,Rows=512,Columns=512,ImagePositionPatient=[-256,-256,z*2.],ImageOrientationPatient=[1,0,0,0,1,0],PixelSpacing=[1.,1.],SliceThickness=2.,PixelRepresentation=1,PixelData=voxels.tobytes(),RescaleSlope=1,RescaleIntercept=0,StudyDescription='ANALYTIC PHANTOM RESOURCE QA',SeriesDescription='SYNTHETIC NOT CLINICAL')
            response=client.post(f'/api/imports/{job}/files',headers={**HEADERS,'Content-Type':'application/octet-stream'},content=data);response.raise_for_status()
            if response.json()['outcome']!='imported':raise RuntimeError('Phantom intake failed')
        client.post(f'/api/imports/{job}/finish',headers=HEADERS)
        sid=client.get('/api/studies').json()['items'][0]['id'];series_id=client.get(f'/api/studies/{sid}/series').json()['items'][0]['id']
        for model in ['total','lung_nodules','pleural_pericard_effusion','monai_nodule']:
            started=time.monotonic();response=client.post(f'/api/series/{series_id}/analyses',headers=HEADERS,json={'confirmed':True,'model_id':model});response.raise_for_status();rid=response.json()['id'];rss=0
            while True:
                alive=[process,*process.children(recursive=True)]
                total=0
                for child in alive:
                    try:total+=child.memory_info().rss
                    except psutil.Error:pass
                rss=max(rss,total)
                run=next(r for r in client.get(f'/api/series/{series_id}/analyses').json()['items'] if r['id']==rid)
                if run['status'] not in {'running','queued'}:break
                if time.monotonic()-started>criteria['seconds_per_model'] or rss>criteria['sampled_tree_rss_bytes']:
                    client.post(f'/api/analyses/{rid}/cancel',headers=HEADERS);break
                time.sleep(.5)
            metrics=client.get(f'/api/analyses/{rid}/result').json().get('metrics',{}) if run['status']=='completed' else {}
            results[model]={'run_id':rid,'status':run['status'],'wall_seconds':time.monotonic()-started,'sampled_tree_peak_rss_bytes':rss,'metrics':metrics,
                            'within_limits':run['status']=='completed' and time.monotonic()-started<=criteria['seconds_per_model'] and rss<=criteria['sampled_tree_rss_bytes'] and metrics.get('cuda_peak_reserved_bytes',10**20)<=criteria['cuda_reserved_bytes']}
            print(json.dumps({'model':model,**results[model]}),flush=True)
            (home/'performance-results.json').write_text(json.dumps({'criteria':criteria,'workspace':str(root),'series_id':series_id,'results':results},indent=2),encoding='utf-8')
    if not all(r['within_limits'] for r in results.values()):raise SystemExit('Some phantom stress criteria failed; see retained result states')


if __name__=='__main__':main()
