#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
beatgrid_fix.py — VirtualDJ Beatgrid Fix Tool
==============================================
Mode 1 - FIX:    Finds songs without a beatgrid POI and adds one
                  based on the Phase value from the Scan block.
                  Sets User1="#SoundSwitch-FIX" as a marker.

Mode 2 - CHECK:  Checks ALL songs with a beatgrid POI + Phase value
                  for deviations. Corrects if needed and sets
                  User1="#Beatgrid-FIX". If the track already has
                  "#SoundSwitch-FIX" it will be updated to "#Beatgrid-FIX"
                  only if a correction was made.

IMPORTANT: VirtualDJ must be closed before running this tool!

Changelog:
  0.3.0 - xml_decode complete: &apos; &quot; &lt; &gt; &amp;
          Line-based parser instead of regex (no more CPU hang)
          M3U: Author/Title are also decoded
          Duplicate match fix in mode_check
  0.2.0 - Mode 1: marker "#SoundSwitch-FIX" instead of "#Beatgrid-FIX"
          Mode 2: checks ALL tracks (not just marked ones),
                   sets "#Beatgrid-FIX", renames "#SoundSwitch-FIX"
  0.1.0 - Multiple XMLs in INI (xml_1, xml_2, ...)
          New backup logic: empty=next to XML, subfolder=relative, absolute=direct
  0.0.1 - Initial version: Mode 1 (FIX) + Mode 2 (CHECK)
"""

import os
import sys
import re
import shutil
import configparser
from datetime import datetime

VERSION = "0.3.0"

# ─────────────────────────────────────────────
# INI laden
# ─────────────────────────────────────────────

def load_config():
    ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beatgrid_fix.ini")
    if not os.path.exists(ini_path):
        print(f"[ERROR] beatgrid_fix.ini not found: {ini_path}")
        input("\nPress Enter to exit...")
        sys.exit(1)
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(ini_path, encoding="utf-8")
    return cfg

# ─────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────

def xml_decode(path: str) -> str:
    """Decode XML entities — including double-encoded entities (e.g. &amp;apos;)"""
    # Decode twice for double-encoded entities from old tools
    for _ in range(2):
        path = path.replace("&amp;", "&")
        path = path.replace("&apos;", "'")
        path = path.replace("&quot;", '"')
        path = path.replace("&lt;", "<")
        path = path.replace("&gt;", ">")
    return path

def check_vdj_running() -> bool:
    import subprocess
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq VirtualDJ.exe"],
            capture_output=True, text=False
        )
        return b"virtualdj.exe" in result.stdout.lower()
    except Exception:
        return False

def backup_xml(xml_path: str, backup_dir: str) -> str:
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"database_backup_{timestamp}.xml"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(xml_path, backup_path)
    return backup_path

def write_m3u(filepath: str, tracks: list, header: str):
    if not tracks:
        print(f"    → 0 tracks, M3U will not be created.")
        return
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        f.write(f"# {header}\n")
        f.write(f"# Erstellt von beatgrid_fix.py v{VERSION}\n")
        f.write(f"# Datum: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"# Tracks: {len(tracks)}\n\n")
        for t in tracks:
            author  = xml_decode(t.get("author", ""))
            title   = xml_decode(t.get("title", ""))
            info    = f"{author} - {title}" if (author or title) else os.path.basename(t["filepath_fs"])
            f.write(f"#EXTINF:-1,{info}\n")
            f.write(f"{t['filepath_fs']}\n")
    print(f"    → {len(tracks):>6} Tracks → {os.path.basename(filepath)}")



def expand_path(path: str) -> str:
    """Expands environment variables and user home in paths.
    e.g. %USERNAME%, %APPDATA%, ~ etc.
    """
    import os
    return os.path.expandvars(os.path.expanduser(path))


def resolve_backup_path(xml_path: str, backup_setting: str) -> str:
    """
    Resolves the backup path:
    - Empty                   = same folder as the XML
    - [Backslash]Subfolder    = subfolder next to the XML
    - Absolute path           = use that path directly
    """
    xml_dir = os.path.dirname(os.path.abspath(xml_path))
    if not backup_setting or not backup_setting.strip():
        return xml_dir
    setting = backup_setting.strip()
    if setting.startswith(chr(92)) or setting.startswith("/"):
        return os.path.join(xml_dir, setting.lstrip("/\\"))
    return setting


def get_xml_paths(cfg: configparser.ConfigParser) -> list:
    """
    Reads all xml_N entries from [SETTINGS].
    Falls back to xml_path (singular) for backwards compatibility.
    """
    paths = []
    i = 1
    while cfg.has_option("SETTINGS", f"xml_{i}"):
        p = expand_path(cfg.get("SETTINGS", f"xml_{i}").strip())
        if p:
            paths.append(p)
        i += 1
    if not paths:
        p = expand_path(cfg.get("SETTINGS", "xml_path", fallback="").strip())
        if p:
            paths.append(p)
    return paths

# ─────────────────────────────────────────────
# Song-Block Parsing
# ─────────────────────────────────────────────

def get_attr(block: str, attr: str) -> str:
    m = re.search(rf'\b{attr}="([^"]*)"', block)
    return m.group(1) if m else ""

def has_beatgrid(block: str) -> bool:
    return bool(re.search(r'Type="beatgrid"', block))

def has_beatgrid_fix_marker(block: str) -> bool:
    """Checks if User1="#Beatgrid-FIX" is present in the Tags block."""
    tags_match = re.search(r'<Tags\s[^>]*/>', block)
    if not tags_match:
        return False
    return '#Beatgrid-FIX' in tags_match.group(0)

def get_phase(block: str) -> str:
    """Phase value from <Scan ... Phase="..." .../>"""
    return get_attr(block, "Phase")

def get_beatgrid_pos(block: str) -> str:
    """Pos value of the beatgrid POI."""
    m = re.search(r'<Poi\s[^>]*Type="beatgrid"[^>]*/>', block)
    if not m:
        return ""
    return get_attr(m.group(0), "Pos")

def get_real_start_pos(block: str) -> str:
    """Pos value of the automix realStart POI."""
    m = re.search(r'<Poi\s[^>]*Point="realStart"[^>]*/>', block)
    if not m:
        return ""
    return get_attr(m.group(0), "Pos")

# ─────────────────────────────────────────────
# XML Manipulation
# ─────────────────────────────────────────────

def insert_beatgrid_poi(block: str, phase: str) -> str:
    """
    Inserts <Poi Pos="[phase]" Type="beatgrid" /> in chronological
    order into the song block. Line-based.
    """
    new_poi = f'  <Poi Pos="{phase}" Type="beatgrid" />'
    phase_f = float(phase)

    blines = block.split("\n")
    poi_lines = []
    for i, line in enumerate(blines):
        if "<Poi " in line and "/>" in line:
            pos_val = get_attr(line, "Pos")
            try:
                poi_lines.append((i, float(pos_val) if pos_val else 0.0))
            except ValueError:
                poi_lines.append((i, 0.0))

    if not poi_lines:
        result = []
        for line in blines:
            if "</Song>" in line:
                result.append(new_poi)
            result.append(line)
        return "\n".join(result)

    insert_after_idx = None
    for idx, pos_f in poi_lines:
        if pos_f <= phase_f:
            insert_after_idx = idx

    if insert_after_idx is None:
        blines.insert(poi_lines[0][0], new_poi)
    else:
        blines.insert(insert_after_idx + 1, new_poi)

    return "\n".join(blines)

def set_user1_marker(block: str, marker: str) -> str:
    """
    Sets User1="[marker]" in the <Tags .../> block.
    Overwrites any existing User1 value.
    """
    tags_match = re.search(r'(<Tags\s)((?:[^>](?!/>))*[^>]?)(/>\s*)', block, re.DOTALL)
    if not tags_match:
        return block

    tags_full  = tags_match.group(0)
    tags_open  = tags_match.group(1)
    tags_attrs = tags_match.group(2)
    tags_close = tags_match.group(3)

    if 'User1="' in tags_attrs:
        tags_attrs = re.sub(r'User1="[^"]*"', f'User1="{marker}"', tags_attrs)
    else:
        tags_attrs = tags_attrs.rstrip() + f' User1="{marker}"'

    new_tags = tags_open + tags_attrs + tags_close
    return block.replace(tags_full, new_tags)

def update_beatgrid_pos(block: str, new_phase: str) -> str:
    """Updates the Pos value of an existing beatgrid POI."""
    return re.sub(
        r'(<Poi\s[^>]*Type="beatgrid"[^>]*Pos=")[^"]*(")',
        lambda m: m.group(1) + new_phase + m.group(2),
        block
    )

def update_beatgrid_pos_alt(block: str, new_phase: str) -> str:
    """
    Updates beatgrid POI — even if Pos comes before Type.
    Replaces the complete beatgrid POI block.
    """
    return re.sub(
        r'<Poi\s[^>]*Type="beatgrid"[^>]*/>',
        f'<Poi Pos="{new_phase}" Type="beatgrid" />',
        block
    )


def parse_song_blocks(content: str) -> list:
    """
    Line-based parsing of song blocks.
    Safer than regex for large XML files.
    Returns a list of block strings.
    """
    blocks = []
    current = []
    in_song = False

    for line in content.split("\n"):
        if "<Song " in line and "FilePath=" in line:
            in_song = True
            current = [line]
        elif in_song:
            current.append(line)
            if "</Song>" in line:
                blocks.append("\n".join(current))
                current = []
                in_song = False
        # Einzeilige Songs: <Song ... />
        elif not in_song and "<Song " in line and "/>" in line:
            blocks.append(line)

    return blocks

# ─────────────────────────────────────────────
# Modus 1: FIX
# ─────────────────────────────────────────────

def modus_fix(content: str, output_dir: str, tolerance: float) -> tuple:
    """
    Finds all songs without a beatgrid POI and adds one.
    Returns (new_content, fixes_list).
    """
    fixes = []
    new_content = content

    for block in parse_song_blocks(content):

        # beatgrid already present? → skip
        if has_beatgrid(block):
            continue

        filepath = get_attr(block, "FilePath")
        phase    = get_phase(block)

        if not phase:
            continue  # No Scan block → skip

        author = get_attr(block, "Author")
        title  = get_attr(block, "Title")

        # Insert beatgrid POI
        new_block = insert_beatgrid_poi(block, phase)
        # Set User1 marker
        new_block = set_user1_marker(new_block, "#SoundSwitch-FIX")

        updated = new_content.replace(block, new_block, 1)
        if updated == new_content:
            continue  # Block already replaced (duplicate match)
        new_content = updated

        fixes.append({
            "filepath":    filepath,
            "filepath_fs": xml_decode(filepath),
            "author":      xml_decode(author),
            "title":       xml_decode(title),
            "phase":       phase,
        })

    return new_content, fixes

# ─────────────────────────────────────────────
# Modus 2: CHECK
# ─────────────────────────────────────────────

def get_user1(block: str) -> str:
    """Reads User1 value from the Tags block."""
    tags_match = re.search(r'<Tags\s[^>]*/>', block)
    if not tags_match:
        return ""
    m = re.search(r'User1="([^"]*)"', tags_match.group(0))
    return m.group(1) if m else ""


def modus_check(content: str, output_dir: str, tolerance: float) -> tuple:
    """
    Checks ALL songs with a beatgrid POI + Phase value for deviations.
    On deviation: correct beatgrid + set User1="#Beatgrid-FIX".
    If track has "#SoundSwitch-FIX" → rename to "#Beatgrid-FIX" only on correction.
    Returns (new_content, corrections_list).
    """
    corrections = []
    new_content = content

    for block in parse_song_blocks(content):

        # Only tracks with beatgrid POI AND Phase value
        if not has_beatgrid(block):
            continue

        phase        = get_phase(block)
        beatgrid_pos = get_beatgrid_pos(block)

        if not phase or not beatgrid_pos:
            continue

        try:
            phase_f = float(phase)
            bg_f    = float(beatgrid_pos)
        except ValueError:
            continue

        filepath = get_attr(block, "FilePath")
        author   = get_attr(block, "Author")
        title    = get_attr(block, "Title")
        user1    = get_user1(block)

        # Check for deviation
        abweichung = abs(phase_f - bg_f) > tolerance

        if abweichung:
            # Correct beatgrid Pos
            new_block = update_beatgrid_pos_alt(block, phase)
            # Set marker: #Beatgrid-FIX (even if #SoundSwitch-FIX was present)
            new_block = set_user1_marker(new_block, "#Beatgrid-FIX")
            updated = new_content.replace(block, new_block, 1)
            if updated == new_content:
                continue  # block already replaced (duplicate match), skip
            new_content = updated
            corrections.append({
                "filepath":     filepath,
                "filepath_fs":  xml_decode(filepath),
                "author":       xml_decode(author),
                "title":        xml_decode(title),
                "phase":        phase,
                "beatgrid_alt": beatgrid_pos,
                "marker_alt":   user1,
            })
            print(f"  CORRECTED: {author} - {title}")
            print(f"    Phase: {phase} | Beatgrid was: {beatgrid_pos}"
                  + (f" | Marker: {user1}" if user1 else ""))

        # No deviation → leave everything as is, marker stays unchanged

    return new_content, corrections

# ─────────────────────────────────────────────
# Hauptprogramm
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"  beatgrid_fix.py v{VERSION}")
    print(f"  VirtualDJ Beatgrid Fix Tool")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    print()

    cfg = load_config()

    xml_paths  = get_xml_paths(cfg)
    backup_setting = expand_path(cfg.get("SETTINGS", "backup_dir", fallback="").strip())
    output_dir = expand_path(cfg.get("SETTINGS", "output_dir"))
    tolerance  = float(cfg.get("SETTINGS", "phase_tolerance", fallback="0.001"))
    test_mode  = cfg.getboolean("SETTINGS", "test_mode", fallback=True)

    if not xml_paths:
        print("  [ERROR] No xml_path / xml_1 entries found in the INI file.")
        input("\nPress Enter to exit...")
        sys.exit(1)

    print(f"  {len(xml_paths)} XML(s) configured:")
    for i, p in enumerate(xml_paths, 1):
        print(f"    {i}. {p}")

    backup_label = backup_setting if backup_setting else "(next to each XML file)"
    print(f"  Backup: {backup_label}\n")

    # VDJ Prozess pruefen
    if check_vdj_running():
        print("  [WARNING] VirtualDJ is currently running!")
        print("  Please close VirtualDJ before running this tool.")
        print()
        antwort = input("  Continue anyway? (y/N): ").strip().lower()
        if antwort != "j":
            print("  Cancelled.")
            input("\nPress Enter to exit...")
            sys.exit(0)
        print()

    # Modus waehlen (einmalig fuer alle XMLs)

    # Modus waehlen (einmalig)
    print("  Which mode would you like to run?")
    print()
    print("  [1] FIX   — Add missing beatgrid POIs")
    print("              (songs without beatgrid, Phase value will be used)")
    print()
    print("  [2] CHECK — Check all tracks for beatgrid deviations")
    print("              (Phase value vs. existing beatgrid POI)")
    print()
    print("  [Q] Quit")
    print()

    while True:
        modus = input("  Selection: ").strip().upper()
        if modus in ("1", "2", "Q"):
            break
        print("  Please enter 1, 2 or Q.")

    if modus == "Q":
        print("\n  Goodbye!")
        input("\nPress Enter to exit...")
        sys.exit(0)

    print()

    if test_mode:
        print("  *** TEST MODE — XML will NOT be modified ***\n")

    total_results = 0

    for xml_path in xml_paths:
        xml_path_fs = xml_decode(xml_path)
        if not os.path.exists(xml_path_fs):
            print(f"  [ERROR] XML not found: {xml_path_fs} — uebersprungen")
            continue

        print(f"\n{'─'*60}")
        print(f"  XML: {xml_path_fs}")

        with open(xml_path_fs, "r", encoding="utf-8", errors="replace") as f:
            xml_content = f.read()
        print(f"  Loaded: {len(xml_content):,} characters")

        # Backup erstellen
        if not test_mode:
            backup_dir = resolve_backup_path(xml_path_fs, backup_setting)
            backup_path = backup_xml(xml_path_fs, backup_dir)
            print(f"  Backup created: {backup_path}")

        # Modus ausfuehren
        if modus == "1":
            print("\n  [Mode 1] Searching for songs without beatgrid POI...\n")
            new_content, results = modus_fix(xml_content, output_dir, tolerance)
            print(f"\n  Result: {len(results)} songs without beatgrid found and fixed.")

            if results:
                # Label aus Laufwerksbuchstaben bauen (eindeutig)
                drive_letter = xml_path_fs[0] if len(xml_path_fs) > 1 and xml_path_fs[1] == ":" else "X"
                m3u_path = os.path.join(output_dir, f"beatgrid_fix_{drive_letter}.m3u")
                write_m3u(m3u_path, results, f"Beatgrid FIX — {xml_path_fs}")
                print("\n  First 5 fixed tracks:")
                for t in results[:5]:
                    print(f"    {t['author']} - {t['title']} | Phase: {t['phase']}")

            if not test_mode and results:
                with open(xml_path_fs, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"\n  XML saved: {xml_path_fs}")
            elif test_mode and results:
                print(f"\n  [TEST] XML was NOT modified.")

        elif modus == "2":
            print("\n  [Mode 2] Checking all tracks for beatgrid deviations...\n")
            new_content, results = modus_check(xml_content, output_dir, tolerance)
            print(f"\n  Result: {len(results)} tracks with deviating beatgrid corrected.")

            if results:
                drive_letter = xml_path_fs[0] if len(xml_path_fs) > 1 and xml_path_fs[1] == ":" else "X"
                m3u_path = os.path.join(output_dir, f"beatgrid_check_{drive_letter}.m3u")
                write_m3u(m3u_path, results, f"Beatgrid CHECK — {xml_path_fs}")

            if not test_mode and results:
                with open(xml_path_fs, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"\n  XML saved: {xml_path_fs}")
            elif test_mode and results:
                print(f"\n  [TEST] XML was NOT modified.")
            elif not results:
                print("  All tracks are up to date — no corrections needed.")

        total_results += len(results)

    print()
    print("=" * 60)
    print(f"  Done! {total_results} tracks processed ({len(xml_paths)} XML(s))")
    print("=" * 60)
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
