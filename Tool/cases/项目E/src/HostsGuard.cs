// HostsGuard - 屏蔽 项目E 在线核验/更新服务器（可选加固）
// C# 5 / .NET Framework 4.x compatible.
//
// 逆向确认：激活时主程序经 项目EHelper.exe 向
// 项目E.license-manage.com/verify.php 做在线核验；版本更新走 项目E.com。
// patch 使主程序本地判定恒 3 后，在线核验不再影响注册状态；屏蔽域名可进一步
// 减少 Helper 的联网行为（网络异常时核验失败也不影响已注册状态）。
using System;
using System.Diagnostics;
using System.IO;

namespace UtLicense
{
    public static class HostsGuard
    {
        public const string Host = "项目E.license-manage.com";
        public const string BlockEntry = "0.0.0.0 " + Host;

        public static string HostsPath()
        {
            return Path.Combine(Environment.SystemDirectory, "drivers", "etc", "hosts");
        }

        // true 表示 hosts 已有非注释行的屏蔽记录
        public static bool IsBlocked()
        {
            try
            {
                string path = HostsPath();
                if (!File.Exists(path)) return false;
                foreach (string raw in File.ReadAllLines(path))
                {
                    string line = raw.Trim();
                    if (line.Length == 0 || line.StartsWith("#")) continue;
                    int hash = line.IndexOf('#');
                    if (hash >= 0) line = line.Substring(0, hash).Trim();
                    if (line.IndexOf(Host, StringComparison.OrdinalIgnoreCase) >= 0)
                        return true;
                }
                return false;
            }
            catch { return false; }
        }

        // 提权追加 hosts 记录（UAC）；返回是否成功发起
        public static bool BlockViaUac()
        {
            string args = "-NoProfile -WindowStyle Hidden -Command \"" +
                          "Add-Content -Path $env:SystemRoot\\System32\\drivers\\etc\\hosts " +
                          "-Value '\\r\\n# block uninstall-tool license verification\\r\\n" +
                          BlockEntry + "' -Encoding ASCII\"";
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = "powershell.exe";
                psi.Arguments = args;
                psi.Verb = "runas";
                psi.UseShellExecute = true;
                psi.WindowStyle = ProcessWindowStyle.Hidden;
                Process.Start(psi);
                return true;
            }
            catch { return false; }
        }
    }
}