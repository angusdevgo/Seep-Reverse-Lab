// 项目I <目标版本> license algorithm (reconstructed from 项目IX64.dll)
// Evidence: cases/20260901-项目I-keygen/exports/ (Ghidra headless decompile)
//   FUN_180001a20 : md5hex  (BCryptHash MD5 -> "%02x" x16)
//   FUN_180001a90 : A = system disk ATA serial, fallback "xxxx xxxx"
//   FUN_180001b9c : B = SMBIOS Type1 UUID,  fallback "yyyy yyyy"
//   FUN_180001d24 : LicenseHash = md5hex(License default value) when len > 0x1e
//   Ordinal_103   : request R = LicenseHash + md5hex(A) + md5hex(B)  (96 hex)
//   FUN_180001e8c : P = base64(ActivationData)^e mod n; sliding window o in [0,0x1b]:
//       P[o:o+32]     == LicenseHash hex
//       P[o+32:o+96]  == CONST (universal)  OR  md5hex(A)+md5hex(B) (machine bound)
//       P[o+96:o+102] == "SABALL"
// Verdict: the final element requires the vendor RSA private key (d); offline keygen
// cannot forge ActivationData. This tool reproduces local elements and manages state.
using System;
using System.Security.Cryptography;
using System.Text;

namespace SabLicense
{
    public static class LicenseAlgo
    {
        // CNG BCRYPT_RSAPUBLICBLOB @ 项目IX64.dll file offset 0xA3160 (A64: 0xB1FB0)
        public const string MODULUS_HEX =
            "c3a6cca1d7df7c50b15badef2d7663d4358ff20aa9ff78a7e6d9083c24ee9f" +
            "1b27d2271538f3268bf5abeddb740cfa9569a5e487e009c6b39b72f7c156a5" +
            "1a603ec4bf53f49501c3c4621ed502ea55170444b98add84485b98eb6d33e8" +
            "61fe5834558cb08d29b1fd6adfd78a1cc04b44cdbd7ef5a395c4cb1de140d5" +
            "63ce79";
        public const long PUB_E = 65537;
        public const int MODULUS_BITS = 1016; // weak modulus: smallest prime factor 2663

        // embedded universal digest constant (.rdata @0x1800A3E90, 64 hex chars)
        public const string CONST_HEX =
            "4e9934f69c3fd8c3e8502a2fd1ab89c2e78671d38a9b97ba313f5eaba6fd420f";

        public const string MAGIC = "SABALL";
        public const int REQ_LEN = 96;            // request hex length (Ordinal_103)
        public const int PLAIN_LEN = 128;         // RSA-1024 block
        public const int MIGRATION_MIN_KEY_LEN = 0x1F; // FUN_180001d24 threshold (>0x1e)

        public const string DEFAULT_DISK_SN = "xxxx xxxx";
        public const string DEFAULT_SMBIOS_UUID = "yyyy yyyy";

        public static string Md5Hex(string text)
        {
            using (var md5 = MD5.Create())
            {
                byte[] h = md5.ComputeHash(Encoding.ASCII.GetBytes(text));
                var sb = new StringBuilder(32);
                foreach (byte b in h) sb.Append(b.ToString("x2"));
                return sb.ToString();
            }
        }

        public static string Md5Hex(byte[] data)
        {
            using (var md5 = MD5.Create())
            {
                byte[] h = md5.ComputeHash(data);
                var sb = new StringBuilder(32);
                foreach (byte b in h) sb.Append(b.ToString("x2"));
                return sb.ToString();
            }
        }

        // FUN_180001d24: LicenseHash = md5hex(key) (32 hex chars)
        public static string LicenseHash(string keyText)
        {
            return Md5Hex(keyText);
        }

        // Ordinal_103: R = LicenseHash + md5hex(A) + md5hex(B)
        public static string ExpectedRequest(string licenseHashHex, string diskSn, string smbiosUuid)
        {
            return licenseHashHex + Md5Hex(diskSn) + Md5Hex(smbiosUuid);
        }

        // FUN_180001e8c plaintext-level verdict (structure in header comment)
        public static bool VerifyPlaintext(byte[] plain, string requestHex)
        {
            if (plain == null || plain.Length < PLAIN_LEN || requestHex == null
                || requestHex.Length != REQ_LEN)
                return false;
            string lh = requestHex.Substring(0, 32);
            string md5a = requestHex.Substring(32, 32);
            string md5b = requestHex.Substring(64, 32);
            for (int off = 0; off < 0x1B; off++)
            {
                if (!EqualsAt(plain, off, lh)) continue;
                bool universal = EqualsAt(plain, off + 32, CONST_HEX);
                bool machine = EqualsAt(plain, off + 32, md5a) && EqualsAt(plain, off + 64, md5b);
                bool magic = Encoding.ASCII.GetString(plain, off + 96, 6) == MAGIC;
                if ((universal || machine) && magic) return true;
            }
            return false;
        }

        private static bool EqualsAt(byte[] buf, int off, string hexOrAscii)
        {
            if (off + hexOrAscii.Length > buf.Length) return false;
            for (int i = 0; i < hexOrAscii.Length; i++)
            {
                if (buf[off + i] != (byte)hexOrAscii[i]) return false;
            }
            return true;
        }

        // Build the plaintext shape that the vendor would sign (server-side logic;
        // kept for documentation/selftest only - the signature itself needs d).
        public static byte[] BuildPlaintextShape(string requestHex, bool machineBound)
        {
            var plain = new byte[PLAIN_LEN];
            byte[] lh = Encoding.ASCII.GetBytes(requestHex.Substring(0, 32));
            byte[] mid = machineBound
                ? Encoding.ASCII.GetBytes(requestHex.Substring(32, 64))
                : Encoding.ASCII.GetBytes(CONST_HEX);
            byte[] magic = Encoding.ASCII.GetBytes(MAGIC);
            Buffer.BlockCopy(lh, 0, plain, 0, 32);
            Buffer.BlockCopy(mid, 0, plain, 32, 64);
            Buffer.BlockCopy(magic, 0, plain, 96, 6);
            return plain;
        }

        // base64 decode of ActivationData (FUN_005d07a0: CryptStringToBinaryA BASE64)
        public static byte[] DecodeActivation(string b64)
        {
            return Convert.FromBase64String(b64);
        }
    }
}
