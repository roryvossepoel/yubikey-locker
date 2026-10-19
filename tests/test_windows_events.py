"""Exercise the Windows integration using isolated OS API doubles on every OS."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from sciber_yklocker.models.removaloption import RemovalOption

KEY = r"\\?\USB#VID_1050&PID_0407#serial#{a5dcbf10-6530-11d2-901f-00c04fb951ed}"


@pytest.fixture
def windows():
    names = (
        "winreg servicemanager win32api win32con win32event win32gui "
        "win32gui_struct win32process win32profile win32service "
        "win32serviceutil win32ts"
    ).split()
    modules = {name: MagicMock() for name in names}

    class ServiceFramework:
        def __init__(self, args):
            self.ssh = 123

        def GetAcceptedControls(self):
            return 1

    modules["win32serviceutil"].ServiceFramework = ServiceFramework
    for name, value in dict(
        SERVICE_CONTROL_DEVICEEVENT=11,
        SERVICE_CONTROL_SESSIONCHANGE=14,
        SERVICE_ACCEPT_SESSIONCHANGE=128,
    ).items():
        setattr(modules["win32service"], name, value)
    for name, value in dict(
        DBT_DEVICEARRIVAL=0x8000,
        DBT_DEVICEREMOVECOMPLETE=0x8004,
        DBT_DEVTYP_DEVICEINTERFACE=5,
    ).items():
        setattr(modules["win32con"], name, value)
    modules["win32event"].WAIT_OBJECT_0 = 0
    modules["win32ts"].WTSGetActiveConsoleSessionId.return_value = 7
    modules["win32ts"].WTSQuerySessionInformation.return_value = "user"
    path = Path(__file__).parents[1] / "src/sciber_yklocker/lib/win.py"
    spec = importlib.util.spec_from_file_location("_isolated_win", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict("sys.modules", modules):
        spec.loader.exec_module(module)
    return module


def notify(windows, service, arrived=False, path=KEY):
    windows.win32gui_struct.UnpackDEV_BROADCAST.return_value = SimpleNamespace(
        devicetype=5, classguid=windows.GUID_DEVINTERFACE_USB_DEVICE, name=path
    )
    service.SvcOtherEx(11, 0x8000 if arrived else 0x8004, b"event")


def test_callback_queues_once_and_rearms(windows):
    service = windows.AppServerSvc([])
    assert service.device_events.empty()
    notify(windows, service)
    notify(windows, service)
    assert service.device_events.qsize() == 1
    notify(windows, service, arrived=True)
    notify(windows, service)
    assert service.device_events.qsize() == 2
    windows.win32process.CreateProcessAsUser.assert_not_called()


def test_unrelated_device_and_stop_do_not_queue(windows):
    service = windows.AppServerSvc([])
    notify(windows, service, path=KEY.replace("1050", "1234"))
    service.stopping = True
    notify(windows, service)
    assert service.device_events.empty()


def test_worker_applies_policy_to_original_session(windows):
    service = windows.AppServerSvc([])
    locker = MagicMock()
    locker.get_removal_option.return_value = RemovalOption.LOCK
    notify(windows, service)
    with patch.object(windows, "lock_system") as lock:
        service.process_removal(locker, service.device_events.get_nowait())
        assert lock.call_args.kwargs["session_id"] == 7
        assert lock.call_args.kwargs["still_current"]()
        windows.win32ts.WTSGetActiveConsoleSessionId.return_value = 8
        assert not lock.call_args.kwargs["still_current"]()


@pytest.mark.parametrize(
    "change", ["session", "generation", "expired", "stop", "no_user", "nothing"]
)
def test_worker_discards_inapplicable_actions(windows, change):
    service = windows.AppServerSvc([])
    locker = MagicMock()
    locker.get_removal_option.return_value = RemovalOption.LOCK
    notify(windows, service)
    event = service.device_events.get_nowait()
    if change == "session":
        windows.win32ts.WTSGetActiveConsoleSessionId.return_value = 8
    elif change == "generation":
        service.SvcOtherEx(14, 0, (7,))
    elif change == "expired":
        event = (7, 0, windows.monotonic() - 10)
    elif change == "stop":
        service.stopping = True
    elif change == "no_user":
        windows.win32ts.WTSQuerySessionInformation.return_value = ""
    else:
        locker.get_removal_option.return_value = RemovalOption.NOTHING
    with patch.object(windows, "lock_system") as lock:
        service.process_removal(locker, event)
        lock.assert_not_called()


def test_listener_waits_without_scanning_and_unregisters(windows):
    service = windows.AppServerSvc([])
    windows.win32event.WaitForMultipleObjects.return_value = 0
    locker = MagicMock()
    service.run_device_events(locker)
    locker.is_yubikey_connected.assert_not_called()
    locker.lock.assert_not_called()
    windows.win32gui.RegisterDeviceNotification.assert_called_once()
    windows.win32gui.UnregisterDeviceNotification.assert_called_once()


def test_worker_failure_does_not_stop_listener(windows):
    service = windows.AppServerSvc([])
    notify(windows, service)
    windows.win32event.WaitForMultipleObjects.side_effect = [1, 0]
    with patch.object(service, "process_removal", side_effect=RuntimeError("gone")):
        service.run_device_events(MagicMock())
    assert windows.win32event.WaitForMultipleObjects.call_count == 2
    windows.win32gui.UnregisterDeviceNotification.assert_called_once()


def test_lock_uses_captured_session_and_closes_handles(windows):
    windows.win32process.CreateProcessAsUser.return_value = (100, 101, 102, 103)
    windows.lock_system(RemovalOption.LOCK, session_id=7, still_current=lambda: True)
    windows.win32ts.WTSQueryUserToken.assert_called_once_with(7)
    assert windows.win32api.CloseHandle.call_count == 3


def test_final_session_check_prevents_launch_and_releases_token(windows):
    windows.lock_system(RemovalOption.LOCK, session_id=7, still_current=lambda: False)
    windows.win32process.CreateProcessAsUser.assert_not_called()
    windows.win32api.CloseHandle.assert_called_once()
