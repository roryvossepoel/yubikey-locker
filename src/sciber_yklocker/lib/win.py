import socket
import winreg
from queue import Empty, Queue
from time import monotonic

import servicemanager
import win32api
import win32con
import win32event
import win32gui
import win32gui_struct
import win32process
import win32profile
import win32service
import win32serviceutil
import win32ts

from sciber_yklocker.models.removal_events import RemovalEvents
from sciber_yklocker.models.removaloption import RemovalOption

GUID_DEVINTERFACE_USB_DEVICE = "{A5DCBF10-6530-11D2-901F-00C04FB951ED}"

REG_REMOVALOPTION = "RemovalOption"
REG_TIMEOUT = "Timeout"
REG_PATH = r"SOFTWARE\\Policies\\Sciber\\YubiKey Removal Behavior\\"


def log_message(msg: str) -> None:
    servicemanager.LogInfoMsg(msg)


def lock_system(
    removal_option: RemovalOption, session_id=None, still_current=None
) -> None:
    # Capture a token for the event's session, never retarget a queued action.
    if removal_option == RemovalOption.NOTHING:
        return
    if session_id is None:
        session_id = win32ts.WTSGetActiveConsoleSessionId()
    console_user_token = win32ts.WTSQueryUserToken(session_id)
    try:
        startup = win32process.STARTUPINFO()
        startup.lpDesktop = "winsta0\\default"
        environment = win32profile.CreateEnvironmentBlock(console_user_token, False)
        system_dir = win32api.GetSystemDirectory()
        if removal_option == RemovalOption.LOCK:
            command = f'"{system_dir}\\rundll32.exe" user32.dll,LockWorkStation'
        elif removal_option == RemovalOption.LOGOUT:
            command = f'"{system_dir}\\logoff.exe"'
        else:
            return
        if still_current is not None and not still_current():
            return
        process, thread, _, _ = win32process.CreateProcessAsUser(
            console_user_token,
            None,
            command,
            None,
            None,
            False,
            win32con.NORMAL_PRIORITY_CLASS,
            environment,
            None,
            startup,
        )
        win32api.CloseHandle(thread)
        win32api.CloseHandle(process)
    finally:
        win32api.CloseHandle(console_user_token)


# Windows Service Class Definition
class AppServerSvc(win32serviceutil.ServiceFramework):
    _svc_name_ = "YubiKeyLocker"
    _svc_display_name_ = "Sciber YubiKey Locker"

    def __init__(self, args) -> None:
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.hDeviceEvent = win32event.CreateEvent(None, 0, 0, None)
        self.device_events = Queue()
        self.removals = RemovalEvents()
        self.session_generation = 0
        self.stopping = False
        socket.setdefaulttimeout(60)

    def SvcStop(self) -> None:
        self.stopping = True
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self) -> None:
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        from sciber_yklocker.main import init_yklocker

        # instantiate a yklocker-object and start running the code
        yklocker = init_yklocker(None, None)
        yklocker.set_service_object(self)

        # To handle service interruptions etc, pass the win service class instance along
        self.run_device_events(yklocker)

    def GetAcceptedControls(self):
        # Device notifications are enabled by registration, not an ACCEPT bit.
        return super().GetAcceptedControls() | win32service.SERVICE_ACCEPT_SESSIONCHANGE

    def SvcOtherEx(self, control, event_type, data):
        if control == win32service.SERVICE_CONTROL_SESSIONCHANGE:
            # Invalidate pending actions on lock/unlock, logon/logoff or switch.
            self.session_generation += 1
            return
        if self.stopping or control != win32service.SERVICE_CONTROL_DEVICEEVENT:
            return
        if event_type not in (
            win32con.DBT_DEVICEARRIVAL,
            win32con.DBT_DEVICEREMOVECOMPLETE,
        ):
            return
        try:
            info = win32gui_struct.UnpackDEV_BROADCAST(data)
            if info.devicetype != win32con.DBT_DEVTYP_DEVICEINTERFACE:
                return
            if str(info.classguid).lower() != GUID_DEVINTERFACE_USB_DEVICE.lower():
                return
            if self.removals.handle(
                info.name, event_type == win32con.DBT_DEVICEARRIVAL
            ):
                # Keep the SCM callback short: do not read policy or launch here.
                self.device_events.put(
                    (
                        win32ts.WTSGetActiveConsoleSessionId(),
                        self.session_generation,
                        monotonic(),
                    )
                )
                win32event.SetEvent(self.hDeviceEvent)
        except Exception as exc:
            log_message(f"Unable to handle USB notification: {exc}")

    def process_removal(self, yklocker, event):
        session_id, generation, timestamp = event

        def still_current():
            return (
                not self.stopping
                and generation == self.session_generation
                and monotonic() - timestamp < 5
                and session_id != 0xFFFFFFFF
                and session_id == win32ts.WTSGetActiveConsoleSessionId()
            )

        if not still_current():
            return
        # Read current policy for each event. Timeout is intentionally unused.
        reg_check_removal_option(yklocker)
        option = yklocker.get_removal_option()
        if option == RemovalOption.NOTHING:
            return
        if not win32ts.WTSQuerySessionInformation(
            None, session_id, win32ts.WTSUserName
        ):
            return
        log_message(f"YubiKey removed; session {session_id}, action: {option}")
        lock_system(option, session_id=session_id, still_current=still_current)

    def run_device_events(self, yklocker):
        notification_filter = win32gui_struct.PackDEV_BROADCAST_DEVICEINTERFACE(
            GUID_DEVINTERFACE_USB_DEVICE
        )
        notification = win32gui.RegisterDeviceNotification(
            self.ssh, notification_filter, win32con.DEVICE_NOTIFY_SERVICE_HANDLE
        )
        try:
            log_message("Listening for YubiKey USB removal events; Timeout is ignored")
            while not self.stopping:
                result = win32event.WaitForMultipleObjects(
                    (self.hWaitStop, self.hDeviceEvent), False, win32event.INFINITE
                )
                if result == win32event.WAIT_OBJECT_0:
                    break
                while not self.stopping:
                    try:
                        event = self.device_events.get_nowait()
                    except Empty:
                        break
                    try:
                        self.process_removal(yklocker, event)
                    except Exception as exc:
                        # An absent/logged-off user must not terminate monitoring.
                        log_message(f"Unable to apply YubiKey removal action: {exc}")
        finally:
            win32gui.UnregisterDeviceNotification(notification)


def check_service_interruption(serviceObject: AppServerSvc) -> bool:
    # Check if hWaitStop has been issued
    if (
        win32event.WaitForSingleObject(serviceObject.hWaitStop, 5000)
        == win32event.WAIT_OBJECT_0
    ):  # Then stop the loop
        return False
    else:
        return True


def reg_query_key(key_name: str):
    try:
        # Attemt to open the handle to registry
        key_handle = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH)
        # QueryValueEx returns a tuple, the value and the type
        ret = winreg.QueryValueEx(key_handle, key_name)[0]
        # Close the handle to the key
        key_handle.Close()
        return ret
    except (OSError, TypeError, FileNotFoundError, KeyError) as e:
        log_message("Error when attempting to read the registry: " + str(e))
        return False


def reg_check_timeout(yklocker) -> int:
    timeoutValue = int(reg_query_key(REG_TIMEOUT))
    if timeoutValue is not False:
        yklocker.set_timeout(timeoutValue)
    # Return current timeout
    return yklocker.get_timeout()


def reg_check_removal_option(yklocker) -> RemovalOption:
    lockValue = reg_query_key(REG_REMOVALOPTION)
    if lockValue is not False:
        yklocker.set_removal_option(lockValue)

    # Return current RemovalOption
    return yklocker.get_removal_option()


def reg_check_updates(yklocker) -> None:
    # check for changes in the registry
    timeoutValue = yklocker.get_timeout()
    removalOption = yklocker.get_removal_option()
    # Check registry and get the latest values
    timeoutValue2 = reg_check_timeout(yklocker)
    removalOption2 = reg_check_removal_option(yklocker)

    if timeoutValue != timeoutValue2 or removalOption != removalOption2:
        message = f"Updated YubiKeyLocker with RemovalOption {yklocker.get_removal_option()} after {yklocker.get_timeout()} seconds without a detected YubiKey"
        yklocker.logger(message)


def win_main() -> None:
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(AppServerSvc)
    try:
        servicemanager.StartServiceCtrlDispatcher()
    except BaseException as e:
        print("The executable needs to be installed and started as a service.")
        print(e)
