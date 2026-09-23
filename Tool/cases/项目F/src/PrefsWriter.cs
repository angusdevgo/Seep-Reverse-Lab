// PrefsWriter - 将激活配置写入 项目F Preferences.json（独立于 UI，可单测）
// 目标文件: %APPDATA%\项目F\UserProfile\Settings\Preferences.json
// 结构: 顶层对象含 "Settings" 子对象，内部为点分键 -> 值：
//   "项目F5.ProLicense.Name" / ".Email" / ".Key"
// 写入流程: 备份 -> 全量 JSON 解析 -> 更新 Settings 三键 -> 写回 -> 复读校验
// 依赖: System.Web.Extensions.dll (JavaScriptSerializer, .NET Framework 内置)
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;

namespace 项目FLicense
{
    public static class PrefsWriter
    {
        public const string KEY_NAME = "项目F5.ProLicense.Name";
        public const string KEY_EMAIL = "项目F5.ProLicense.Email";
        public const string KEY_LICENSE = "项目F5.ProLicense.Key";
        // disguised JSON key: property LastProCheckFailDate (Pro online-check failure date)
        // stored under the name "LastUpdateTimeV1" - used by ScheduleAutoCheck to clear
        // the license after 7 days of failed online checks. We reset it on every write.
        public const string KEY_FAILDATE = "LastUpdateTimeV1";
        public const string BACKUP_SUFFIX = ".bak";

        public static string DefaultPath()
        {
            string appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            return Path.Combine(appData, "项目F", "UserProfile", "Settings", "Preferences.json");
        }

        // returns true on success; log receives step-by-step messages
        public static bool Write(string path, string name, string email, string license,
                                 StringBuilder log, out string error)
        {
            error = null;
            try
            {
                string dir = Path.GetDirectoryName(path);
                if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);

                Dictionary<string, object> root;
                if (File.Exists(path))
                {
                    string json = File.ReadAllText(path, Encoding.UTF8);
                    if (string.IsNullOrWhiteSpace(json))
                        throw new InvalidDataException("配置文件为空");
                    var ser = new JavaScriptSerializer();
                    object obj = ser.DeserializeObject(json);
                    root = obj as Dictionary<string, object>;
                    if (root == null)
                        throw new InvalidDataException("配置文件不是 JSON 对象，拒绝覆盖");
                    log.AppendLine("[1/5] 已读取现有配置: " + path + " (" + json.Length + " 字节)");
                }
                else
                {
                    root = new Dictionary<string, object>();
                    log.AppendLine("[1/5] 配置文件不存在，将新建: " + path);
                }

                // backup
                string bak = path + BACKUP_SUFFIX;
                if (File.Exists(path))
                {
                    File.Copy(path, bak, true);
                    log.AppendLine("[2/5] 已备份原配置 -> " + bak);
                }
                else
                {
                    log.AppendLine("[2/5] 无原文件，跳过备份");
                }

                // update Settings keys
                object settingsObj;
                Dictionary<string, object> settings;
                if (root.TryGetValue("Settings", out settingsObj))
                    settings = settingsObj as Dictionary<string, object>;
                else
                    settings = null;
                if (settings == null)
                {
                    settings = new Dictionary<string, object>();
                    root["Settings"] = settings;
                }
                settings[KEY_NAME] = name;
                settings[KEY_EMAIL] = email;
                settings[KEY_LICENSE] = license;
                // reset the online-check failure date so the 7-day countdown never starts
                // (ProService.ScheduleAutoCheck clears the three keys once now - failDate > 7d)
                settings[KEY_FAILDATE] = "0001-01-01T00:00:00";
                log.AppendLine("[3/5] 已写入 " + KEY_NAME + " / " + KEY_EMAIL + " / " + KEY_LICENSE);
                log.AppendLine("      并重置在线校验失败计时（" + KEY_FAILDATE + " -> MinValue）");

                // serialize & write back (UTF-8 no BOM, keep other settings intact)
                var writer = new JavaScriptSerializer();
                string outJson = writer.Serialize(root);
                File.WriteAllText(path, outJson, new UTF8Encoding(false));
                log.AppendLine("[4/5] 已写回 " + path + " (" + outJson.Length + " 字节)");

                // re-read & verify
                string check = File.ReadAllText(path, Encoding.UTF8);
                var checkSer = new JavaScriptSerializer();
                Dictionary<string, object> checkRoot = checkSer.DeserializeObject(check) as Dictionary<string, object>;
                if (checkRoot == null)
                    throw new InvalidDataException("写回后重读失败：不是 JSON 对象");
                Dictionary<string, object> checkSet = checkRoot["Settings"] as Dictionary<string, object>;
                if (checkSet == null)
                    throw new InvalidDataException("写回后重读失败：Settings 缺失");
                bool ok = true;
                ok &= (string)checkSet[KEY_NAME] == name;
                ok &= (string)checkSet[KEY_EMAIL] == email;
                ok &= (string)checkSet[KEY_LICENSE] == license;
                if (!ok)
                    throw new InvalidDataException("写回校验不一致，请检查文件");
                log.AppendLine("[5/5] 复读校验通过：三个字段已就位");
                return true;
            }
            catch (Exception ex)
            {
                error = ex.Message;
                log.AppendLine("[失败] " + ex.Message);
                return false;
            }
        }

        // returns (name, email, license) currently stored, or nulls
        public static string[] Read(string path)
        {
            string[] result = new string[3];
            if (!File.Exists(path)) return result;
            try
            {
                string json = File.ReadAllText(path, Encoding.UTF8);
                var ser = new JavaScriptSerializer();
                Dictionary<string, object> root = ser.DeserializeObject(json) as Dictionary<string, object>;
                if (root == null) return result;
                Dictionary<string, object> settings = root["Settings"] as Dictionary<string, object>;
                if (settings == null) return result;
                result[0] = settings.ContainsKey(KEY_NAME) ? (string)settings[KEY_NAME] : null;
                result[1] = settings.ContainsKey(KEY_EMAIL) ? (string)settings[KEY_EMAIL] : null;
                result[2] = settings.ContainsKey(KEY_LICENSE) ? (string)settings[KEY_LICENSE] : null;
            }
            catch { /* ignore */ }
            return result;
        }
    }
}
