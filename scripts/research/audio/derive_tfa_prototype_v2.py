#!/usr/bin/env python3
"""Derive the corrected, independent TFA development-environment recipe.

The first attempt is retained unchanged: its reduced development copy omitted
the generated architecture headers, and the inherited TMPDIR was not writable
by the deliberately unprivileged compiler. This revision only supplies those
build-environment inputs. It does not change the driver or frozen R4 build.
"""
import hashlib
import json
from pathlib import Path

TEMPLATE = Path('/src/scripts/research/audio/tfa_module_prototype.py')
DESTINATION = Path('/work/tfa-module-prototype-recipe-v2')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    data = TEMPLATE.read_bytes()
    # The exact template hash is recorded in the fixed derivation description;
    # each replacement is unique and the source remains on disk unchanged.
    expected = '73a4a3f48ee95626598dcea2df95963208e5536d1da6af6a1becfe6e8fee968d'
    if digest(data) != expected:
        raise ValueError('unexpected first-attempt recipe')
    substitutions = {
        "Path('/work/tfa-module-prototype-v1')": "Path('/work/tfa-module-prototype-v2')",
        "Path('/work/tfa-module-prototype-jobs-v1')": "Path('/work/tfa-module-prototype-jobs-v2')",
        '    WORK.mkdir()\n': '    WORK.mkdir()\n    temporary = WORK / "tmp"\n    temporary.mkdir(mode=0o700)\n    os.chown(temporary, 1000, 1000)\n',
        "    members = ('.config', 'Makefile', 'Module.symvers', 'System.map', 'vmlinux', 'include', 'scripts', 'tools')\n":
            "    members = ('.config', 'Makefile', 'Module.symvers', 'System.map', 'vmlinux', 'include', 'scripts', 'tools', 'arch/arm64/include')\n",
        "        subprocess.run(['cp', '-a', '--reflink=auto', str(path), str(output / name)], check=True)\n":
            "        (output / name).parent.mkdir(parents=True, exist_ok=True)\n        subprocess.run(['cp', '-a', '--reflink=auto', str(path), str(output / name)], check=True)\n",
        "               SOURCE_DATE_EPOCH='1795392000')\n":
            "               SOURCE_DATE_EPOCH='1795392000', TMPDIR=str(WORK / 'tmp'))\n",
    }
    source = data.decode()
    for old, new in substitutions.items():
        if source.count(old) != 1:
            raise ValueError('non-unique recipe change: ' + old)
        source = source.replace(old, new)
    if DESTINATION.exists() or DESTINATION.is_symlink():
        raise ValueError('a new recipe prefix is required')
    DESTINATION.mkdir()
    output = DESTINATION / 'tfa_module_prototype.py'
    output.write_text(source)
    output.chmod(0o755)
    record = {'schema_version': 1, 'template_sha256': digest(data),
              'derived_sha256': digest(output.read_bytes()), 'derived_path': str(output),
              'substitutions': substitutions, 'driver_source_changes': False,
              'frozen_r4_changed': False, 'first_failed_attempt_modified': False}
    (DESTINATION / 'derivation.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
