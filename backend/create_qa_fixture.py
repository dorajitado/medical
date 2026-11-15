"""Generate a tiny clearly synthetic CT under ignored QA storage."""
from pathlib import Path
from .test_intake import ct_bytes
from pydicom.uid import generate_uid

if __name__ == '__main__':
    folder = Path(__file__).resolve().parents[1] / 'data' / 'qa-fixtures' / 'ct'
    folder.mkdir(parents=True, exist_ok=True)
    study, series = generate_uid(), generate_uid()
    (folder / 'synthetic.dcm').write_bytes(ct_bytes(study=study, series=series, StudyDescription='SYNTHETIC QA ONLY'))
    (folder / 'nested').mkdir(exist_ok=True)
    (folder / 'nested' / 'synthetic2.dcm').write_bytes(ct_bytes(study=study, series=series, StudyDescription='SYNTHETIC QA ONLY', ImagePositionPatient=[0,0,1]))
