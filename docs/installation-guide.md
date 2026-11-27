# FileSense Installation Guide

FileSense is a Windows desktop application. The released installer and portable package include the runtime needed to run the app; Python is not required on the computer where FileSense is used.

## System requirements

- Windows 10 or Windows 11, 64-bit.
- Administrator approval for installing to the default Program Files location.
- Free disk space for the application and its bundled Qt/Python runtime. The exact package size is listed with each GitHub release.

## Install with the Windows installer

1. Open the repository's **Releases** page on GitHub and download `ProSoft-FileSense-Setup.exe` from the release assets.
2. Open the downloaded installer. If Windows displays a security prompt, verify that the file came from the expected ProSoft GitHub release before continuing.
3. Follow the setup wizard. The default installation location is `C:\Program Files\ProSoft\FileSense`.
4. Optionally choose the desktop shortcut task.
5. Finish setup and launch **ProSoft - FileSense** from the Start menu or desktop shortcut.

The installer requests administrator approval so it can install under Program Files. FileSense itself can be opened as a normal user. Some Startup Manager changes may require administrator privileges; if Windows denies a change, close FileSense, reopen it with **Run as administrator**, and retry that action.

## Run the portable package

1. Download the complete `FileSense` portable folder/archive from the GitHub release, if one is provided.
2. Extract or copy the entire folder to a location you can access.
3. Run `FileSense.exe` inside that folder.

Keep the folder structure intact. The executable depends on the runtime files next to it; copying only `FileSense.exe` will not work.

## Update FileSense

Download and run the newer setup file from the GitHub Releases page. Setup installs the new version over the current installation. To preserve your preferences and license state, do not remove the FileSense settings from your Windows user profile. Check the release notes for version-specific changes.

## Uninstall

1. Open **Settings → Apps → Installed apps** in Windows, or use **Apps and Features**.
2. Select **ProSoft - FileSense** and choose **Uninstall**.
3. Confirm the prompt and follow the uninstaller.

The portable version has no installer entry; close the app and delete its folder to remove the program files.

## Run from source (developers)

End users should use the installer or portable release. To run the source checkout, use Windows with Python 3.10 or newer, then from the project folder:

```powershell
py -m pip install -r requirements.txt
py .\FileSense.py
```

To build a distributable package, run `packaging\build_exe.bat` on a Windows build machine with Python 3.10 or newer. This is a build-time requirement only; the resulting installer and portable package include their runtime. See the [Developer Guide](developer-guide.md) for developer and release details.

## Troubleshooting

- **Windows says a file is missing:** confirm you extracted the full portable package or rerun the installer. Do not launch a lone executable copied out of the package.
- **An autorun change is denied:** that particular Windows startup setting may require elevation. Reopen FileSense with **Run as administrator** and retry.
- **Windows blocks the downloaded installer:** download it again from the project's official GitHub Releases page and review the repository's release information. Do not bypass a security warning for a file whose origin you cannot verify.
- **A scan reports inaccessible items:** some system-protected or in-use paths cannot be read by a normal user. Review scan notices; run with elevated privileges only when needed and appropriate.

For feature usage and the behavior of scans, filters, rules, and cleanup actions, see the [User Guide](user-guide.md).
