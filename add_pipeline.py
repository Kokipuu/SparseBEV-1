
# # 画像加工処理をパイプラインに追加
# test_pipeline.append(
#     dict(type='RandomColorAdjust', brightness=0.2, contrast=0.2, saturation=0.2, hue=0.1)
# )

# import numpy as np
# from PIL import Image

# @PIPELINES.register_module()
# class RandomTransformImage(object):
#     def __init__(self, ida_aug_conf=None, training=True, apply_to_front_only=True):
#         self.ida_aug_conf = ida_aug_conf
#         self.training = training
#         self.apply_to_front_only = apply_to_front_only

#     def __call__(self, results):
#         if not self.training or not self.apply_to_front_only:
#             # トレーニングモードでない、またはフロントカメラ画像のみに適用しない設定の場合は、
#             # 何も変更せずに結果を返します。
#             return results

#         for i, img_info in enumerate(results['img_metas']):
#             if 'front' in img_info['filename']:
#                 # フロントカメラの画像に対してのみ加工を適用します。
#                 img = Image.fromarray(np.uint8(results['img'][i]))
#                 img = self.apply_random_color_change(img)
#                 results['img'][i] = np.array(img).astype(np.uint8)

#         return results

#     def apply_random_color_change(self, img):
#         """
#         画像の左上隅にランダムな色のオーバーレイを適用します。
#         """
#         # 画像サイズの取得
#         width, height = img.size

#         # オーバーレイする領域のサイズ（例：画像の10%）
#         overlay_width, overlay_height = width // 10, height // 10

#         # ランダムな色を生成
#         color = (np.random.randint(0, 255), np.random.randint(0, 255), np.random.randint(0, 255))

#         # PILのImageDrawを使用してオーバーレイを描画
#         from PIL import ImageDraw
#         draw = ImageDraw.Draw(img)
#         draw.rectangle([(0, 0), (overlay_width, overlay_height)], fill=color)

#         return img


train_pipeline = [
    dict(type='LoadMultiViewImageFromFiles', to_float32=False, color_type='color'),
    dict(type='LoadMultiViewImageFromMultiSweeps', sweeps_num=num_frames - 1),
    dict(type='LoadAnnotations3D', with_bbox_3d=True, with_label_3d=True, with_attr_label=False),
    dict(type='ObjectRangeFilter', point_cloud_range=point_cloud_range),
    dict(type='ObjectNameFilter', classes=class_names),
    dict(type='RandomTransformImage', ida_aug_conf=ida_aug_conf, training=True),
    # ここにカスタムステップを追加
    dict(type='RandomBlackout', prob=0.5, ratio_range=(0.02, 0.2)),
    dict(type='GlobalRotScaleTransImage', rot_range=[-0.3925, 0.3925], scale_ratio_range=[0.95, 1.05]),
    dict(type='DefaultFormatBundle3D', class_names=class_names),
    dict(type='Collect3D', keys=['gt_bboxes_3d', 'gt_labels_3d', 'img'], meta_keys=(
        'filename', 'ori_shape', 'img_shape', 'pad_shape', 'lidar2img', 'img_timestamp'))
]

test_pipeline = [
    dict(type='LoadMultiViewImageFromFiles', to_float32=False, color_type='color'),
    dict(type='LoadMultiViewImageFromMultiSweeps', sweeps_num=num_frames - 1, test_mode=True),
    # テスト時にはランダムなデータ拡張を適用しないことが一般的ですが、
    # 特定の目的のためにここにカスタムステップを追加することもできます。
    # dict(type='RandomBlackout', prob=0.5, ratio_range=(0.02, 0.2)),
    dict(type='RandomTransformImage', ida_aug_conf=ida_aug_conf, training=False),
    dict(
        type='MultiScaleFlipAug3D',
        img_scale=(1600, 900),
        pts_scale_ratio=1,
        flip=False,
        transforms=[
            dict(type='DefaultFormatBundle3D', class_names=class_names, with_label=False),
            dict(type='Collect3D', keys=['img'], meta_keys=(
                'filename', 'box_type_3d', 'ori_shape', 'img_shape', 'pad_shape',
                'lidar2img', 'img_timestamp'))
        ])
]


@PIPELINES.register_module()
class RandomBlackout(object):
    """Randomly blackout a part of the image.
    
    Args:
        prob (float): Probability of the blackout operation being applied.
        ratio_range (tuple[float]): A tuple of min and max ratio for blackout area
                                    relative to the image size.
    """

    def __init__(self, prob=0.5, ratio_range=(0.02, 0.2)):
        assert 0 <= prob <= 1
        self.prob = prob
        self.ratio_range = ratio_range

    def __call__(self, results):
        """Apply the blackout operation to each image.
        
        Args:
            results (dict): Result dict from loading pipeline containing 'img'.
        
        Returns:
            dict: Updated result dict with blackout applied.
        """
        if np.random.rand() < self.prob:
            for i in range(len(results['img'])):
                img = results['img'][i]
                height, width = img.shape[:2]
                area = height * width
                
                # Determine blackout area size
                ratio = np.random.uniform(*self.ratio_range)
                blackout_area = int(area * ratio)
                
                # Determine position of blackout rectangle
                bh = int(np.sqrt(blackout_area * height / width))
                bw = int(blackout_area / bh)
                bx = np.random.randint(0, width - bw)
                by = np.random.randint(0, height - bh)
                
                # Apply blackout
                img[by:by+bh, bx:bx+bw, :] = 0
                results['img'][i] = img

        return results
