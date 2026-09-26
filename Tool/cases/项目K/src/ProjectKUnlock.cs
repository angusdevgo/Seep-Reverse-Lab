using System;
using System.IO;
using System.Management;
using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using Microsoft.Win32;

/// <summary>
/// 项目K 客户端鉴权旁路 + 云控剥离 PoC (AppDomainManager 注入)
///
/// 1) 本地许可伪造：由机器码派生 AES-128-CBC 密钥，写入永久授权载荷
/// 2) 云控剥离：精准拦截 <vendor-domain>，阻断在线复核回写
/// 3) 内存锁：看门狗线程持续锁定 App.Days = 63282（永久授权阈值 >= 29200）
/// </summary>
public class Manager : AppDomainManager
{
    const string LOGPATH = @"D:\Data\Allen\ProjectKUnlock.log";
    // 盐值为目标程序内 19 字符硬编码常量，已按脱敏规范屏蔽；
    // 完整值仅保留在本地私有报告，替换为真实值后本 PoC 即可直接运行。
    const string SALT = "<REDACTED_SALT>";
    // 目标主程序集名（脱敏占位，替换为真实值即可运行）
    const string TARGET_ASM = "<TargetAssembly>";
    const string EXPIRE = "2199-12-31";
    const string EMAIL = "unlock@local";
    const int PERMANENT_DAYS = 63282;      // >= 29200 => 永久授权版
    const string CLOUD_HOST = "<vendor-domain>";
    const string DEAD_PROXY = "http://127.0.0.1:9";

    static string _jqm;
    static string _b64;
    static string _regSub;
    static string _filePath;
    static Assembly _target;
    static FieldInfo _daysField;
    static volatile bool _ready;

    static void Log(string s)
    {
        try
        {
            lock (typeof(Manager))
                File.AppendAllText(LOGPATH, DateTime.Now.ToString("HH:mm:ss.fff") + "  " + s + "\r\n");
        }
        catch { }
    }

    public override void InitializeNewDomain(AppDomainSetup appDomainInfo)
    {
        Log("================ ProjectKUnlock loaded ================");
        try { CloudControlKill(); } catch (Exception e) { Log("cloud err " + e.Message); }
        try { ForgeLicense(); } catch (Exception e) { Log("forge err " + e.Message); }
        Thread t = new Thread(Watchdog);
        t.IsBackground = true;
        t.Start();
        base.InitializeNewDomain(appDomainInfo);
    }

    // ------------------------------------------------------------------
    // 1) 云控剥离：只拦截 <vendor-domain>，其余流量直连
    // ------------------------------------------------------------------
    sealed class CloudBlockProxy : IWebProxy
    {
        public ICredentials Credentials { get; set; }
        public bool IsBypassed(Uri host)
        {
            if (host == null) return true;
            string h = host.Host.ToLowerInvariant();
            if (h.Contains(CLOUD_HOST)) return false;   // 走死代理 -> 连接失败
            return true;                                 // 其余直连
        }
        public Uri GetProxy(Uri dest)
        {
            return new Uri(DEAD_PROXY);
        }
    }

    static void CloudControlKill()
    {
        WebRequest.DefaultWebProxy = new CloudBlockProxy();
        WebRequest.DefaultWebProxy.Credentials = CredentialCache.DefaultCredentials;
        Log("cloud control blocked -> " + CLOUD_HOST + " routed to " + DEAD_PROXY);
    }

    // ------------------------------------------------------------------
    // 2) 机器码 / 密钥派生 / 许可伪造
    // ------------------------------------------------------------------
    static string Wmi(string wql, string prop)
    {
        try
        {
            using (ManagementObjectSearcher s = new ManagementObjectSearcher(wql))
            using (ManagementObjectCollection c = s.Get())
                foreach (ManagementObject o in c)
                {
                    object v = o[prop];
                    if (v != null) return v.ToString();
                }
        }
        catch (Exception e) { Log("wmi err " + e.Message); }
        return "";
    }

    static string Md5Jqm(string raw)
    {
        byte[] h;
        using (MD5 md5 = MD5.Create())
            h = md5.ComputeHash(Encoding.ASCII.GetBytes(raw));
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < h.Length; i++)
        {
            int hi = (h[i] >> 4) & 0xF, lo = h[i] & 0xF;
            sb.Append((char)(hi <= 9 ? '0' + hi : 'A' + hi - 10));
            sb.Append((char)(lo <= 9 ? '0' + lo : 'A' + lo - 10));
            if ((i + 1) != h.Length && (i + 1) % 2 == 0) sb.Append('-');
        }
        return sb.ToString();
    }

    static string GetMachineCode()
    {
        // 首选：与目标程序完全一致的 WMI 组合
        string board = Wmi("SELECT SerialNumber FROM Win32_BaseBoard", "SerialNumber");
        string cpu = Wmi("SELECT ProcessorID FROM Win32_Processor", "ProcessorID");
        if (!string.IsNullOrEmpty(board) && !string.IsNullOrEmpty(cpu))
        {
            string jqm = Md5Jqm(board + SALT + cpu);
            Log("machine code (wmi) = " + jqm);
            return jqm;
        }
        // 兜底：从既有许可文件名反推
        try
        {
            string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                                      @"Microsoft\Crypto\Keys");
            if (Directory.Exists(dir))
                foreach (string f in Directory.GetFiles(dir))
                {
                    string n = Path.GetFileNameWithoutExtension(f);
                    if (n.Length == 32 && IsHex(n))
                    {
                        string up = n.ToUpperInvariant();
                        StringBuilder sb = new StringBuilder();
                        for (int i = 0; i < up.Length; i++)
                        {
                            if (i > 0 && i % 4 == 0) sb.Append('-');
                            sb.Append(up[i]);
                        }
                        Log("machine code (file) = " + sb);
                        return sb.ToString();
                    }
                }
        }
        catch (Exception e) { Log("jqm fallback err " + e.Message); }
        return null;
    }

    static bool IsHex(string s)
    {
        foreach (char c in s)
            if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) return false;
        return true;
    }

    static string[] DeriveKeyIv(string jqm)
    {
        string t = jqm.Replace("-", "");
        string a = t.Substring(0, 1);
        string b = t.Substring(1, 6);
        string c = t.Substring(7, 7);
        string d = t.Substring(14, 2);
        string e = t.Substring(16, 4);
        string f = t.Substring(20, 3);
        string g = t.Substring(23, 4);
        string h = t.Substring(27, 5);
        return new string[] { f + g + h + e, a + c + d + b };  // Key, IV
    }

    static string AesEncrypt(string plain, string key, string iv)
    {
        using (RijndaelManaged rm = new RijndaelManaged())
        {
            rm.Key = Encoding.UTF8.GetBytes(key);
            rm.IV = Encoding.UTF8.GetBytes(iv);
            rm.Mode = CipherMode.CBC;
            rm.Padding = PaddingMode.PKCS7;
            byte[] data = Encoding.UTF8.GetBytes(plain);
            using (ICryptoTransform enc = rm.CreateEncryptor())
                return Convert.ToBase64String(enc.TransformFinalBlock(data, 0, data.Length));
        }
    }

    static string AesDecrypt(string b64, string key, string iv)
    {
        try
        {
            using (RijndaelManaged rm = new RijndaelManaged())
            {
                rm.Key = Encoding.UTF8.GetBytes(key);
                rm.IV = Encoding.UTF8.GetBytes(iv);
                rm.Mode = CipherMode.CBC;
                rm.Padding = PaddingMode.PKCS7;
                byte[] data = Convert.FromBase64String(b64);
                using (ICryptoTransform dec = rm.CreateDecryptor())
                    return Encoding.UTF8.GetString(dec.TransformFinalBlock(data, 0, data.Length));
            }
        }
        catch { return null; }
    }

    static string RegSubName(string jqm)
    {
        StringBuilder sb = new StringBuilder();
        foreach (char c in jqm.Replace("-", ""))
            if (!char.IsDigit(c)) sb.Append(c);
        string s = sb.ToString();
        if (s.Length >= 3) return s.Substring(0, 3);
        return jqm.EndsWith("-EN") ? "LEN" : "LLA";
    }

    static void ForgeLicense()
    {
        _jqm = GetMachineCode();
        if (_jqm == null) { Log("machine code unavailable -> abort forge"); return; }

        string[] kv = DeriveKeyIv(_jqm);
        string payload = _jqm + "\t" + EXPIRE + "\t" + EMAIL;
        _b64 = AesEncrypt(payload, kv[0], kv[1]);

        _regSub = "SOFTWARE\\Microsoft\\" + RegSubName(_jqm);
        _filePath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                                 @"Microsoft\Crypto\Keys", _jqm.Replace("-", "").ToLowerInvariant());

        WriteLicense(_b64);
        Log("license forged: " + payload.Replace("\t", " | "));
        Log("  Key=" + kv[0] + "  IV=" + kv[1]);
        Log("  reg=" + _regSub + "  file=" + _filePath);
        _ready = true;
    }

    static void WriteLicense(string b64)
    {
        try
        {
            using (RegistryKey k = Registry.CurrentUser.CreateSubKey(_regSub))
                k.SetValue("Configuration", b64, RegistryValueKind.String);
        }
        catch (Exception e) { Log("reg write err " + e.Message); }

        try
        {
            string dir = Path.GetDirectoryName(_filePath);
            if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
            if (File.Exists(_filePath)) { File.SetAttributes(_filePath, FileAttributes.Normal); File.Delete(_filePath); }
            File.WriteAllText(_filePath, b64);
            File.SetAttributes(_filePath, FileAttributes.Hidden);
            // 伪造时间戳，与 %APPDATA% 目录创建时间对齐（规避原厂的时间线一致性检查）
            DateTime t = Directory.GetCreationTime(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData));
            File.SetCreationTime(_filePath, t);
            File.SetLastWriteTime(_filePath, t);
            File.SetLastAccessTime(_filePath, t);
        }
        catch (Exception e) { Log("file write err " + e.Message); }
    }

    // ------------------------------------------------------------------
    // 3) 看门狗：锁定 App.Days + 复查许可，云控无法翻盘
    // ------------------------------------------------------------------
    static void Watchdog()
    {
        int ticks = 0;
        for (int i = 0; i < 100000; i++)
        {
            try
            {
                if (_target == null)
                {
                    foreach (Assembly a in AppDomain.CurrentDomain.GetAssemblies())
                        if (a.GetName().Name == TARGET_ASM) { _target = a; break; }
                    if (_target != null)
                    {
                        _daysField = _target.GetType(TARGET_ASM + ".App")
                                            .GetField("Days", BindingFlags.Public | BindingFlags.Static);
                        Log("hooked App.Days field = " + (_daysField != null ? "OK" : "MISSING"));
                    }
                }

                if (_target != null && _daysField != null)
                {
                    object cur = _daysField.GetValue(null);
                    int ci = (cur is int) ? (int)cur : int.MinValue;
                    if (ci != PERMANENT_DAYS)
                    {
                        _daysField.SetValue(null, PERMANENT_DAYS);
                        Log("App.Days " + ci + " -> " + PERMANENT_DAYS + " (re-asserted)");
                    }
                }

                // 每 5 秒校验一次磁盘许可，被云控改写则立即复原
                ticks++;
                if (_ready && (ticks % 5) == 0)
                {
                    string[] kv = DeriveKeyIv(_jqm);
                    string onDisk = null;
                    try
                    {
                        using (RegistryKey k = Registry.CurrentUser.OpenSubKey(_regSub))
                            if (k != null) onDisk = k.GetValue("Configuration") as string;
                    }
                    catch { }
                    string plain = onDisk != null ? AesDecrypt(onDisk, kv[0], kv[1]) : null;
                    if (plain == null || plain.IndexOf(EXPIRE) < 0)
                    {
                        Log("license tampered (cloud rollback) -> restoring");
                        WriteLicense(_b64);
                    }
                }
            }
            catch { }
            Thread.Sleep(1000);
        }
    }
}
