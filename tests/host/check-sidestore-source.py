#!/usr/bin/env python3
"""Exercise version stamping and source generation against real ZIP/plist fixtures."""

import importlib.util
import plistlib
import struct
import tempfile
import zipfile
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("source", repo / "tools/build/sidestore-source.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


def macho(permissions):
    xml = plistlib.dumps(permissions)
    blob = struct.pack(">II", 0xFADE7171, len(xml) + 8) + xml
    signature = struct.pack(">IIIII", 0xFADE0CC0, 20 + len(blob), 1, 5, 20) + blob
    header = struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 2, 1, 16, 0, 0)
    return header + struct.pack("<4I", 0x1D, 16, 48, len(signature)) + signature


with tempfile.TemporaryDirectory(prefix="madeira-source-") as tmp:
    root = Path(tmp)
    app = root / "Payload/Madeira.app"
    extension = app / "PlugIns/Helper.appex"
    extension.mkdir(parents=True)
    for bundle, identifier, version, permission in (
        (app, "com.example.madeira", "0.2.0", "com.apple.security.cs.allow-jit"),
        (extension, "com.example.madeira.helper", "1.0", "get-task-allow"),
    ):
        info = {
            "CFBundleIdentifier": identifier, "CFBundleExecutable": "App",
            "CFBundleShortVersionString": version, "CFBundleVersion": "5",
            "MinimumOSVersion": "18.0", "NSLocalNetworkUsageDescription": "Pair for JIT.",
        }
        (bundle / "Info.plist").write_bytes(plistlib.dumps(info))
        (bundle / "App").write_bytes(macho({permission: True}))
    source.stamp(app, 42, 3)
    for bundle in (app, extension):
        info = plistlib.loads((bundle / "Info.plist").read_bytes())
        assert info["CFBundleShortVersionString"] == "0.42.3"
        assert info["CFBundleVersion"] == "42.3"
    ipa = root / "Madeira.ipa"
    with zipfile.ZipFile(ipa, "w") as archive:
        for path in app.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    sha = "1234567" + "0" * 33
    document = source.make_source(ipa, "kinghuijae/Madeira", "ci-42-3-1234567", sha)
    entry = document["apps"][0]
    version = entry["versions"][0]
    assert entry["bundleIdentifier"] == "com.example.madeira"
    assert version["version"] == "0.42.3"
    assert version["size"] == ipa.stat().st_size
    assert version["minOSVersion"] == "18.0"
    assert "/ci-42-3-1234567/Madeira.ipa" in version["downloadURL"]
    assert "/main-latest/source.json" in document["sourceURL"]
    assert entry["appPermissions"]["entitlements"] == ["com.apple.security.cs.allow-jit", "get-task-allow"]
    assert entry["appPermissions"]["privacy"]["NSLocalNetworkUsageDescription"] == "Pair for JIT."
    assert "marketplaceID" not in entry and "buildVersion" not in version
    # A cache hit keeps its embedded version, even if a later run publishes it.
    cached = source.make_source(ipa, "kinghuijae/Madeira", "ci-43-1-1234567", sha)
    assert cached["apps"][0]["versions"][0]["version"] == "0.42.3"
    source.stamp(app, 43, 1)
    assert plistlib.loads((app / "Info.plist").read_bytes())["CFBundleShortVersionString"] == "0.43.1"
    empty = root / "empty.ipa"
    with zipfile.ZipFile(empty, "w"):
        pass
    try:
        source.make_source(empty, "kinghuijae/Madeira", "ci-42-3-1234567", sha)
        raise AssertionError("Empty IPA was accepted")
    except ValueError:
        pass
    try:
        source.entitlements(b"invalid executable")
        raise AssertionError("Invalid Mach-O was accepted")
    except ValueError:
        pass

package = (repo / "tools/build/package-ipa.sh").read_text(encoding="utf-8")
assert package.index('sidestore-source.py" stamp') < package.index("codesign --force")
assert 'if [[ "${GITHUB_ACTIONS:-}" == true ]]' in package
print("SideStore source checks passed (versions, extensions, cache reuse, permissions, invalid IPA).")
