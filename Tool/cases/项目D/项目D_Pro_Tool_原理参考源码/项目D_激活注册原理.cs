// ============================================================================
//  项目D Pro Tool —— 激活与注册原理参考源码
// ----------------------------------------------------------------------------
//  用途：仅用于学习、研究 项目D 授权校验机制的工作方式。
//  说明：本文件是「原理参考版」，只保留激活 / 注册 / 还原的核心逻辑，
//        并附带详尽中文注释，便于对照阅读。
//        本目录不含编译脚本与图标；可编译的完整工程位于同级 IDM_Pro_Tool\。
//
//  目标程序：项目D.exe  <目标版本> build 10
//    原始文件：6,199,664 字节
//      SHA256：<实测哈希>
//    修补之后：6,189,056 字节
//      SHA256：<实测哈希>
//
//  三条主线：
//    ① 二进制指令修补 —— 18 个补丁点 / 共 31 字节
//    ② 注册表授权登记 —— 写入授权人姓名，且必须删除 Serial 键
//    ③ 签名剥离与截断 —— 清空证书目录并截断尾部 10,608 字节
// ============================================================================

using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using Microsoft.Win32;

namespace IDM_Activation_Principle
{
    // ========================================================================
    //  一、补丁点数据结构
    // ------------------------------------------------------------------------
    //  每个补丁点描述「在文件的哪个绝对偏移、把哪几个字节、改成哪几个字节」。
    //  采用绝对偏移而非特征码搜索，原因是 项目D v6.43b10 的镜像布局固定，
    //  绝对偏移更精确；同时保留 Expected（原始字节）用于二次校验，
    //  避免把不匹配的版本误改坏。
    // ========================================================================
    internal class PatchPoint
    {
        public string Name;         // 补丁点名称（用于日志说明）
        public long FileOffset;     // 在文件中的绝对偏移
        public byte[] Expected;     // 期望读到的原始字节（全部匹配才动手）
        public byte[] Patch;        // 实际写入的补丁字节

        public PatchPoint(string name, long offset, string expectedHex, string patchHex)
        {
            Name = name;
            FileOffset = offset;
            Expected = HexToBytes(expectedHex);
            Patch = HexToBytes(patchHex);
        }

        // 十六进制字符串 -> 字节数组
        private static byte[] HexToBytes(string hex)
        {
            byte[] bytes = new byte[hex.Length / 2];
            for (int i = 0; i < bytes.Length; i++)
                bytes[i] = Convert.ToByte(hex.Substring(i * 2, 2), 16);
            return bytes;
        }
    }

    // ========================================================================
    //  二、二进制指令修补引擎
    // ========================================================================
    internal static class NativeBinaryPatcher
    {
        // 修补后的标准文件大小：原版 6,199,664 字节去掉尾部 10,608 字节的签名数据
        public const int TARGET_FILE_SIZE = 6189056;

        // 修补后的标准指纹，用于验证是否与参考结果逐字节一致
        public const string TARGET_SHA256 =
            "E0C308B1150E748C26D1F7105F5F6C287C1881288B46AEEAC68383D166A72183";

        // --------------------------------------------------------------------
        //  18 个补丁点，按作用分为四组
        // --------------------------------------------------------------------
        public static readonly PatchPoint[] POINTS = new PatchPoint[]
        {
            // === 第 1 组：PE 头部修正（3 处）==================================
            // 项目D 启动时会自检 PE 结构与数字签名，若不修正会自校验失败。
            //
            // 0x150 处是 PE 可选头中的 CheckSum 字段。
            // 改动正文后必须同步改写校验和，否则加载器/自检会认为文件被篡改。
            new PatchPoint("PE 校验和校正", 0x150L, "00CD5E", "EA0B5F"),

            // 0x191 / 0x194 是数据目录表里 Security（数字签名）目录的 RVA 与大小。
            // 全部置 0 等价于「本文件没有数字签名」，让签名校验直接跳过。
            new PatchPoint("证书目录 RVA 清零", 0x191L, "705E", "0000"),
            new PatchPoint("证书目录 Size 清零", 0x194L, "7029", "0000"),

            // === 第 2 组：授权判定与试用期（3 处）==============================
            // 0x2D7BD 原本是 test eax,eax（85 C0），比较授权校验函数返回值。
            // 改成 xor eax,eax（33 C0）后 eax 恒为 0，授权分支被强制走「通过」。
            new PatchPoint("授权分支强制通过", 0x2D7BDL, "85", "33"),

            // 0x4C100 原本是 83 E0 0F 83 C0 0F：
            //   and eax,0F  ; 取低 4 位
            //   add eax,0F  ; 再加 15，结果最多 30（即试用 30 天）
            // 改为 B8 FF FF FF 7F 90：
            //   mov eax,0x7FFFFFFF ; 剩余天数直接变成天文数字，等价「永久」
            //   nop                ; 占位，保持指令长度一致
            new PatchPoint("试用期常量最大化", 0x4C100L, "83E00F83C00F", "B8FFFFFF7F90"),

            // 0x378CDC / 0x378CE0 是试用状态的标志位与天数常量。
            // 标志位 01 -> 00 表示「非试用」；天数常量 0x1E(30) -> 0x7FFFFFFF 表示永久。
            new PatchPoint("试用状态标志置零", 0x378CDCL, "01", "00"),
            new PatchPoint("试用天数常量最大化", 0x378CE0L, "1E000000", "FFFFFF7F"),

            // === 第 3 组：守护线程 / 看门狗（7 处）============================
            // 项目D 内部会启动多个后台线程周期性复检授权状态，一旦发现异常就
            // 弹窗或强制退出。这些函数入口的第一条指令都是 push（6A）或
            // push ebp（55），把首字节改成 C3（ret）后函数立刻返回，
            // 线程等于「启动即结束」，复检逻辑永远不会执行。
            new PatchPoint("阻断守护线程 A", 0x74920L, "6A", "C3"),
            new PatchPoint("阻断守护线程 B", 0x753C0L, "6A", "C3"),
            new PatchPoint("阻断守护线程 C", 0x7BC00L, "6A", "C3"),
            new PatchPoint("阻断守护线程 D", 0x7CA50L, "6A", "C3"),
            new PatchPoint("阻断看门狗钩子", 0x834E0L, "6A", "C3"),
            new PatchPoint("阻断额外校验函数", 0x842E0L, "55", "C3"),
            new PatchPoint("阻断守护线程 F", 0x131C60L, "6A", "C3"),

            // === 第 4 组：弹窗与联网校验（3 处）==============================
            // 0x53F78 / 0xF710E 处是「假冒序列号」提示框前的条件跳转。
            // 74（jz，条件成立才跳）改成 EB（jmp，无条件跳），
            // 相当于永远跳过弹窗，直接继续执行。
            new PatchPoint("绕过假序列号弹窗 A", 0x53F78L, "74", "EB"),
            new PatchPoint("绕过假序列号弹窗 B", 0xF710EL, "74", "EB"),

            // 0x91ABC 处是「试用过期 -> 强制退出」的条件跳转。
            // 0F 85（jne 近跳）改为 90 E9（nop + jmp 近跳），长度不变但永不强退。
            new PatchPoint("绕过过期强退", 0x91ABCL, "0F85", "90E9"),

            // 0x99A6D 是联网校验结果标志位，01（需要校验）改成 00（跳过）。
            new PatchPoint("联网验证标志置零", 0x99A6DL, "01", "00"),
        };

        // --------------------------------------------------------------------
        //  打补丁主流程
        // --------------------------------------------------------------------
        public static bool ApplyPatch(string targetExe, out int appliedCount)
        {
            appliedCount = 0;

            if (!File.Exists(targetExe))
            {
                Console.WriteLine("错误：未找到目标文件 " + targetExe);
                return false;
            }

            // 步骤 1：备份原版。只在 BAK 不存在时备份，防止把已打补丁的
            //         文件覆盖掉真正的原始备份。
            string bakPath = targetExe + ".BAK";
            if (!File.Exists(bakPath))
            {
                try
                {
                    File.Copy(targetExe, bakPath);
                    Console.WriteLine("已备份官方原版至: " + bakPath);
                }
                catch (Exception ex)
                {
                    Console.WriteLine("备份提示: " + ex.Message);
                }
            }

            // 步骤 2：整文件读入内存，所有修改都在内存里完成，最后一次性落盘。
            byte[] data = File.ReadAllBytes(targetExe);
            int skipped = 0;

            // 步骤 3：逐个补丁点处理
            foreach (PatchPoint pt in POINTS)
            {
                long off = pt.FileOffset;

                // 越界保护
                if (off < 0 || off + pt.Patch.Length > data.Length)
                {
                    skipped++;
                    continue;
                }

                // 3.1 幂等检查：如果该处已经是补丁字节，说明之前打过，直接算作已生效。
                bool alreadyPatched = true;
                for (int i = 0; i < pt.Patch.Length; i++)
                {
                    if (data[off + i] != pt.Patch[i]) { alreadyPatched = false; break; }
                }
                if (alreadyPatched)
                {
                    appliedCount++;
                    continue;
                }

                // 3.2 原始字节校验：不匹配说明不是目标版本，宁可跳过也不乱改。
                bool match = true;
                for (int i = 0; i < pt.Expected.Length; i++)
                {
                    if (data[off + i] != pt.Expected[i]) { match = false; break; }
                }
                if (!match)
                {
                    skipped++;
                    continue;
                }

                // 3.3 写入补丁字节
                for (int i = 0; i < pt.Patch.Length; i++)
                    data[off + i] = pt.Patch[i];

                appliedCount++;
            }

            // 全部不匹配 => 不是受支持的版本，直接失败退出
            if (skipped == POINTS.Length)
            {
                Console.WriteLine("全部补丁点均不匹配，当前 项目D.exe 不是受支持的版本。");
                return false;
            }

            // 步骤 4：签名剥离与截断。
            //   PE 文件末尾的数字签名（Authenticode）以 8 字节对齐存放在
            //   Security Directory 指向的区域，原版这部分共 10,608 字节。
            //   由于前面已把证书目录 RVA/Size 清零，这里直接把尾部数据截掉，
            //   文件大小变为 6,189,056 字节，与参考结果完全一致。
            if (data.Length > TARGET_FILE_SIZE)
            {
                Array.Resize(ref data, TARGET_FILE_SIZE);
                Console.WriteLine("已剥离数字签名并截断至 " + TARGET_FILE_SIZE + " 字节");
            }

            // 步骤 5：落盘
            File.WriteAllBytes(targetExe, data);

            // 步骤 6：指纹自检，确认结果与参考实现逐字节一致
            using (SHA256 sha = SHA256.Create())
            {
                byte[] hash = sha.ComputeHash(data);
                StringBuilder sb = new StringBuilder();
                foreach (byte b in hash) sb.Append(b.ToString("X2"));

                if (sb.ToString().Equals(TARGET_SHA256, StringComparison.OrdinalIgnoreCase))
                    Console.WriteLine("完整性校验通过：SHA256 与参考结果逐字节对齐");
                else
                    Console.WriteLine("提示：SHA256 与参考值不同，请核对 项目D 版本");
            }

            return true;
        }
    }

    // ========================================================================
    //  三、注册表授权身份登记
    // ------------------------------------------------------------------------
    //  项目D 判断「是否已授权」的路径在 HKCU\Software\DownloadManager：
    //
    //    FName  —— 授权人姓名。只要该值存在且非空，项目D 的「关于」窗口就会
    //              显示「此产品授权给：<姓名>」，并按已注册状态运行。
    //    Email  —— 绑定邮箱，仅用于界面展示。
    //    Serial —— 序列号，整个方案里最容易踩坑的地方：
    //              项目D 会用内置的非对称公钥算法对 Serial 做真实校验，
    //              任何伪造 / 明文序列号都会被判定为「假冒序列号」，
    //              随即弹出「注册 项目D」对话框。
    //              ★ 正确做法是「删除」Serial 键，而不是写入一个假序列号。
    //
    //    其余字段（scansk / tvfrdt / radxcnt / ptrk_scdt / LastCheckQU /
    //    scTime / NextCheck / BList / md5pks / itb_r / ncl_r）分别对应
    //    试用计数、黑名单回传标记、更新时间戳等，一并清除可避免
    //    过期提示与联网校验弹窗。
    //
    //    CheckUpdtVM = 0 用于关闭启动时的自动更新检查。
    // ========================================================================
    internal static class LicenseRegistry
    {
        private const string KEY_PATH = @"Software\DownloadManager";

        public static void Write(string customName, string customEmail)
        {
            // 默认使用当前 Windows 登录用户名作为授权人
            string name = customName;
            if (string.IsNullOrEmpty(name))
            {
                name = Environment.UserName;
                if (string.IsNullOrEmpty(name)) name = "User";
            }

            // 默认生成 <用户名>@vipuser.com 形式的邮箱
            string email = customEmail;
            if (string.IsNullOrEmpty(email))
            {
                string sanitize = Regex.Replace(name, @"[^\w\.\-]", "").ToLowerInvariant();
                if (string.IsNullOrEmpty(sanitize)) sanitize = "user";
                email = sanitize + "@vipuser.com";
            }

            using (RegistryKey k = Registry.CurrentUser.CreateSubKey(KEY_PATH))
            {
                if (k == null) return;

                // 写入授权人身份
                k.SetValue("FName", name, RegistryValueKind.String);
                k.SetValue("LName", " ", RegistryValueKind.String);
                k.SetValue("Email", email, RegistryValueKind.String);

                // ★ 关键：删除而非写入 Serial
                try { k.DeleteValue("Serial", false); } catch { }

                // 关闭启动自动更新检查
                k.SetValue("CheckUpdtVM", 0, RegistryValueKind.DWord);
                k.SetValue("LstCheck", "0", RegistryValueKind.String);

                // 清除试用计数 / 黑名单 / 校验时间戳等干扰字段
                string[] cleanList = new string[]
                {
                    "scansk", "tvfrdt", "radxcnt", "ptrk_scdt", "LastCheckQU",
                    "scTime", "NextCheck", "BList", "md5pks", "itb_r", "ncl_r"
                };
                foreach (string field in cleanList)
                {
                    try { k.DeleteValue(field, false); } catch { }
                }
            }

            Console.WriteLine("已登记授权身份：姓名 [" + name + "]，邮箱 [" + email + "]");
        }

        // --------------------------------------------------------------------
        //  还原：删除全部授权登记与策略字段，回到「官方未注册原版」状态
        // --------------------------------------------------------------------
        public static void Restore()
        {
            using (RegistryKey k = Registry.CurrentUser.OpenSubKey(KEY_PATH, true))
            {
                if (k == null) return;

                string[] wipeList = new string[]
                {
                    "FName", "LName", "Email", "Serial",
                    "scansk", "tvfrdt", "radxcnt", "ptrk_scdt", "LastCheckQU",
                    "scTime", "NextCheck", "BList", "md5pks", "itb_r", "ncl_r",
                    "LstCheck", "CheckUpdtVM"
                };
                foreach (string prop in wipeList)
                {
                    try { k.DeleteValue(prop, false); } catch { }
                }
            }
            Console.WriteLine("已抹除注册表授权登记与策略配置");
        }
    }

    // ========================================================================
    //  四、还原与清理
    // ========================================================================
    internal static class RestoreHelper
    {
        // 从 .BAK 无损还原官方原版主程序
        public static void RestoreOriginalBinary(string idmDir)
        {
            string target = Path.Combine(idmDir, "项目D.exe");
            string bak = target + ".BAK";

            if (!File.Exists(bak))
            {
                Console.WriteLine("未检测到原版备份 (项目D.exe.BAK)，跳过文件还原");
                return;
            }

            try
            {
                File.Copy(bak, target, true);
                Console.WriteLine("官方原版主程序已无损还原 (项目D.exe.BAK -> 项目D.exe)");
            }
            catch (Exception ex)
            {
                Console.WriteLine("还原文件失败: " + ex.Message);
            }
        }

        // 清理 CLSID 下带试用时间戳特征的隐藏项（出厂重置）
        public static int CleanClsidTrialKeys()
        {
            int deleted = 0;
            string[] roots = new string[]
            {
                @"Software\Classes\CLSID",
                @"Software\Classes\WOW6432Node\CLSID"
            };
            Regex guidRegex = new Regex(
                @"^\{[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}\}$",
                RegexOptions.IgnoreCase);

            foreach (string root in roots)
            {
                try
                {
                    using (RegistryKey clsidKey = Registry.CurrentUser.OpenSubKey(root, true))
                    {
                        if (clsidKey == null) continue;

                        foreach (string subName in clsidKey.GetSubKeyNames())
                        {
                            if (!guidRegex.IsMatch(subName)) continue;

                            try
                            {
                                using (RegistryKey testKey = clsidKey.OpenSubKey(subName))
                                {
                                    if (testKey == null) continue;

                                    object defVal = testKey.GetValue("");
                                    if (defVal == null) continue;

                                    // 默认值为纯数字、或含 + / = 的，视为试用时间戳特征
                                    string s = defVal.ToString();
                                    if (Regex.IsMatch(s, @"^\d+$") || s.Contains("+") || s.Contains("="))
                                    {
                                        clsidKey.DeleteSubKeyTree(subName, false);
                                        deleted++;
                                    }
                                }
                            }
                            catch { }
                        }
                    }
                }
                catch { }
            }
            return deleted;
        }
    }

    // ========================================================================
    //  五、主程序：串起三条主线
    // ========================================================================
    internal class Program
    {
        private static void Main(string[] args)
        {
            Console.OutputEncoding = Encoding.UTF8;

            string idmDir = FindIdmDir();
            string idmExe = Path.Combine(idmDir, "项目D.exe");

            if (args.Length > 0)
            {
                string cmd = args[0].ToLowerInvariant();
                if (cmd == "--patch") { Patch(idmExe); return; }
                if (cmd == "--restore") { Restore(idmDir, idmExe); return; }
                if (cmd == "--reset") { Reset(idmDir, idmExe); return; }
            }

            Console.WriteLine("项目D 激活与注册原理参考（仅用于学习研究）");
            Console.WriteLine("项目D 目录: " + idmDir);
            Console.WriteLine();
            Console.WriteLine("  1) 执行激活（二进制修补 + 注册表登记）");
            Console.WriteLine("  2) 还原官方原版（BAK 恢复 + 清理注册表）");
            Console.WriteLine("  3) 出厂重置（还原 + 清理 CLSID 试用特征）");
            Console.WriteLine("  0) 退出");
            Console.WriteLine();
            Console.Write("请选择: ");

            string choice = Console.ReadLine();
            if (choice == "1") Patch(idmExe);
            else if (choice == "2") Restore(idmDir, idmExe);
            else if (choice == "3") Reset(idmDir, idmExe);
        }

        // 定位 项目D 安装目录：优先注册表，其次默认路径
        private static string FindIdmDir()
        {
            string dir = null;

            try
            {
                using (RegistryKey k = Registry.CurrentUser.OpenSubKey(@"Software\DownloadManager"))
                    if (k != null) dir = k.GetValue("ExePath") as string;
            }
            catch { }

            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir))
            {
                try
                {
                    using (RegistryKey k = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\项目D"))
                        if (k != null) dir = k.GetValue("Path") as string;
                }
                catch { }
            }

            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir))
            {
                string def = @"C:\Program Files (x86)\项目D";
                if (Directory.Exists(def)) dir = def;
            }

            return dir ?? @"C:\Program Files (x86)\项目D";
        }

        // 结束 项目D 进程，避免文件被占用
        private static void KillIdm()
        {
            foreach (Process p in Process.GetProcessesByName("项目D"))
            {
                try { p.Kill(); p.WaitForExit(1000); } catch { }
            }
        }

        // 激活：修补二进制 + 登记授权身份
        private static void Patch(string idmExe)
        {
            KillIdm();
            Thread.Sleep(300);

            int count;
            if (NativeBinaryPatcher.ApplyPatch(idmExe, out count))
            {
                LicenseRegistry.Write(null, null);
                Console.WriteLine("激活完成：共 " + count + "/" + NativeBinaryPatcher.POINTS.Length + " 个补丁位点生效");
            }
            else
            {
                Console.WriteLine("激活失败，请检查权限与文件状态");
            }
        }

        // 还原官方原版
        private static void Restore(string idmDir, string idmExe)
        {
            KillIdm();
            Thread.Sleep(300);
            RestoreHelper.RestoreOriginalBinary(idmDir);
            LicenseRegistry.Restore();
            Console.WriteLine("已还原为官方未注册原版状态");
        }

        // 出厂重置：还原 + 清理 CLSID 试用特征
        private static void Reset(string idmDir, string idmExe)
        {
            Restore(idmDir, idmExe);
            int n = RestoreHelper.CleanClsidTrialKeys();
            Console.WriteLine("已清理 CLSID 试用特征键 " + n + " 处");
            Console.WriteLine("出厂重置完成");
        }
    }
}
