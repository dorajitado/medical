from .native_imaging import ROOT
from .test_intake import ct_bytes
from pydicom.uid import generate_uid
import numpy as np

if __name__=='__main__':
    folder=ROOT/'data'/'qa-fixtures'/'volume'
    folder.mkdir(parents=True,exist_ok=True)
    study,series=generate_uid(),generate_uid()
    yy,xx=np.mgrid[:128,:128]
    for z in range(32):
        pixels=np.full((128,128),-1000,dtype='<i2')
        pixels[(xx-64)**2+(yy-64)**2<55**2]=40+z
        pixels[((xx-42)/18)**2+((yy-64)/32)**2<1]=-800
        pixels[((xx-86)/18)**2+((yy-64)/32)**2<1]=-800
        pixels[(xx-64)**2+(yy-100)**2<8**2]=700
        payload=ct_bytes(study,series,ImagePositionPatient=[0,0,z*2],PixelSpacing=[.8,.8],
                         Rows=128,Columns=128,PixelData=pixels.tobytes(),PixelRepresentation=1,
                         RescaleSlope=1,RescaleIntercept=0,SliceThickness=2,SpacingBetweenSlices=2,
                         WindowCenter=40,WindowWidth=400,InstanceNumber=z+1,
                         StudyDescription='SYNTHETIC VOLUME QA',SeriesDescription='PHANTOM CT',ConvolutionKernel='STANDARD')
        (folder/f'{z:03d}.dcm').write_bytes(payload)
