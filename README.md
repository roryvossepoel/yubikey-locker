# Sciber YubiKey Locker
[![main - tests and build](https://github.com/sciber-io/yubikey-locker/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/sciber-io/yubikey-locker/actions/workflows/ci.yml)

For YubiKey users to enable automatic device locking when removing the YubiKey.

<img src="images/sciber_yklocker.png" alt="YubiKey Autolocker by Sciber" width="250"/>




### Actions on YubiKey removal (Windows) or absence (macOS/Linux)
| Action        | Windows   | Mac  | Linux (Ubuntu)  |
| ---           | ---       | ---  | ---    |
| Nothing       | ✅       | ✅   | ✅    |
| Lock Computer | ✅       | ✅   | ✅    |
| Log Out User  | ✅       | ✅   | ✅    |

### Available installation instructions
| Method        | Windows   | Mac   | Linux (Ubuntu) |
| ---           | ---       | ---  | ---    |
| Intune        | ✅       | ✅   | ❌
| Manual        | ✅       | ✅   | ✅    |

### How to inspect application logs:
Windows: ```Get-EventLog -LogName Application -Source YubiKeyLocker | Select TimeGenerated,ReplacementStrings ```
Mac:   ```log show --predicate 'process = "yubikey-locker-macos"' ```
Linux (Ubuntu):  ```cat /var/log/syslog | grep yubikey-locker ```


## Installation via Intune
### Windows
1. Download the .admx and .adml files from [src/windows_utils/Administrative template (ADMX)/](src/windows_utils/Administrative%20template%20(ADMX)/)
2. Intune/GPO: Follow Jonas guide on his blog: https://swjm.blog/locking-the-workstation-on-fido2-security-key-removal-part-2-80962c944c78 to set up GPO/Intune control to decide what you want to do if the YubiKey is removed.
### Mac
1. Add an macOS app, upload yubikey-locker-macos.pkg
2. Add the contents of [src/macos_utils/post_install_script.sh](src/macos_utils/post_install_script.sh) to the post-install-script box in Intune
3. Depending on the groups that the app is pushed to, change contents of the post-install-script to pass apropriate arguments to the application


## Manual Installation
### Windows
1. Download and execute yubikey-locker.msi from [releases](https://github.com/sciber-io/yubikey-locker/releases)
#### Set registry values

1. Download the .admx and .adml files from [src/windows_utils/Administrative template (ADMX)/](src/windows_utils/Administrative%20template%20(ADMX)/) to `C:\Windows\PolicyDefinitions`
2. Start "local group policy editor" from Control Panel -> "Edit group policy" and navigate to:
  - "Computer Configuration"
    - "Administrative Templates"
      - "Sciber YubiKey Locker Settings"
        - Turn on to set registry values

### Mac
1. Download and execute yubikey-locker-macos.pkg from [releases](https://github.com/sciber-io/yubikey-locker/releases)
2. Download, modify script content if necessary, and execute [src/macos_utils/post_install_script.sh](src/macos_utils/post_install_script.sh)
3. Perform a logout or a reboot

### Linux (Ubuntu)
1. Download yubikey-locker-linux from [releases](https://github.com/sciber-io/yubikey-locker/releases) into  `/home/<your-user>/.sciber/yubikey-locker-linux `
2. Download [src/linux_utils/yubikey-locker.service](src/linux_utils/yubikey-locker.service) to `/etc/systemd/user/yubikey-locker.service`
3. Modify the service file to specify the correct path to the binary
4. Enable the service to start on reboot:  ```systemctl enable yubikey-locker --user ```
5. Start the service:  ```systemctl start yubikey-locker --user ```



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
- `Timeout` is retained for policy compatibility but is ignored on Windows;
  removal actions are immediate, with no configured grace period.
- Pending events are discarded on session transitions, service stop, or if they
  are more than five seconds old. They are never deliberately retargeted to a
  newly active session. Failures are logged without stopping the listener.

This is USB removal detection, not verification of which key authenticated the
user. It allows any Windows sign-in method permitted by your policies, for all
accounts. RDP/NFC removal is not covered. Disconnecting a dock containing a key,
or a USB device reset/reconfiguration reported as removal, can also trigger it.

### macOS / Linux
These platforms retain their existing periodic presence checks (10 seconds by
default). Without an action configured, the application does nothing.

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






### Comand line options for Linux/MacOS
```bash
# Run yubikey-locker
# Defaults to doNothing with the device after 10 seconds without a YubiKey
yubikey-locker

# Optional arguments:
# Set removalOption
-l Lock|Logout|doNothing

# Set timeout
-t 20

# Example
yubikey-locker -l Logout -t 30
```


### Credits
Special thanks to [Jonas Markström](https://github.com/JMarkstrom/) for valuable feedback and support during this project.


## Known Issues
[MacOS: The check for the Yubikey may cause issues with gpg](https://github.com/sciber-io/yubikey-locker/issues/78)
____
For information regarding how to continue development and build your own binaries see [README-development.md](README_development.md)
