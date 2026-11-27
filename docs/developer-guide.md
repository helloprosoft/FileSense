# FileSense — Developer Guide

This guide is for maintaining, building, and issuing offline licenses for FileSense. The end-user documentation is in `docs/user-guide.md`; the app's in-app Read Me content is loaded from the root `README.md`. This developer guide is not bundled with the application.

## Project layout

- `FileSense.py` — small source-tree launcher; the application entry point is `src/filesense/application.py`.
- `src/filesense/` — application package containing feature modules, the QML bridge, licensing, and shared helpers.
- `qml/Main.qml` — Qt Quick shell, navigation, home cards, modern dark theme, dialogs, and feature screens.
- `tools/` — command-line and GUI utilities for issuing offline activation keys; not bundled in FileSense builds.
- `packaging/` — build script, PyInstaller spec and hook, version metadata, and Inno Setup script.
- `legal/EULA.txt` — end-user agreement shown by the installer.

## Run from source

Use Python 3.10 or newer on Windows. The application has one third-party runtime dependency: `PySide6`, listed in `requirements.txt`. The QML edition does not need Qt Creator, a separate Qt installation, or Qt Fluent Widgets. From this folder, install the runtime dependency and run the app:

```powershell
py -m pip install -r requirements.txt
py .\FileSense.py
```

The activation-key GUI is separate from the product app:

```powershell
py .\tools\activation_key_gui.py
```

It requires the project dependencies (especially PySide6) and the private key described below.

## Build and distribution

Run `packaging\build_exe.bat` to create the PyInstaller `onedir` output under `dist\FileSense`. Python 3.10 or newer is required on the build PC only; users do not need Python installed. The script creates an isolated `.venv-build` environment and installs the one runtime dependency (`PySide6`, pinned in `requirements.txt`) plus the build-only packager (`PyInstaller`, pinned in `packaging/requirements-build.txt`). The spec includes the app assets, QML files, README, and only the Qt Quick/QML runtime modules used by this app. It excludes QtWidgets from the exclusion list because the startup manager uses its file icon provider. Unused Qt modules and unused QML themes are omitted. The developer guide, activation utilities, and `developer_keys` are not packaged. Compile `packaging\installer.iss` with Inno Setup to package the complete `dist\FileSense` directory using solid LZMA2 compression at the maximum setting (`lzma2/max`). UPX is optional and is not installed as an extra prerequisite.

Do not distribute a lone `FileSense.exe` from an `onedir` build; distribute the installer or the complete `dist\FileSense` folder. The installer and complete portable folder include the bundled Python and Qt runtimes. Never build or distribute with the private signing key inside the packaged output.

## Publish a GitHub release

1. Update the version consistently in `packaging\version_info.txt`, `packaging\installer.iss`, and the application documentation, then review the release notes and user-facing guides.
2. Commit the source changes and create a version tag such as `v2.0.0`.
3. On a clean Windows build machine, run `packaging\build_exe.bat`, then compile `packaging\installer.iss` with Inno Setup. The installer is written to `installer\ProSoft-FileSense-Setup.exe`.
4. Create a GitHub Release for the version tag and attach `ProSoft-FileSense-Setup.exe` plus a zip of the complete `dist\FileSense` folder for portable use.
5. Verify the release page includes installation and update notes. Keep generated executables, `dist/`, `build/`, and signing keys out of Git commits.

## Offline trial and activation

### Product behavior

- `src/filesense/license_manager.py` starts a 30-day trial on first launch, displays remaining days on Home, and opens an activation gate after expiry.
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
   py .\tools\activation_key_gui.py
   ```

3. Enter the device code, select `developer_keys\FileSense_activation_private.pem` if it is not already selected, and click **Generate activation key**.
4. Copy the generated key and deliver it to the customer through your chosen channel. The app does not transmit it.
5. The customer pastes the key into FileSense and clicks **Activate**.

You can also issue a key from PowerShell:

```powershell
py .\tools\activation_key_tool.py --machine-code FS1-DEVICE-CODE
```

The key tool checks that the private key corresponds to the public modulus embedded in `src/filesense/license_manager.py`. If they do not match, it refuses to issue a key.

### Protect the signing key

The RSA private key is stored at `developer_keys\FileSense_activation_private.pem` on this developer workspace. `.gitignore` excludes PEM files in `developer_keys`, and the build script does not bundle that folder. Keep a secure, access-controlled backup; never send the private key to a customer or place it in a release archive. Anyone with it can issue licenses for every device.

If the private key is lost, existing activations continue to verify, but you cannot issue new keys. If it is exposed, generate a replacement RSA key pair and update `RSA_PUBLIC_MODULUS` in `src/filesense/license_manager.py` to the replacement public modulus before rebuilding. Existing keys signed with the old private key will no longer verify in that build, so plan a customer reactivation path before rotating.

For a deliberate key rotation, with OpenSSL available on the developer PC:

```powershell
New-Item -ItemType Directory -Force developer_keys
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out developer_keys\FileSense_activation_private.pem
openssl pkey -in developer_keys\FileSense_activation_private.pem -pubout -out developer_keys\FileSense_activation_public.pem
openssl rsa -pubin -in developer_keys\FileSense_activation_public.pem -modulus -noout
```

Replace the hexadecimal value in `RSA_PUBLIC_MODULUS` with the printed modulus (without `Modulus=`), keep exponent `65537`, and rebuild. Do not rotate just to create a customer key; the existing private key already matches the app.

### Key requirements

The key utility reads an unencrypted RSA PKCS#8 or PKCS#1 PEM with at least 2048 bits and public exponent 65537. The signing key is handled locally. `src/filesense/license_manager.py` and `tools/activation_key_tool.py` use the Python standard library, so the FileSense app does not need a separate cryptography package.

## Configuration notes

- Change the trial duration in `src/filesense/license_manager.py` (`TRIAL_DAYS`).
- The signing public modulus and exponent are constants in `src/filesense/license_manager.py`; a new key pair requires updating the modulus and rebuilding the app.
- `packaging\build_exe.bat` invokes `packaging\FileSense.spec` to build the PyInstaller `onedir` package. The spec is the sole source of packaging configuration.
- Keep `docs/`, `developer_keys/`, and build tooling out of the packaged data. Only the root `README.md` is bundled for the in-app Read Me screen.
