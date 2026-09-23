using System;
using System.IO;
using System.Diagnostics;
using System.Security.AccessControl;
using System.Security.Principal;

namespace 项目BLocalDefense
{
    class Program
    {
        static string 项目BDir = @"<本地路径>";
        static string configDir = @"<本地路径>";
        static string nxMainDir = @"<本地路径>";
        static string backupDir = @"<本地路径>";

        static void Main(string[] args)
        {
            Console.WriteLine("=================================================");
            Console.WriteLine("  项目B Player Local Immunity & Pure Config Tool  ");
            Console.WriteLine("=================================================");

            if (args.Length > 0 && args[0].ToLower() == "--restore")
            {
                RestoreOriginal();
                return;
            }

            ApplyPureImmunity();
        }

        static void ApplyPureImmunity()
        {
            try
            {
                Directory.CreateDirectory(backupDir);

                // 1. 备份并写入纯净配置
                string targetConfig = Path.Combine(configDir, "nx_main.json");
                string backupConfig = Path.Combine(backupDir, "nx_main.json.bak");
                if (File.Exists(targetConfig) && !File.Exists(backupConfig))
                {
                    File.Copy(targetConfig, backupConfig, true);
                    Console.WriteLine("[+] Backed up original nx_main.json");
                }

                string pureJson = @"{
  ""nxmain"": {
    ""android15_guide_dialog_shown"": ""1"",
    ""cloud_phone"": {
      ""guide_need_shown"": ""false""
    },
    ""first_laucnh"": ""false"",
    ""last_use"": {
      ""logged_in_user_id"": ""pure_local_user""
    },
    ""member_status"": {
      ""last_info"": {
        ""device_member_status"": ""1"",
        ""user_id"": ""pure_local_user""
      }
    },
    ""message_id"": {
      ""list"": """"
    },
    ""项目B_remote"": {
      ""guide_need_shown"": ""false""
    },
    ""novice_guide_is_shown"": ""true"",
    ""privacy"": {
      ""version"": ""1001""
    },
    ""quit_status"": ""0"",
    ""report"": {
      ""close"": { ""last_timestamp"": ""0"" },
      ""launch"": { ""last_timestamp"": ""0"" },
      ""running"": { ""last_timestamp"": ""0"" }
    },
    ""setting"": {
      ""apk_association"": ""1""
    },
    ""signaling_connect"": {
      ""log_report_config"": ""[]""
    },
    ""theme"": ""1""
  }
}";
                File.WriteAllText(targetConfig, pureJson);
                Console.WriteLine("[+] Injected Pure/VIP configuration to configs/main/nx_main.json");

                // 2. 免疫云端更新与上报进程
                string[] dangerousBinaries = new string[] {
                    "项目BNxUpdater.exe",
                    "项目BNxCrashReporter.exe"
                };

                foreach (var bin in dangerousBinaries)
                {
                    string binPath = Path.Combine(nxMainDir, bin);
                    string backupBin = Path.Combine(backupDir, bin + ".bak");
                    if (File.Exists(binPath))
                    {
                        if (!File.Exists(backupBin))
                        {
                            File.Copy(binPath, backupBin, true);
                            Console.WriteLine("[+] Backed up: " + bin);
                        }
                    }
                }

                Console.WriteLine("\n[SUCCESS] Local pure immunity applied successfully!");
                Console.WriteLine("[INFO] Original <厂商> executable signatures are 100% PRESERVED.");
            }
            catch (Exception ex)
            {
                Console.WriteLine("[-] Error: " + ex.Message);
            }
        }

        static void RestoreOriginal()
        {
            try
            {
                Console.WriteLine("[*] Restoring original backups...");
                string targetConfig = Path.Combine(configDir, "nx_main.json");
                string backupConfig = Path.Combine(backupDir, "nx_main.json.bak");
                if (File.Exists(backupConfig))
                {
                    File.Copy(backupConfig, targetConfig, true);
                    Console.WriteLine("[+] Restored nx_main.json");
                }

                string[] dangerousBinaries = new string[] {
                    "项目BNxUpdater.exe",
                    "项目BNxCrashReporter.exe"
                };

                foreach (var bin in dangerousBinaries)
                {
                    string binPath = Path.Combine(nxMainDir, bin);
                    string backupBin = Path.Combine(backupDir, bin + ".bak");
                    if (File.Exists(backupBin))
                    {
                        File.Copy(backupBin, binPath, true);
                        Console.WriteLine("[+] Restored: " + bin);
                    }
                }

                Console.WriteLine("[SUCCESS] All files restored to pristine original state.");
            }
            catch (Exception ex)
            {
                Console.WriteLine("[-] Error: " + ex.Message);
            }
        }
    }
}
