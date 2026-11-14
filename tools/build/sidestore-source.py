#!/usr/bin/env python3
"""Stamp CI versions before signing and describe the resulting IPA for SideStore."""

import argparse
import json
import plistlib
import re
import struct
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def stamp(app, run_number, run_attempt):
    if run_number < 1 or run_attempt < 1:
        raise ValueError("CI run number and attempt must be positive")
    version = f"0.{run_number}.{run_attempt}"
    # Include extensions with literal versions in their source Info.plist.
    for path in app.rglob("Info.plist"):
        if path.parent.suffix not in (".app", ".appex"):
            continue
        info = plistlib.loads(path.read_bytes())
        info["CFBundleShortVersionString"] = version
        info["CFBundleVersion"] = f"{run_number}.{run_attempt}"
        path.write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_BINARY))
    print(f"CI app and extension version: {version}")


def entitlements(executable):
    """Read XML entitlements from the app's thin arm64 Mach-O code signature."""
    if executable[:4] != b"\xcf\xfa\xed\xfe":
        raise ValueError("Expected a little-endian 64-bit Mach-O executable")
    count = struct.unpack_from("<I", executable, 16)[0]
    offset = 32
    for _ in range(count):
        command, size = struct.unpack_from("<II", executable, offset)
        if size < 8 or offset + size > len(executable):
            raise ValueError("Invalid Mach-O load command")
        if command == 0x1D:  # LC_CODE_SIGNATURE
            start, length = struct.unpack_from("<II", executable, offset + 8)
            signature = executable[start:start + length]
            magic, total, slots = struct.unpack_from(">III", signature)
            if magic != 0xFADE0CC0 or total > len(signature):
                raise ValueError("Invalid code signature superblob")
            for index in range(slots):
                slot, position = struct.unpack_from(">II", signature, 12 + index * 8)
                if slot == 5:  # CSSLOT_ENTITLEMENTS
                    magic, size = struct.unpack_from(">II", signature, position)
                    if magic != 0xFADE7171 or position + size > total:
                        raise ValueError("Invalid entitlements blob")
                    return plistlib.loads(signature[position + 8:position + size])
            return {}
        offset += size
    return {}  # Unsigned extensions are signed by the sideloading client.


def make_source(ipa, repository, tag, sha):
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        raise ValueError("Expected owner/repository")
    if not re.fullmatch(r"ci-\d+-\d+-[0-9a-f]{7}", tag):
        raise ValueError("Expected an immutable CI release tag")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected a full commit SHA")
    with zipfile.ZipFile(ipa) as archive:
        mains = [n for n in archive.namelist()
                 if re.fullmatch(r"Payload/[^/]+\.app/Info.plist", n)]
        if len(mains) != 1:
            raise ValueError("IPA must contain exactly one main application")
        main = plistlib.loads(archive.read(mains[0]))
        permissions = set()
        privacy = {}
        for name in archive.namelist():
            if not name.endswith((".app/Info.plist", ".appex/Info.plist")):
                continue
            info = plistlib.loads(archive.read(name))
            binary = name.rsplit("/", 1)[0] + "/" + info["CFBundleExecutable"]
            permissions.update(entitlements(archive.read(binary)))
            privacy.update({k: v for k, v in info.items() if "UsageDescription" in k})
    version = main["CFBundleShortVersionString"]
    bundle_id = main["CFBundleIdentifier"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or "$" in bundle_id:
        raise ValueError("Unresolved IPA version or bundle identifier")
    base = f"https://github.com/{repository}"
    icon = (f"https://raw.githubusercontent.com/{repository}/{sha}/"
            "app/Madeira/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png")
    # Keep a cached source's version tied to its exact IPA, even during promotion
    # of main-latest. Never point a version entry at the mutable IPA alias.
    release = {
        "version": version,
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "localizedDescription": f"Main CI build from {sha[:7]}. {base}/releases/tag/{tag}",
        "downloadURL": f"{base}/releases/download/{tag}/Madeira.ipa",
        "size": ipa.stat().st_size,
        "minOSVersion": main["MinimumOSVersion"],
    }
    return {
        "name": "Madeira Main",
        "identifier": f"io.github.{repository.replace('/', '.').lower()}.main",
        "subtitle": "Latest successful main build",
        "description": "Personal Madeira main builds published by GitHub Actions.",
        "website": base,
        "sourceURL": f"{base}/releases/download/main-latest/source.json",
        "iconURL": icon,
        "apps": [{
            "name": main.get("CFBundleDisplayName", "Madeira"),
            "bundleIdentifier": bundle_id,
            "developerName": "Madeira contributors / " + repository.split("/")[0],
            "localizedDescription": "Run Windows games on iPhone and iPad. Requires JIT.",
            "iconURL": icon,
            "versions": [release],
            # Do not emit marketplaceID or buildVersion: this is a classic IPA
            # source, and CI updates have distinct marketing versions.
            "appPermissions": {"entitlements": sorted(permissions), "privacy": privacy},
        }],
        "news": [],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stamping = commands.add_parser("stamp")
    stamping.add_argument("app", type=Path)
    stamping.add_argument("--run-number", type=int, required=True)
    stamping.add_argument("--run-attempt", type=int, required=True)
    source = commands.add_parser("generate")
    source.add_argument("ipa", type=Path)
    source.add_argument("--repository", required=True)
    source.add_argument("--tag", required=True)
    source.add_argument("--sha", required=True)
    source.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "stamp":
        stamp(args.app, args.run_number, args.run_attempt)
    else:
        document = make_source(args.ipa, args.repository, args.tag, args.sha)
        args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
