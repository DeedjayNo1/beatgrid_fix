# beatgrid_fix.py

Tool to Make VirtualDJ 2026 Part 2 (b9246) , with new Fluid Beatgrids, compatible with SoundSwitch v2.10.2
This is an unofficial community tool, not affiliated with VirtualDJ or SoundSwitch
Made for my personal use — shared with the community
Hopefully useful until the great People of the SoundSwitch Team will support the new Beatgrid out of the box

**Version:** 0.3.0  
**Requires:** Python 3.10+

---

## Background

VirtualDJ (from a certain EarlyAccess build onwards, now Stable) uses a new
**Fluid Beatgrid** format. The beatgrid value is stored as a `Phase` attribute
inside the `<Scan>` block of the XML — instead of as a separate
`<Poi Type="beatgrid" />` entry as in VDJ 2026 v9004.

**Problem:** SoundSwitch reads the `<Poi Type="beatgrid" />` entry from
`database.xml` to synchronize the light show. Since the new VDJ Stable no
longer writes this entry, SoundSwitch auto-scripts cannot be created for
new tracks.

**Solution:** This tool reads the `Phase` value from the `<Scan>` block
and writes it as a `<Poi Type="beatgrid" />` entry into the XML.

---

## Two Modes

### Mode 1 — FIX
Finds all songs **without** a `Type="beatgrid"` POI and adds one
based on the `Phase` value from the `<Scan>` block.

**What happens:**
- `<Poi Pos="[Phase]" Type="beatgrid" />` is inserted chronologically
  (by Pos value) into the song block
- `User1="#SoundSwitch-FIX"` is set in the `<Tags>` block as a marker
  (searchable in VDJ)
- Output: `beatgrid_fix_[drive].m3u` with all fixed tracks

**Prerequisite:** The song must have a `<Scan>` block with a `Phase` attribute.
Songs without `Phase` (older VDJ format) are skipped —
they already have the `beatgrid` POI directly.

### Mode 2 — CHECK
Checks **all** songs that have both a `beatgrid` POI and a `Phase` value,
and corrects any deviation between them.

**When is this needed?**  
When you manually correct the first beat of a track in VDJ,
VDJ updates the `Phase` value in the `<Scan>` block.
The `beatgrid` POI (set by Mode 1) remains on the old value.
Mode 2 detects this deviation and corrects the `beatgrid` POI.

**Marker logic:**
- Deviation found → correct POI + set `User1="#Beatgrid-FIX"`
  (overwrites `#SoundSwitch-FIX` if present)
- No deviation → nothing is changed, existing marker stays as is

**Tolerance:** Small deviations (default: 0.001 seconds) are ignored.
Configurable in the INI under `phase_tolerance`.

---

## Requirements

- Python 3.10 or higher just download it from https://www.python.org/downloads/
- No additional packages required

---

## Quick Start

1. Download Python from https://www.python.org/downloads/
2. Install Python with the installer for your system
3. Check the checkbox **"Add python.exe to PATH"** during installation
4. Place `beatgrid_fix.py` and `beatgrid_fix.ini` in the same folder
5. Open `beatgrid_fix.ini`, adjust the paths and save
6. **Close VirtualDJ** (so all AudioSigs are written to the XML) — the tool will remind you too
7. Open a terminal in the tool folder:
   - **Windows:** right-click in the folder → choose `Open in Terminal`, then type `python beatgrid_fix.py` and press ENTER
   - **Mac:** open Terminal, navigate with `cd /path/to/folder`, then type `python3 beatgrid_fix.py` and press ENTER
8. Select mode (1 = FIX, 2 = CHECK)
9. In test mode: check the result in the M3U output — test mode is set inside the `.ini` file
10. Set `test_mode = no` and run again for real changes

---

## Configuration (beatgrid_fix.ini)

```ini
[SETTINGS]
# Path(s) to VirtualDJ database.xml
# Multiple XMLs supported: xml_1, xml_2, ...
xml_1 = I:\VirtualDJ\database.xml
xml_2 = D:\VirtualDJ\database.xml

# Backup folder:
#   empty         = backup next to each XML file
#   \Subfolder    = subfolder next to the XML
#   absolute path = use exactly this folder
backup_dir = \Backup_beatgrid

# Output folder for M3U files
output_dir = C:\Users\Your_Username\Desktop\beatgrid_fix_output

# Test mode: yes = XML will NOT be modified
#            no  = XML will be modified
test_mode = yes

# Tolerance for Phase vs. beatgrid comparison (Mode 2)
phase_tolerance = 0.001
```

---

## Backup Logic

A backup of the XML is created automatically before any changes.
The filename includes date and time: `database_backup_20260330_143022.xml`

Backup path options:
- **Empty** → backup is placed next to the source XML
- **`\Backup_beatgrid`** → subfolder `Backup_beatgrid` next to the XML
- **`C:\Users\You\Backup`** → absolute path

In **test mode** no backup is created (nothing is changed).

---

## Markers in VirtualDJ

Tracks fixed by Mode 1 receive `User1="#SoundSwitch-FIX"`.  
Tracks corrected by Mode 2 receive `User1="#Beatgrid-FIX"`.

Search in VirtualDJ:
```
#SoundSwitch-FIX    → tracks where beatgrid POI was added
#Beatgrid-FIX       → tracks where beatgrid POI was corrected
```

Run Mode 2 after manually correcting beatgrids in VDJ to keep
the POI in sync with the Phase value.

---

## Multiple XMLs

```ini
[SETTINGS]
xml_1 = I:\VirtualDJ\database.xml
xml_2 = D:\VirtualDJ\database.xml
```

The selected mode is applied to all XMLs in sequence.
A separate M3U is created per drive letter (e.g. `beatgrid_fix_I.m3u`).

---

## Technical Background

**Why does this happen?**  
VirtualDJ's new Fluid Beatgrid format stores the beat position as `Phase`
in the `<Scan>` block. SoundSwitch currently only reads the legacy
`<Poi Type="beatgrid" />` entry. This tool bridges the gap until
SoundSwitch is updated to read the `Phase` value directly.

**Phase value:**  
The `Phase` value in the `<Scan>` block is identical to the `Pos` value
of the `beatgrid` POI in older VDJ versions. This relationship was
confirmed by comparing tracks that contain both fields.

**Chronological insertion:**  
The new `beatgrid` POI is inserted between existing POI entries
sorted by their `Pos` value.

**Compatibility:**  
Songs in the older format (VDJ 2026 v9005) already have a `beatgrid` POI
and no `Phase` value — these are correctly skipped by Mode 1.


---

## Changelog

| Version | Date | Changes |
|---|---|---|
| 0.3.0 | 2026-03-31 | Full XML entity decoding (incl. double-encoded), line-based parser, duplicate fix |
| 0.2.0 | 2026-03-31 | Mode 1: `#SoundSwitch-FIX` marker; Mode 2: checks all tracks |
| 0.1.0 | 2026-03-31 | Multiple XMLs, new backup logic |
| 0.0.1 | 2026-03-30 | Initial version: Mode 1 (FIX) + Mode 2 (CHECK) |
