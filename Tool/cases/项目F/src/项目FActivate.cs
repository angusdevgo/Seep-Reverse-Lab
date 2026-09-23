// 项目FActivate - 项目F Pro 一键激活工具（GUI）
// 单窗口完成：邮箱（手动/随机）→ 自动生成密钥 → 校验 → 检测 项目F 进程
//            → 备份 Preferences.json → 写入 Settings 三键 → 复读校验
// 底部常驻：免责声明 + 正版购买链接 + 开源仓库地址
// 编译：csc /nologo /target:winexe /codepage:65001 /out:项目FActivate.exe
//       /r:System.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll
//       /r:System.Web.Extensions.dll /r:System.Numerics.dll
//       项目FActivate.cs LicenseAlgo.cs PrefsWriter.cs
using System;
using System.Diagnostics;
using System.Drawing;
using System.Text;
using System.Windows.Forms;
using 项目FLicense;

namespace 项目FActivateApp
{
    public class MainForm : Form
    {
        TextBox txtName;
        TextBox txtEmail;
        TextBox txtKey;
        TextBox txtConfigPath;
        TextBox txtLog;

        const string VERSION_TAG = "v1.0.0";
        const string REPO_URL = "https://项目F.int0.cc";
        const string BUY_URL = "https://www.项目F.com/pro";

        public MainForm()
        {
            Text = "项目F Pro 一键激活";
            Font = new Font("Microsoft YaHei UI", 9F);
            ClientSize = new Size(680, 560);
            StartPosition = FormStartPosition.CenterScreen;
            MaximizeBox = false;
            FormBorderStyle = FormBorderStyle.FixedSingle;

            int y = 12;
            Label lblName = new Label();
            lblName.Text = "用户名（Name）:";
            lblName.SetBounds(12, y, 200, 20);
            Controls.Add(lblName);
            txtName = new TextBox();
            txtName.SetBounds(220, y - 2, 448, 24);
            txtName.Text = "Pro User";
            Controls.Add(txtName);
            y += 34;

            Label lblEmail = new Label();
            lblEmail.Text = "邮箱（Email）:";
            lblEmail.SetBounds(12, y, 200, 20);
            Controls.Add(lblEmail);
            txtEmail = new TextBox();
            txtEmail.SetBounds(220, y - 2, 340, 24);
            Controls.Add(txtEmail);
            Button btnRandom = new Button();
            btnRandom.Text = "随机邮箱";
            btnRandom.SetBounds(568, y - 2, 100, 26);
            btnRandom.Click += delegate { AddRandomEmail(); };
            Controls.Add(btnRandom);
            y += 34;

            Label lblKey = new Label();
            lblKey.Text = "密钥（License）:";
            lblKey.SetBounds(12, y, 200, 20);
            Controls.Add(lblKey);
            txtKey = new TextBox();
            txtKey.SetBounds(220, y - 2, 448, 24);
            txtKey.Font = new Font("Consolas", 9F);
            Controls.Add(txtKey);
            y += 36;

            Button btnGen = new Button();
            btnGen.Text = "仅生成密钥";
            btnGen.SetBounds(220, y, 130, 28);
            btnGen.Click += delegate { GenerateKey(); };
            Controls.Add(btnGen);

            Button btnActivate = new Button();
            btnActivate.Text = "一键激活";
            btnActivate.SetBounds(360, y, 140, 28);
            btnActivate.BackColor = Color.FromArgb(215, 235, 215);
            btnActivate.Click += delegate { DoActivate(); };
            Controls.Add(btnActivate);
            y += 42;

            Label lblCfg = new Label();
            lblCfg.Text = "配置文件:";
            lblCfg.SetBounds(12, y, 200, 20);
            Controls.Add(lblCfg);
            txtConfigPath = new TextBox();
            txtConfigPath.SetBounds(220, y - 2, 340, 24);
            txtConfigPath.Text = PrefsWriter.DefaultPath();
            Controls.Add(txtConfigPath);
            Button btnBrowse = new Button();
            btnBrowse.Text = "浏览...";
            btnBrowse.SetBounds(568, y - 2, 100, 26);
            btnBrowse.Click += delegate { BrowseConfig(); };
            Controls.Add(btnBrowse);
            y += 38;

            // anti-rollback protection: block the activation server so the
            // scheduled online check (ScheduleAutoCheck) never invalidates the license
            Label lblGuard = new Label();
            lblGuard.SetBounds(12, y, 460, 24);
            UpdateGuardLabel(lblGuard);
            Controls.Add(lblGuard);
            Button btnGuard = new Button();
            btnGuard.Text = "屏蔽激活服务器（防回退）";
            btnGuard.SetBounds(480, y - 2, 188, 28);
            btnGuard.Click += delegate { BlockActivationServer(lblGuard, btnGuard); };
            Controls.Add(btnGuard);
            y += 40;

            txtLog = new TextBox();
            txtLog.Multiline = true;
            txtLog.ReadOnly = true;
            txtLog.ScrollBars = ScrollBars.Vertical;
            txtLog.Font = new Font("Consolas", 9F);
            txtLog.SetBounds(12, y, 656, 180);
            Controls.Add(txtLog);
            y += 192;

            Label lblWarn = new Label();
            lblWarn.Text = "仅供授权范围内的逆向学习与研究，请遵守 项目F 服务条款，勿用于未授权用途";
            lblWarn.ForeColor = Color.FromArgb(90, 90, 90);
            lblWarn.Font = new Font("Microsoft YaHei UI", 8.5F);
            lblWarn.SetBounds(12, y, 656, 20);
            Controls.Add(lblWarn);
            y += 24;

            LinkLabel lnkLinks = new LinkLabel();
            string p1 = "正版购买: ";
            string p2 = "   |   开源仓库: ";
            string p3 = "   |   版本: " + VERSION_TAG;
            lnkLinks.Text = p1 + BUY_URL + p2 + REPO_URL + p3;
            lnkLinks.ForeColor = Color.FromArgb(90, 90, 90);
            lnkLinks.Font = new Font("Microsoft YaHei UI", 8.5F);
            lnkLinks.LinkColor = Color.FromArgb(0, 102, 204);
            lnkLinks.ActiveLinkColor = Color.FromArgb(0, 60, 140);
            lnkLinks.VisitedLinkColor = Color.FromArgb(0, 102, 204);
            lnkLinks.LinkBehavior = LinkBehavior.HoverUnderline;
            lnkLinks.AutoEllipsis = true;
            lnkLinks.SetBounds(12, y, 656, 20);
            lnkLinks.Links.Clear();
            lnkLinks.Links.Add(p1.Length, BUY_URL.Length, BUY_URL);
            lnkLinks.Links.Add(p1.Length + BUY_URL.Length + p2.Length, REPO_URL.Length, REPO_URL);
            lnkLinks.LinkClicked += delegate(object sender, LinkLabelLinkClickedEventArgs e)
            {
                if (e.Link != null && e.Link.LinkData != null)
                {
                    OpenUrl(e.Link.LinkData.ToString());
                }
            };
            Controls.Add(lnkLinks);

            Log("就绪（v" + VERSION_TAG + "）。目标配置: " + PrefsWriter.DefaultPath());
            Log("提示：写入前请退出 项目F，否则退出时内存数据会覆盖新配置。");
        }

        void UpdateGuardLabel(Label lbl)
        {
            if (HostsGuard.IsBlocked())
            {
                lbl.Text = "✓ 已屏蔽激活服务器 account.项目F.com —— 在线校验不会回退激活状态";
                lbl.ForeColor = Color.ForestGreen;
            }
            else
            {
                lbl.Text = "⚠ 未屏蔽激活服务器 —— 项目F 启动 15 分钟后联网校验，失败累计 7 天会回退";
                lbl.ForeColor = Color.Firebrick;
            }
        }

        void BlockActivationServer(Label lbl, Button btn)
        {
            if (HostsGuard.IsBlocked())
            {
                MessageBox.Show(this, "激活服务器已在 hosts 中屏蔽，无需重复操作。", "提示",
                                MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            DialogResult r = MessageBox.Show(this,
                "将在系统 hosts 文件中添加：\r\n\r\n    " + HostsGuard.BlockEntry +
                "\r\n\r\n作用：让 项目F 的在线激活校验（account.项目F.com）无法连接。\r\n" +
                "联网校验失败（网络异常）时程序不会清除本地激活配置，且本地校验不受影响。\r\n" +
                "需要管理员权限（UAC 弹窗）。\r\n\r\n继续？",
                "屏蔽激活服务器", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (r != DialogResult.Yes) return;
            bool launched = HostsGuard.BlockViaUac();
            System.Threading.Thread.Sleep(1200);   // give the elevated process time to finish
            bool nowBlocked = HostsGuard.IsBlocked();
            UpdateGuardLabel(lbl);
            if (nowBlocked)
                Log("已屏蔽激活服务器（hosts 写入成功）——在线校验将因网络异常而不做任何处理。");
            else if (launched)
                Log("已发起 hosts 写入，但未检测到生效（可能 UAC 被拒绝或写入失败），请手动检查。");
            else
                Log("hosts 写入未执行（UAC 被取消）。可再次点击按钮重试。");
        }

        void Log(string msg)
        {
            txtLog.AppendText("[" + DateTime.Now.ToString("HH:mm:ss") + "] " + msg + "\r\n");
        }

        void AddRandomEmail()
        {
            txtEmail.Text = LicenseAlgo.RandomEmail();
            Log("已生成随机邮箱: " + txtEmail.Text.Trim() + "（点“一键激活”或“仅生成密钥”继续）");
        }

        void GenerateKey()
        {
            string email = txtEmail.Text.Trim();
            if (email.Length == 0)
            {
                email = LicenseAlgo.RandomEmail();
                txtEmail.Text = email;
                Log("邮箱为空，已自动生成: " + email);
            }
            try
            {
                string lic = LicenseAlgo.Generate(email);
                if (!LicenseAlgo.Verify(email, lic))
                {
                    MessageBox.Show(this, "生成结果未通过自校验，请更换邮箱重试", "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }
                txtKey.Text = lic;
                Log("已为 " + email + " 生成密钥（" + lic.Length + " 字符），自校验通过（Verify=True）");
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "生成失败: " + ex.Message, "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        void BrowseConfig()
        {
            OpenFileDialog dlg = new OpenFileDialog();
            dlg.Filter = "JSON 文件 (*.json)|*.json|所有文件 (*.*)|*.*";
            dlg.FileName = txtConfigPath.Text;
            if (dlg.ShowDialog(this) == DialogResult.OK)
                txtConfigPath.Text = dlg.FileName;
        }

        void DoActivate()
        {
            string email = txtEmail.Text.Trim();
            string lic = txtKey.Text.Trim();

            // ensure email + key are present and match
            if (email.Length == 0)
            {
                email = LicenseAlgo.RandomEmail();
                txtEmail.Text = email;
                Log("邮箱为空，已自动生成: " + email);
            }
            if (lic.Length == 0)
            {
                Log("密钥为空，自动生成中...");
                GenerateKey();
                lic = txtKey.Text.Trim();
            }
            if (lic.Length != LicenseAlgo.LICENSE_LEN)
            {
                MessageBox.Show(this, "密钥长度应为 " + LicenseAlgo.LICENSE_LEN + " 字符，当前 " + lic.Length,
                                "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            if (!LicenseAlgo.Verify(email, lic))
            {
                Log("警告：密钥与邮箱不匹配，自动重新生成...");
                GenerateKey();
                lic = txtKey.Text.Trim();
                if (!LicenseAlgo.Verify(email, lic))
                {
                    MessageBox.Show(this, "密钥仍未通过校验，请更换邮箱或手动填入有效密钥", "错误",
                                    MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }
            }

            string name = txtName.Text.Trim();
            if (name.Length == 0) name = "Pro User";

            // process check: writing while 项目F is running gets overwritten on exit
            Process[] procs = Process.GetProcessesByName("项目F");
            if (procs.Length > 0)
            {
                DialogResult r = MessageBox.Show(this,
                    "项目F 正在运行（PID: " + procs[0].Id + "）。\r\n" +
                    "若现在写入，项目F 退出时内存数据可能覆盖新配置。\r\n\r\n" +
                    "建议先退出 项目F 再写入。仍然继续？",
                    "项目F 正在运行", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
                if (r != DialogResult.Yes)
                {
                    Log("已取消写入（项目F 仍在运行）。请退出 项目F 后再试。");
                    return;
                }
            }

            string path = txtConfigPath.Text.Trim();
            StringBuilder log = new StringBuilder();
            string error;
            bool ok = PrefsWriter.Write(path, name, email, lic, log, out error);
            foreach (string line in log.ToString().Split(new string[] { "\r\n" }, StringSplitOptions.RemoveEmptyEntries))
                Log(line);
            if (ok)
            {
                Log("完成：邮箱 " + email + " 的激活配置已写入。重启 项目F 后生效（Pro 状态）。");
                MessageBox.Show(this, "一键激活成功！\r\n\r\n邮箱: " + email + "\r\n配置文件: " + path +
                                "\r\n\r\n重启 项目F 后 Pro 状态生效。", "激活成功",
                                MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            else
            {
                MessageBox.Show(this, "写入失败: " + error + "\r\n\r\n原配置已保留（备份: " + path + PrefsWriter.BACKUP_SUFFIX + "）",
                                "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        static void OpenUrl(string url)
        {
            try
            {
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            }
            catch (Exception ex)
            {
                try
                {
                    Process.Start(url);
                }
                catch
                {
                    MessageBox.Show("无法打开链接: " + ex.Message, "提示", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
            }
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