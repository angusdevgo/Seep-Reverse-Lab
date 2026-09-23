// Machine code collectors: disk serial (A) and SMBIOS UUID (B).
// Mirrors FUN_180001a90 / FUN_180001b9c; on failure returns the same
// fallback literals the target uses ("xxxx xxxx" / "yyyy yyyy") so that the
// request string matches what 项目I would send on this machine.
using System;
using System.Management;
using System.Text;

namespace SabLicense
{
    public static class MachineCode
    {
        public static string DiskSerial()
        {
            try
            {
                // system drive letter -> Win32_DiskDrive index via partition association
                string sysDrive = Environment.GetFolderPath(Environment.SpecialFolder.System); // C:\Windows\system32
                string driveLetter = sysDrive.Substring(0, 2);
                using (var searcher = new ManagementObjectSearcher(
                    "ASSOCIATORS OF {Win32_LogicalDisk.DeviceID='" + driveLetter + "'} " +
                    "WHERE AssocClass = Win32_LogicalDiskToPartition"))
                {
                    foreach (ManagementObject part in searcher.Get())
                    {
                        using (var diskSearcher = new ManagementObjectSearcher(
                            "ASSOCIATORS OF {Win32_DiskPartition.DeviceID='" +
                            part["DeviceID"].ToString() + "'} " +
                            "WHERE AssocClass = Win32_DiskDriveToDiskPartition"))
                        {
                            foreach (ManagementObject disk in diskSearcher.Get())
                            {
                                string sn = Convert.ToString(disk["SerialNumber"]);
                                if (!string.IsNullOrWhiteSpace(sn))
                                    return Clean(sn);
                            }
                        }
                    }
                }
            }
            catch (Exception)
            {
                // fall through
            }
            return LicenseAlgo.DEFAULT_DISK_SN;
        }

        public static string SmbiosUuid()
        {
            try
            {
                using (var searcher = new ManagementObjectSearcher(
                    "SELECT UUID FROM Win32_ComputerSystemProduct"))
                {
                    foreach (ManagementObject o in searcher.Get())
                    {
                        string uuid = Convert.ToString(o["UUID"]);
                        if (!string.IsNullOrWhiteSpace(uuid) && uuid != "00000000-0000-0000-0000-000000000000")
                            return uuid.Trim();
                    }
                }
            }
            catch (Exception)
            {
                // fall through
            }
            return LicenseAlgo.DEFAULT_SMBIOS_UUID;
        }

        // ATA word-swap heuristic: the target swaps byte pairs of IDENTIFY DEVICE
        // words 10-19; WMI usually reports the already-swapped serial, so keep as-is
        // but trim. FUN_18001fac8/FUN_18001fc2c equivalent handling.
        private static string Clean(string s)
        {
            var sb = new StringBuilder();
            foreach (char c in s.Trim())
            {
                if (char.IsLetterOrDigit(c)) sb.Append(c);
                else if (c == ' ' && sb.Length > 0) break;
            }
            return sb.Length > 0 ? sb.ToString() : LicenseAlgo.DEFAULT_DISK_SN;
        }

        public static string RequestHex(string keyText)
        {
            string lh = LicenseAlgo.LicenseHash(keyText);
            return LicenseAlgo.ExpectedRequest(lh, DiskSerial(), SmbiosUuid());
        }
    }
}
