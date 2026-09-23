import zipfile
import zlib
import struct
from pathlib import Path

apk_path = Path("Hills/Hills.apk")
so_path = Path("Hills/extracted/lib/arm64-v8a/libapp_work.so")
out_apk = Path("Hills/Hills_Pro_Unlocked_V3.apk")

# 1. 拷贝原始apk作为基础
out_apk.write_bytes(apk_path.read_bytes())

# 2. 读取新的so文件
so_data = so_path.read_bytes()
new_crc = zlib.crc32(so_data) & 0xFFFFFFFF
new_size = len(so_data)

# 3. 在APK里找到 lib/arm64-v8a/libapp.so 并替换
# 我们通过直接搜索本地文件头的名字来原地修改，因为文件大小不变，所以直接覆盖内容和CRC
with open(out_apk, "r+b") as f:
    apk_data = bytearray(f.read())
    
    # 查找 Local File Header 中的 lib/arm64-v8a/libapp.so
    name = b"lib/arm64-v8a/libapp.so"
    idx = apk_data.find(name)
    if idx == -1:
        print("Not found in ZIP!")
        exit(1)
        
    lfh_start = idx - 30 # Local file header size before name
    if apk_data[lfh_start:lfh_start+4] != b"PK\x03\x04":
        print("Invalid LFH signature")
        exit(1)
        
    # 假设它是未压缩的 (STORED), 0x590000 左右偏移
    method = struct.unpack_from("<H", apk_data, lfh_start + 8)[0]
    if method != 0:
        print("SO is compressed, cannot inplace update.")
        exit(1)
        
    name_len = struct.unpack_from("<H", apk_data, lfh_start + 26)[0]
    extra_len = struct.unpack_from("<H", apk_data, lfh_start + 28)[0]
    
    data_start = lfh_start + 30 + name_len + extra_len
    
    print(f"Found LFH at {hex(lfh_start)}, data start {hex(data_start)}")
    print(f"Old CRC: {hex(struct.unpack_from('<I', apk_data, lfh_start + 14)[0])}")
    print(f"New CRC: {hex(new_crc)}")
    
    # 修改 LFH 的 CRC32
    struct.pack_into("<I", apk_data, lfh_start + 14, new_crc)
    
    # 覆盖文件内容
    apk_data[data_start:data_start+new_size] = so_data
    
    # 查找 Central Directory 中的条目并修改 CRC32
    cd_idx = apk_data.find(b"PK\x01\x02", data_start)
    while cd_idx != -1:
        cd_name_len = struct.unpack_from("<H", apk_data, cd_idx + 28)[0]
        cd_name = apk_data[cd_idx + 46 : cd_idx + 46 + cd_name_len]
        if cd_name == name:
            print(f"Found CD at {hex(cd_idx)}")
            struct.pack_into("<I", apk_data, cd_idx + 16, new_crc)
            break
        cd_idx = apk_data.find(b"PK\x01\x02", cd_idx + 46)
        
    f.seek(0)
    f.write(apk_data)
    
print("Injected successfully, but V2 signature is invalidated.")
