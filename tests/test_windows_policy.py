"""Check the shipped policy resources and machine-only removal contract."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path


def test_policy_has_one_machine_setting_and_all_resources_resolve():
    root = (
        Path(__file__).parents[1]
        / "src/windows_utils/Administrative template (ADMX)/ADMX"
    )
    admx_text = (root / "SciberYklocker.admx").read_text()
    admx = ET.fromstring(admx_text)
    adml = ET.parse(root / "en-US/SciberYklocker.adml").getroot()
    strings = {node.attrib["id"] for node in adml.findall(".//stringTable/string")}
    assert set(re.findall(r"\$\(string\.([^)]+)\)", admx_text)) <= strings
    policy = admx.find("./policies/policy")
    assert policy.attrib["class"] == "Machine"
    assert [item.attrib["id"] for item in policy.find("elements")] == ["RemovalOption"]
    assert policy.find("./disabledList/item/value/string").text == "doNothing"
    definition = policy.find("supportedOn").attrib["ref"].split(":")[-1]
    assert definition in {
        item.attrib["name"]
        for item in admx.findall("./supportedOn/definitions/definition")
    }
    presentation = adml.find(".//presentation")
    assert [item.attrib["refId"] for item in presentation] == ["RemovalOption"]
    assert 'valueName="Timeout"' not in admx_text
