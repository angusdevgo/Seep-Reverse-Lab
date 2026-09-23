// Patcher - 对 项目E.exe 副本应用「IsRegistered 恒 3」补丁
// C# 5 / .NET Framework 4.x compatible. 纯字节数组操作，可单测。
//
// Patch 说明（逆向结论，地址均为 VA / 文件偏移）：
//   FUN_140009db0 = IsRegistered 查询封装，函数尾 `mov eax, edi` 返回
//   json["result"]（3=已注册）。把 `0x140009e0f call 0x1402de8c8`
//   （atoi(json["result"])）重定向到 .text 空隙 stub：
//     VA 0x140001622 : B8 03 00 00 00 C3   (mov eax,3 ; ret)
//   效果：主程序侧所有 result 判定（CheckRegistration / Activate）恒为 3。
//   项目EHelper.exe 与原始安装目录二进制均不被修改。
using System;
using System.Collections.Generic;

namespace UtLicense
{
    public static class Patcher
    {
        // 已知目标样本 SHA256（2026-08 版 项目E.exe / <目标版本>）
        public const string EXPECT_SHA256 = "<实测哈希>";
        // 已 patch 输出的典型 SHA256（仅提示用）
        public const string PATCHED_SHA256 = "<实测哈希>";

        public const string STUB_VA_TEXT = "0x140001622";
        public static readonly byte[] STUB_BYTES = new byte[] { 0xB8, 0x03, 0x00, 0x00, 0x00, 0xC3 }; // mov eax,3; ret

        // call 指令位置与原始目标（VA）
        public const long CALL_VA = 0x140009E0FL;
        public const long ORIG_TARGET_VA = 0x1402DE8C8L;

        // 供 UI 展示的字节变化记录
        public struct Change
        {
            public long Va;
            public long FileOffset;
            public byte[] OldBytes;
            public byte[] NewBytes;
            public string Note;
        }

        // 把 VA 映射为文件偏移。返回 false 表示不在任何节内。
        static bool VaToOffset(byte[] pe, long va, out long offset)
        {
            offset = 0;
            int peOff = BitConverter.ToInt32(pe, 0x3C);
            int nsec = BitConverter.ToUInt16(pe, peOff + 6);
            int opt = peOff + 24;
            long imgBase = BitConverter.ToInt64(pe, opt + 24);
            int secOff = opt + BitConverter.ToUInt16(pe, peOff + 20);
            for (int i = 0; i < nsec; i++)
            {
                int so = secOff + i * 40;
                int vsize = BitConverter.ToInt32(pe, so + 8);
                long vaddr = BitConverter.ToUInt32(pe, so + 12);
                int rsize = BitConverter.ToInt32(pe, so + 16);
                long raddr = BitConverter.ToUInt32(pe, so + 20);
                long sva = imgBase + vaddr;
                if (va >= sva && va < sva + Math.Max(vsize, rsize))
                {
                    offset = raddr + (va - sva);
                    return true;
                }
            }
            return false;
        }

        static string Sha256Hex(byte[] data)
        {
            var sha = System.Security.Cryptography.SHA256.Create();
            byte[] h = sha.ComputeHash(data);
            var sb = new System.Text.StringBuilder(h.Length * 2);
            for (int i = 0; i < h.Length; i++) sb.Append(h[i].ToString("x2"));
            return sb.ToString();
        }

        // 检查是否已打过补丁（call 已指向 stub 或 stub 已写入）
        public static bool IsPatched(byte[] pe)
        {
            try
            {
                long off;
                if (!VaToOffset(pe, CALL_VA, out off)) return false;
                if (off + 5 > pe.Length) return false;
                if (pe[off] != 0xE8) return false;
                int rel = BitConverter.ToInt32(pe, (int)off + 1);
                long target = (CALL_VA + 5 + rel) & 0xFFFFFFFFFFFF;
                return target == 0x140001622L;
            }
            catch { return false; }
        }

        // 核心：把补丁应用到 PE 字节数组（不落盘），返回修改记录。
        // 输入可已被 patch（幂等：重复应用返回空变更）。
        public static Change[] Apply(byte[] pe)
        {
            List<Change> changes = new List<Change>();
            if (IsPatched(pe)) return changes.ToArray();

            long stubOff;
            if (!VaToOffset(pe, 0x140001622L, out stubOff))
                throw new InvalidOperationException("stub VA 不在节内");
            if (stubOff + STUB_BYTES.Length > pe.Length)
                throw new InvalidOperationException("stub 区域越界");

            // 1) 写入 stub
            byte[] oldStub = new byte[STUB_BYTES.Length];
            Array.Copy(pe, stubOff, oldStub, 0, STUB_BYTES.Length);
            Array.Copy(STUB_BYTES, 0, pe, stubOff, STUB_BYTES.Length);
            changes.Add(new Change { Va = 0x140001622L, FileOffset = stubOff, OldBytes = oldStub, NewBytes = STUB_BYTES, Note = "stub: mov eax,3 / ret" });

            // 2) 重定向 call
            long callOff;
            if (!VaToOffset(pe, CALL_VA, out callOff))
                throw new InvalidOperationException("call VA 不在节内");
            byte[] oldCall = new byte[5];
            Array.Copy(pe, callOff, oldCall, 0, 5);
            if (oldCall[0] != 0xE8)
                throw new InvalidOperationException("call 指令校验失败（非 E8）: " + BitConverter.ToString(oldCall));
            long oldTarget = (CALL_VA + 5 + BitConverter.ToInt32(oldCall, 1)) & 0xFFFFFFFFFFFF;
            if (oldTarget != ORIG_TARGET_VA)
                throw new InvalidOperationException("call 原始目标不符: " + oldTarget.ToString("x"));
            int rel = unchecked((int)((0x140001622L - (CALL_VA + 5)) & 0xFFFFFFFFL));
            byte[] newCall = new byte[5];
            newCall[0] = 0xE8;
            BitConverter.GetBytes(rel).CopyTo(newCall, 1);
            Array.Copy(newCall, 0, pe, callOff, 5);
            changes.Add(new Change { Va = CALL_VA, FileOffset = callOff, OldBytes = oldCall, NewBytes = newCall, Note = "call -> IsRegisteredStub" });
            return changes.ToArray();
        }

        // 便捷：读文件 -> 校验指纹 -> patch -> 备份 -> 落盘。
        // returns (newSha256, changes)
        public static string PatchFile(string inPath, string outPath, string backupPath, IList<string> log)
        {
            byte[] pe = System.IO.File.ReadAllBytes(inPath);
            log.Add("输入: " + inPath + " (" + pe.Length + " 字节)");
            string sha = Sha256Hex(pe);
            if (!sha.Equals(EXPECT_SHA256, StringComparison.OrdinalIgnoreCase))
                log.Add("注意: 输入 SHA256 与已知样本不同 (" + sha + ")，按结构应用补丁");

            Change[] changes = Apply(pe);
            if (changes.Length == 0)
            {
                log.Add("已是补丁版本，跳过写入（直接复制）");
            }
            else
            {
                log.Add("应用 " + changes.Length + " 处修改：");
                foreach (Change c in changes)
                    log.Add("  VA " + c.Va.ToString("x") + " (file " + c.FileOffset.ToString("x") + "): "
                        + BitConverter.ToString(c.OldBytes) + " -> " + BitConverter.ToString(c.NewBytes) + "  " + c.Note);
                if (!string.IsNullOrEmpty(backupPath))
                {
                    System.IO.File.Copy(inPath, backupPath, true);
                    log.Add("原文件已备份: " + backupPath);
                }
            }
            System.IO.File.WriteAllBytes(outPath, pe);
            string newSha = Sha256Hex(pe);
            log.Add("输出: " + outPath + "  SHA256: " + newSha);
            log.Add(IsPatched(pe) ? "校验：补丁已生效（IsRegistered 判定恒 3）" : "校验失败：补丁未生效！");
            return newSha;
        }

        // 自动替换：备份原位 -> 原位写补丁版。适用于安装目录/快捷方式指向的 exe。
        // 文件被占用（程序运行中）抛出 IOException；目录不可写抛出 UnauthorizedAccessException。
        public static string AutoPatchAndReplace(string exePath, IList<string> log)
        {
            byte[] pe = System.IO.File.ReadAllBytes(exePath);
            log.Add("目标: " + exePath + " (" + pe.Length + " 字节)");
            string sha = Sha256Hex(pe);
            log.Add("SHA256: " + sha);
            log.Add(sha.Equals(EXPECT_SHA256, StringComparison.OrdinalIgnoreCase)
                ? "指纹匹配已知样本，继续" : "注意: 指纹与已知样本不同，按结构应用补丁");

            Change[] changes = Apply(pe);
            if (changes.Length == 0)
            {
                log.Add("目标已带补丁，无需修改（保持原位）");
                return "already-patched";
            }

            string backupPath = System.IO.Path.ChangeExtension(exePath, ".orig.exe");
            if (System.IO.File.Exists(backupPath))
            {
                // 已有备份则仅记录，不覆盖（保留最初原件）
                log.Add("备份已存在: " + backupPath + "（保留，不覆盖）");
            }
            else
            {
                System.IO.File.Copy(exePath, backupPath, false);
                log.Add("已备份原件 -> " + backupPath);
            }

            // 原位写回（程序运行中会抛 IOException: 文件被占用）
            System.IO.File.WriteAllBytes(exePath, pe);
            log.Add("已写回补丁版 -> " + exePath);

            // 复读校验
            byte[] verify = System.IO.File.ReadAllBytes(exePath);
            if (!IsPatched(verify))
                throw new InvalidOperationException("写回后校验失败：补丁未生效");
            log.Add("复读校验通过：IsRegistered 判定恒 3（result==3）");
            log.Add("新 SHA256: " + Sha256Hex(verify));
            return "patched-in-place";
        }
    }
}