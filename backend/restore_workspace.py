"""Offline restore CLI with an explicit backup-ID confirmation."""
import argparse
import json
from .analysis_runtime import ROOT
from .maintenance import restore_backup
from .storage import Store

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Restore only this project workspace while services are stopped')
    parser.add_argument('--backup-id',required=True)
    args=parser.parse_args()
    print('현재 앱의 원본 복사본/분석/문서/검토 DB를 교체합니다. 기존 데이터는 recovery에 보존하고 외부 원본/모델/백업은 유지합니다.')
    confirmation=input('확인 문자열 RESTORE <백업ID>: ').strip()
    print(json.dumps(restore_backup(Store(ROOT/'data'),args.backup_id,confirmation),ensure_ascii=False))
