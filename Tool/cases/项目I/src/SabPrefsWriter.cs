// Registry writer for activation state with backup & restore.
// Targets (evidence: FUN_005d08a0 / FUN_180001d24 / Ordinal_103):
//   HKCU\Software\项目I\License  : default value (key text, optional)
//                                        LicenseHash (REG_SZ, md5hex(key))
//                                        ActivationData (REG_BINARY, 128 bytes)
//   HKLM\Software\项目I\License  : same (requires elevation, best effort)
//   HKCU\Software\项目I\AutoUpdatePending : deleted on successful activate
// Backup: full export of both License keys into case exports dir before write.
using System;
using System.IO;
using System.Text;
using Microsoft.Win32;

namespace SabLicense
{
    public static class PrefsWriter
    {
        public const string LICENSE_PATH = @"Software\项目I\License";
        public const string ROOT_KEY = @"Software\项目I";
        public const string STOP_AUTO_DOWNLOAD = @"Software\项目I\StopAutoDownload";
        public const string AUTO_UPDATE_PENDING = @"Software\项目I\AutoUpdatePending";

        public static string BackupAndReport(string backupDir)
        {
            Directory.CreateDirectory(backupDir);
            string stamp = DateTime.Now.ToString("yyyyMMdd-HHmmss");
            string report = "";
            report += ExportKey(Registry.CurrentUser, LICENSE_PATH,
                Path.Combine(backupDir, "hkcu-license-" + stamp + ".reg"));
            report += ExportKey(Registry.LocalMachine, LICENSE_PATH,
                Path.Combine(backupDir, "hklm-license-" + stamp + ".reg"));
            return report;
        }

        private static string ExportKey(RegistryKey root, string sub, string file)
        {
            try
            {
                using (var k = root.OpenSubKey(sub, false))
                {
                    var sb = new System.Text.StringBuilder();
                    sb.AppendLine("Windows Registry Editor Version 5.00");
                    sb.AppendLine();
                    sb.AppendLine("[" + RootName(root) + "\\" + sub + "]");
                    if (k != null)
                    {
                        foreach (string name in k.GetValueNames())
                        {
                            object v = k.GetValue(name, null, RegistryValueOptions.DoNotExpandEnvironmentNames);
                            var kind = k.GetValueKind(name);
                            string n = name.Length == 0 ? "@" : "\"" + name + "\"";
                            if (kind == RegistryValueKind.String || kind == RegistryValueKind.ExpandString)
                                sb.AppendLine(n + "=hex(2):" + HexOfUtf16((string)v));
                            else if (kind == RegistryValueKind.DWord)
                                sb.AppendLine(n + "=dword:" + Convert.ToInt32(v).ToString("x8"));
                            else if (kind == RegistryValueKind.Binary)
                                sb.AppendLine(n + "=hex:" + HexOfBytes((byte[])v));
                            else if (kind == RegistryValueKind.QWord)
                                sb.AppendLine(n + "=hex(b):" + HexOfBytes(BitConverter.GetBytes(Convert.ToInt64(v))));
                            else
                                sb.AppendLine(n + "=hex:" + HexOfBytes((byte[])v));
                        }
                    }
                    File.WriteAllText(file, sb.ToString());
                    return "backup: " + file + Environment.NewLine;
                }
            }
            catch (Exception ex)
            {
                return "backup FAILED (" + RootName(root) + "\\" + sub + "): " + ex.Message + Environment.NewLine;
            }
        }

        private static string RootName(RegistryKey root)
        {
            return root == Registry.CurrentUser ? "HKEY_CURRENT_USER" : "HKEY_LOCAL_MACHINE";
        }

        private static string HexOfUtf16(string s)
        {
            var bytes = Encoding.Unicode.GetBytes(s);
            var all = new byte[bytes.Length + 2];
            Buffer.BlockCopy(bytes, 0, all, 0, bytes.Length); // NUL-terminated
            return HexOfBytes(all);
        }

        private static string HexOfBytes(byte[] b)
        {
            if (b == null || b.Length == 0) return "";
            var sb = new System.Text.StringBuilder(b.Length * 3);
            for (int i = 0; i < b.Length; i++)
            {
                sb.Append(b[i].ToString("x2"));
                if (i < b.Length - 1) sb.Append(",");
            }
            return sb.ToString();
        }

        public static string WriteActivation(string keyText, string activationB64, bool alsoHklm)
        {
            string log = "";
            string lh = LicenseAlgo.LicenseHash(keyText);

            using (var k = Registry.CurrentUser.CreateSubKey(LICENSE_PATH, true))
            {
                if (activationB64 != null)
                    k.SetValue("ActivationData", Convert.FromBase64String(activationB64), RegistryValueKind.Binary);
                else
                    k.DeleteValue("ActivationData", false);
                k.SetValue("LicenseHash", lh, RegistryValueKind.String);
                if (keyText.Length > 0x1E) k.SetValue("", keyText, RegistryValueKind.String);
            }
            log += "HKCU License written (LicenseHash=" + lh + ")" + Environment.NewLine;

            if (alsoHklm)
            {
                try
                {
                    using (var k = Registry.LocalMachine.CreateSubKey(LICENSE_PATH, true))
                    {
                        if (activationB64 != null)
                            k.SetValue("ActivationData", Convert.FromBase64String(activationB64), RegistryValueKind.Binary);
                        else
                            k.DeleteValue("ActivationData", false);
                        k.SetValue("LicenseHash", lh, RegistryValueKind.String);
                        if (keyText.Length > 0x1E) k.SetValue("", keyText, RegistryValueKind.String);
                    }
                    log += "HKLM License written" + Environment.NewLine;
                }
                catch (Exception ex)
                {
                    log += "HKLM write skipped (need admin): " + ex.Message + Environment.NewLine;
                }
            }

            // successful activation must clear AutoUpdatePending (evidence: FUN_005d1c20)
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(ROOT_KEY, true))
                {
                    if (k != null) k.DeleteSubKeyTree("AutoUpdatePending", false);
                }
                log += "AutoUpdatePending cleared" + Environment.NewLine;
            }
            catch (Exception ex)
            {
                log += "AutoUpdatePending cleanup: " + ex.Message + Environment.NewLine;
            }
            return log;
        }

        // read-back verification (c16)
        public static string ReadBack()
        {
            using (var k = Registry.CurrentUser.OpenSubKey(LICENSE_PATH, false))
            {
                if (k == null) return "HKCU License: MISSING";
                var lh = k.GetValue("LicenseHash") as string;
                var ad = k.GetValue("ActivationData") as byte[];
                return "HKCU License: LicenseHash=" + (lh ?? "<null>")
                     + " ActivationData=" + (ad == null ? "<null>" : ad.Length + " bytes");
            }
        }

        public static string Restore(string backupDir)
        {
            string log = "";
            foreach (string f in Directory.GetFiles(backupDir, "*.reg"))
            {
                var psi = new System.Diagnostics.ProcessStartInfo("reg.exe", "import \"" + f + "\"")
                {
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                };
                using (var p = System.Diagnostics.Process.Start(psi))
                {
                    string outp = p.StandardOutput.ReadToEnd();
                    p.WaitForExit();
                    log += f + " -> exit " + p.ExitCode + " " + outp.Trim() + Environment.NewLine;
                }
            }
            return log;
        }
    }
}
