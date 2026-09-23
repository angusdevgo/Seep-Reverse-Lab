// LicenseWriter - 将激活配置写入 HKCU\Software\项目E Software\项目E
// C# 5 / .NET Framework 4.x compatible. 独立于 UI，可单测。
//
// 目标键（逆向确认）：
//   HKEY_CURRENT_USER\Software\项目E Software\项目E
//     RN  REG_SZ  注册名（Activate 写，CheckRegistration 读）
//     RC  REG_SZ  注册码（Activate 写，CheckRegistration 读）
//   VH/VL=版本戳、RF/RL=试用期时间戳（本工具不触碰）。
// 写入前自动备份原值到本地 .bak 文本；仅更新 RN/RC 两值。
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Microsoft.Win32;

namespace UtLicense
{
    public static class LicenseWriter
    {
        public const string ROOT_KEY = @"Software\项目E Software\项目E";
        public const string VALUE_NAME = "RN";
        public const string VALUE_CODE = "RC";
        public const string BACKUP_SUFFIX = ".bak";

        public static string RegistryPath()
        {
            return @"HKCU\" + ROOT_KEY;
        }

        // 备份文件路径：%TEMP%\uninstall-tool-keygen\registry-backup.txt
        public static string DefaultBackupPath()
        {
            string dir = Path.Combine(Path.GetTempPath(), "uninstall-tool-keygen");
            return Path.Combine(dir, "registry-backup.txt");
        }

        // 读取当前 RN/RC；未设置时为 null
        public static string[] Read()
        {
            string[] result = new string[2];
            try
            {
                using (RegistryKey k = Registry.CurrentUser.OpenSubKey(ROOT_KEY))
                {
                    if (k == null) return result;
                    result[0] = k.GetValue(VALUE_NAME) as string;
                    result[1] = k.GetValue(VALUE_CODE) as string;
                }
            }
            catch { /* ignore */ }
            return result;
        }

        // 写入 RN/RC；backupPath 为空则跳过备份。返回 true 表示写入并复读校验通过。
        public static bool Write(string name, string code, string backupPath, IList<string> log, out string error)
        {
            error = null;
            try
            {
                log.Add("[1/4] 目标键: " + RegistryPath());
                using (RegistryKey k = Registry.CurrentUser.CreateSubKey(ROOT_KEY))
                {
                    if (k == null) throw new InvalidOperationException("无法打开/创建注册表键");

                    if (!string.IsNullOrEmpty(backupPath))
                    {
                        string[] old = Read();
                        string dir = Path.GetDirectoryName(backupPath);
                        if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
                        StringBuilder sb = new StringBuilder();
                        sb.AppendLine("RN=" + old[0]);
                        sb.AppendLine("RC=" + old[1]);
                        File.WriteAllText(backupPath, sb.ToString(), Encoding.UTF8);
                        log.Add("[2/4] 原值已备份 -> " + backupPath);
                    }
                    else
                    {
                        log.Add("[2/4] 跳过备份（backupPath 为空）");
                    }

                    k.SetValue(VALUE_NAME, name, RegistryValueKind.String);
                    k.SetValue(VALUE_CODE, code, RegistryValueKind.String);
                    log.Add("[3/4] 已写入 RN='" + name + "' / RC='" + code + "'");

                    // 复读校验
                    string[] back = Read();
                    if (back[0] != name || back[1] != code)
                        throw new InvalidOperationException("复读校验不一致");
                    log.Add("[4/4] 复读校验通过：RN/RC 已就位");
                    return true;
                }
            }
            catch (Exception ex)
            {
                error = ex.Message;
                log.Add("[失败] " + ex.Message);
                return false;
            }
        }
    }
}