using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.Security.Cryptography;

namespace IDM_Toolkit_Wpf
{
    /// <summary>
    /// 补丁引擎回归测试（AOB 特征码版 v3）
    /// 覆盖：项目D 6.43 build 10 / build 11 (6.43.11.2) / build 11 (6.43.11.3)
    /// 用法: PatchEngineTests.exe [b10] [b11.2] [b11.3]
    /// </summary>
    public class TestHarness
    {
        static int pass = 0, fail = 0;

        static void Check(string name, bool ok)
        {
            Console.WriteLine((ok ? "  [PASS] " : "  [FAIL] ") + name);
            if (ok) pass++; else fail++;
        }

        static void Nop(string s) { }

        static string Sha(string p)
        {
            using (var s = SHA256.Create())
            {
                byte[] h = s.ComputeHash(File.ReadAllBytes(p));
                StringBuilder sb = new StringBuilder();
                foreach (byte b in h) sb.Append(b.ToString("X2"));
                return sb.ToString();
            }
        }

        static List<int> DiffOffsets(byte[] a, byte[] b)
        {
            List<int> d = new List<int>();
            int n = Math.Min(a.Length, b.Length);
            for (int i = 0; i < n; i++) if (a[i] != b[i]) d.Add(i);
            return d;
        }

        static bool DiffAllExpected(List<int> diffs, MainWindow.PeInfo pe,
                                    MainWindow.NativeBinaryPatcher.AobHit[] hits, out string detail)
        {
            HashSet<int> expected = new HashSet<int>();
            foreach (var h in hits)
                for (int i = 0; i < h.Point.Patch.Length; i++) expected.Add(h.SiteOffset + i);
            for (int i = 0; i < 8; i++) expected.Add(pe.SecurityDirOffset + i);
            for (int i = 0; i < 4; i++) expected.Add(pe.CheckSumOffset + i);

            List<int> unexpected = new List<int>();
            foreach (int o in diffs) if (!expected.Contains(o)) unexpected.Add(o);
            detail = unexpected.Count == 0 ? "" : ("意外改动偏移: " + string.Join(", ", unexpected.ConvertAll(x => "0x" + x.ToString("X")).ToArray()));
            return unexpected.Count == 0;
        }

        static void RunVersion(string label, string srcPath, string baseDir)
        {
            Console.WriteLine("=======================================================");
            Console.WriteLine("=== " + label);
            Console.WriteLine("=======================================================");

            string work = Path.Combine(baseDir, label.Replace(" ", "_").Replace(".", "").Replace("(", "").Replace(")", ""));
            Directory.CreateDirectory(work);
            string t = Path.Combine(work, "项目D.exe");
            File.Copy(srcPath, t, true);
            byte[] orig = File.ReadAllBytes(t);

            MainWindow.PeInfo pe0; string e0;
            Check("原版 PE 解析成功", MainWindow.PeImageUtil.TryParse(orig, out pe0, out e0));
            Console.WriteLine("    版本=v" + MainWindow.NativeBinaryPatcher.GetFileVersionSafe(srcPath)
                            + "  体积=" + orig.Length.ToString("N0")
                            + "  映像末尾=0x" + pe0.ImageEnd.ToString("X"));

            int cnt = 0;
            bool ok = MainWindow.NativeBinaryPatcher.ApplyPatch(t, true, Nop, out cnt);
            Check("补丁执行返回 true", ok);
            Check("生效位点数 = " + MainWindow.NativeBinaryPatcher.RulesCount,
                  cnt == MainWindow.NativeBinaryPatcher.RulesCount);
            Check("BAK 备份已创建", File.Exists(t + ".BAK"));
            Check("无残留临时文件",
                  !File.Exists(t + ".rollback.tmp") && !File.Exists(t + ".new.tmp"));

            byte[] patched = File.ReadAllBytes(t);

            MainWindow.PeInfo pe1; string e1;
            Check("产物 PE 结构合法", MainWindow.PeImageUtil.TryParse(patched, out pe1, out e1));

            uint stored = (uint)(patched[pe1.CheckSumOffset] | (patched[pe1.CheckSumOffset + 1] << 8)
                               | (patched[pe1.CheckSumOffset + 2] << 16) | (patched[pe1.CheckSumOffset + 3] << 24));
            Check("产物 PE 校验和自洽", stored == MainWindow.PeImageUtil.ComputeChecksum(patched, pe1.CheckSumOffset));
            Check("已剥离 Authenticode 签名尾部", patched.Length == pe0.ImageEnd);

            MainWindow.NativeBinaryPatcher.AobHit[] hits;
            bool rescan = MainWindow.NativeBinaryPatcher.ScanAll(patched, Nop, out hits);
            Check("产物 AOB 复扫全表命中", rescan);
            int already = 0;
            if (hits != null) foreach (var h in hits) if (h != null && h.AlreadyPatched) already++;
            Check("产物 " + MainWindow.NativeBinaryPatcher.RulesCount + "/" + MainWindow.NativeBinaryPatcher.RulesCount + " 位点均为已补丁态",
                  already == MainWindow.NativeBinaryPatcher.RulesCount);

            List<int> diffs = DiffOffsets(orig, patched);
            string detail;
            bool clean = DiffAllExpected(diffs, pe0, hits, out detail);
            Console.WriteLine("    相对原版差异字节数 = " + diffs.Count + (clean ? "" : "   " + detail));
            Check("所有改动均落在预期位点（无意外改动）", clean);

            string before = Sha(t);
            int c2 = 0;
            bool ok2 = MainWindow.NativeBinaryPatcher.ApplyPatch(t, true, Nop, out c2);
            Check("重复执行返回 true（幂等）", ok2);
            Check("重复执行文件零变化", Sha(t).Equals(before, StringComparison.OrdinalIgnoreCase));

            Console.WriteLine("    产物 SHA256: " + before);
            Console.WriteLine();
        }

        /// <summary>陈旧 BAK 回归用例：项目D 升级后旧备份必须被识别并刷新</summary>
        static void RunStaleBackupCase(string staleBak, string currentExe, string baseDir)
        {
            Console.WriteLine("=======================================================");
            Console.WriteLine("=== 陈旧 BAK 回归用例（升级后回滚点错版缺陷）");
            Console.WriteLine("=======================================================");

            string work = Path.Combine(baseDir, "stalebak");
            Directory.CreateDirectory(work);
            string t = Path.Combine(work, "项目D.exe");
            File.Copy(currentExe, t, true);
            File.Copy(staleBak, t + ".BAK", true);   // 放入上一版本的旧备份

            string curVer = MainWindow.NativeBinaryPatcher.GetFileVersionSafe(t);
            string oldBakVer = MainWindow.NativeBinaryPatcher.GetFileVersionSafe(t + ".BAK");
            Console.WriteLine("    当前 项目D.exe      = v" + curVer);
            Console.WriteLine("    陈旧 项目D.exe.BAK  = v" + oldBakVer);
            Check("构造成功：备份版本与当前版本确实不同", curVer != oldBakVer);

            int cnt = 0;
            bool ok = MainWindow.NativeBinaryPatcher.ApplyPatch(t, true, Nop, out cnt);
            Check("补丁执行返回 true（自动刷新备份后继续）", ok);

            string newBakVer = MainWindow.NativeBinaryPatcher.GetFileVersionSafe(t + ".BAK");
            Check("BAK 已刷新为当前版本 (v" + curVer + ")", newBakVer == curVer);
            Check("BAK 内容 = 当前版本的官方原版（哈希一致）",
                  Sha(t + ".BAK").Equals(Sha(currentExe), StringComparison.OrdinalIgnoreCase));

            string archived = t + ".BAK." + oldBakVer.Replace(", ", ".").Replace(" ", "");
            Check("旧版备份已归档保留 (" + Path.GetFileName(archived) + ")", File.Exists(archived));

            // 还原必须成功且得到当前版本
            bool restored = MainWindow.RestoreBinaryOnly(work, Nop, false);
            Check("一键还原成功", restored);
            Check("还原后版本 = " + curVer, MainWindow.NativeBinaryPatcher.GetFileVersionSafe(t) == curVer);
            Check("还原后哈希 = 当前版本官方原版",
                  Sha(t).Equals(Sha(currentExe), StringComparison.OrdinalIgnoreCase));
            Console.WriteLine();
        }

        /// <summary>版本不一致时必须拒绝还原</summary>
        static void RunRestoreGuardCase(string staleBak, string currentExe, string baseDir)
        {
            Console.WriteLine("=======================================================");
            Console.WriteLine("=== 还原守卫用例（版本不一致必须拒绝）");
            Console.WriteLine("=======================================================");

            string work = Path.Combine(baseDir, "restoreguard");
            Directory.CreateDirectory(work);
            string t = Path.Combine(work, "项目D.exe");
            File.Copy(currentExe, t, true);
            File.Copy(staleBak, t + ".BAK", true);
            string before = Sha(t);

            bool restored = MainWindow.RestoreBinaryOnly(work, Nop, false);
            Check("版本不一致时还原被拒绝", !restored);
            Check("项目D.exe 未被旧版覆盖", Sha(t).Equals(before, StringComparison.OrdinalIgnoreCase));
            Console.WriteLine();
        }

        public static void Main(string[] args)
        {
            string b10 = args.Length > 0 ? args[0] : Path.Combine("..", "samples", "项目D_643b10_original.exe");
            string b112 = args.Length > 1 ? args[1] : Path.Combine("..", "samples", "项目D_643b11_original.exe");
            string b113 = args.Length > 2 ? args[2] : Path.Combine("..", "samples", "项目D_643b11b3_original.exe");

            foreach (var p in new[] { b10, b112, b113 })
                if (!File.Exists(p)) { Console.WriteLine("找不到样本: " + p); Environment.ExitCode = 2; return; }

            string baseDir = Path.Combine(Path.GetTempPath(), "idm_aob_test_" + Guid.NewGuid().ToString("N").Substring(0, 8));
            Directory.CreateDirectory(baseDir);
            Console.WriteLine("SANDBOX: " + baseDir);
            Console.WriteLine("b10   : " + b10);
            Console.WriteLine("b11.2 : " + b112);
            Console.WriteLine("b11.3 : " + b113);
            Console.WriteLine();

            // 用例 0：校验和算法自校验
            Console.WriteLine("=== 用例0: PE 校验和算法自校验（对齐官方原版）===");
            foreach (var pair in new[] { new[] { "b10", b10 }, new[] { "b11.2", b112 }, new[] { "b11.3", b113 } })
            {
                byte[] d = File.ReadAllBytes(pair[1]);
                MainWindow.PeInfo pi; string er;
                MainWindow.PeImageUtil.TryParse(d, out pi, out er);
                uint st = (uint)(d[pi.CheckSumOffset] | (d[pi.CheckSumOffset + 1] << 8)
                               | (d[pi.CheckSumOffset + 2] << 16) | (d[pi.CheckSumOffset + 3] << 24));
                uint cv = MainWindow.PeImageUtil.ComputeChecksum(d, pi.CheckSumOffset);
                Check(pair[0] + " 标准算法复现官方存储校验和 (0x" + st.ToString("X8") + ")", st == cv);
            }
            Console.WriteLine();

            // 三版本端到端
            RunVersion("项目D 6.43 build 10", b10, baseDir);
            RunVersion("项目D 6.43 build 11 (6.43.11.2)", b112, baseDir);
            RunVersion("项目D 6.43 build 11 (6.43.11.3)", b113, baseDir);

            // 备份/还原相关
            RunStaleBackupCase(b10, b113, baseDir);
            RunRestoreGuardCase(b10, b113, baseDir);

            // 负向用例
            Console.WriteLine("=======================================================");
            Console.WriteLine("=== 负向用例（必须拒绝且零写入）");
            Console.WriteLine("=======================================================");
            string neg = Path.Combine(baseDir, "neg");
            Directory.CreateDirectory(neg);
            byte[] o113 = File.ReadAllBytes(b113);

            string t3 = Path.Combine(neg, "trunc.exe");
            byte[] d3 = new byte[6000000];
            Array.Copy(o113, d3, 6000000);
            File.WriteAllBytes(t3, d3);
            string h3 = Sha(t3);
            int c3 = 0;
            Check("节区截断的损坏映像 -> 拒绝", !MainWindow.NativeBinaryPatcher.ApplyPatch(t3, true, Nop, out c3));
            Check("损坏文件零改动", Sha(t3).Equals(h3, StringComparison.OrdinalIgnoreCase));
            Check("未创建 BAK", !File.Exists(t3 + ".BAK"));
            Check("DiagnoseExecutable 识别损坏", MainWindow.NativeBinaryPatcher.DiagnoseExecutable(t3) != null);

            string t4 = Path.Combine(neg, "unknown.exe");
            byte[] d4 = (byte[])o113.Clone();
            d4[0x2D3FD] = 0x90;   // 破坏 b11.3 的授权分支检测位点
            File.WriteAllBytes(t4, d4);
            string h4 = Sha(t4);
            int c4 = 0;
            Check("特征码不匹配（未支持版本）-> 拒绝", !MainWindow.NativeBinaryPatcher.ApplyPatch(t4, true, Nop, out c4));
            Check("未知版本文件零改动", Sha(t4).Equals(h4, StringComparison.OrdinalIgnoreCase));
            Check("未创建 BAK", !File.Exists(t4 + ".BAK"));

            string t5 = Path.Combine(neg, "empty.exe");
            File.WriteAllBytes(t5, new byte[0]);
            int c5 = 0;
            Check("空文件 -> 拒绝", !MainWindow.NativeBinaryPatcher.ApplyPatch(t5, true, Nop, out c5));

            string t6 = Path.Combine(neg, "text.exe");
            File.WriteAllBytes(t6, Encoding.UTF8.GetBytes("This is definitely not a PE file, just plain text."));
            int c6 = 0;
            Check("非 PE 文本 -> 拒绝", !MainWindow.NativeBinaryPatcher.ApplyPatch(t6, true, Nop, out c6));
            Console.WriteLine();

            Console.WriteLine("=======================================================");
            Console.WriteLine("  测试结果:  PASS = " + pass + "   FAIL = " + fail);
            Console.WriteLine("=======================================================");
            try { Directory.Delete(baseDir, true); } catch { }
            Environment.ExitCode = (fail == 0) ? 0 : 1;
        }
    }
}
