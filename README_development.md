# Windows development

This fork builds, tests and publishes Windows x64 packages with Python 3.13.
Linux/macOS source remains for upstream continuity, but is outside the supported
scope. Refer to the [original project](https://github.com/sciber-io/yubikey-locker)
for those platforms.

The workflow is in [.github/workflows/ci.yml](.github/workflows/ci.yml).

```powershell
python -m venv .venv
.venv/Scripts/Activate.ps1
python -m pip install tox
python -m pip install -e .
python -m tox
python -m tox -e build_win
```

The executable is created in `dist/`. The workflow builds the MSI with WiX 5,
waits for installation to complete and checks its exit code. PR/manual builds
upload a Windows artifact; release builds publish only the MSI, EXE, matching
ADMX/ADML, README and license. Physical USB/session testing remains necessary.

The Windows MSI version is defined in
[src/windows_utils/yubikey-locker.wxs](src/windows_utils/yubikey-locker.wxs).
Update the MSI version when distributing changed binaries. Install the MSI to
register and start the `YubiKeyLocker` Windows service.
