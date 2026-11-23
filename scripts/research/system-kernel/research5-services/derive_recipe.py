#!/usr/bin/env python3
"""Derive a separately versioned R5 recipe from the frozen R4 build recipe."""
from pathlib import Path
import ast
import difflib
import hashlib
import json

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'tb371fc-linux/scripts/research/system-kernel/research4'
DESTINATION = HERE / 'recipe-v1'
R4_CONFIG = '0236496603f168aacc5586eac7e199ca8f840b5d0c9b5ed111da64e9d28ec275'
R4_CERT = 'da222772fe59edc2d0efc6826ff4c31504ee9420b057121cd0a2e2503d81788d'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, before, after):
    assert text.count(before) == 1, (before, text.count(before))
    return text.replace(before, after)


def main():
    assert not DESTINATION.exists()
    contract_raw = (HERE / 'services-contract.json').read_bytes()
    contract = json.loads(contract_raw)
    assert contract['schema_version'] == 1 and contract['baseline_config_sha256'] == R4_CONFIG
    assert contract['physical_hardware_tested'] is False
    requested = contract['requested']
    assert requested['CONFIG_LOCALVERSION'] == '"-tb371fc-research5-services"'
    fragment = '# Independent R5 service support, starting with the exact resolved R4 config.\n'
    fragment += '# Each change is derived from the retained original Nura/NixOS service inputs.\n'
    for key, value in requested.items():
        assert key.startswith('CONFIG_') and isinstance(value, str)
        fragment += ('# ' + key + ' is not set\n') if value == 'n' else key + '=' + value + '\n'

    original_build = (BASE / 'build_system.py').read_text()
    build = original_build.replace('research4-system', 'research5-services').replace('research4 kernel', 'research5 kernel')
    build = replace_once(build, 'DTB_TARGET = "qcom/sm8250-lenovo-tb371fc-display-input-test-6.12.dtb"',
        'DTB_TARGET = "qcom/sm8250-lenovo-tb371fc-display-input-test-6.12.dtb"\n'
        f'R4_CONFIG_SHA = "{R4_CONFIG}"\nR4_CERT_SHA = "{R4_CERT}"\n'
        f'CONTRACT_SHA = "{sha(contract_raw)}"')
    build = replace_once(build, '    namespace = runpy.run_path(str(helper))',
        '    if digest(work / "baseline-r4/kernel.config") != R4_CONFIG_SHA:\n'
        '        raise RuntimeError("resolved R4 baseline config differs")\n'
        '    if digest(work / "baseline-r4/signing-cert.der") != R4_CERT_SHA:\n'
        '        raise RuntimeError("retained R4 public certificate differs")\n'
        '    namespace = runpy.run_path(str(helper))')
    build = replace_once(build, '    before = config_values(work / "source-input/baseline-abi/kernel.config")',
        '    before = config_values(work / "baseline-r4/kernel.config")\n'
        '    contract_path = Path(__file__).with_name("services-contract.json")\n'
        '    if digest(contract_path) != CONTRACT_SHA:\n'
        '        raise RuntimeError("service-derived config contract differs")\n'
        '    contract = json.loads(contract_path.read_text())')
    build = replace_once(build, '    required = {**fragment, "CONFIG_BPF_EVENTS": "y",',
        '    required = {**fragment, **contract["required_resolved"], "CONFIG_BPF_EVENTS": "y",')
    build = replace_once(build, '    return {"required": required, "preserved_security": protected, "changes": changes}',
        '    if changes != contract["exact_changes"]:\n'
        '        raise RuntimeError("resolved config delta differs from the reviewed exact contract: " +\n'
        '                           json.dumps(changes, sort_keys=True))\n'
        '    return {"required": required, "preserved_security": protected, "changes": changes,\n'
        '            "services_contract_sha256": CONTRACT_SHA, "all_other_r4_config_values_preserved": True}')
    build = replace_once(build, '            shutil.copyfile(work / "source-input/baseline-abi/kernel.config", output / "base.config")',
        '            record["recipe"]["services-contract.json"] = identity(Path(__file__).with_name("services-contract.json"))\n'
        '            shutil.copyfile(work / "baseline-r4/kernel.config", output / "base.config")')
    build = replace_once(build, '                        "baseline_config_sha256": BASE_CONFIG_SHA, "system_config_sha256": digest(work / "system.config"),',
        '                        "source_reproduction_baseline_config_sha256": BASE_CONFIG_SHA,\n'
        '                        "resolved_r4_baseline_config_sha256": R4_CONFIG_SHA,\n'
        '                        "services_contract_sha256": CONTRACT_SHA,\n'
        '                        "system_config_sha256": digest(work / "system.config"),')

    original_inspect = (BASE / 'inspect_system.py').read_text()
    inspect = original_inspect.replace('research4-system', 'research5-services').replace('research4 Image', 'research5 Image')
    inspect = inspect.replace('The separate full Fedora VM run owns runtime acceptance.',
                              'Separate NixOS and Nura system VM runs own runtime acceptance.')
    inspect = replace_once(inspect, '        if profile.digest(cert) == OLD_CERT_SHA or cert_bytes not in image:',
        '        if profile.digest(cert) in (OLD_CERT_SHA, profile.R4_CERT_SHA) or cert_bytes not in image:')
    inspect = replace_once(inspect, '        baseline_index = Path("/work/research2-display/artifacts/modules.SHA256SUMS")',
        '        baseline_index = work / "baseline-r4/modules.SHA256SUMS"')
    inspect = replace_once(inspect, '        for item in module_records:\n            if profile.digest(work / "modules" / item["path"]) != item["sha256"]:',
        '        if len(before) != 84 or len(module_records) != 84 or before != after:\n'
        '            raise ValueError("builtin service additions must preserve the complete R4 module path set")\n'
        '        for item in module_records:\n            if profile.digest(work / "modules" / item["path"]) != item["sha256"]:')
    inspect = replace_once(inspect, '"module_set_changes_from_research2":', '"module_set_changes_from_research4":')
    inspect = inspect.replace('"Generic Fedora system VM validation is recorded separately; physical tablet entry and hardware remain untested."',
                              '"NixOS/Nura generic system VM validation is recorded separately; physical tablet entry and hardware remain untested."')
    for text in (build, inspect):
        ast.parse(text)
    DESTINATION.mkdir(mode=0o700)
    files = {'build_system.py': build.encode(), 'inspect_system.py': inspect.encode(),
             'system.config': fragment.encode(), 'services-contract.json': contract_raw}
    manifest = {}
    for name, raw in files.items():
        path = DESTINATION / name
        with path.open('xb') as stream:
            stream.write(raw)
        path.chmod(0o755 if name.endswith('.py') else 0o644)
        manifest[name] = {'bytes': len(raw), 'sha256': sha(raw), 'mode': '0755' if name.endswith('.py') else '0644'}
    patch = ''.join(difflib.unified_diff(original_build.splitlines(True), build.splitlines(True),
                                        fromfile='research4/build_system.py', tofile='research5/build_system.py'))
    patch += ''.join(difflib.unified_diff(original_inspect.splitlines(True), inspect.splitlines(True),
                                         fromfile='research4/inspect_system.py', tofile='research5/inspect_system.py'))
    patch += ''.join(difflib.unified_diff((BASE / 'system.config').read_text().splitlines(True), fragment.splitlines(True),
                                         fromfile='research4/system.config', tofile='research5/system.config'))
    with (HERE / 'recipe-derivation.patch').open('x') as stream:
        stream.write(patch)
    record = {'schema_version': 1, 'files': manifest,
              'prior_recipe': {name: {'bytes': (BASE / name).stat().st_size, 'sha256': sha((BASE / name).read_bytes())}
                               for name in ('build_system.py', 'inspect_system.py', 'system.config')},
              'patch': {'bytes': len(patch.encode()), 'sha256': sha(patch.encode())},
              'old_objects_copied': False, 'old_private_key_copied': False,
              'executed': False, 'physical_hardware_tested': False}
    with (HERE / 'recipe-derivation.json').open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
