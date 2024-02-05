import os
import csv

HOGE_LIST, FUGA_LIST = [],[]
hoge_list, fuga_list = [],[]
cam_type = ['FRONT_RIGHT', 'FRONT', 'FRON_LEFT']

def save(hoge, fuga, piyo, file_path_iii):
    """
    FRONT_RIGHT_stereo| FRONT_RIGHT_mono | FRONT_stereo | FRONT_mono | FRONT_LEFT_stereo | FRONT_LEFT_mono
    -------------------------------------------------------------------------------------------------------
            1         |        2         |       3      |      4     |         5         |        6
            7         |        8         |       9      |      1     |         2         |        3
    """

    for cam_i in cam_type:
        a = 1
        b = 2
        c = 3
        d = a+b+c
        if a==1:
            hoge_list.append(a)
        else:
            fuga_list.append(b)
    HOGE_LIST.append(hoge_list)
    FUGA_LIST.append(fuga_list)

    # Prepare the CSV header
    header = 'FRONT_RIGHT_stereo, FRONT_RIGHT_mono, FRONT_stereo, FRONT_mono, FRONT_LEFT_stereo, FRONT_LEFT_mono\n'
    
    # Open the file to write
    with open(file_path_iii, 'w') as file:
        file.write(header)
        
        # Calculate the number of rows (assuming data_1 and data_2 have the same shape)
        num_rows = len(data_1)
        
        # Iterate through each row to organize and write data
        for i in range(num_rows):
            for j in range(len(data_1[i])):
                # Organize data as per the specified format
                row_data = [
                    data_1[j][i],  # Column A, B, C from data_1
                    data_2[j][i],  # Column D, E, F from data_2
                ]
                # Write the organized data as a row in the CSV
                file.write(','.join(str(item) for item in row_data) + '\n')


###############################
    
import numpy as np

def calculate_column_averages(csv_folder):
    # 初期化
    column_sums = np.zeros(6)  # 6列分の合計値
    num_rows = 0  # 総行数
    
    # 指定フォルダ内の全CSVファイルをリストアップ
    csv_files = [f for f in os.listdir(csv_folder) if f.endswith('.csv')]
    
    # 各ファイルを読み込み、列の合計を計算
    for file_name in csv_files:
        file_path = os.path.join(csv_folder, file_name)
        
        with open(file_path, mode='r') as csv_file:
            reader = csv.reader(csv_file)
            next(reader)  # ヘッダーをスキップ
            
            for row in reader:
                # 文字列のリストを浮動小数点数のnumpy配列に変換
                row_data = np.array(row, dtype=np.float64)
                column_sums += row_data
                num_rows += 1
    
    # 各列の平均値を計算
    column_averages = column_sums / num_rows
    
    return column_averages

# CSVファイルが保存されているフォルダを指定
csv_folder = 'csv'

# 平均値を計算
column_averages = calculate_column_averages(csv_folder)

# 結果を出力
columns = ['A', 'B', 'C', 'D', 'E', 'F']
for column, average in zip(columns, column_averages):
    print(f"{column}列の平均値: {average}")

