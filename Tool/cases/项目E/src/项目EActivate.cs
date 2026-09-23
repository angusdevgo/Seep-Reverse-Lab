// 项目EActivate - 项目E PRO / 项目E 一键激活工具（暗黑极客版）
// 严格遵循 INT0 Unified Design System (DWM Dark Mode, Cyber Orange Accent, CRT Console)
// 编译：csc /nologo /target:winexe /codepage:65001 /out:项目EActivate.exe
//       /r:System.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll
//       项目EActivate.cs LicenseAlgo.cs LicenseWriter.cs Patcher.cs HostsGuard.cs Int0Theme.cs
using System;
using System.Diagnostics;
using System.Drawing;
using System.Text;
using System.Windows.Forms;
using UtLicense;
using Int0.UI;

namespace UtActivateApp
{
    public class MainForm : Int0BaseForm
    {
        TextBox txtName;
        TextBox txtKey;
        TextBox txtExePath;
        TextBox txtBackup;
        Int0ConsoleBox _console;
        System.Collections.Generic.List<string> _sharedLog = new System.Collections.Generic.List<string>();

        const string VERSION_TAG = "v1.1.0";

        public MainForm()
        {
            Text = "INT0 // 项目E PRO & 项目E <目标版本> Activator (" + VERSION_TAG + ")";
            ClientSize = new Size(720, 580);

            // 1. Header Banner
            Int0Header header = new Int0Header();
            header.Title = "项目E PRO // 项目E <目标版本>";
            header.Subtitle = "EXECryptor VM Root Gate Bypass & Atomic In-Place Activator";
            header.VersionTag = VERSION_TAG;
            Controls.Add(header);

            int y = 76;
            int labelX = 16;
            int labelWidth = 140;
            int inputX = 160;
            int inputWidth = 400;
            int btnX = 572;
            int btnWidth = 132;

            // Row 1: Name
            Label lblName = CreateLabel("注册名 (Name):", labelX, y + 4, labelWidth);
            Controls.Add(lblName);
            txtName = CreateTextBox(LicenseAlgo.RandomName(), inputX, y, inputWidth, false);
            Controls.Add(txtName);
            Int0Button btnRandom = new Int0Button();
            btnRandom.Text = "随机生成";
            btnRandom.Variant = Int0ButtonVariant.Secondary;
            btnRandom.SetBounds(btnX, y, btnWidth, 26);
            btnRandom.Click += delegate { txtName.Text = LicenseAlgo.RandomName(); };
            Controls.Add(btnRandom);
            y += 36;

            // Row 2: Key
            Label lblKey = CreateLabel("注册码 (Key):", labelX, y + 4, labelWidth);
            Controls.Add(lblKey);
            txtKey = CreateTextBox(LicenseAlgo.RandomKey(), inputX, y, inputWidth, true);
            Controls.Add(txtKey);
            Int0Button btnGenKey = new Int0Button();
            btnGenKey.Text = "重生成密钥";
            btnGenKey.Variant = Int0ButtonVariant.Secondary;
            btnGenKey.SetBounds(btnX, y, btnWidth, 26);
            btnGenKey.Click += delegate { txtKey.Text = LicenseAlgo.RandomKey(); };
            Controls.Add(btnGenKey);
            y += 36;

            // Row 3: Exe Path
            Label lblExe = CreateLabel("目标主程序:", labelX, y + 4, labelWidth);
            Controls.Add(lblExe);
            txtExePath = CreateTextBox(FindDefaultExe(), inputX, y, inputWidth, true);
            Controls.Add(txtExePath);
            Int0Button btnBrowse = new Int0Button();
            btnBrowse.Text = "浏览选择...";
            btnBrowse.Variant = Int0ButtonVariant.Secondary;
            btnBrowse.SetBounds(btnX, y, btnWidth, 26);
            btnBrowse.Click += delegate { BrowseExe(); };
            Controls.Add(btnBrowse);
            y += 36;

            // Row 4: Backup Path
            Label lblBak = CreateLabel("注册表备份:", labelX, y + 4, labelWidth);
            Controls.Add(lblBak);
            txtBackup = CreateTextBox(LicenseWriter.DefaultBackupPath(), inputX, y, inputWidth, true);
            Controls.Add(txtBackup);
            y += 42;

            // Action Buttons Bar
            Int0Button btnPatch = new Int0Button();
            btnPatch.Text = "仅补丁替换";
            btnPatch.Variant = Int0ButtonVariant.Secondary;
            btnPatch.SetBounds(inputX, y, 110, 32);
            btnPatch.Click += delegate { ApplyPatch(); };
            Controls.Add(btnPatch);

            Int0Button btnActivate = new Int0Button();
            btnActivate.Text = "⚡ 一键激活（全自动）";
            btnActivate.Variant = Int0ButtonVariant.Primary;
            btnActivate.SetBounds(inputX + 118, y, 170, 32);
            btnActivate.Click += delegate { DoActivate(); };
            Controls.Add(btnActivate);

            Int0Button btnGuard = new Int0Button();
            btnGuard.Text = "屏蔽核验服务器";
            btnGuard.Variant = Int0ButtonVariant.Secondary;
            btnGuard.SetBounds(inputX + 296, y, 126, 32);
            btnGuard.Click += delegate { BlockServer(); };
            Controls.Add(btnGuard);
            y += 44;

            // Terminal CRT Output Console
            _console = new Int0ConsoleBox();
            _console.SetBounds(16, y, 688, 220);
            Controls.Add(_console);
            y += 228;

            // Footer Disclaimer
            Label lblWarn = new Label();
            lblWarn.Text = "仅供授权范围内的逆向学习与学术研究。Support original creators at 项目E.com // int0.cc";
            lblWarn.ForeColor = Int0Theme.TextFaint;
            lblWarn.Font = Int0Theme.GetMonoFont(7.5F);
            lblWarn.SetBounds(16, y, 688, 20);
            Controls.Add(lblWarn);

            Log("[*] INT0 Command Console Initialized (" + VERSION_TAG + ")");
            Log("[*] 补丁说明：重定向 IsRegistered 根门控 0x140009E0F 至 stub 0x140001622");
            Log("[+] 就绪。推荐直接点击「⚡ 一键激活（全自动）」完成进程终止、备份、原地替换与注册写入。");
        }

        private Label CreateLabel(string text, int x, int y, int width)
        {
            Label lbl = new Label();
            lbl.Text = text;
            lbl.SetBounds(x, y, width, 20);
            lbl.ForeColor = Int0Theme.TextMuted;
            lbl.Font = Int0Theme.GetMonoFont(8.5F, FontStyle.Bold);
            return lbl;
        }

        private TextBox CreateTextBox(string text, int x, int y, int width, bool isMono)
        {
            TextBox tb = new TextBox();
            tb.Text = text;
            tb.SetBounds(x, y, width, 24);
            tb.BackColor = Int0Theme.Surface;
            tb.ForeColor = Int0Theme.TextPrimary;
            tb.BorderStyle = BorderStyle.FixedSingle;
            tb.Font = isMono ? Int0Theme.GetMonoFont(9F) : Int0Theme.GetSansFont(9F);
            return tb;
        }

        static string FindDefaultExe()
        {
            try
            {
                using (Microsoft.Win32.RegistryKey k = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                    @"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\项目E_is1"))
                {
                    if (k != null)
                    {
                        string loc = k.GetValue("InstallLocation") as string;
                        if (!string.IsNullOrEmpty(loc))
                            return System.IO.Path.Combine(loc, "项目E.exe");
                    }
                }
            }
            catch { }
            return "";
        }

        void BrowseExe()
        {
            OpenFileDialog dlg = new OpenFileDialog();
            dlg.Filter = "项目E.exe|项目E.exe|所有文件 (*.*)|*.*";
            dlg.FileName = txtExePath.Text;
            if (dlg.ShowDialog(this) == DialogResult.OK)
                txtExePath.Text = dlg.FileName;
        }

        void Log(string msg)
        {
            _console.AppendLog("[" + DateTime.Now.ToString("HH:mm:ss") + "] " + msg);
        }

        void ApplyPatch()
        {
            string exe = txtExePath.Text.Trim();
            if (exe.Length == 0 || !System.IO.File.Exists(exe))
            {
                MessageBox.Show(this, "请先选择 项目E.exe", "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            Process[] procs = Process.GetProcessesByName("项目E");
            if (procs.Length > 0)
            {
                MessageBox.Show(this, "项目E 正在运行（PID " + procs[0].Id + "）。\r\n" +
                                "替换 exe 需要先完全退出程序（含托盘进程与 项目EHelper.exe）。",
                                "正在运行", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            System.Collections.Generic.List<string> logLines = new System.Collections.Generic.List<string>();
            try
            {
                string mode = Patcher.AutoPatchAndReplace(exe, logLines);
                Log("[*] === 应用补丁（自动替换） ===");
                foreach (string line in logLines)
                    Log(line);
                if (mode == "already-patched")
                {
                    Log("[!] 目标已是补丁版，无需重复替换。");
                    MessageBox.Show(this, "该 项目E.exe 已是补丁版，无需重复操作。\r\n\r\n" + exe,
                                    "无需补丁", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return;
                }
                Log("[+] 完成：已自动替换安装目录 exe，原件备份为 .orig.exe（同目录）。");
                MessageBox.Show(this,
                    "补丁已自动替换：\r\n" + exe + "\r\n\r\n" +
                    "原件已备份为同目录 项目E.orig.exe。\r\n" +
                    "现在点击「一键激活」写入注册表，然后重启 项目E 即可。",
                    "补丁完成", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (System.IO.IOException ioEx)
            {
                Log("[-] 补丁失败: " + ioEx.Message);
                MessageBox.Show(this, "补丁失败（文件被占用或无法写入）: " + ioEx.Message +
                                "\r\n\r\n请确认 项目E 已完全退出；若安装在受保护目录请以管理员身份运行本工具。",
                                "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            catch (UnauthorizedAccessException uaEx)
            {
                Log("[-] 补丁失败: " + uaEx.Message);
                MessageBox.Show(this, "补丁失败（无写入权限）: " + uaEx.Message +
                                "\r\n\r\n请以管理员身份运行本工具（右键 → 以管理员身份运行）。",
                                "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            catch (Exception ex)
            {
                Log("[-] 补丁失败: " + ex.Message);
                MessageBox.Show(this, "补丁失败: " + ex.Message, "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        void DoActivate()
        {
            string name = txtName.Text.Trim();
            string code = txtKey.Text.Trim();
            if (name.Length == 0) name = LicenseAlgo.RandomName();
            if (code.Length == 0) code = LicenseAlgo.RandomKey();
            if (!LicenseAlgo.Verify(name, code))
            {
                MessageBox.Show(this, "注册名/注册码格式不正确", "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            string exe = txtExePath.Text.Trim();

            Log("[*] === 开始全自动一键激活流水线 ===");
            Log("[*] [1/5] 目标 exe: " + (exe.Length > 0 ? exe : "(未指定，仅写入注册表)"));

            // 1) 进程检测与生命周期管理
            Process[] procs = Process.GetProcessesByName("项目E");
            if (procs.Length > 0)
            {
                DialogResult r = MessageBox.Show(this,
                    "项目E 正在运行（PID " + procs[0].Id + "）。\r\n" +
                    "自动替换 exe 前必须完全退出程序（含托盘进程与 项目EHelper.exe）。\r\n\r\n" +
                    "点「是」将自动尝试结束进程（可能需要 UAC 确认），然后继续。",
                    "正在运行", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
                if (r != DialogResult.Yes) { Log("[!] [2/5] 已取消（程序仍在运行）"); return; }
                if (!Kill项目E())
                {
                    Log("[-] [2/5] 无法自动结束进程，请手动退出后重试");
                    MessageBox.Show(this, "无法自动结束 项目E，请手动退出（托盘右键 Exit）后重试。",
                                    "需要手动退出", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }
                System.Threading.Thread.Sleep(800);
                Log("[+] [2/5] 已成功终止 项目E / 项目EHelper 进程");
            }

            // 2) 补丁 + 原位自动替换
            if (exe.Length > 0 && System.IO.File.Exists(exe))
            {
                try
                {
                    string mode = Patcher.AutoPatchAndReplace(exe, _sharedLog);
                    foreach (string line in _sharedLog) Log(line);
                    _sharedLog.Clear();
                    Log(mode == "already-patched" ? "[+] [3/5] 目标已是补丁版（跳过替换）" : "[+] [3/5] 补丁已自动替换生效");
                }
                catch (System.IO.IOException ioEx)
                {
                    Log("[-] [3/5] 补丁替换失败（文件占用/IO）: " + ioEx.Message);
                    MessageBox.Show(this, "补丁替换失败: " + ioEx.Message +
                                    "\r\n\r\n请确认 项目E 完全退出；若目录受保护请以管理员身份运行本工具。",
                                    "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }
                catch (UnauthorizedAccessException uaEx)
                {
                    Log("[-] [3/5] 补丁替换失败（无写入权限）: " + uaEx.Message);
                    MessageBox.Show(this, "无写入权限: " + uaEx.Message +
                                    "\r\n\r\n请以管理员身份运行本工具（右键 → 以管理员身份运行）。",
                                    "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }
                catch (Exception ex)
                {
                    Log("[-] [3/5] 补丁替换失败: " + ex.Message);
                    MessageBox.Show(this, "补丁替换失败: " + ex.Message, "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }
            }
            else
            {
                Log("[!] [3/5] exe 未指定或不存在，跳过补丁（仅写入注册表，需自行确保 exe 已打补丁）");
            }

            // 3) 写注册表 RN/RC
            string backup = txtBackup.Text.Trim();
            string error;
            System.Collections.Generic.List<string> wlog = new System.Collections.Generic.List<string>();
            bool ok = LicenseWriter.Write(name, code, backup.Length > 0 ? backup : null, wlog, out error);
            foreach (string line in wlog) Log(line);
            if (!ok)
            {
                Log("[-] [4/5] 注册表写入失败: " + error);
                MessageBox.Show(this, "注册表写入失败: " + error, "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            // 4) 完成
            Log("[+] [5/5] 全部流程完成：补丁（如需）已替换，RN/RC 已写入并通过复读哈希校验！");
            Log("    [*] 授权注册名: " + name);
            Log("    [*] 授权注册码: " + code);
            MessageBox.Show(this,
                "一键激活成功（全自动）！\r\n\r\n" +
                "补丁: " + (exe.Length > 0 ? exe + "（原件备份: .orig.exe）" : "（未指定 exe，跳过）") +
                "\r\n注册名: " + name +
                "\r\n注册码: " + code +
                "\r\n\r\n重启 项目E 后生效（About 对话框显示已授权）。",
                "激活成功", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        static bool Kill项目E()
        {
            try
            {
                Process[] procs = Process.GetProcessesByName("项目E");
                foreach (Process p in procs) p.Kill();
                procs = Process.GetProcessesByName("项目EHelper");
                foreach (Process p in procs) p.Kill();
                System.Threading.Thread.Sleep(1000);
                if (Process.GetProcessesByName("项目E").Length == 0 &&
                    Process.GetProcessesByName("项目EHelper").Length == 0)
                    return true;
            }
            catch { }
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = "taskkill.exe";
                psi.Arguments = "/F /IM 项目E.exe /T";
                psi.Verb = "runas";
                psi.UseShellExecute = true;
                Process.Start(psi);
                psi = new ProcessStartInfo();
                psi.FileName = "taskkill.exe";
                psi.Arguments = "/F /IM 项目EHelper.exe /T";
                psi.Verb = "runas";
                psi.UseShellExecute = true;
                Process.Start(psi);
                System.Threading.Thread.Sleep(2000);
                return Process.GetProcessesByName("项目E").Length == 0 &&
                       Process.GetProcessesByName("项目EHelper").Length == 0;
            }
            catch { return false; }
        }

        void BlockServer()
        {
            if (HostsGuard.IsBlocked())
            {
                MessageBox.Show(this, "核验服务器已在 hosts 中屏蔽，无需重复操作。", "提示",
                                MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            DialogResult r = MessageBox.Show(this,
                "将在系统 hosts 文件中添加：\r\n\r\n    " + HostsGuard.BlockEntry +
                "\r\n\r\n作用：让 项目E 的在线核验（项目E.license-manage.com）无法连接，\r\n" +
                "减少 Helper 的联网行为。需要管理员权限（UAC 弹窗）。\r\n\r\n继续？",
                "屏蔽核验服务器", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (r != DialogResult.Yes) return;
            bool launched = HostsGuard.BlockViaUac();
            System.Threading.Thread.Sleep(1200);
            if (HostsGuard.IsBlocked())
                Log("[+] 已成功屏蔽核验服务器（hosts 写入完成）。");
            else if (launched)
                Log("[!] 已发起 hosts 写入，但未检测到生效（UAC 被拒绝或写入失败）。");
            else
                Log("[-] hosts 写入未执行（UAC 被取消）。");
        }
    }

    static class Program
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }
}