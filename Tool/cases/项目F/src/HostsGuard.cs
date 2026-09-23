// HostsGuard - block 项目F activation server via hosts file (prevents online
// license check from clearing locally-activated license keys).
//
// Background (from ProService.ScheduleAutoCheck decompilation):
//   - 15 min after startup 项目F POSTs email+key to account.项目F.com/api/v1/activate
//   - InvalidLicense/NoActivationsLeft -> after 7 days it CLEARS 项目F5.ProLicense.*
//   - Network failure -> ActivationResult.UnknownError -> switch has no branch -> no-op
// Therefore blocking DNS for account.项目F.com makes the auto-check permanently inert,
// while local activation (offline CheckLicense) keeps working.
using System;
using System.Diagnostics;
using System.IO;

namespace 项目FLicense
{
    public static class HostsGuard
    {
        public const string Host = "account.项目F.com";
        public const string BlockEntry = "0.0.0.0 " + Host;

        public static string HostsPath()
        {
            return Path.Combine(Environment.SystemDirectory, "drivers", "etc", "hosts");
        }

        // true if a non-comment hosts line already blocks the host
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
                    // strip trailing comment
                    int hash = line.IndexOf('#');
                    if (hash >= 0) line = line.Substring(0, hash).Trim();
                    if (line.IndexOf(Host, StringComparison.OrdinalIgnoreCase) >= 0)
                        return true;
                }
                return false;
            }
            catch { return false; }
        }

        // elevated one-shot: append block entry via runas PowerShell (UAC prompt)
        // returns true if the elevated process was launched (user accepted UAC)
        public static bool BlockViaUac()
        {
            string args = "-NoProfile -WindowStyle Hidden -Command \"" +
                          "Add-Content -Path $env:SystemRoot\\System32\\drivers\\etc\\hosts " +
                          "-Value '\\r\\n# block 项目F activation server (license auto-check)\\r\\n" +
                          BlockEntry + "' -Encoding ASCII\"";
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = "powershell.exe";
                psi.Arguments = args;
                psi.Verb = "runas";          // triggers UAC
                psi.UseShellExecute = true;
                psi.WindowStyle = ProcessWindowStyle.Hidden;
                Process.Start(psi);
                return true;
            }
            catch { return false; }          // user declined UAC or other failure
        }
    }
}