import utils
import logging
import argparse
import importlib
import torch
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from PIL import Image
from mmcv import Config, DictAction
from mmcv.parallel import MMDataParallel
from mmcv.runner import load_checkpoint
from mmdet.apis import set_random_seed
from mmdet3d.datasets import build_dataset, build_dataloader
from mmdet3d.models import build_model
from nuscenes.utils.data_classes import Box
from pyquaternion import Quaternion
from nuscenes.nuscenes import NuScenes
from nuscenes.utils.geometry_utils import box_in_image
from configs.r50_nuimg_704x256 import class_names
from models.utils import VERSION


classname_to_color = {  # RGB
    'car': (255, 158, 0),  # Orange
    'pedestrian': (0, 0, 230),  # Blue
    'trailer': (255, 140, 0),  # Darkorange
    'truck': (255, 99, 71),  # Tomato
    'bus': (255, 127, 80),  # Coral
    'motorcycle': (255, 61, 99),  # Red
    'construction_vehicle': (233, 150, 70),  # Darksalmon
    'bicycle': (220, 20, 60),  # Crimson
    'barrier': (112, 128, 144),  # Slategrey
    'traffic_cone': (47, 79, 79),  # Darkslategrey
}


def convert_to_nusc_box(bboxes, scores=None, labels=None, names=None, score_threshold=0.3, lift_center=False):
    results = []
    for q in range(bboxes.shape[0]):
        if scores is not None:
            score = scores[q]
        else:
            score = 1.0

        if score < score_threshold:
            continue

        if labels is not None:
            label = labels[q]
        else:
            label = 0

        if names is not None:
            name = names[q]
        else:
            name = class_names[label]

        if name not in class_names:
            name = class_names[-1]

        bbox = bboxes[q].copy()
        if lift_center:
            bbox[2] += bbox[5] * 0.5

        orientation = Quaternion(axis=[0, 0, 1], radians=bbox[6])

        box = Box(
            center=[bbox[0], bbox[1], bbox[2]],
            size=[bbox[4], bbox[3], bbox[5]],
            orientation=orientation,
            score=score,
            label=label,
            velocity=(bbox[7], bbox[8], 0),
            name=name
        )

        results.append(box)

    return results


def viz_bbox(nusc, bboxes, data_info, fig, gs):
    cam_types = [
        'CAM_FRONT_LEFT', 'CAM_FRONT', 'CAM_FRONT_RIGHT',
        'CAM_BACK_RIGHT', 'CAM_BACK', 'CAM_BACK_LEFT',
    ]

    for cam_id, cam_type in enumerate(cam_types):
        sample_data_token = nusc.get('sample', data_info['token'])['data'][cam_type]

        sd_record = nusc.get('sample_data', sample_data_token)
        cs_record = nusc.get('calibrated_sensor', sd_record['calibrated_sensor_token'])
        intrinsic = np.array(cs_record['camera_intrinsic'])

        img_path = nusc.get_sample_data_path(sample_data_token)
        img_size = (sd_record['width'], sd_record['height'])

        ax = fig.add_subplot(gs[cam_id // 3, cam_id % 3])
        ax.imshow(Image.open(img_path))

        for bbox in bboxes:
            bbox = bbox.copy()

            # Move box to ego vehicle coord system
            bbox.rotate(Quaternion(data_info['lidar2ego_rotation']))
            bbox.translate(np.array(data_info['lidar2ego_translation']))

            # Move box to sensor coord system
            bbox.translate(-np.array(cs_record['translation']))
            bbox.rotate(Quaternion(cs_record['rotation']).inverse)

            if box_in_image(bbox, intrinsic, img_size):
                c = np.array(classname_to_color[bbox.name]) / 255.0
                bbox.render(ax, view=intrinsic, normalize=True, colors=(c, c, c), linewidth=1)

        ax.axis('off')
        ax.set_title(cam_type)
        ax.set_xlim(0, img_size[0])
        ax.set_ylim(img_size[1], 0)

    sample = nusc.get('sample', data_info['token'])
    lidar_data_token = sample['data']['LIDAR_TOP']

    ax = fig.add_subplot(gs[0:2, 3])
    nusc.explorer.render_sample_data(lidar_data_token, with_anns=False, ax=ax, verbose=False)
    ax.axis('off')
    ax.set_title('LIDAR_TOP')
    ax.set_xlim(-40, 40)
    ax.set_ylim(-40, 40)

    sd_record = nusc.get('sample_data', lidar_data_token)
    pose_record = nusc.get('ego_pose', sd_record['ego_pose_token'])
    cs_record = nusc.get('calibrated_sensor', sd_record['calibrated_sensor_token'])

    for bbox in bboxes:
        bbox = bbox.copy()

        bbox.rotate(Quaternion(cs_record['rotation']))
        bbox.translate(np.array(cs_record['translation']))
        bbox.rotate(Quaternion(pose_record['rotation']))

        yaw = Quaternion(pose_record['rotation']).yaw_pitch_roll[0]
        bbox.rotate(Quaternion(scalar=np.cos(yaw / 2), vector=[0, 0, np.sin(yaw / 2)]).inverse)

        c = np.array(classname_to_color[bbox.name]) / 255.0
        bbox.render(ax, view=np.eye(4), colors=(c, c, c))


def compute_iou(boxA, boxB):
    # 各BBoxの最小角と最大角を計算
    xA_min = boxA["x"] - boxA["width"] / 2
    yA_min = boxA["y"] - boxA["height"] / 2
    zA_min = boxA["z"] - boxA["depth"] / 2
    xA_max = boxA["x"] + boxA["width"] / 2
    yA_max = boxA["y"] + boxA["height"] / 2
    zA_max = boxA["z"] + boxA["depth"] / 2

    xB_min = boxB["x"] - boxB["width"] / 2
    yB_min = boxB["y"] - boxB["height"] / 2
    zB_min = boxB["z"] - boxB["depth"] / 2
    xB_max = boxB["x"] + boxB["width"] / 2
    yB_max = boxB["y"] + boxB["height"] / 2
    zB_max = boxB["z"] + boxB["depth"] / 2

    # 重なりの各次元の長さを計算
    overlap_x = max(0, min(xA_max, xB_max) - max(xA_min, xB_min))
    overlap_y = max(0, min(yA_max, yB_max) - max(yA_min, yB_min))
    overlap_z = max(0, min(zA_max, zB_max) - max(zA_min, zB_min))

    # 重なりの体積
    overlap_volume = overlap_x * overlap_y * overlap_z

    # 各BBoxの体積
    volumeA = boxA["width"] * boxA["height"] * boxA["depth"]
    volumeB = boxB["width"] * boxB["height"] * boxB["depth"]

    # IoUを計算
    iou = overlap_volume / (volumeA + volumeB - overlap_volume) if (volumeA + volumeB - overlap_volume) != 0 else 0
    return iou

# # テストケース
# boxA = {"x": 1, "y": 1, "z": 1, "width": 2, "height": 2, "depth": 2}
# boxB = {"x": 2, "y": 2, "z": 2, "width": 2, "height": 2, "depth": 2}

# iou = compute_iou(boxA, boxB)
# print(f"IoU: {iou}")


def compute_precision_recall(detections, ground_truths, iou_threshold=0.5):
    """
    detectionsとground_truthsのリストからPrecisionとRecallを計算します。
    各要素は{"x": float, "y": float, "z": float, "width": float, "height": float, "depth": float}の形式です。
    """
    TP = 0
    FP = 0
    FN = len(ground_truths)

    for det in detections:
        matched = False
        for gt in ground_truths:
            iou = compute_iou(det, gt)
            if iou >= iou_threshold:
                matched = True
                FN -= 1
                break
        if matched:
            TP += 1
        else:
            FP += 1

    precision = TP / (TP + FP) if (TP + FP) > 0 else 0
    recall = TP / (TP + FN) if (TP + FN) > 0 else 0

    return precision, recall

def compute_ap(precisions, recalls):
    """
    PrecisionとRecallのリストからAPを計算します。
    """
    # Recall値を昇順にソートし、対応するPrecisionでAPを計算
    recalls = sorted(recalls + [0, 1])  # 開始と終了を追加
    precisions = [0] + precisions + [0]  # 開始と終了を追加

    # PrecisionをRecallの関数として補間
    for i in range(len(precisions) - 2, -1, -1):
        precisions[i] = max(precisions[i], precisions[i + 1])

    # APを計算
    ap = sum((recalls[i + 1] - recalls[i]) * precisions[i + 1] for i in range(len(recalls) - 1))

    return ap

# # テストデータの例（検出結果とグラウンドトゥルース）
# detections = [
#     {"x": 1, "y": 1, "z": 1, "width": 2, "height": 2, "depth": 2},  # 例えば検出結果
#     # 他の検出結果...
# ]
# ground_truths = [
#     {"x": 2, "y": 2, "z": 2, "width": 2, "height": 2, "depth": 2},  # 例えばグラウンドトゥルース
#     # 他のグラウンドトゥルース...
# ]

# # PrecisionとRecallを計算
# precisions, recalls = [], []
# for det in detections:
#     precision, recall = compute_precision_recall([det], ground_truths)
#     precisions.append(precision)
#     recalls.append(recall)

# # APを計算
# ap = compute_ap(precisions, recalls)
# print(f"AP: {ap}")




def main():
    parser = argparse.ArgumentParser(description='Validate a detector')
    parser.add_argument('--config', required=True)
    parser.add_argument('--weights', required=True)
    parser.add_argument('--override', nargs='+', action=DictAction)
    parser.add_argument('--score_threshold', default=0.3)
    args = parser.parse_args()

    # parse configs
    cfgs = Config.fromfile(args.config)
    if args.override is not None:
        cfgs.merge_from_dict(args.override)

    # use val-mini for visualization
    cfgs.data.val.ann_file = cfgs.data.val.ann_file.replace('val', 'val_mini')

    # register custom module
    importlib.import_module('models')
    importlib.import_module('loaders')

    # MMCV, please shut up
    from mmcv.utils.logging import logger_initialized
    logger_initialized['root'] = logging.Logger(__name__, logging.WARNING)
    logger_initialized['mmcv'] = logging.Logger(__name__, logging.WARNING)

    # you need one GPU
    assert torch.cuda.is_available()
    assert torch.cuda.device_count() == 1

    utils.init_logging(None, cfgs.debug)
    logging.info('Using GPU: %s' % torch.cuda.get_device_name(0))
    logging.info('Setting random seed: 0')
    set_random_seed(0, deterministic=True)

    logging.info('Loading validation set from %s' % cfgs.data.val.data_root)
    world_size=1
    train_dataset = build_dataset(cfgs.data.train)
    train_loader = build_dataloader(
        train_dataset,
        samples_per_gpu=cfgs.batch_size // world_size,
        workers_per_gpu=cfgs.data.workers_per_gpu,
        num_gpus=world_size,
        dist=world_size > 1,
        shuffle=True,
        seed=0,
    )
    val_dataset = build_dataset(cfgs.data.val)
    val_loader = build_dataloader(
        val_dataset,
        samples_per_gpu=1,
        workers_per_gpu=cfgs.data.workers_per_gpu,
        num_gpus=1,
        dist=False,
        shuffle=False,
        seed=0,
    )

    logging.info('Creating model: %s' % cfgs.model.type)
    model = build_model(cfgs.model)
    model.cuda()
    model = MMDataParallel(model, [0])

    logging.info('Loading checkpoint from %s' % args.weights)
    checkpoint = load_checkpoint(
        model, args.weights, map_location='cuda', strict=True,
        logger=logging.Logger(__name__, logging.ERROR)
    )

    if 'version' in checkpoint:
        VERSION.name = checkpoint['version']

    logging.info('Initialize nuscenes toolkit...')
    if 'mini' in cfgs.data.val.ann_file:
        nusc = NuScenes(version='v1.0-mini', dataroot=cfgs.data.val.data_root, verbose=False)
    else:
        nusc = NuScenes(version='v1.0-trainval', dataroot=cfgs.data.val.data_root, verbose=False)

    for i, (data, data_train) in enumerate(zip(val_loader, train_loader)):
        model.eval()

        with torch.no_grad():
            results = model(return_loss=False, rescale=True, **data)
            results = results[0]['pts_bbox']

        bboxes_pred = convert_to_nusc_box(
            bboxes=results['boxes_3d'].tensor.numpy(),
            scores=results['scores_3d'].numpy(),
            labels=results['labels_3d'].numpy(),
            score_threshold=args.score_threshold,
            lift_center=True,
        )

        bboxes_gt = convert_to_nusc_box(
            bboxes=data_train['gt_boxes_3d'].tensor.numpy(),
            scores=results['scores_3d'].numpy(),
            labels=data_train['gt_labels_3d'].numpy(),
            score_threshold=args.score_threshold,
            lift_center=True,
        )

        fig = plt.figure(figsize=(15.5, 5))
        gs = GridSpec(2, 4, figure=fig)

        viz_bbox(nusc, bboxes_pred, val_dataset.data_infos[i], fig, gs)
        viz2_bbox(nusc, bboxes_gt, train_dataset.data_infos[i], fig, gs)

        plt.tight_layout()
        plt.savefig('outputs/bbox_%04d.jpg' % i, dpi=200)
        plt.close()

        logging.info('Visualized result is dumped to outputs/bbox_%04d.jpg' % i)


if __name__ == '__main__':
    main()
