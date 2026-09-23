// INT0 Unified Design System — Desktop Windows GUI Suite
// Reusable C# WinForms Theme & Controls for all INT0 keygens/activators.
// Strictly compatible with C# 5 (.NET Framework 4.0/4.5/4.8+ csc.exe).
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace Int0.UI
{
    public static class Int0Theme
    {
        // Colors
        public static readonly Color Canvas = Color.FromArgb(13, 14, 18);          // #0D0E12
        public static readonly Color Surface = Color.FromArgb(21, 24, 31);         // #15181F
        public static readonly Color SurfaceElevated = Color.FromArgb(28, 32, 42); // #1C202A
        public static readonly Color ConsoleBg = Color.FromArgb(7, 8, 10);          // #07080A
        public static readonly Color Border = Color.FromArgb(37, 42, 54);          // #252A36
        public static readonly Color BorderSubtle = Color.FromArgb(48, 54, 70);    // #303646
        public static readonly Color BorderActive = Color.FromArgb(62, 72, 86);    // #3E4856

        public static readonly Color AccentOrange = Color.FromArgb(255, 59, 0);    // #FF3B00
        public static readonly Color AccentOrangeHover = Color.FromArgb(255, 85, 34); // #FF5522
        public static readonly Color AccentOrangeDeep = Color.FromArgb(204, 47, 0);   // #CC2F00
        public static readonly Color AccentCyan = Color.FromArgb(0, 229, 255);     // #00E5FF
        public static readonly Color AccentCyanHover = Color.FromArgb(51, 234, 255);  // #33EAFF
        public static readonly Color AccentEmerald = Color.FromArgb(16, 185, 129); // #10B981
        public static readonly Color AccentAmber = Color.FromArgb(245, 158, 11);    // #F59E0B
        public static readonly Color AccentCrimson = Color.FromArgb(239, 68, 68);  // #EF4444

        public static readonly Color TextPrimary = Color.FromArgb(255, 255, 255);
        public static readonly Color TextSecondary = Color.FromArgb(228, 228, 231);
        public static readonly Color TextMuted = Color.FromArgb(161, 161, 170);
        public static readonly Color TextFaint = Color.FromArgb(113, 113, 122);

        // DWM Immersive Dark Mode P/Invoke
        [DllImport("dwmapi.dll", PreserveSig = true)]
        private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);

        public static void EnableImmersiveDarkMode(IntPtr hWnd)
        {
            if (hWnd == IntPtr.Zero) return;
            try
            {
                int dark = 1;
                // Try attribute 20 (Windows 10 20H1+ / Windows 11)
                int res = DwmSetWindowAttribute(hWnd, 20, ref dark, sizeof(int));
                if (res != 0)
                {
                    // Fallback to attribute 19 (Windows 10 1809-1909)
                    DwmSetWindowAttribute(hWnd, 19, ref dark, sizeof(int));
                }
            }
            catch { }
        }

        public static Font GetMonoFont(float size, FontStyle style)
        {
            string[] preferred = new string[] { "JetBrains Mono", "Consolas", "SF Mono", "Lucida Console", "Courier New" };
            foreach (var name in preferred)
            {
                using (var test = new Font(name, size, style))
                {
                    if (test.Name.Equals(name, StringComparison.OrdinalIgnoreCase))
                        return new Font(name, size, style);
                }
            }
            return new Font(FontFamily.GenericMonospace, size, style);
        }

        public static Font GetMonoFont(float size)
        {
            return GetMonoFont(size, FontStyle.Regular);
        }

        public static Font GetSansFont(float size, FontStyle style)
        {
            string[] preferred = new string[] { "Inter", "Segoe UI", "Microsoft YaHei UI", "Arial" };
            foreach (var name in preferred)
            {
                using (var test = new Font(name, size, style))
                {
                    if (test.Name.Equals(name, StringComparison.OrdinalIgnoreCase))
                        return new Font(name, size, style);
                }
            }
            return new Font(FontFamily.GenericSansSerif, size, style);
        }

        public static Font GetSansFont(float size)
        {
            return GetSansFont(size, FontStyle.Regular);
        }

        public static GraphicsPath CreateRoundedRectangle(Rectangle bounds, int radius)
        {
            GraphicsPath path = new GraphicsPath();
            if (radius <= 0)
            {
                path.AddRectangle(bounds);
                return path;
            }
            int d = radius * 2;
            path.AddArc(bounds.X, bounds.Y, d, d, 180, 90);
            path.AddArc(bounds.Right - d, bounds.Y, d, d, 270, 90);
            path.AddArc(bounds.Right - d, bounds.Bottom - d, d, d, 0, 90);
            path.AddArc(bounds.X, bounds.Bottom - d, d, d, 90, 90);
            path.CloseFigure();
            return path;
        }
    }

    public class Int0BaseForm : Form
    {
        public Int0BaseForm()
        {
            DoubleBuffered = true;
            BackColor = Int0Theme.Canvas;
            ForeColor = Int0Theme.TextSecondary;
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            Font = Int0Theme.GetSansFont(9F);
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            Int0Theme.EnableImmersiveDarkMode(Handle);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            using (var p = new Pen(Int0Theme.BorderSubtle, 1))
            {
                e.Graphics.DrawLine(p, 0, 0, ClientSize.Width, 0);
            }
        }
    }

    public enum Int0ButtonVariant
    {
        Primary,    // Cyber Orange fill
        Secondary,  // Dark surface with hairline border
        Success,    // Emerald fill
        Danger      // Crimson border/fill
    }

    public class Int0Button : Button
    {
        private bool _isHovered = false;
        private bool _isPressed = false;
        private Int0ButtonVariant _variant = Int0ButtonVariant.Secondary;
        private int _cornerRadius = 4;

        public Int0ButtonVariant Variant
        {
            get { return _variant; }
            set { _variant = value; Invalidate(); }
        }

        public int CornerRadius
        {
            get { return _cornerRadius; }
            set { _cornerRadius = value; Invalidate(); }
        }

        public Int0Button()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint |
                     ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            Cursor = Cursors.Hand;
            Font = Int0Theme.GetMonoFont(8.5F, FontStyle.Bold);
            Height = 28;
        }

        protected override void OnMouseEnter(EventArgs e)
        {
            base.OnMouseEnter(e);
            _isHovered = true;
            Invalidate();
        }

        protected override void OnMouseLeave(EventArgs e)
        {
            base.OnMouseLeave(e);
            _isHovered = false;
            _isPressed = false;
            Invalidate();
        }

        protected override void OnMouseDown(MouseEventArgs mevent)
        {
            base.OnMouseDown(mevent);
            if (mevent.Button == MouseButtons.Left)
            {
                _isPressed = true;
                Invalidate();
            }
        }

        protected override void OnMouseUp(MouseEventArgs mevent)
        {
            base.OnMouseUp(mevent);
            _isPressed = false;
            Invalidate();
        }

        protected override void OnPaint(PaintEventArgs pevent)
        {
            var g = pevent.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;

            var bounds = new Rectangle(0, 0, Width - 1, Height - 1);
            using (var path = Int0Theme.CreateRoundedRectangle(bounds, _cornerRadius))
            {
                Color bg, border, text;

                if (!Enabled)
                {
                    bg = Color.FromArgb(18, 20, 26);
                    border = Color.FromArgb(30, 34, 44);
                    text = Int0Theme.TextFaint;
                }
                else if (_variant == Int0ButtonVariant.Primary)
                {
                    bg = _isPressed ? Int0Theme.AccentOrangeDeep : (_isHovered ? Int0Theme.AccentOrangeHover : Int0Theme.AccentOrange);
                    border = _isHovered ? Color.FromArgb(255, 120, 70) : Int0Theme.AccentOrange;
                    text = Color.White;
                }
                else if (_variant == Int0ButtonVariant.Success)
                {
                    bg = _isPressed ? Color.FromArgb(10, 140, 95) : (_isHovered ? Color.FromArgb(20, 205, 145) : Int0Theme.AccentEmerald);
                    border = bg;
                    text = Color.White;
                }
                else if (_variant == Int0ButtonVariant.Danger)
                {
                    bg = _isPressed ? Color.FromArgb(180, 40, 40) : (_isHovered ? Int0Theme.AccentCrimson : Int0Theme.Surface);
                    border = Int0Theme.AccentCrimson;
                    text = _isHovered ? Color.White : Int0Theme.AccentCrimson;
                }
                else // Secondary
                {
                    bg = _isPressed ? Int0Theme.SurfaceElevated : (_isHovered ? Color.FromArgb(26, 30, 39) : Int0Theme.Surface);
                    border = _isHovered ? Int0Theme.AccentCyan : Int0Theme.Border;
                    text = _isHovered ? Color.White : Int0Theme.TextSecondary;
                }

                using (var b = new SolidBrush(bg))
                {
                    g.FillPath(b, path);
                }
                using (var p = new Pen(border, 1f))
                {
                    g.DrawPath(p, path);
                }

                TextRenderer.DrawText(g, Text, Font, bounds, text,
                    TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis);
            }
        }
    }

    public class Int0InputGroup : Panel
    {
        private TextBox _innerBox;
        private Label _label;
        private bool _isFocused = false;

        public string LabelText
        {
            get { return _label.Text; }
            set { _label.Text = value; }
        }

        public string Value
        {
            get { return _innerBox.Text; }
            set { _innerBox.Text = value; }
        }

        public TextBox InnerTextBox
        {
            get { return _innerBox; }
        }

        public Int0InputGroup(string label, string defaultValue, bool isMonospace)
        {
            Height = 28;
            BackColor = Int0Theme.Canvas;
            DoubleBuffered = true;

            _label = new Label();
            _label.Text = label;
            _label.ForeColor = Int0Theme.TextMuted;
            _label.Font = Int0Theme.GetSansFont(8.5F);
            _label.Location = new Point(0, 5);
            _label.AutoSize = true;
            Controls.Add(_label);

            _innerBox = new TextBox();
            _innerBox.Text = defaultValue;
            _innerBox.BackColor = Int0Theme.Surface;
            _innerBox.ForeColor = Int0Theme.TextPrimary;
            _innerBox.BorderStyle = BorderStyle.None;
            _innerBox.Font = isMonospace ? Int0Theme.GetMonoFont(9F) : Int0Theme.GetSansFont(9F);

            _innerBox.GotFocus += delegate { _isFocused = true; Invalidate(); };
            _innerBox.LostFocus += delegate { _isFocused = false; Invalidate(); };

            Controls.Add(_innerBox);
        }

        public Int0InputGroup(string label, string defaultValue)
            : this(label, defaultValue, false)
        {
        }

        public Int0InputGroup(string label)
            : this(label, "", false)
        {
        }

        public void SetupLayout(int labelWidth, int inputWidth)
        {
            _label.Width = labelWidth;
            _innerBox.Location = new Point(labelWidth + 8, 5);
            _innerBox.Width = inputWidth;
            Width = labelWidth + inputWidth + 16;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            var g = e.Graphics;
            var boxRect = new Rectangle(_innerBox.Left - 4, 1, _innerBox.Width + 8, Height - 2);

            using (var b = new SolidBrush(Int0Theme.Surface))
            {
                g.FillRectangle(b, boxRect);
            }

            Color borderColor = _isFocused ? Int0Theme.AccentCyan : Int0Theme.Border;
            using (var p = new Pen(borderColor, 1f))
            {
                g.DrawRectangle(p, boxRect);
            }
        }
    }

    public class Int0ConsoleBox : UserControl
    {
        private RichTextBox _rtb;

        public Int0ConsoleBox()
        {
            SetStyle(ControlStyles.DoubleBuffer | ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint, true);
            Padding = new Padding(2);
            BackColor = Int0Theme.Border;

            _rtb = new RichTextBox();
            _rtb.Dock = DockStyle.Fill;
            _rtb.BackColor = Int0Theme.ConsoleBg;
            _rtb.ForeColor = Int0Theme.TextSecondary;
            _rtb.BorderStyle = BorderStyle.None;
            _rtb.ReadOnly = true;
            _rtb.Font = Int0Theme.GetMonoFont(8.5F);
            _rtb.ScrollBars = RichTextBoxScrollBars.Vertical;
            Controls.Add(_rtb);
        }

        public void ClearLog()
        {
            if (_rtb.InvokeRequired)
            {
                _rtb.Invoke(new Action(ClearLog));
                return;
            }
            _rtb.Clear();
        }

        public void AppendLog(string line)
        {
            if (_rtb.InvokeRequired)
            {
                _rtb.Invoke(new Action<string>(AppendLog), line);
                return;
            }

            Color c = Int0Theme.TextSecondary;
            if (line.StartsWith("[+]")) c = Int0Theme.AccentEmerald;
            else if (line.StartsWith("[*]")) c = Int0Theme.AccentCyan;
            else if (line.StartsWith("[!]")) c = Int0Theme.AccentAmber;
            else if (line.StartsWith("[-]")) c = Int0Theme.AccentCrimson;
            else if (line.Contains("成功") || line.Contains("OK") || line.Contains("PASS")) c = Int0Theme.AccentEmerald;
            else if (line.Contains("失败") || line.Contains("FAIL") || line.Contains("ERR")) c = Int0Theme.AccentCrimson;

            _rtb.SelectionStart = _rtb.TextLength;
            _rtb.SelectionLength = 0;
            _rtb.SelectionColor = c;
            _rtb.AppendText(line + Environment.NewLine);
            _rtb.SelectionColor = _rtb.ForeColor;
            _rtb.ScrollToCaret();
        }

        public string AllText
        {
            get { return _rtb.Text; }
        }
    }

    public class Int0Header : Panel
    {
        private string _title = "INT0 RESEARCH WORKSTATION";
        private string _versionTag = "v1.1.0";
        private string _subtitle = "ONE-CLICK ATOMIC IN-PLACE ACTIVATION SUITE";

        public string Title
        {
            get { return _title; }
            set { _title = value; Invalidate(); }
        }

        public string VersionTag
        {
            get { return _versionTag; }
            set { _versionTag = value; Invalidate(); }
        }

        public string Subtitle
        {
            get { return _subtitle; }
            set { _subtitle = value; Invalidate(); }
        }

        public Int0Header()
        {
            Height = 64;
            Dock = DockStyle.Top;
            BackColor = Int0Theme.Canvas;
            DoubleBuffered = true;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;

            // Brand glyph box
            var iconBox = new Rectangle(12, 12, 40, 40);
            using (var b = new SolidBrush(Int0Theme.Surface))
            {
                g.FillRectangle(b, iconBox);
            }
            using (var p = new Pen(Int0Theme.Border, 1))
            {
                g.DrawRectangle(p, iconBox);
            }
            using (var f = Int0Theme.GetMonoFont(10F, FontStyle.Bold))
            {
                TextRenderer.DrawText(g, "INT0", f, iconBox, Int0Theme.AccentOrange,
                    TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
            }

            // Title & Subtitle
            int textLeft = 60;
            using (var fTitle = Int0Theme.GetMonoFont(11F, FontStyle.Bold))
            {
                TextRenderer.DrawText(g, _title, fTitle, new Point(textLeft, 14), Int0Theme.TextPrimary);
            }
            using (var fSub = Int0Theme.GetMonoFont(8F, FontStyle.Regular))
            {
                TextRenderer.DrawText(g, _subtitle, fSub, new Point(textLeft, 34), Int0Theme.TextMuted);
            }

            // Version Pill on right
            int right = Width - 14;
            string pillText = _versionTag + " // VERIFIED";
            using (var fPill = Int0Theme.GetMonoFont(8F, FontStyle.Bold))
            {
                var sz = TextRenderer.MeasureText(pillText, fPill);
                var pillRect = new Rectangle(right - sz.Width - 16, 20, sz.Width + 16, 22);
                using (var path = Int0Theme.CreateRoundedRectangle(pillRect, 11))
                {
                    using (var b = new SolidBrush(Int0Theme.Surface)) g.FillPath(b, path);
                    using (var p = new Pen(Int0Theme.BorderSubtle, 1)) g.DrawPath(p, path);
                }
                // Little green dot
                using (var bGreen = new SolidBrush(Int0Theme.AccentEmerald))
                {
                    g.FillEllipse(bGreen, pillRect.X + 8, pillRect.Y + 7, 7, 7);
                }
                TextRenderer.DrawText(g, pillText, fPill, new Point(pillRect.X + 18, pillRect.Y + 3), Int0Theme.AccentEmerald);
            }

            // Bottom 1px divider
            using (var p = new Pen(Int0Theme.Border, 1))
            {
                g.DrawLine(p, 0, Height - 1, Width, Height - 1);
            }
        }
    }
}
