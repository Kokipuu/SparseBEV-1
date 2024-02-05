from PIL import Image
import os

def create_gif(image_folder, output_filename, duration=500):
    # 画像ファイルのリストを取得
    images = [img for img in os.listdir(image_folder) if img.endswith('.jpg')]
    images.sort()  # ファイル名順にソート
    
    # 各画像を読み込み、GIFに追加
    frames = []
    for image in images:
        img_path = os.path.join(image_folder, image)
        new_frame = Image.open(img_path)
        frames.append(new_frame)
    
    # 最初の画像を基にGIFを保存
    frames[0].save(output_filename, format='GIF',
                   append_images=frames[1:],
                   save_all=True,
                   duration=duration, loop=0)

# 画像が保存されているフォルダと出力ファイル名を指定
image_folder = 'image'
output_filename = 'output.gif'

# GIFを作成
create_gif(image_folder, output_filename)

print(f'GIF has been created: {output_filename}')
