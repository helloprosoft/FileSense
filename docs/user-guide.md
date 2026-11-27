# FileSense User Guide

**One smarter way to manage your PC.**

FileSense provides tools to organize files, find same-name entries, inspect disk usage, manage startup entries, review cleanup candidates, and search for files. Scans and searches are started manually; opening a module does not begin one.

> **Safety note:** Review previews and selections before applying file operations. FileSense skips inaccessible paths and symbolic links in supported scans. Some Windows startup settings require administrator privileges.

## Home

Home provides shortcuts to File Organizer, Storage Analyzer, File Search & Finder, Duplicate Finder, Junk Cleaner, and Startup Manager. Opening Home does not scan the computer.

## File Organizer

File Organizer provides **Quick Organize** and **Build a Rule**. Both show a preview before changing files.

### Quick Organize

1. Choose a source folder and optionally exclude folders inside it.
2. Enable **Include subfolders** if nested folders should be scanned.
3. Choose the default conflict action and select **Preview**.
4. Review the proposed destinations and conflict actions. A conflicting file can have its own action, overriding the default for that file.
5. Select **Organize files** and confirm.

Files are grouped into Compressed, Video, Audio, Images, Documents, or Programs based on their extensions. Unrecognized extensions go into **Others**. Category folders are created under the selected source folder when needed.

Conflict actions:

- **Keep both** preserves the existing destination and gives the incoming file a numbered name.
- **Skip** leaves the incoming file in its source location.
- **Replace** replaces the destination file after confirmation.

The operation checks files again before acting. If a source file has disappeared, become ineligible, or is now excluded, it is skipped.

### Build a Rule

1. Add one or more existing monitored source folders. Separate typed paths with semicolons. Set **Include subfolders** to scan nested folders.
2. Add one or more conditions and arrange them in evaluation order.
3. Choose **Move file**, **Copy file**, or **Delete file**. Move and Copy need an existing destination folder. Delete sends matching files to the Windows Recycle Bin.
4. Set the default conflict action, select **Preview**, review the results, then select **Run rule** and confirm.

Only files that match the conditions appear in the preview. Existing destination conflicts show the proposed action. You can choose a different action on an individual conflict row; changing the default updates the rows that use the default. The app rechecks file existence and conditions before applying the operation.

#### Rule conditions

| Field | Available checks and notes |
|---|---|
| **File Type** | Is, Is not, Contains, Does not contain. Uses categories such as Images and Documents. |
| **File Extension** | Is, Is not, Contains, Does not contain. Enter extensions such as `.png` or `.tar.gz`. Is checks the filename ending. |
| **File Size** | Is, Is not, Greater than, Less than, At least, At most. Choose B, KB, MB, or GB. |
| **File Name** | Contains, Does not contain, Starts with, Ends with, Matches exact text, Matches pattern (advanced). Ends with checks the name before its final extension; entering `1` matches `photo1.png`. Exact text includes the extension. |
| **File Date** | Select Date created, Date modified, or Date last accessed, then Before, After, Between, Within last, Older than, or Newer than. Enter dates as MM-DD-YYYY. |

Conditions run top to bottom. The first condition establishes a match; each following connector combines the result with the next condition. **AND** requires both, **OR** accepts either, and **NOT** means the current result and not the next condition. There are no parentheses.

Example: `File Type Is Images` **AND** `File Size Greater than 10 MB` **NOT** `File Name Ends with screenshot` finds large image files whose base name does not end in `screenshot`.

**Matches pattern (advanced)** uses case-insensitive wildcards against the complete filename, including extension. `report-*.pdf` matches `report-january.pdf`; `photo?.jpg` matches `photo1.jpg` but not `photo12.jpg`. `*` represents any sequence of characters, and `?` represents one character.

All condition fields need values. At least one condition is required. If no files match, the preview explains that there are no matching files; no operation is applied.

## Storage Analyzer

1. Choose a drive or browse to a folder.
2. Select **Scan storage**. Changing tabs reuses the scan data and does not start another scan.
3. Review the capacity, used-space, free-space, and scan summary, then choose a results tab:
   - **Folder Breakdown** shows folders, logical size, estimated allocated size, file/folder counts, and share of the parent. Expand folders to inspect their contents. Selected items can be sent to the Recycle Bin after confirmation.
   - **File Types (Extensions)** summarizes usage by extension and type. The share bars use allocated-size totals; very small extensions may be omitted from the chart.
   - **Treemap View** shows the scanned hierarchy as size-proportional rectangles. Hover for details, double-click folders to explore, and use breadcrumbs to move back. Sort, folder depth, and metric (Size, File Count, Allocated Space) affect the display only. Treemap is view-only and has an independent selection state from Folder Breakdown.

Used Space is calculated from Windows volume capacity minus free space. Logical size sums file lengths; allocated size is estimated from allocation units and may differ from Windows' exact accounting. Inaccessible paths are omitted and included in scan notices.

## File Search & Finder

1. Enter one or more existing drive or folder paths separated by semicolons, or use **Add drive** or **Browse**.
2. Optionally add excluded folders and filters.
3. Select **Search**. At least one filter is required; an empty filter set is rejected so the app does not search everything accidentally.

Filters include filename text, extensions, file types, minimum/maximum size, created dates, and modified dates. Different filter fields combine with **AND**. Multiple selected file types or comma-separated extensions match if any selected value matches. Size limits include their endpoints. Dates use MM-DD-YYYY and include the end date.

The filename filter is a case-insensitive substring. Extension filters match filename endings. Type options are Compressed, Video, Audio, Images, Documents, Programs, and Other. A filename-only search can return matching folders; file type, extension, size, and date filters return files. A drive root is scanned recursively even when **Include subfolders** is off; for a selected folder, that option controls nested-folder traversal. Symbolic links are skipped. Results are limited to 10,000 entries.

Select results to Copy, Move, or Delete. Delete sends selected files to the Recycle Bin after confirmation. Double-click a result to open its location.

## Duplicate Finder

Add one or more folders, choose whether to include subfolders, and select **Scan duplicates**. Duplicate Finder groups **files with the same name**, ignoring letter case. It does not compare file contents, so matching names do not guarantee identical files. Sizes are shown to help review candidates.

The **Build a rule** tab can restrict the scan by File Type or File Extension. Conditions are evaluated in order with AND, OR, and NOT connectors. For example, `File Type Is Images` AND `File Extension Is .png` includes PNG images only. Each tab keeps its own results.

Select entries to send to the Recycle Bin; unchecked entries are kept. Leave at least one copy unchecked in each group that you want to retain. Review nested folder selections before deleting.

## Junk Cleaner

Select **Scan cleanup** or **Rescan** to inspect configured cleanup locations. Scanning is manual. Candidates are grouped into Recommended items and Other system/application items. Recommended candidates start preselected; use group, category, and item checkboxes to adjust the selection. Review selected sizes and items before choosing **Clean selected**.

Categories can include temporary files, thumbnail and DirectX caches, Windows Error Reporting, supported browser caches, FileSense cache/log files, NVIDIA and Python pip caches when their known locations exist, minidumps, Prefetch, Delivery Optimization, Recycle Bin, Windows Update cleanup, and empty folders. FileSense scans known locations rather than searching arbitrary application folders. Some categories apply age limits; category descriptions and skipped/info counts provide additional context.

Regular selected files are sent to the Recycle Bin where possible. Delivery Optimization uses a Windows-managed cleanup command. FileSense does not directly delete Windows Update files; review those through Windows Settings. Emptying the Recycle Bin is permanent and requires an additional confirmation. Locked, inaccessible, protected, changed, symbolic-link, or reparse-point items may be skipped. Scans use candidate and traversal limits and report notices for skipped or limited areas.

FileSense does not clean browser history, cookies, passwords, clipboard contents, Windows network certificates, or general Windows event logs. These may contain personal data or be needed for security and diagnostics. Minidumps and Prefetch are optional because dumps can help diagnose crashes and clearing Prefetch can temporarily slow app launches.

## Startup Manager

Select **Scan autoruns** to read the current Windows state. The module does not scan automatically when opened. Use the tabs to filter:

- **Startup apps** — Startup-folder and Run/RunOnce entries.
- **Scheduled tasks** — tasks with startup or sign-in triggers.
- **Services** — services configured to start automatically or during boot.
- **Startup Approved** — Windows records of whether startup entries are allowed.
- **Policies** — startup-related policy entries; these are read-only.

Select an entry to review its publisher, signature, file status, command, arguments, source, and location. Impact is an estimate, not a measured boot-time test. Use **Disable** or **Enable / Restore** for supported entries. Service changes use a separate confirmation; protected services cannot be changed. Some entries are protected by Windows permissions. If Windows denies a change, FileSense identifies the selected entry and asks you to reopen FileSense with **Run as administrator**, then retry. Rescan to refresh the displayed state.

## Results, sorting, and Recent Activity

Where supported, select a result-column heading to sort by that value. Empty result panels explain how to start or adjust a scan or search. Recent Activity shows up to 30 recorded FileSense actions; it is a local app activity log, not a Windows event log.

## Trial and activation

FileSense includes a 30-day trial. The top bar shows the remaining days. To activate, open the license dialog from the top bar, copy the device code, and email it to [hello.prosoft.at@gmail.com](mailto:hello.prosoft.at@gmail.com). ProSoft returns a key for that device. Enter the key in the activation window. Activation works offline; FileSense does not send the code automatically. If the trial has ended, the activation window appears when the app opens.

The device code is tied to the Windows installation and can change after reinstalling Windows. Contact [hello.prosoft.at@gmail.com](mailto:hello.prosoft.at@gmail.com) if you need a replacement key.
