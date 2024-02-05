
# 画像加工処理をパイプラインに追加
test_pipeline.append(
    dict(type='RandomColorAdjust', brightness=0.2, contrast=0.2, saturation=0.2, hue=0.1)
)

import numpy as np
from PIL import Image

@PIPELINES.register_module()
class RandomTransformImage(object):
    def __init__(self, ida_aug_conf=None, training=True, apply_to_front_only=True):
        self.ida_aug_conf = ida_aug_conf
        self.training = training
        self.apply_to_front_only = apply_to_front_only

    def __call__(self, results):
        if not self.training or not self.apply_to_front_only:
            # トレーニングモードでない、またはフロントカメラ画像のみに適用しない設定の場合は、
            # 何も変更せずに結果を返します。
            return results

        for i, img_info in enumerate(results['img_metas']):
            if 'front' in img_info['filename']:
                # フロントカメラの画像に対してのみ加工を適用します。
                img = Image.fromarray(np.uint8(results['img'][i]))
                img = self.apply_random_color_change(img)
                results['img'][i] = np.array(img).astype(np.uint8)

        return results

    def apply_random_color_change(self, img):
        """
        画像の左上隅にランダムな色のオーバーレイを適用します。
        """
        # 画像サイズの取得
        width, height = img.size

        # オーバーレイする領域のサイズ（例：画像の10%）
        overlay_width, overlay_height = width // 10, height // 10

        # ランダムな色を生成
        color = (np.random.randint(0, 255), np.random.randint(0, 255), np.random.randint(0, 255))

        # PILのImageDrawを使用してオーバーレイを描画
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.rectangle([(0, 0), (overlay_width, overlay_height)], fill=color)

        return img
