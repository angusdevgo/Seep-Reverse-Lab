from pathlib import Path
import sys
import struct
import zlib
import os
import hashlib
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography import x509
from cryptography.x509.oid import NameOID
import datetime

# A simplified pure-python APK Signature Scheme v2 signer

def create_key():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"Hills Patch")])
    cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(private_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(datetime.datetime.utcnow()).not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=10000)).sign(private_key, hashes.SHA256())
    return private_key, cert.public_bytes(serialization.Encoding.DER)

def length_prefixed(data):
    return struct.pack('<I', len(data)) + data

def find_eocd(data):
    for i in range(len(data)-22, max(0, len(data)-65535-22), -1):
        if data[i:i+4] == b"PK\x05\x06":
            return i
    raise Exception("EOCD not found")

def get_apk_chunks(data):
    eocd_pos = find_eocd(data)
    cd_start = struct.unpack('<I', data[eocd_pos+16:eocd_pos+20])[0]
    
    # 查找是否有旧的 APK Signing Block
    # CD 之前是一个 APK Signing Block，标志为 "APK Sig Block 42"
    magic = b"APK Sig Block 42"
    if data[cd_start-16:cd_start] == magic:
        sig_block_size = struct.unpack('<Q', data[cd_start-24:cd_start-16])[0]
        sig_block_start = cd_start - 24 - (sig_block_size - 24)
        if struct.unpack('<Q', data[sig_block_start:sig_block_start+8])[0] == sig_block_size:
            chunk1 = data[:sig_block_start]
            chunk3 = data[cd_start:eocd_pos]
            eocd = bytearray(data[eocd_pos:])
            struct.pack_into('<I', eocd, 16, sig_block_start) # 更新 EOCD 中的 CD 偏移
            return chunk1, chunk3, eocd
            
    chunk1 = data[:cd_start]
    chunk3 = data[cd_start:eocd_pos]
    eocd = bytearray(data[eocd_pos:])
    return chunk1, chunk3, eocd

def compute_v2_digest(chunk1, chunk3, eocd):
    md = hashlib.sha256()
    md.update(struct.pack('<I', 1)) # prefix chunks
    md.update(length_prefixed(b'')) # dummy
    
    # 分块计算 (1MB)
    def update_chunk(c, md):
        for i in range(0, len(c), 1048576):
            chunk = c[i:i+1048576]
            m = hashlib.sha256()
            m.update(b'\xa5')
            m.update(struct.pack('<I', len(chunk)))
            m.update(chunk)
            md.update(m.digest())
            
    m = hashlib.sha256()
    chunks_count = (len(chunk1) + 1048575) // 1048576 + (len(chunk3) + 1048575) // 1048576 + (len(eocd) + 1048575) // 1048576
    m.update(struct.pack('<I', chunks_count))
    update_chunk(chunk1, m)
    update_chunk(chunk3, m)
    update_chunk(eocd, m)
    
    res = hashlib.sha256()
    res.update(b'\x5a')
    res.update(struct.pack('<I', chunks_count))
    res.update(m.digest())
    return res.digest()

def build_v2_block(digest, priv, cert):
    # sign
    sig = priv.sign(digest, padding.PKCS1v15(), hashes.SHA256())
    
    # 构造 structures
    # algorithm ID for SHA256withRSA is 0x0103
    alg_id = struct.pack('<I', 0x0103)
    dig_val = length_prefixed(alg_id + length_prefixed(digest))
    sig_val = length_prefixed(alg_id + length_prefixed(sig))
    
    cert_val = length_prefixed(cert)
    
    public_key = priv.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    
    signer = length_prefixed(
        length_prefixed(dig_val) + 
        length_prefixed(cert_val) + 
        length_prefixed(sig_val) + 
        length_prefixed(public_key)
    )
    
    signed_data = length_prefixed(length_prefixed(signer))
    
    v2_id = struct.pack('<I', 0x7109871a)
    v2_val = v2_id + signed_data
    v2_pair = length_prefixed(v2_val)
    
    block_data = v2_pair
    size = len(block_data) + 24
    
    block = struct.pack('<Q', size) + block_data + struct.pack('<Q', size) + b"APK Sig Block 42"
    return block

def sign_apk(in_path, out_path):
    data = Path(in_path).read_bytes()
    c1, c3, eocd = get_apk_chunks(data)
    
    priv, cert = create_key()
    digest = compute_v2_digest(c1, c3, eocd)
    
    sig_block = build_v2_block(digest, priv, cert)
    
    # update CD offset in EOCD
    struct.pack_into('<I', eocd, 16, len(c1) + len(sig_block))
    
    with open(out_path, 'wb') as f:
        f.write(c1)
        f.write(sig_block)
        f.write(c3)
        f.write(eocd)
        
    print(f"Signed {in_path} -> {out_path} with v2 signature.")

sign_apk("Hills/Hills_Pro_Unlocked_V3.apk", "Hills/Hills_Pro_Unlocked_V3_Signed.apk")
