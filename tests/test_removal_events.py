from sciber_yklocker.models.removal_events import RemovalEvents

KEY = r"\\?\USB#VID_1050&PID_0407#serial#{a5dcbf10-6530-11d2-901f-00c04fb951ed}"


def test_removal_of_key_present_before_startup():
    events = RemovalEvents()
    assert events.removed == set()  # Startup itself never triggers anything.
    assert events.handle(KEY, arrived=False)
    assert not events.handle(KEY.upper(), arrived=False)


def test_reinsert_rearms_without_locking_on_arrival():
    events = RemovalEvents()
    assert not events.handle(KEY, arrived=True)
    assert events.handle(KEY, arrived=False)
    assert not events.handle(KEY, arrived=True)
    assert events.handle(KEY, arrived=False)


def test_other_devices_and_composite_children_are_ignored():
    events = RemovalEvents()
    for path in (
        KEY.replace("1050", "1234"),
        KEY.replace("0407", "0030"),
        KEY.replace("0407#", "0407&MI_00#"),
        "",
        "VID_1050&PID_0407",
    ):
        assert not events.handle(path, arrived=False)


def test_fido_only_and_multiple_keys():
    events = RemovalEvents()
    key2 = KEY.replace("serial", "second").replace("0407", "0402")
    events.handle(KEY, arrived=True)
    events.handle(key2, arrived=True)
    assert events.handle(KEY, arrived=False)
    assert events.handle(key2, arrived=False)
