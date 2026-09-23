// 项目I Ordinal_102 activation-state patch engine (C# port of
// scripts/sab_patch_activation.py; spec recovered from case
// 20260901-项目I-keygen, verified against 项目IX64_patched.dll
// SHA256 c07e0cac...).
//
//   file offset 0x1588 = RVA 0x2188 = VA 0x180002188 (Ordinal_102 entry)
//   orig 12B: 48 89 5c 24 08 55 56 57 48 8d ac 24   (prologue)
//   new  12B: c7 01 31 00 00 00 b8 01 00 00 00 c3
//             mov dword ptr [rcx], 0x31 ; out[0] = 0x31 (activated state)
//             mov eax, 1                ; return 1
//             ret
// Equal-length in-place replacement; original DLL backed up before apply.
using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace SabLicense
{
    public static class PatchEngine
    {
        public const int OFFSET = 0x1588;
        public static readonly byte[] ORIG = { 0x48, 0x89, 0x5c, 0x24, 0x08, 0x55, 0x56, 0x57, 0x48, 0x8d, 0xac, 0x24 };
        public static readonly byte[] NEW = { 0xc7, 0x01, 0x31, 0x00, 0x00, 0x00, 0xb8, 0x01, 0x00, 0x00, 0x00, 0xc3 };
        public const string BACKUP_SUBDIR = "patches";
        public const string AUDIT_FILE = "sab_patch_audit.jsonl";

        const string DEFAULT_DLL = @"C:\Program Files\项目I\项目IX64.dll";

        public static string DefaultDllPath()
        {
            string env = Environment.GetEnvironmentVariable("SAB_DLL");
            return string.IsNullOrEmpty(env) ? DEFAULT_DLL : env;
        }

        // Pure byte transform: content[OFFSET .. OFFSET+12] ORIG -> NEW (apply)
        // or NEW -> ORIG (revert). Throws if bytes do not match either.
        public static byte[] Swap(byte[] content, bool apply)
        {
            if (content == null || content.Length < OFFSET + 12)
                throw new InvalidDataException("content too short for patch offset");
            byte[] from = apply ? ORIG : NEW;
            byte[] to = apply ? NEW : ORIG;
            for (int i = 0; i < 12; i++)
                if (content[OFFSET + i] != from[i])
                    throw new InvalidDataException(
                        "bytes at 0x1588 match neither original nor patch; refusing (different DLL version?)");
            byte[] result = (byte[])content.Clone();
            Buffer.BlockCopy(to, 0, result, OFFSET, 12);
            return result;
        }

        public static string State(string dllPath)
        {
            if (!File.Exists(dllPath)) return "missing: " + dllPath;
            byte[] cur = new byte[12];
            using (var f = File.OpenRead(dllPath))
            {
                f.Seek(OFFSET, SeekOrigin.Begin);
                f.Read(cur, 0, 12);
            }
            if (ByteEq(cur, NEW)) return "patched";
            if (ByteEq(cur, ORIG)) return "original";
            return "unknown";
        }

        public static string Apply(string dllPath, string backupDir)
        {
            return DoSwap(dllPath, backupDir, apply: true);
        }

        public static string Revert(string dllPath, string backupDir)
        {
            return DoSwap(dllPath, backupDir, apply: false);
        }

        static string DoSwap(string dllPath, string backupDir, bool apply)
        {
            if (!File.Exists(dllPath))
                return "ERROR: DLL not found: " + dllPath + Environment.NewLine;
            string st = State(dllPath);
            string want = apply ? "original" : "patched";
            if ((apply && st == "patched") || (!apply && st == "original"))
                return (apply ? "already patched" : "not patched") + " (no change)" + Environment.NewLine;
            if (st != want)
                return "ERROR: state is '" + st + "'; refusing to " + (apply ? "patch" : "revert") + Environment.NewLine;

            byte[] content = File.ReadAllBytes(dllPath);
            byte[] replaced;
            try
            {
                replaced = Swap(content, apply); // throws on mismatch
            }
            catch (InvalidDataException ex)
            {
                return "ERROR: " + ex.Message + Environment.NewLine;
            }

            string backup = null;
            if (apply)
            {
                Directory.CreateDirectory(backupDir);
                backup = Path.Combine(backupDir,
                    Path.GetFileName(dllPath) + ".orig-" + DateTime.Now.ToString("yyyyMMdd-HHmmss"));
                File.WriteAllBytes(backup, content);
            }
            File.WriteAllBytes(dllPath, replaced);
            WriteAudit(backupDir, apply, dllPath, backup);
            return (apply ? "patched " : "reverted ") + dllPath + " @0x" + OFFSET.ToString("x4") + Environment.NewLine +
                   "  orig: " + Hex(ORIG) + Environment.NewLine +
                   "  new : " + Hex(NEW) + Environment.NewLine +
                   (backup != null ? "  backup: " + backup + Environment.NewLine : "") +
                   "  sha256: " + Sha256Hex(dllPath) + Environment.NewLine;
        }

        static void WriteAudit(string backupDir, bool apply, string dllPath, string backup)
        {
            try
            {
                string file = Path.Combine(backupDir, AUDIT_FILE);
                Directory.CreateDirectory(Path.GetDirectoryName(file));
                string entry = "{\"ts\":\"" + DateTime.Now.ToString("s") +
                    "\",\"action\":\"" + (apply ? "apply" : "revert") +
                    "\",\"dll\":\"" + dllPath.Replace("\\", "\\\\") +
                    "\",\"offset\":" + OFFSET +
                    ",\"orig_hex\":\"" + Hex(ORIG) +
                    "\",\"new_hex\":\"" + Hex(NEW) +
                    "\",\"sha256_after\":\"" + Sha256Hex(dllPath) +
                    "\",\"backup\":\"" + (backup != null ? Path.GetFileName(backup) : "") + "\"}" + Environment.NewLine;
                File.AppendAllText(file, entry, Encoding.UTF8);
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("audit write failed: " + ex.Message);
            }
        }

        static bool ByteEq(byte[] a, byte[] b)
        {
            if (a.Length != b.Length) return false;
            for (int i = 0; i < a.Length; i++) if (a[i] != b[i]) return false;
            return true;
        }

        public static string Sha256Hex(string path)
        {
            using (var sha = SHA256.Create())
            using (var f = File.OpenRead(path))
                return Hex(sha.ComputeHash(f));
        }

        public static string Hex(byte[] b)
        {
            var sb = new StringBuilder(b.Length * 2);
            foreach (byte x in b) sb.Append(x.ToString("x2"));
            return sb.ToString();
        }
    }
}