# FileSense — Developer Guide

This guide is for maintaining, building, and issuing offline licenses for FileSense. The end-user documentation is in `docs/user-guide.md`; the app's in-app Read Me content is loaded from the root `README.md`. This developer guide is not bundled with the application.

## Project layout

- `FileSense.py` — QGuiApplication + QQmlApplicationEngine entry point.
- `qml/Main.qml` — Qt Quick shell, navigation, home cards, modern dark theme, dialogs, and feature screens.
- `qml_backend.py` — QObject slots/properties that connect QML to Python scans and file operations.
- `file_organizer.py` — Quick Organize and custom file rules.
- `duplicate_finder.py` — duplicate scans and duplicate-rule builder.
- `storage_analyzer.py` — drive/folder analysis and extension breakdown.
- `startup_manager.py` — startup apps, scheduled tasks, services, Startup Approved, and policy entries.
- `junk_cleaner.py` — categorized cleanup scans and execution.
- `file_search.py` — filename search and optional filters.
- `home_interface.py`, `app_common.py`, `activity_log.py` — home page, shared UI/helpers, and recent activity/readme dialogs.
- `license_manager.py`, `license_dialog.py` — trial state, device code, key verification, and activation prompt.
- `activation_key_tool.py` — command-line offline key issuer.
- `activation_key_gui.py` — desktop GUI for issuing keys; developer tool only, not included in FileSense builds.

## Run from source

Use Python 3.10 or newer on Windows. The application has one third-party runtime dependency: `PySide6`, listed in `requirements.txt`. The QML edition does not need Qt Creator, a separate Qt installation, or Qt Fluent Widgets. From this folder, install the runtime dependency and run the app:

```powershell
py -m pip install -r requirements.txt
py .\FileSense.py
```

The activation-key GUI is separate from the product app:

```powershell
py .\activation_key_gui.py
```

It requires the project dependencies (especially PySide6) and the private key described below.

## Build and distribution

Run `build_exe.bat` to create the PyInstaller `onedir` output under `dist\FileSense`. Python 3.10 or newer is required on the build PC only; users do not need Python installed. The script creates an isolated `.venv-build` environment and installs the one runtime dependency (`PySide6`, pinned in `requirements.txt`) plus the build-only packager (`PyInstaller`, pinned in `requirements-build.txt`). The spec includes the app assets, QML files, README, and only the Qt Quick/QML runtime modules used by this app. It excludes QtWidgets from the exclusion list because the startup manager uses its file icon provider. Unused Qt modules and unused QML themes are omitted. The developer guide, activation GUI, key-generation script, and `developer_keys` are not packaged. `installer.iss` packages the complete `dist\FileSense` directory into the Windows installer using solid LZMA2 compression at the maximum setting (`lzma2/max`). UPX is optional and is not installed as an extra prerequisite.

Do not distribute a lone `FileSense.exe` from an `onedir` build; distribute the installer or the complete `dist\FileSense` folder. The installer and complete portable folder include the bundled Python and Qt runtimes. Never build or distribute with the private signing key inside the packaged output.

## Publish a GitHub release

1. Update the version consistently in `version_info.txt`, `installer.iss`, and the application documentation, then review the release notes and user-facing guides.
2. Commit the source changes and create a version tag such as `v2.0.0`.
3. On a clean Windows build machine, run `build_exe.bat`, then compile `installer.iss` with Inno Setup. The installer is written to `installer\ProSoft-FileSense-Setup.exe`.
4. Create a GitHub Release for the version tag and attach `ProSoft-FileSense-Setup.exe` plus a zip of the complete `dist\FileSense` folder for portable use.
5. Verify the release page includes installation and update notes. Keep generated executables, `dist/`, `build/`, and signing keys out of Git commits.

## Offline trial and activation

### Product behavior

- `license_manager.py` starts a 30-day trial on first launch, displays remaining days on Home, and opens an activation gate after expiry.
- The device code is `FS1-` plus a shortened Base32 SHA-256 fingerprint of the Windows `MachineGuid` and product name. It is install-bound; reinstalling Windows may change it. It does not include the user's name or files.
- QSettings use `HKCU\Software\ProSoft\FileSense`. On startup, missing preferences are migrated from the former `HKCU\Software\ProSoft\FileOrganizer` key; the old key is left intact.
- Trial data is written to the `license_trial_state` value in `HKCU\Software\ProSoft\FileSense` and `%LOCALAPPDATA%\ProSoft\FileSense\trial.json`. The app compares both copies and flags clock rollback.
- A successful key is stored as `license_activation_key` in `HKCU\Software\ProSoft\FileSense`.
- Keys are perpetual, signed locally with RSA/SHA-256 PKCS#1 v1.5, and contain the product ID plus device code. The app uses a built-in public modulus to verify the signature; no network call is made.
- Trial data is user-editable. Since licensing must work offline, a determined user with control of the PC can reset local trial state or patch the app. This is tamper resistance against casual resets, not server-enforced DRM.

### Issue an activation key

1. Ask the customer to open activation from the top-bar license badge or **Buy me a Coffee** button, then send you the displayed device code. The dialog's **Copy** button copies it.
2. On the developer PC, open the generator from the project root:

   ```powershell
   py .\activation_key_gui.py
   ```

3. Enter the device code, select `developer_keys\FileSense_activation_private.pem` if it is not already selected, and click **Generate activation key**.
4. Copy the generated key and deliver it to the customer through your chosen channel. The app does not transmit it.
5. The customer pastes the key into FileSense and clicks **Activate**.

You can also issue a key from PowerShell:

```powershell
py .\activation_key_tool.py --machine-code FS1-DEVICE-CODE
```

The key tool checks that the private key corresponds to the public modulus embedded in `license_manager.py`. If they do not match, it refuses to issue a key.

### Protect the signing key

The RSA private key is stored at `developer_keys\FileSense_activation_private.pem` on this developer workspace. `.gitignore` excludes PEM files in `developer_keys`, and the build script does not bundle that folder. Keep a secure, access-controlled backup; never send the private key to a customer or place it in a release archive. Anyone with it can issue licenses for every device.

If the private key is lost, existing activations continue to verify, but you cannot issue new keys. If it is exposed, generate a replacement RSA key pair and update `RSA_PUBLIC_MODULUS` in `license_manager.py` to the replacement public modulus before rebuilding. Existing keys signed with the old private key will no longer verify in that build, so plan a customer reactivation path before rotating.

For a deliberate key rotation, with OpenSSL available on the developer PC:

```powershell
New-Item -ItemType Directory -Force developer_keys
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out developer_keys\FileSense_activation_private.pem
openssl pkey -in developer_keys\FileSense_activation_private.pem -pubout -out developer_keys\FileSense_activation_public.pem
openssl rsa -pubin -in developer_keys\FileSense_activation_public.pem -modulus -noout
```

Replace the hexadecimal value in `RSA_PUBLIC_MODULUS` with the printed modulus (without `Modulus=`), keep exponent `65537`, and rebuild. Do not rotate just to create a customer key; the existing private key already matches the app.

### Key requirements

The key utility reads an unencrypted RSA PKCS#8 or PKCS#1 PEM with at least 2048 bits and public exponent 65537. The signing key is handled locally. `license_manager.py` and `activation_key_tool.py` use the Python standard library, so the FileSense app does not need a separate cryptography package.

## Configuration notes

- Change the trial duration in `license_manager.py` (`TRIAL_DAYS`).
- The signing public modulus and exponent are constants in `license_manager.py`; a new key pair requires updating the modulus and rebuilding the app.
- `build_exe.bat` uses the version-controlled `FileSense.spec` to build the PyInstaller `onedir` package. Keep the batch file and spec synchronized by using the spec as the sole source of packaging configuration.
- Keep `docs/`, `developer_keys/`, and build tooling out of the packaged data. Only the root `README.md` is bundled for the in-app Read Me screen.
