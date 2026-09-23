// 项目F Pro license algorithm (reversed from 项目F.Core.Pro.LicenseChecker)
// C# 5 / .NET Framework 4.x compatible. Shared by 项目FKeyGen / 项目FKeyFill.
// CheckLicense(email, license):
//   1. email/license non-null, len(license)==192
//   2. email = email.ToLowerInvariant()
//   3. v = (h1<<64)|(h2<<32)|h3  (96 bits)
//   4. for i in 0..18: result += charset[(v >> (96-(i+1)*5)) & 31]
//   5. license[160:179] must equal result
//   6. md5hex(email + salt) must not be in blacklist
using System;
using System.Collections.Generic;
using System.Numerics;
using System.Security.Cryptography;
using System.Text;

namespace 项目FLicense
{
    public static class LicenseAlgo
    {
        public const string CHARSET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"; // 32 chars, no 0/1/I/O
        public const string SALT = "项目Fl047YpyZUU5M";
        public const int LICENSE_LEN = 192;
        public const int CHECK_POS = 160;
        public const int CHECK_LEN = 19;

        // blacklist hashes from LicenseChecker (v6 4 known + v7 decoded #5/#6)
        public static readonly HashSet<string> Blacklist = new HashSet<string>(StringComparer.Ordinal)
        {
            "710ab287938947d40d8d5857f663753c",
            "c109e3ee2bd74d5b88de647eebc2fd0e",
            "1229667d8ecc0616bffd7740c4323f9a",
            "b05744004c455956e5408a9b1c95b047",
            "57a39722f37db4727e0f425156f3b2d7",
            "0c16a79693d8d58e1e5b81f48f9ba64b",
        };

        // debug helpers: expose internal hash values (for cross-checking)
        public static string DebugH1(string s) { return H1(s).ToString("X8"); }
        public static string DebugH2(string s) { return H2(s).ToString("X8"); }
        public static string DebugH3(string s) { return H3(s).ToString("X8"); }

        // h1: h = h*43 + c  (uint32 overflow)
        static uint H1(string s)
        {
            uint h = 0;
            for (int i = 0; i < s.Length; i++)
                h = h * 43 + (uint)s[i];
            return h;
        }

        // h2: ELF-style h=(h<<4)+c; g=h&0xF0000000; if(g!=0){h^=g>>24; h^=g}
        static uint H2(string s)
        {
            uint h = 0;
            for (int i = 0; i < s.Length; i++)
            {
                h = (h << 4) + (uint)s[i];
                uint g = h & 0xF0000000u;
                if (g != 0)
                {
                    h ^= (g >> 24);
                    h ^= g;
                }
            }
            return h;
        }

        // h3: 4 rounds: h ^= s[j] << ((r*8)%32), j = r, r+4, r+8, ...
        static uint H3(string s)
        {
            uint h = 0;
            for (int r = 0; r < 4; r++)
            {
                for (int j = r; j < s.Length; j += 4)
                    h ^= ((uint)s[j]) << ((r * 8) % 32);
            }
            return h;
        }

        // 96-bit value: H1 in bits [64,96), H2 in [32,64), H3 in [0,32).
        // NOTE: ulong is only 64 bits and shift counts are masked (<<64 == <<0),
        // so a plain ulong CANNOT hold the 96-bit value - use BigInteger.
        static BigInteger BuildV(string emailLower)
        {
            return ((BigInteger)H1(emailLower) << 64)
                 | ((BigInteger)H2(emailLower) << 32)
                 | (BigInteger)H3(emailLower);
        }

        public static string Checksum(string emailLower)
        {
            string el = emailLower.ToLowerInvariant().Trim();
            BigInteger v = BuildV(el);
            StringBuilder sb = new StringBuilder(CHECK_LEN);
            for (int i = 0; i < CHECK_LEN; i++)
            {
                int shift = 96 - (i + 1) * 5;
                sb.Append(CHARSET[(int)((v >> shift) & 31)]);
            }
            return sb.ToString();
        }

        // shared RNG: .NET Random() seeds from tick count, rapid consecutive
        // new Random() instances yield identical sequences -> use one shared instance
        private static readonly Random _sharedRnd = new Random();

        public static string Generate(string email)
        {
            if (email == null) throw new ArgumentNullException("email");
            string el = email.ToLowerInvariant().Trim();
            if (el.Length == 0) throw new ArgumentException("email is empty");
            string ck = Checksum(el);
            StringBuilder sb = new StringBuilder(LICENSE_LEN);
            lock (_sharedRnd)
            {
                for (int i = 0; i < CHECK_POS; i++) sb.Append(CHARSET[_sharedRnd.Next(CHARSET.Length)]);
                sb.Append(ck);
                for (int i = 0; i < LICENSE_LEN - CHECK_POS - CHECK_LEN; i++) sb.Append(CHARSET[_sharedRnd.Next(CHARSET.Length)]);
            }
            return sb.ToString();
        }

        public static bool Verify(string email, string license)
        {
            if (email == null || license == null) return false;
            if (license.Length != LICENSE_LEN) return false;
            string el = email.ToLowerInvariant().Trim();
            if (el.Length == 0) return false;
            if (license.Substring(CHECK_POS, CHECK_LEN) != Checksum(el)) return false;
            string h = MD5Hex(el + SALT);
            if (Blacklist.Contains(h)) return false;
            return true;
        }

        public static string MD5Hex(string s)
        {
            using (MD5 md5 = MD5.Create())
            {
                byte[] bytes = md5.ComputeHash(Encoding.UTF8.GetBytes(s));
                StringBuilder sb = new StringBuilder(bytes.Length * 2);
                for (int i = 0; i < bytes.Length; i++) sb.Append(bytes[i].ToString("x2"));
                return sb.ToString();
            }
        }

        // --- random mailbox generation (for the keygen GUI) ---
        static readonly string[] MailDomains = new string[]
        {
            "gmail.com", "outlook.com", "qq.com", "163.com", "foxmail.com",
            "proton.me", "mail.com", "example.com", "icloud.com", "hotmail.com"
        };
        static readonly string MailAlnum = "abcdefghijklmnopqrstuvwxyz0123456789";

        // random mailbox like user<8 alnum>@<domain>; lowercase, collision unlikely,
        // practically impossible to hit the embedded MD5 blacklist
        public static string RandomEmail()
        {
            StringBuilder sb = new StringBuilder("user");
            lock (_sharedRnd)
            {
                for (int i = 0; i < 8; i++)
                    sb.Append(MailAlnum[_sharedRnd.Next(MailAlnum.Length)]);
                sb.Append('@');
                sb.Append(MailDomains[_sharedRnd.Next(MailDomains.Length)]);
            }
            return sb.ToString();
        }
    }
}
