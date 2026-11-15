"""Pinned independent MONAI RetinaNet detection; boxes are NOT segmentation.

The network/anchors/preprocessing follow the official 0.6.10 bundle. A smaller
sliding-window ROI is recorded for RTX 3080 memory. Scores remain model-specific
class confidences; no average with TotalSegmentator or malignancy probability.
"""
from itertools import product
import hashlib
import json
from pathlib import Path


def run_monai(directory:Path):
    import numpy as np
    import torch
    from monai.apps.detection.networks.retinanet_network import RetinaNet, resnet_fpn_feature_extractor
    from monai.apps.detection.networks.retinanet_detector import RetinaNetDetector
    from monai.apps.detection.utils.anchor_utils import AnchorGeneratorWithAnchorShape
    from monai.networks.nets.resnet import resnet50
    from monai.transforms import Compose, LoadImaged, EnsureChannelFirstd, Orientationd, Spacingd, ScaleIntensityRanged, EnsureTyped
    from .analysis_runtime import ROOT

    source=json.loads((directory/'source.json').read_text(encoding='utf-8'))
    network=RetinaNet(spatial_dims=3,num_classes=1,num_anchors=3,
                     feature_extractor=resnet_fpn_feature_extractor(resnet50(spatial_dims=3,n_input_channels=1,conv1_t_stride=[2,2,1],conv1_t_size=[7,7,7]),3,False,[1,2],None),
                     size_divisible=[16,16,8],use_list_output=False).cuda().eval()
    network.load_state_dict(torch.load(ROOT/'runtime'/'monai-bundle'/'models'/'model.pt',map_location='cpu',weights_only=True))
    anchors=AnchorGeneratorWithAnchorShape(feature_map_scales=[1,2,4],base_anchor_shapes=[[6,8,4],[8,6,5],[10,10,6]])
    detector=RetinaNetDetector(network=network,anchor_generator=anchors,debug=False,spatial_dims=3,num_classes=1,size_divisible=[16,16,8])
    detector.set_target_keys(box_key='box',label_key='label')
    detector.set_box_selector_parameters(score_thresh=.02,topk_candidates_per_level=1000,nms_thresh=.22,detections_per_img=300)
    detector.set_sliding_window_inferer(roi_size=[192,192,96],overlap=.25,sw_batch_size=1,mode='constant',device='cpu')
    detector.eval()
    transform=Compose([LoadImaged(keys='image',reader='NibabelReader'),EnsureChannelFirstd(keys='image'),
                       Orientationd(keys='image',axcodes='RAS'),Spacingd(keys='image',pixdim=[.703125,.703125,1.25],mode='bilinear'),
                       ScaleIntensityRanged(keys='image',a_min=-1024,a_max=300,b_min=0.,b_max=1.,clip=True),EnsureTyped(keys='image')])
    image=transform({'image':str(directory/'input.nii.gz')})['image']
    with torch.inference_mode(),torch.autocast('cuda',enabled=True):
        output=detector([image.cuda()],use_inferer=True)[0]
    boxes=output['box'].detach().cpu().numpy();scores=output['label_scores'].detach().cpu().numpy()
    raw={'boxes_preprocessed_xyzxyz':boxes.tolist(),'scores':scores.tolist(),'affine_preprocessed_ras':image.affine.cpu().numpy().tolist(),
         'preprocessed_shape':list(image.shape[1:]),'score_threshold':.02,'nms_threshold':.22,'roi_size':[192,192,96]}
    raw_path=directory/'detection-boxes.json';raw_path.write_text(json.dumps(raw),encoding='utf-8')
    original=np.array(source['affine_ras']);inverse=np.linalg.inv(original);processed=np.array(raw['affine_preprocessed_ras'])
    shape=np.array(source['geometry']['shape_xyz']);findings=[]
    for index,(box,score) in enumerate(zip(boxes,scores)):
        low=np.maximum(box[:3],0);high=np.minimum(box[3:],np.array(image.shape[1:]))
        if np.any(high<=low) or not np.isfinite(score):continue
        corners=np.array(list(product(*zip(low,high))))
        ras=(processed@np.c_[corners,np.ones(8)].T).T[:,:3]
        original_points=(inverse@np.c_[ras,np.ones(8)].T).T[:,:3]
        a=np.maximum(np.floor(original_points.min(axis=0)).astype(int),0)
        b=np.minimum(np.ceil(original_points.max(axis=0)).astype(int),shape-1)
        if np.any(b<a):continue
        representative=np.clip(np.rint((a+b)/2).astype(int),0,shape-1)
        lps=ras*np.array([-1.,-1.,1.]);position=(original@np.r_[representative,1.])[:3]*[-1,-1,1]
        findings.append({'id':f'monai-box-{index+1}','selection_label':index+1,'kind':'lung_nodules','title':f'MONAI 결절 탐지상자 {index+1}',
                         'label':2,'color':'#e6b34a','model_id':'monai_nodule','representation':'detection_box_not_segmentation',
                         'voxel_count':None,'volume_mm3':None,'volume_ml':None,'diameter_mm':None,'diameter_slice_z':None,
                         'diameter_method':'not provided: detector box dimensions are not segmented lesion size',
                         'representative_index_xyz':representative.tolist(),'representative_lps_mm':position.tolist(),'centroid_lps_mm':position.tolist(),
                         'bounds_index_xyz':[a.tolist(),b.tolist()],'box_vertices_lps_mm':lps.tolist(),
                         'touches_boundary':bool(np.any(a==0)|np.any(b==shape-1)),
                         'source_instance_id':source['sources'][int(representative[2])]['instance_id'],
                         'score':float(score),'score_meaning':'MONAI RetinaNet class confidence; NOT malignancy probability','review_status':'unreviewed_ai_candidate'})
    # Empty label lattice is an explicit interface placeholder, never a claimed
    # segmentation. UI draws the separate detector rectangles and 3D boxes.
    np.save(directory/'labels.npy',np.zeros(tuple(shape),dtype=np.uint8),allow_pickle=False)
    result={'model_id':'monai_nodule','series_id':source['id'],'study_id':source['study_id'],'shape_xyz':shape.tolist(),
            'spacing_xyz':source['geometry']['spacing_xyz'],'source':source,'structures':[], 'findings':findings,'finding_count':len(findings),
            'finding_status':'candidates_present' if findings else 'no_candidates','representation':'detection_boxes_not_segmentation',
            'measurement_method':'detector box only; lesion diameter/volume not measured','restoration':'processed affine RAS -> original voxel indices and patient LPS',
            'detection_transform':raw,'boxes_sha256':hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            'labels_sha256':hashlib.sha256((directory/'labels.npy').read_bytes()).hexdigest(),
            'limitations':['MONAI 독립 탐지상자이며 분할/장경/부피를 제공하지 않습니다.','탐지 점수는 악성 확률이 아니며 다른 모델과 평균하지 않습니다.','이 예제 모델의 조영 CT 임상 성능은 검증되지 않았습니다.']}
    (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    return result
