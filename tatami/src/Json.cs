using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Web.Script.Serialization;

namespace Tatami
{
    /// <summary>Minimal fast JSON writer (and a parser for small request bodies).</summary>
    sealed class Json
    {
        readonly StringBuilder sb = new StringBuilder(4096);
        bool comma;

        public Json Obj() { Sep(); sb.Append('{'); comma = false; return this; }
        public Json EndObj() { sb.Append('}'); comma = true; return this; }
        public Json Arr() { Sep(); sb.Append('['); comma = false; return this; }
        public Json EndArr() { sb.Append(']'); comma = true; return this; }
        public Json Key(string k) { Sep(); Str(k); sb.Append(':'); comma = false; return this; }

        public Json Val(string v) { Sep(); if (v == null) sb.Append("null"); else Str(v); comma = true; return this; }
        public Json Val(long v) { Sep(); sb.Append(v.ToString(CultureInfo.InvariantCulture)); comma = true; return this; }
        public Json Val(double v)
        {
            Sep();
            sb.Append(double.IsNaN(v) || double.IsInfinity(v) ? "0" : v.ToString("R", CultureInfo.InvariantCulture));
            comma = true; return this;
        }
        public Json Val(bool v) { Sep(); sb.Append(v ? "true" : "false"); comma = true; return this; }
        public Json Raw(string json) { Sep(); sb.Append(json); comma = true; return this; }
        public Json Null() { Sep(); sb.Append("null"); comma = true; return this; }

        public Json P(string k, string v) { return Key(k).Val(v); }
        public Json P(string k, long v) { return Key(k).Val(v); }
        public Json P(string k, double v) { return Key(k).Val(v); }
        public Json P(string k, bool v) { return Key(k).Val(v); }

        void Sep() { if (comma) sb.Append(','); }

        void Str(string s)
        {
            sb.Append('"');
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                        else sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
        }

        public override string ToString() { return sb.ToString(); }

        static readonly JavaScriptSerializer parser = new JavaScriptSerializer { MaxJsonLength = 64 * 1024 * 1024 };

        public static Dictionary<string, object> Parse(string body)
        {
            if (string.IsNullOrWhiteSpace(body)) return new Dictionary<string, object>();
            var o = parser.DeserializeObject(body) as Dictionary<string, object>;
            return o ?? new Dictionary<string, object>();
        }

        public static string Ser(object o) { return parser.Serialize(o); }

        public static string S(Dictionary<string, object> d, string k, string def = null)
        {
            object v; return d.TryGetValue(k, out v) && v != null ? Convert.ToString(v, CultureInfo.InvariantCulture) : def;
        }
        public static long L(Dictionary<string, object> d, string k, long def = 0)
        {
            object v; return d.TryGetValue(k, out v) && v != null ? Convert.ToInt64(v, CultureInfo.InvariantCulture) : def;
        }
        public static bool B(Dictionary<string, object> d, string k, bool def = false)
        {
            object v; return d.TryGetValue(k, out v) && v is bool ? (bool)v : def;
        }
        public static List<long> Ls(Dictionary<string, object> d, string k)
        {
            var r = new List<long>();
            object v;
            if (d.TryGetValue(k, out v) && v is IEnumerable && !(v is string))
                foreach (var x in (IEnumerable)v) r.Add(Convert.ToInt64(x, CultureInfo.InvariantCulture));
            return r;
        }
    }
}
