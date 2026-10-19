"""State for native USB notifications; no periodic device enumeration."""

import re

from yubikit.core import PID


class RemovalEvents:
    def __init__(self):
        self.removed = set()

    def handle(self, path: str, arrived: bool) -> bool:
        """Return True once per removal of a YubiKey USB parent interface.

        A removal notification is itself evidence of prior presence, including
        keys connected before service startup. Arrival rearms the same path.
        """
        path = path.rstrip("\0").lower()
        match = re.match(r"^\\\\\?\\usb#vid_1050&pid_([0-9a-f]{4})#", path)
        if not match:
            return False
        try:
            PID(int(match[1], 16))
        except ValueError:
            return False
        if arrived:
            self.removed.discard(path)
            return False
        if path in self.removed:
            return False
        self.removed.add(path)
        return True
