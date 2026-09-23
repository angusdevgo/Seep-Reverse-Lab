// 项目I Activate - one-click activation & rollback-guard GUI.
// Research/educational use; structure aligned with A:/项目F-keygen/src/项目FActivate.cs
using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
using SabLicense;

namespace SabActivate
{
    public class MainForm : Form
    {
        TextBox txtKey;
        TextBox txtLog;
        Button btnOneClick, btnBackup, btnWrite, btnGuard, btnUndoGuard, btnStatus, btnRestore;
        CheckBox chkHklm, chkHosts, chkStopDownload, chkDisableTask;

        public MainForm()
        {
            Text = "项目I 一键激活工具 (research)";
            Size = new Size(760, 620);
            Font = new Font("Segoe UI", 9F);

            var lbl = new Label { Text = "License key text (stored default value; LicenseHash = md5hex(key))", Location = new Point(12, 12), AutoSize = true };
            txtKey = new TextBox { Location = new Point(12, 32), Width = 500, Text = "SAB-RESEARCH-0000000000000000000" };

            chkHklm = new CheckBox { Text = "Also write HKLM (elevated)", Location = new Point(12, 60), AutoSize = true };
            btnOneClick = new Button
            {
                Text = "⚡ 一键激活（备份 → DLL 补丁 → 写激活状态 → 防回退）",
                Location = new Point(12, 88),
                Size = new Size(600, 44),
                Font = new Font("Segoe UI", 11F, FontStyle.Bold),
            };
            btnBackup = new Button { Text = "1. Backup", Location = new Point(12, 145), Width = 120 };
            btnWrite = new Button { Text = "2. Write activation state", Location = new Point(140, 145), Width = 180 };
            chkHosts = new CheckBox { Text = "hosts block activation/update endpoints", Location = new Point(12, 180), Checked = true, AutoSize = true };
            chkStopDownload = new CheckBox { Text = "StopAutoDownload (official switch)", Location = new Point(260, 180), Checked = true, AutoSize = true };
            chkDisableTask = new CheckBox { Text = "Disable \"\\项目I Update\" task", Location = new Point(520, 180), AutoSize = true };
            btnGuard = new Button { Text = "3. Apply rollback guard", Location = new Point(12, 205), Width = 180 };
            btnUndoGuard = new Button { Text = "Undo guard (revert)", Location = new Point(200, 205), Width = 140 };
            btnStatus = new Button { Text = "Status", Location = new Point(348, 205), Width = 80 };
            btnRestore = new Button { Text = "Restore backups", Location = new Point(436, 205), Width = 130 };

            txtLog = new TextBox
            {
                Location = new Point(12, 245),
                Size = new Size(720, 330),
                Multiline = true,
                ScrollBars = ScrollBars.Vertical,
                ReadOnly = true,
                WordWrap = false,
            };

            btnOneClick.Click += (s, e) => DoOneClick();
            btnBackup.Click += (s, e) => Log(PrefsWriter.BackupAndReport(BackupDir()));
            btnWrite.Click += (s, e) => DoWrite();
            btnGuard.Click += (s, e) => Log(RollbackGuard.ApplyAll(chkHosts.Checked, chkStopDownload.Checked, chkDisableTask.Checked));
            btnUndoGuard.Click += (s, e) => Log(RollbackGuard.RemoveHosts() + RollbackGuard.UndoStopAutoDownload() + RollbackGuard.ApplyTaskEnable());
            btnStatus.Click += (s, e) => Log(RollbackGuard.Status() + PrefsWriter.ReadBack());
            btnRestore.Click += (s, e) => Log(PrefsWriter.Restore(BackupDir()));

            Controls.AddRange(new Control[] { lbl, txtKey, chkHklm, btnOneClick, btnBackup, btnWrite, chkHosts, chkStopDownload, chkDisableTask, btnGuard, btnUndoGuard, btnStatus, btnRestore, txtLog });
        }

        string BackupDir()
        {
            string dir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "backups");
            Directory.CreateDirectory(dir);
            return dir;
        }

        // One-click: backup -> DLL patch -> license state -> rollback guard.
        void DoOneClick()
        {
            string key = txtKey.Text.Trim();
            Log("===== One-click activate =====" + Environment.NewLine);

            Log(PrefsWriter.BackupAndReport(BackupDir()));

            string dll = PatchEngine.DefaultDllPath();
            Log("DLL: " + dll + "  state: " + PatchEngine.State(dll) + Environment.NewLine);
            Log(PatchEngine.Apply(dll, PatchBackupDir()));

            Log(PrefsWriter.WriteActivation(key, null, chkHklm.Checked));

            Log(RollbackGuard.ApplyAll(chkHosts.Checked, chkStopDownload.Checked, chkDisableTask.Checked));

            Log("===== Done. Restart explorer (or reboot) so the shell reloads the patched DLL =====" + Environment.NewLine);
        }

        string PatchBackupDir()
        {
            string dir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "patches");
            Directory.CreateDirectory(dir);
            return dir;
        }

        void DoWrite()
        {
            string key = txtKey.Text.Trim();
            if (key.Length <= 0x1E)
            {
                Log("key too short: LicenseHash migration needs default value length > 0x1E" + Environment.NewLine);
            }
            string req = MachineCode.RequestHex(key);
            Log("request R (local elements) = " + req + Environment.NewLine);
            Log("NOTE: ActivationData requires the vendor RSA private key; this tool writes" + Environment.NewLine +
                "local-verifiable state only. If a server-issued activation block exists," + Environment.NewLine +
                "paste it into tools dir 'activation.b64' and it will be applied." + Environment.NewLine);
            string b64 = null;
            string b64File = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "activation.b64");
            if (File.Exists(b64File))
            {
                b64 = File.ReadAllText(b64File).Trim();
                byte[] blob = LicenseAlgo.DecodeActivation(b64);
                if (blob.Length != LicenseAlgo.PLAIN_LEN)
                    Log("activation.b64 decodes to " + blob.Length + " bytes (expected 128)" + Environment.NewLine);
            }
            Log(PrefsWriter.WriteActivation(key, b64, chkHklm.Checked));
            Log(PrefsWriter.ReadBack() + Environment.NewLine);
        }

        void Log(string s)
        {
            txtLog.AppendText(s);
            if (!s.EndsWith(Environment.NewLine)) txtLog.AppendText(Environment.NewLine);
        }

        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }
}
