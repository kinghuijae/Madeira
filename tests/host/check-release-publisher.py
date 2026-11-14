#!/usr/bin/env python3
"""Run the release publisher with an offline GitHub CLI fixture, including failures."""

import os
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
bash = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else "bash"
stub = r'''#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> events.log
case "$1 $2" in
  'release view')
    if [[ "$*" == *--json* ]]; then
      echo "https://api.github.com/releases/$3"
    elif [[ "$SCENARIO" == fresh && ! -f rolling-created ]]; then
      exit 1
    fi
    ;;
  'release create')
    [[ "$SCENARIO" != create_failure ]] || exit 1
    if [[ "$3" == main-latest ]]; then touch rolling-created; fi
    ;;
  'release upload')
    [[ "$SCENARIO" != upload_failure ]] || exit 1
    ;;
  'release edit') ;;
  'api --method') ;;
  api*)
    if [[ "$2" == *compare/* ]]; then
      if [[ "$SCENARIO" == stale ]]; then echo behind; else echo ahead; fi
    elif [[ "$2" == *git/ref/* ]]; then
      [[ "$SCENARIO" != fresh ]]
    else
      file=$(printf '%s' "$4" | sed -n 's/.*name == "\([^"]*\)".*/\1/p')
      digest=$(sha256sum "dist/$file" | cut -d ' ' -f 1)
      if [[ "$SCENARIO" == bad_immutable_digest && "$2" != */main-latest ]] ||
         [[ "$SCENARIO" == bad_mirror_digest && "$2" == */main-latest && "$file" == Madeira.ipa ]] ||
         [[ "$SCENARIO" == bad_source_digest && "$2" == */main-latest && "$file" == source.json ]]; then
        digest=wrong
      fi
      echo "uploaded $(stat -c %s "dist/$file") sha256:$digest"
    fi
    ;;
  *) exit 99 ;;
esac
'''

scenarios = ("fresh", "update", "stale", "create_failure", "bad_immutable_digest",
             "bad_mirror_digest", "upload_failure", "bad_source_digest", "foreign")
with tempfile.TemporaryDirectory(prefix="madeira-publisher-") as folder:
    for scenario in scenarios:
        case = Path(folder) / scenario
        (case / "bin").mkdir(parents=True)
        (case / "dist").mkdir()
        (case / "tools/build").mkdir(parents=True)
        shutil.copy(repo / "tools/build/sidestore-source.py", case / "tools/build")
        # The publisher runs on Ubuntu, but preflight also runs on macOS where
        # stat uses BSD flags and sha256sum is not guaranteed to be installed.
        commands = {
            "gh": stub,
            "python3": '#!/bin/bash\nexec "$TEST_PYTHON" "$@"\n',
            "stat": '#!/bin/bash\nexec "$TEST_PYTHON" -c \'import os,sys; print(os.stat(sys.argv[1]).st_size)\' "$3"\n',
            "sha256sum": '#!/bin/bash\nexec "$TEST_PYTHON" -c \'import hashlib,sys; from pathlib import Path; [print(hashlib.sha256(Path(p).read_bytes()).hexdigest() + "  " + p) for p in sys.argv[1:]]\' "$@"\n',
        }
        for name, text in commands.items():
            path = case / "bin" / name
            path.write_text(text, encoding="utf-8", newline="\n")
            path.chmod(0o755)
        info = {
            "CFBundleIdentifier": "com.example.madeira", "CFBundleExecutable": "Madeira",
            "CFBundleShortVersionString": "0.7.2", "CFBundleVersion": "7.2", "MinimumOSVersion": "18.0",
        }
        with zipfile.ZipFile(case / "dist/Madeira.ipa", "w") as archive:
            archive.writestr("Payload/Madeira.app/Info.plist", plistlib.dumps(info))
            archive.writestr("Payload/Madeira.app/Madeira", struct.pack("<8I", 0xFEEDFACF, 0, 0, 0, 0, 0, 0, 0))
        env = dict(os.environ, SCENARIO=scenario, TEST_PYTHON=Path(sys.executable).as_posix(),
                   GITHUB_REPOSITORY="other/repo" if scenario == "foreign" else "kinghuijae/Madeira",
                   GITHUB_REF="refs/heads/main", GITHUB_EVENT_NAME="push",
                   GITHUB_RUN_NUMBER="7", GITHUB_RUN_ATTEMPT="2", GITHUB_RUN_ID="123",
                   GITHUB_SHA="0123456789abcdef0123456789abcdef01234567", GITHUB_SERVER_URL="https://github.com",
                   RUNNER_TEMP=case.as_posix(), GITHUB_STEP_SUMMARY=(case / "summary.md").as_posix())
        result = subprocess.run([bash, "-c", 'export PATH="$PWD/bin:$PATH"; bash "$1"', "test-publisher",
                                 (repo / "tools/build/publish-release.sh").as_posix()],
                                cwd=case, env=env, capture_output=True, text=True)
        events = (case / "events.log").read_text() if (case / "events.log").exists() else ""
        assert (result.returncode == 0) == (scenario in ("fresh", "update", "stale")), (scenario, result.stderr)
        published = "release edit main-latest" in events
        assert published == (scenario in ("fresh", "update")), (scenario, events)
        if scenario in ("fresh", "update"):
            assert events.index("release edit ci-") < events.index("release upload main-latest")
            assert events.index('name == "Madeira.ipa"', events.index("release upload main-latest")) < events.index("release upload main-latest dist/source.json")
            assert "releases/download/main-latest/source.json" in (case / "summary.md").read_text()
        elif scenario in ("bad_mirror_digest", "upload_failure", "stale", "bad_immutable_digest"):
            assert "release upload main-latest dist/source.json" not in events
        if scenario == "foreign":
            assert not events
        print(f"PASS release publisher: {scenario}")
