"""Exercise the real toolbar views without linking the device-only Wine runtime."""
import json
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
root = here.parents[2]
if len(sys.argv) == 3 and sys.argv[1] == '--device':
    inventory = json.loads(Path(sys.argv[2]).read_text())
    matches = [d for devices in inventory['devices'].values() for d in devices
               if d.get('isAvailable') and 'Duo' in d['name']]
    if not matches:
        sys.exit('No available iPhone Duo simulator; this test must exercise vertical bars.')
    print(matches[-1]['udid'])
    sys.exit(0)

source = (root / 'app/Madeira/Library.swift').read_text(encoding='utf-8')

def declaration(start, end):
    return source[source.index(start):source.index(end)].replace('private struct LibraryTabNavigation', 'struct LibraryTabNavigation')

controls = declaration('struct LibraryLargeTitle:', '/// Whether JIT is available')
controls += declaration('private struct LibraryTabNavigation:', 'struct SteamMatch:')
# The baseline retains the production behavior. This one diagnostic switch
# isolates the title's hit-testing flag; it does not change the shipped app.
controls = controls.replace('.allowsHitTesting(false)', '.allowsHitTesting(ProcessInfo.processInfo.arguments.contains("--interactive-title"))')
(here / 'ProductionControls.swift').write_text('import SwiftUI\nimport UIKit\n' + controls, encoding='utf-8')
