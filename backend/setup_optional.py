"""Install-time only pinned OCR/MONAI/CPU-LLM assets, never patient inputs.

Every download is staged and SHA-256 checked before replacing its local target.
Inference workers have no download fallback. Files in locks are project-owned.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def install(kind):
    lock=json.loads((ROOT/f'{kind}-runtime-lock.json').read_text(encoding='utf-8'))
    home=ROOT/'runtime'/{'ocr':'ocr','monai':'monai-bundle','llm':'llm'}[kind];home.mkdir(parents=True,exist_ok=True)
    for item in lock['files']:
        relative=(item['language']+'.traineddata') if kind=='ocr' else item['path']
        target=(home/relative).resolve()
        if not target.is_relative_to(home.resolve()):raise ValueError('설치 경로가 런타임을 벗어났습니다.')
        url=item.get('url') or f"https://huggingface.co/{lock['repository']}/resolve/{lock['commit']}/{relative}"
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and target.stat().st_size==item['bytes'] and digest(target)==item['sha256']:continue
        stage=target.with_suffix(target.suffix+'.part')
        try:
            with urllib.request.urlopen(url,timeout=60) as source,stage.open('wb') as out:shutil.copyfileobj(source,out,1024*1024)
            if stage.stat().st_size!=item['bytes'] or digest(stage)!=item['sha256']:raise ValueError('다운로드 크기/해시 검증 실패')
            stage.replace(target)
        finally:stage.unlink(missing_ok=True)
    if kind=='llm':
        with zipfile.ZipFile(home/'runtime.zip') as archive:
            # Distribution files are flattened to the fixed runtime directory.
            for item in archive.infolist():
                if item.is_dir():continue
                name=Path(item.filename).name
                if not name or ':' in name or '\\' in name:raise ValueError('런타임 배포 경로 오류')
                with archive.open(item) as source,(home/name).open('wb') as out:shutil.copyfileobj(source,out)
    (home/'manifest.json').write_text(json.dumps(lock,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{kind}: pinned files verified; no medical data read')


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as source:
        while chunk:=source.read(1024*1024):value.update(chunk)
    return value.hexdigest()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['ocr','monai','llm']);install(parser.parse_args().kind)
