# YubiKey Locker — Windows removal-event fork
[![main - tests and build](https://github.com/roryvossepoel/yubikey-locker/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/roryvossepoel/yubikey-locker/actions/workflows/ci.yml)

This fork of [Sciber YubiKey Locker](https://github.com/sciber-io/yubikey-locker)
locks Windows on actual USB YubiKey removal. Signing in without a key remains
possible, including local administrator troubleshooting. Original attribution
and MIT license are retained.

**This fork targets Windows only.** We build and publish Windows x64 packages.
Linux/macOS source is retained for upstream continuity, but is not maintained,
validated or offered as a supported release here. For those platforms, use the
[original Sciber project](https://github.com/sciber-io/yubikey-locker).

PR test installers are available from the Windows artifact in this repository's
[Actions](https://github.com/roryvossepoel/yubikey-locker/actions). A successful build
is not a substitute for the physical Windows validation below.

<img src="images/sciber_yklocker.png" alt="YubiKey Autolocker by Sciber" width="250"/>




### Actions on YubiKey removal
Choose Lock Computer, Log Out User, or Nothing via computer policy.

### Application logs
```powershell
Get-EventLog -LogName Application -Source YubiKeyLocker | Select TimeGenerated,ReplacementStrings
```

## Installation via Intune
### Windows
1. Download the .admx and .adml files from [src/windows_utils/Administrative template (ADMX)/](src/windows_utils/Administrative%20template%20(ADMX)/)
2. Intune/GPO: Follow Jonas guide on his blog: https://swjm.blog/locking-the-workstation-on-fido2-security-key-removal-part-2-80962c944c78 to set up GPO/Intune control to decide what you want to do if the YubiKey is removed.
## Manual Installation
### Windows
1. Download and execute yubikey-locker.msi from [releases](https://github.com/roryvossepoel/yubikey-locker/releases)
#### Set registry values

1. Download the .admx and .adml files from [src/windows_utils/Administrative template (ADMX)/](src/windows_utils/Administrative%20template%20(ADMX)/) to `C:\Windows\PolicyDefinitions`
2. Start "local group policy editor" from Control Panel -> "Edit group policy" and navigate to:
  - "Computer Configuration"
    - "Administrative Templates"
      - "Sciber YubiKey Locker Settings"
        - Turn on to set registry values

## Default behavior
### Windows (this fork)
The service listens for native USB arrival/removal notifications. It performs the
configured `RemovalOption` once when a YubiKey is disconnected, without periodic
YubiKey scans. Keys already connected when the service starts are covered because
the removal event identifies the device itself.

- Starting the service or signing in without a key does **not** lock the computer.
- Removing a key locks/logs out the active local console session once.
- Signing in again without a key does not cause repeated locking.
- Reconnecting the same key rearms its removal action.
- Other USB devices and duplicate removal notifications are ignored. Removing
  either of two connected YubiKeys triggers the action, even if another remains.
- `RemovalOption` retains its existing registry path and Lock/Logout/doNothing
  values. It is read for each removal. The default remains doNothing.
- `Timeout` has been removed from the Windows code and ADMX. Existing registry
  values may remain but are never read; actions are immediate.
- Pending events are discarded on session transitions, service stop, or if they
  are more than five seconds old. They are never deliberately retargeted to a
  newly active session. Failures are logged without stopping the listener.

This is USB removal detection, not verification of which key authenticated the
user. It allows any Windows sign-in method permitted by your policies, for all
accounts. RDP/NFC removal is not covered. Disconnecting a dock containing a key,
or a USB device reset/reconfiguration reported as removal, can also trigger it.

### Windows validation before deployment
Build the Windows MSI and test on a physical Windows PC:
1. Set RemovalOption to Lock, sign in as a local administrator without a key and
   wait at least a minute: the session must remain usable.
2. Connect/remove a key: expect one immediate lock. Sign in without the key and
   confirm there is no repeated lock.
3. Restart the service with a key attached, then remove it: expect one lock.
4. Repeat insert/remove; test FIDO-only and composite OTP/FIDO/CCID configurations,
   unrelated USB devices, two keys, dock removal, and sleep/resume.
5. Test switching users and lock/unlock around removal. No queued action should
   affect the newly active session. Also test doNothing and Logout policies.
6. Check Application log entries from YubiKeyLocker and verify service stop/start.

The automated tests mock Windows APIs; physical USB and session tests are still
required before production deployment.






### Credits
Special thanks to [Jonas Markström](https://github.com/JMarkstrom/) for valuable feedback and support during this project.


For information regarding how to continue development and build your own binaries see [README-development.md](README_development.md)


## Windows policy and upgrade notes (1.0.2.0)

The supplied ADMX/English ADML configure a **computer** policy with one setting:
`RemovalOption` = `Lock`, `Logout`, or `doNothing`. Disabled or unconfigured means
no action. Only HKLM is read; HKCU policy was never used by the service.

For local Group Policy, copy SciberYklocker.admx to
`C:\Windows\PolicyDefinitions` and SciberYklocker.adml to its `en-US` subfolder.
Enable the policy under Computer Configuration > Administrative Templates >
Sciber YubiKey Locker Settings and select Lock. For Intune, import the matching
ADMX/ADML pair and assign the computer setting to a test device group first.
Existing imported templates/profiles may need to be replaced to remove the old
required Timeout field; do not delete production assignments before preparing
the replacement. Existing RemovalOption registry values remain compatible.

For a manual test, run in elevated PowerShell:

```powershell
$Path = 'HKLM:\SOFTWARE\Policies\Sciber\YubiKey Removal Behavior'
New-Item -Path $Path -Force | Out-Null
New-ItemProperty -Path $Path -Name RemovalOption -PropertyType String -Value Lock -Force | Out-Null
Restart-Service YubiKeyLocker
Get-Service YubiKeyLocker
```

Upgrade by installing the new MSI over the test version. Restarting the service
without upgrading does not remove the obsolete Timeout read in 1.0.1.0.
The new version does not log a registry error for absent optional policy values.
Policy changes are read on the next removal event; service restart is not required
for a change to RemovalOption. To disable actions manually, set it to doNothing.

The fork's MSI/EXE are not code-signed by this workflow. If App Control blocks the
build, use your normal signing/allowlisting process; do not disable App Control.
