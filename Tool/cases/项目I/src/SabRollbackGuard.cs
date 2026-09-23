// Anti-rollback guard (HostsGuard equivalent for 项目I).
// Rollback vectors (evidence: cases/20260901-项目I-keygen/exports):
//   1. Scheduled task "\项目I Update" -> UpdateCheck.exe elevated
//      (newversion_all.php, auto-download 项目I_update.exe)
//   2. sib-reactivate: / sib-update: protocol handlers
//   3. Uninstall option "Delete settings and license data"
//   4. Trial timer key HKCU\...\Explorer\CLSID\{md5(项目I+PINGROUP)-1-31-9}
// Mitigations (all reversible):
//   A. hosts block 项目I.com / www.项目I.com / www.项目I.com
//   B. write HKCU\Software\项目I\StopAutoDownload (official switch read by
//      UpdateCheck.exe, evidence: UpdateCheck strings)
//   C. schtasks /Change /TN "\项目I Update" /DISABLE (reversible enable)
using System;
using System.Diagnostics;
using System.IO;
using System.Security.AccessControl;
using Microsoft.Win32;

namespace SabLicense
{
    public static class RollbackGuard
    {
        public static readonly string[] HostsEntries =
        {
            "0.0.0.0 项目I.com",
            "0.0.0.0 www.项目I.com",
            "0.0.0.0 www.项目I.com",
        };

        public const string HOSTS = @"C:\Windows\System32\drivers\etc\hosts";
        public const string MARK_BEGIN = "# >>> 项目I-keygen guard >>>";
        public const string MARK_END = "# <<< 项目I-keygen guard <<<";
        public const string TASK_NAME = @"\项目I Update";

        public static string ApplyAll(bool hosts, bool stopAutoDownload, bool disableTask)
        {
            string log = "";
            if (hosts) log += ApplyHosts();
            if (stopAutoDownload) log += ApplyStopAutoDownload();
            if (disableTask) log += ApplyTaskDisable();
            return log;
        }

        public static string ApplyHosts()
        {
            try
            {
                string content = File.ReadAllText(HOSTS);
                if (content.Contains(MARK_BEGIN)) return "hosts: guard already present" + Environment.NewLine;
                var sb = new System.Text.StringBuilder();
                sb.AppendLine();
                sb.AppendLine(MARK_BEGIN);
                foreach (string e in HostsEntries) sb.AppendLine(e);
                sb.AppendLine(MARK_END);
                File.AppendAllText(HOSTS, sb.ToString());
                return "hosts: guard added" + Environment.NewLine;
            }
            catch (Exception ex)
            {
                return "hosts: FAILED (need admin) " + ex.Message + Environment.NewLine;
            }
        }

        public static string RemoveHosts()
        {
            try
            {
                string content = File.ReadAllText(HOSTS);
                int b = content.IndexOf(MARK_BEGIN, StringComparison.Ordinal);
                int e = content.IndexOf(MARK_END, StringComparison.Ordinal);
                if (b < 0 || e < 0) return "hosts: no guard present" + Environment.NewLine;
                string removed = content.Substring(b, e + MARK_END.Length - b);
                File.WriteAllText(HOSTS, content.Remove(b, e + MARK_END.Length - b));
                return "hosts: guard removed" + Environment.NewLine;
            }
            catch (Exception ex)
            {
                return "hosts: remove FAILED (need admin) " + ex.Message + Environment.NewLine;
            }
        }

        public static string ApplyStopAutoDownload()
        {
            try
            {
                Registry.SetValue(@"HKEY_CURRENT_USER\" + PrefsWriter.STOP_AUTO_DOWNLOAD, "", 1, RegistryValueKind.DWord);
                return "StopAutoDownload=1 (official switch)" + Environment.NewLine;
            }
            catch (Exception ex)
            {
                return "StopAutoDownload FAILED: " + ex.Message + Environment.NewLine;
            }
        }

        public static string UndoStopAutoDownload()
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(@"Software\项目I", true))
                {
                    if (k != null) k.DeleteSubKeyTree("StopAutoDownload", false);
                }
                return "StopAutoDownload removed" + Environment.NewLine;
            }
            catch (Exception ex)
            {
                return "StopAutoDownload undo FAILED: " + ex.Message + Environment.NewLine;
            }
        }

        public static string ApplyTaskDisable()
        {
            return RunSchtasks("/Change /TN \"" + TASK_NAME + "\" /DISABLE");
        }

        public static string ApplyTaskEnable()
        {
            return RunSchtasks("/Change /TN \"" + TASK_NAME + "\" /ENABLE");
        }

        private static string RunSchtasks(string args)
        {
            try
            {
                var psi = new ProcessStartInfo("schtasks.exe", args)
                {
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                };
                using (var p = Process.Start(psi))
                {
                    string o = p.StandardOutput.ReadToEnd() + p.StandardError.ReadToEnd();
                    p.WaitForExit();
                    return "schtasks " + args + " -> exit " + p.ExitCode + " " + o.Trim() + Environment.NewLine;
                }
            }
            catch (Exception ex)
            {
                return "schtasks FAILED: " + ex.Message + Environment.NewLine;
            }
        }

        public static string Status()
        {
            string log = "";
            try
            {
                string content = File.ReadAllText(HOSTS);
                log += "hosts guard: " + (content.Contains(MARK_BEGIN) ? "PRESENT" : "absent") + Environment.NewLine;
            }
            catch (Exception ex)
            {
                log += "hosts unreadable: " + ex.Message + Environment.NewLine;
            }
            var sad = Registry.GetValue(@"HKEY_CURRENT_USER\" + PrefsWriter.STOP_AUTO_DOWNLOAD, "", null);
            log += "StopAutoDownload: " + (sad != null ? Convert.ToString(sad) : "absent") + Environment.NewLine;
            log += RunSchtasks("/Query /TN \"" + TASK_NAME + "\"");
            return log;
        }
    }
}
