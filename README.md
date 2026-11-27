![Logo](assets/FSICO.png)
# FileSense 2.0.0

**One smarter way to manage your PC.**

Current release: **2.0.0**.

FileSense provides tools to organize files, find same-name entries, inspect disk usage, manage startup entries, review cleanup candidates, and search for files. This guide describes how each module works and what happens when you preview, scan, or apply an action.

## Documentation

- [Installation guide](docs/installation-guide.md) — install, launch, update, and uninstall FileSense on Windows.
- [User guide](docs/user-guide.md) — learn how to use each module and understand its options and actions.
- [Developer guide](docs/developer-guide.md) — run from source, build packages, and manage offline activation keys.

## Repository layout

```text
FileSense/
├── FileSense.py            # Source-tree launcher
├── README.md               # Project overview and user guide
├── LICENSE                 # GitHub repository license terms
├── requirements.txt        # Runtime dependency
├── src/filesense/          # Application modules
├── tools/                  # Offline activation-key utilities
├── assets/                 # App icons, illustrations, installer artwork
├── qml/                    # Qt Quick interface
├── docs/                   # Installation, user, and developer guides
├── legal/EULA.txt          # Product EULA used by the installer
└── packaging/              # Build deps, PyInstaller, build script, installer setup
```

## License

FileSense and its source code are proprietary; public GitHub visibility does not grant permission to reuse or redistribute the code. The application is licensed for personal, non-commercial use under the [End User License Agreement](legal/EULA.txt). See [LICENSE](LICENSE) for the repository terms. Third-party components retain their own licenses.

Generated `build/`, `dist/`, virtual environments, signing keys, and installer binaries are local build/release outputs and are excluded from Git. Attach the installer and portable package to a GitHub Release instead of committing those binaries to the source tree.

## Start here

Choose a module from the left navigation or Home page. Searches and scans are started manually; opening a module does not start a scan. Results can take time on large folders or drives. The app may skip inaccessible locations, symbolic links, or items that change during a scan, and reports scan notices when available.

For normal use, install FileSense with `ProSoft-FileSense-Setup.exe`. The installer includes the runtime, so Python does not need to be installed on the Windows PC. For portable use, copy the complete `dist\\FileSense` folder and run `FileSense.exe` from it; the executable needs the neighboring runtime files. To build from source, use Python 3.10 or newer on the build PC and run `packaging\\build_exe.bat`.

## Home

Home gives access to the six main tools:

- File Organizer
- Storage Analyzer
- File Search & Finder
- Duplicate Finder
- Junk Cleaner
- Startup Manager

Use a module card or the left navigation to open a tool. Home does not scan your computer on its own.

## File Organizer

File Organizer has **Quick Organize** and **Build a Rule** tabs. Both work on files, show a preview first, and require you to run the operation explicitly.

### Quick Organize

1. Choose a source folder and optionally add excluded folders inside it.
2. Turn on **Include subfolders** to scan below the source folder. Excluded folders are skipped during a recursive scan.
3. Choose the default conflict action and select **Preview**.
4. Review the proposed source, category, destination, and conflict action. You can change the conflict action for an individual conflicting file.
5. Select **Organize files** and confirm.

Files are sorted by extension into Compressed, Video, Audio, Images, Documents, or Programs. Extensions that do not belong to those lists go into **Others**. The category folders, including Others when needed, are created under the chosen source folder. If the destination already contains a same-named file, the conflict action applies:

- **Keep both** keeps the existing file and gives the incoming file a numbered name.
- **Skip** leaves the incoming file in its source folder.
- **Replace** replaces the destination file after confirmation.

Files are checked again before the operation. If a source file has been removed, is no longer a regular file, becomes excluded, or no longer belongs to its previewed category, it is skipped. The operation uses the file as it exists when organizing begins; preview again after changing the folder or settings.

### Build a Rule

1. Add one or more existing monitored source folders. Separate typed paths with semicolons. Set **Include subfolders** if nested folders should be scanned.
2. Add conditions in the order they should be evaluated.
3. Choose **Move file**, **Copy file**, or **Delete file**. Move and Copy require an existing destination folder. Delete sends matching files to the Windows Recycle Bin and does not use a destination.
4. Choose the default conflict action, select **Preview**, review the output, then select **Run rule** and confirm.

The rule preview lists matching files and proposed destinations. Conflict actions are shown only where the destination already exists; each conflicting row can use its own action. Changing the default updates the conflicting rows. **Keep both** preserves the destination file and creates a numbered name for the incoming file; **Skip** leaves the source untouched; **Replace** overwrites the destination after confirmation. Run rechecks source files and rule conditions before applying the operation.

#### Rule fields and conditions

Each condition checks one property of a file:

| Field | Operators and behavior |
|---|---|
| **File Type** | Is, Is not, Contains, Does not contain. Types include the organizer’s file categories, such as Images or Documents. |
| **File Extension** | Is, Is not, Contains, Does not contain. Enter an extension such as `.png` or `.tar.gz`. Is checks whether the filename ends with that extension. |
| **File Size** | Is, Is not, Greater than, Less than, At least, At most. Enter a number and choose B, KB, MB, or GB. |
| **File Name** | Contains, Does not contain, Starts with, Ends with, Matches exact text, Matches pattern (advanced). Ends with checks the filename before its final extension, so `report1.png` matches `1`. Exact text compares the complete filename, including its extension. |
| **File Date** | Choose Date created, Date modified, or Date last accessed; then use Before, After, Between, Within last, Older than, or Newer than. Enter dates as MM-DD-YYYY. Relative periods use days, 30-day months, or 365-day years. Between includes both endpoint dates. |

Conditions are evaluated **top to bottom**, without parentheses. The first condition establishes the current result. Each later connector combines that result with its condition: **AND** requires both, **OR** accepts either, and **NOT** means the current result AND NOT the next condition.

Example: `File Type Is Images` **AND** `File Size Greater than 10 MB` **NOT** `File Name Ends with screenshot` selects image files larger than 10 MB whose filename (before the final extension) does not end in `screenshot`.

**Matches pattern (advanced)** uses case-insensitive filename wildcards and includes the extension. `report-*.pdf` matches `report-january.pdf`; `photo?.jpg` matches `photo1.jpg` but not `photo12.jpg`. `*` matches any sequence of characters and `?` matches one character.

All condition fields must be filled in. At least one condition is required. If no files match, the preview reports that no files match; nothing is moved, copied, or deleted.

## Duplicate Finder

Duplicate Finder has **Find duplicates** and **Build a rule** tabs. Add one or more folders, choose whether to include subfolders, then select **Scan duplicates**. Folder names are not candidates; this module groups files that have the same name, ignoring case. It does not verify that their contents are identical. Sizes are shown for comparison, but equal sizes do not prove files are identical.

In **Build a rule**, add conditions for File Type or File Extension to restrict which files are grouped. You can combine them in order with AND, OR, or NOT. For example, `File Type Is Images` AND `File Extension Is .png` considers only PNG images.

Mark entries you want removed, then apply the selection. Checked files are sent to the Recycle Bin; unchecked files are kept. You can mark every entry in a group for deletion, so leave at least one unchecked if you want to retain a copy. Review folder selections carefully when folders contain nested entries. Each tab keeps its own scan and rule results.

## Storage Analyzer

1. Choose a drive or browse to a folder.
2. Select **Scan storage**. Opening the module or changing tabs does not start another scan.
3. Review the summary and use the tabs:
   - **Folder Breakdown** shows the folder tree, logical Size, estimated Allocated size, file/folder counts, and share of the parent. Expand a folder to list its files. Select items and use **Delete selected** to send them to the Recycle Bin after confirmation.
   - **File Types (Extensions)** breaks usage down by extension and file type. Shares and bars use allocated-size totals; small extensions below 1% of the root allocation are omitted from this report.
   - **Treemap View** visualizes the scanned hierarchy as proportional rectangles. Hover for details, double-click a folder to explore it, and use breadcrumbs to move back. Sort, folder depth, and display metric (Size, File Count, Allocated Space) change the view only. Treemap is view-only and does not change Folder Breakdown selections.

The volume summary uses Windows capacity and free-space information; Used Space is Capacity minus Free Space. File and folder totals come from the scan. Logical Size is the sum of file lengths. Allocated size is estimated from the volume allocation unit for regular files; compressed and sparse files use filesystem-reported sizes. The estimate may differ from Windows' exact disk accounting. Fast NTFS enumeration is available on NTFS volumes; it is a batched directory enumeration, not a direct Master File Table scan. Inaccessible paths are excluded and counted in scan notices.

## File Search & Finder

1. Enter one or more existing drive or folder paths separated by semicolons, or add a drive/browse for a folder.
2. Optionally exclude folders and set one or more filters.
3. Select **Search**. At least one filter is required; an empty filter set is rejected instead of searching everything.

Filters include filename contains, comma-separated extensions, file type, minimum/maximum size with B/KB/MB/GB units, created-date range, and modified-date range. Different enabled filter fields combine with **AND**: a file must satisfy each one. Within a comma-separated extension list or multiple selected file types, matching any selected value is enough. Size limits are inclusive (a file equal to the minimum or maximum qualifies). Date ranges include the selected end date. Dates use MM-DD-YYYY.

The name filter is a case-insensitive substring. Extensions match the end of a filename, so `.jpg` matches `photo.jpg`. Type filters include Compressed, Video, Audio, Images, Documents, Programs, and Other. If filename is the only filter, matching folders may also appear; file type, extension, size, or date filters return files. When a drive root is selected, the scan is recursive even if **Include subfolders** is off; for a selected folder, that option controls whether nested folders are searched. Symbolic links and reparse points are skipped. Results are capped at 10,000; the status indicates if the limit is reached. Select results to Copy, Move, or Delete; Delete sends selected files to the Recycle Bin after confirmation. Double-click a result to open its location.

## Junk Cleaner

Select **Scan cleanup** or **Rescan** to inspect supported locations. The module groups candidates into Recommended items and Other system/application items. Recommended candidates are preselected after scanning; group and category checkboxes let you change the selection. Review the selected size and item details before choosing **Clean selected**.

Current categories include user and Windows temporary files, thumbnail and DirectX caches, Windows Error Reporting, per-browser Chrome/Edge/Firefox caches, FileSense cache/log files, NVIDIA and Python pip caches when their known folders exist, user and Windows minidumps, Windows Prefetch, Delivery Optimization, Recycle Bin, Windows Update cleanup, and empty folders. Age limits are shown in each category’s description (for example, browser cache files newer than 7 days and Prefetch files newer than 30 days are left alone). Only specific known cache and cleanup locations are scanned; arbitrary application folders are not searched.

Regular selected files are sent to the Recycle Bin where possible. Delivery Optimization uses a Windows-managed cleanup command. FileSense does not directly delete Windows Update files; use **Settings → System → Storage → Cleanup recommendations** to review them. Emptying the Recycle Bin is permanent and requires a separate confirmation. Locked, inaccessible, protected, changed, symbolic-link, or reparse-point items are skipped. The scanner limits work to 5,000 candidates per category and 100,000 inspected entries per location; scan notices report skipped or limited areas.

FileSense does not clean browser history, cookies, passwords, clipboard contents, Windows network certificates, or general Windows event logs. These can contain personal data or be needed for security and diagnostics. Windows minidumps and Prefetch are optional because dumps can help diagnose crashes and clearing Prefetch may temporarily slow app launches.

## Startup Manager

Choose **Scan autoruns** to read the current Windows state. The module does not scan automatically on entry. Use the category tabs to filter:

- **Startup apps** — Startup-folder and Run/RunOnce entries.
- **Scheduled tasks** — tasks with startup or sign-in triggers.
- **Services** — services configured to start automatically or during boot.
- **Startup Approved** — Windows records indicating whether startup entries are allowed.
- **Policies** — startup-related policy entries; these are read-only.

Select an entry to inspect its publisher, signature, file status, command, arguments, source, and location. Impact is an estimate, not a measured boot-time test. Use Enable/Restore or Disable for supported entries. FileSense asks for confirmation where Windows or the entry requires it. Service changes use a separate advanced confirmation and can affect Windows or installed software; protected services cannot be changed. Rescan to refresh from Windows after changes.

## Results, sorting, and Recent Activity

Where a result table supports sorting, select a column heading to change the order. Empty result panels explain how to start or adjust the current search/scan. Recent Activity shows up to 30 recorded actions, such as scans and completed file operations; it is a local activity log, not a Windows event log.

## Trial and activation

FileSense includes a 30-day trial. The top bar shows the remaining days. To activate, open the license dialog from the top bar, copy the device code, and send it to ✉️ **[hello.prosoft.at@gmail.com](mailto:hello.prosoft.at@gmail.com)**. The ProSoft team will return a key for that device. Enter the key in the activation window. Activation works offline; FileSense does not send the code automatically. If the trial has ended, the activation window appears when the app opens.

The device code is tied to the Windows installation and may change after reinstalling Windows. Contact ✉️ **[hello.prosoft.at@gmail.com](mailto:hello.prosoft.at@gmail.com)** if you need a replacement.
