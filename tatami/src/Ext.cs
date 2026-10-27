using System;
using System.Collections.Concurrent;
using System.Collections.Generic;

namespace Tatami
{
    /// <summary>File extensions seen in a scan (index 0 = no extension) and the category each belongs to.</summary>
    sealed class ExtTable
    {
        public static readonly string[] Categories = {
            "Other", "Video", "Audio", "Pictures", "Archives", "Disk images", "Programs", "Documents",
            "Code", "Game data", "System & cache", "Folders"
        };
        public const int C_OTHER = 0, C_VIDEO = 1, C_AUDIO = 2, C_PICTURES = 3, C_ARCHIVES = 4, C_DISK = 5,
            C_PROGRAMS = 6, C_DOCS = 7, C_CODE = 8, C_GAME = 9, C_SYSTEM = 10, C_FOLDER = 11;

        static readonly Dictionary<string, int> Known = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

        static void Add(int cat, string list) { foreach (var e in list.Split(' ')) Known[e] = cat; }

        static ExtTable()
        {
            Add(C_VIDEO, "mp4 mkv avi mov wmv webm m4v flv ts m2ts mts mpg mpeg 3gp vob ogv rmvb divx f4v braw r3d prproj");
            Add(C_AUDIO, "mp3 wav flac aac ogg m4a wma opus aiff aif alac mid midi ape wv amr m4b caf");
            Add(C_PICTURES, "jpg jpeg png gif bmp heic heif webp tif tiff raw cr2 cr3 nef arw dng orf rw2 raf psd psb ai " +
                "svg ico cur ani avif jxl tga dds exr hdr kra xcf eps emf wmf");
            Add(C_ARCHIVES, "zip 7z rar tar gz tgz bz2 xz zst lz4 lzma cab arj z tbz2 txz zipx sit apk xapk nupkg " +
                "whl crx deb rpm pkg");
            Add(C_DISK, "iso img vhd vhdx vmdk vdi qcow2 avhdx wim esd swm dmg vmem vmsn nvram hds");
            Add(C_PROGRAMS, "exe dll sys msi msp msix msixbundle appx appxbundle ocx drv mui efi cpl scr com node so " +
                "dylib winmd tlb ax acm");
            Add(C_DOCS, "pdf doc docx docm xls xlsx xlsm xlsb ppt pptx pptm txt rtf odt ods odp md epub mobi fb2 csv " +
                "one onepkg pst ost msg eml vsd vsdx pub xps oxps tex djvu chm pages numbers key");
            Add(C_CODE, "cs js mjs cjs ts tsx jsx py pyc pyd pyi java class jar c cpp cc h hpp hxx go rs rb php swift " +
                "kt kts scala lua pl r m mm sh ps1 psm1 psd1 bat cmd vbs json xml yaml yml toml ini cfg conf html htm " +
                "css scss less sass vue svelte sql pdb lib obj o a ilk ipdb iobj pch idb tlog map wasm gradle csproj " +
                "sln vcxproj props targets resx xaml dart ex exs erl hs ml fs fsx nim zig asm s cmake mk ninja gitignore " +
                "lock sum mod");
            Add(C_GAME, "pak pack vpk bsa ba2 wad uasset uexp ubulk ucas utoc assets bundle resource resources sav " +
                "esm esp esl gcf ncf vdf acf forge big rpf arc cpk awb acb wem bnk fsb pck xnb unity3d ress sharedassets " +
                "pkx bdt sb ff rgssad");
            Add(C_SYSTEM, "log tmp temp etl evtx dmp mdmp hdmp cache db sqlite sqlite3 db-wal db-shm edb jfm chk sdf mum cat " +
                "manifest regtrans-ms blf dat ttf otf ttc fon nls bak old swp lnk url ldb dex odex vdex oat " +
                "wer pf ndf mdf ldf frx bin checkpoint journal lck pri xbf");
        }

        readonly ConcurrentDictionary<string, int> map = new ConcurrentDictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        readonly List<string> names = new List<string> { "" };
        readonly List<int> cats = new List<int> { C_OTHER };

        public int Count { get { lock (names) return names.Count; } }
        public string Name(int i) { lock (names) return names[i]; }
        public int Category(int i) { lock (names) return cats[i]; }

        public int[] CategoryArray() { lock (names) return cats.ToArray(); }
        public string[] NameArray() { lock (names) return names.ToArray(); }

        /// <summary>Extension index for a file name held in buf[off..off+len).</summary>
        public int Of(char[] buf, int off, int len)
        {
            int dot = -1;
            for (int k = len - 1; k >= 0 && k >= len - 17; k--) { char c = buf[off + k]; if (c == '.') { dot = k; break; } }
            if (dot <= 0 || dot == len - 1) return 0;
            string e = new string(buf, off + dot + 1, len - dot - 1).ToLowerInvariant();
            int idx;
            if (map.TryGetValue(e, out idx)) return idx;
            lock (names)
            {
                if (map.TryGetValue(e, out idx)) return idx;
                idx = names.Count;
                names.Add(e);
                int cat;
                cats.Add(Known.TryGetValue(e, out cat) ? cat : C_OTHER);
                map[e] = idx;
                return idx;
            }
        }

        /// <summary>Re-add an extension when loading a saved scan (indices must come back in order).</summary>
        public void Restore(string ext, int cat)
        {
            lock (names) { map[ext] = names.Count; names.Add(ext); cats.Add(cat); }
        }

        public int Of(string name)
        {
            var a = name.ToCharArray();
            return Of(a, 0, a.Length);
        }

        /// <summary>Category for a specific file; a few well-known system files are special-cased by name.</summary>
        public static bool IsSystemName(string lowerName)
        {
            return lowerName == "pagefile.sys" || lowerName == "hiberfil.sys" || lowerName == "swapfile.sys" ||
                   lowerName == "memory.dmp" || lowerName == "dumpstack.log";
        }
    }
}
