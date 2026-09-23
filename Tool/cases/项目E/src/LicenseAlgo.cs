// LicenseAlgo - 项目E 激活信息生成（patch 版工具）
// C# 5 / .NET Framework 4.x compatible.
//
// 背景：项目E 的注册校验是 EXECryptor 授权运行时（项目EHelper.exe，
// 共享内存 XML-RPC）+ 激活时在线核验 项目E.license-manage.com/verify.php。
// 序列号绑定机器码且私钥不可得，不存在纯算号器路径（见 docs/algorithm.md）。
// 因此本工具交付「patch + 写入激活」方案：patch 主程序 IsRegistered 判定后，
// 任意注册名/注册码组合都会被识别为已注册（result==3）。
// LicenseAlgo 只负责生成展示用注册名/注册码与格式校验，不再有密码学义务。
using System;
using System.Text;

namespace UtLicense
{
    public static class LicenseAlgo
    {
        public const int KEY_LEN = 29;          // 展示用注册码长度（不参与校验）
        public const string KEY_CHARSET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"; // 32 chars, no 0/1/I/O

        private static readonly Random _rnd = new Random();

        // 随机注册名：Pro User 风格，中文环境友好
        public static string RandomName()
        {
            string[] bases = new string[] { "Pro User", "Registered User", "Power User", "UT Pro User" };
            string b = bases[_rnd.Next(bases.Length)];
            if (_rnd.Next(3) == 0) b += " " + _rnd.Next(100, 9999).ToString();
            return b;
        }

        // 随机注册码：4 组 × 7 字符，'-' 分隔（纯展示，patch 后任意值均有效）
        public static string RandomKey()
        {
            StringBuilder sb = new StringBuilder();
            lock (_rnd)
            {
                for (int i = 0; i < KEY_LEN; i++)
                {
                    if (i > 0 && (i % 7) == 0) sb.Append('-');
                    sb.Append(KEY_CHARSET[_rnd.Next(KEY_CHARSET.Length)]);
                }
            }
            return sb.ToString();
        }

        // patch 版下任何非空注册码均被主程序接受（IsRegistered 判定恒 3）。
        public static bool Verify(string name, string key)
        {
            return !string.IsNullOrWhiteSpace(name)
                && !string.IsNullOrWhiteSpace(key)
                && key.Length >= 8;
        }
    }
}