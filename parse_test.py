import pandas as pd
import glob
import os

DATA_DIR = "D:/RESEARCH/Nakdong"
param_files = glob.glob(os.path.join(DATA_DIR, "매개변수비교", "*_매개변수비교.xlsx"))
opt_status = {}
for f in param_files:
    df = pd.read_excel(f)
    for idx, row in df.iterrows():
        name = row['지점명']
        # if any of 변화량 != 0, it's optimized
        amc = row.get('AMC_변화량', 0)
        bk = row.get('bas_K_변화량', 0)
        btl = row.get('bas_Tl_변화량', 0)
        if amc != 0 or bk != 0 or btl != 0:
            opt_status[name] = "최적화 지점"
        else:
            opt_status[name] = "default 지점"
print(list(opt_status.items())[:10])
