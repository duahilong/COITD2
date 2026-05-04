#!/usr/bin/env python3
import sys
import time
from pathlib import Path

print("[INFO] CloudflareSpeedTest 模拟程序启动")
print("[INFO] 收到参数:", " ".join(sys.argv[1:]))

output_path = Path("data/results/mock_output.csv")
args = sys.argv[1:]
for index, value in enumerate(args):
    if value == "-o" and index + 1 < len(args):
        output_path = Path(args[index + 1])
        break

for i in range(1, 6):
    print(f"[INFO] 测速进度: {i*20}%")
    time.sleep(1)

output_path.parent.mkdir(parents=True, exist_ok=True)
with output_path.open("w", encoding="utf-8") as f:
    f.write("IP 地址,已发送,已接收,丢包率,平均延迟,下载速度(MB/s),地区码\n")
    f.write("172.64.229.115,4,4,0.00,89.33,47.51,NRT\n")
    f.write("104.18.42.114,4,4,0.00,91.43,0.83,SIN\n")
    f.write("172.64.40.51,4,4,0.00,90.94,0.40,SIN\n")

print("[INFO] 测试完成")
print(f"[INFO] 结果已保存: {output_path}")
print("[INFO] 退出码: 0")

sys.exit(0)
