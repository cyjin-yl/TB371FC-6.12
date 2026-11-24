{
  description = "TB371FC NixOS userspace and external boot artifact research";

  # NixOS 26.05 channel revision observed on 2026-11-23 (Asia/Shanghai).
  # The full commit is fixed even before a generated flake.lock is retained.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/94c3211b0ee8ba969a3f12eb4aff8ba0f72971dd";

  outputs = { self, nixpkgs }:
    let
      lib = nixpkgs.lib;
      buildSystems = [ "x86_64-linux" "aarch64-linux" ];
      forBuildSystems = lib.genAttrs buildSystems;
      target = import nixpkgs { system = "aarch64-linux"; };
      userspacePackages = with target; [
        hello mesa libdrm vulkan-loader vulkan-tools
        wayland wayland-utils weston foot
        libinput evtest networkmanager bluez
      ];
      artifacts = self.nixosConfigurations.tb371fc.config.tb371fc.artifacts;
      requiredFiles = [
        "kernelImage" "deviceTreeBlob" "initramfs"
        "kernelConfig" "moduleSymvers"
      ];
      requiredDirectories = [ "moduleRoot" "firmwareRoot" ];
      required = requiredFiles ++ requiredDirectories ++ [ "kernelRelease" ];
      missing = builtins.filter (name: artifacts.${name} == null) required;
    in
    {
      nixosConfigurations.tb371fc = lib.nixosSystem {
        system = "aarch64-linux";
        modules = [ ./hardware-configuration.nix ];
      };

      # This is a machine-readable boundary, not a statement that hardware works.
      lib.tb371fc = {
        targetSystem = "aarch64-linux";
        nixpkgsRevision = "94c3211b0ee8ba969a3f12eb4aff8ba0f72971dd";
        bootIntegrationComplete = false;
        missingArtifactInputs = missing;
      };

      packages = forBuildSystems (buildSystem:
        let
          buildPkgs = import nixpkgs { system = buildSystem; };
          artifactDescription = buildPkgs.writeText "tb371fc-artifacts.json"
            (builtins.toJSON artifacts);
        in
        {
          # These two aliases can be substituted from the official aarch64 cache.
          # They do not execute an ARM binary or exercise the tablet's GPU.
          default = target.hello;
          hello-aarch64 = target.hello;
          mesa-aarch64 = target.mesa;

          # The manifest builder runs on buildSystem. Its roots are aarch64
          # packages, so a cache miss still needs a suitable builder; no foreign
          # execution or sandbox exception is silently enabled by this flake.
          aarch64-userspace-closure = buildPkgs.closureInfo {
            rootPaths = userspacePackages;
          };

          # Toolchain/packaging probes only: this vanilla kernel has no TB371FC
          # DT, external drivers or boot-chain integration from this repository.
          vanilla-kernel-cross =
            buildPkgs.pkgsCross.aarch64-multiplatform.linuxPackages_6_12.kernel;

          # Explicit, opt-in gate. An ordinary userspace build must not be
          # presented as a tablet boot payload. No placeholder hashes are used.
          artifact-gate = buildPkgs.runCommand "tb371fc-external-artifact-gate"
            {
              nativeBuildInputs = [ buildPkgs.python3 buildPkgs.kmod ];
            }
            (if missing != [ ] then ''
              echo "TB371FC boot integration is incomplete. Missing artifact inputs:" >&2
              echo ${lib.escapeShellArg (lib.concatStringsSep ", " missing)} >&2
              exit 1
            '' else ''
              python3 - ${artifactDescription} "$out" <<'PY'
              import hashlib
              import json
              import pathlib
              import subprocess
              import sys

              description = json.loads(pathlib.Path(sys.argv[1]).read_text())
              for name in ("kernelImage", "deviceTreeBlob", "initramfs", "kernelConfig", "moduleSymvers"):
                  path = pathlib.Path(description[name])
                  if not path.is_file() or path.stat().st_size == 0:
                      raise SystemExit("missing or empty file: " + name)
              for name in ("moduleRoot", "firmwareRoot"):
                  if not pathlib.Path(description[name]).is_dir():
                      raise SystemExit("missing directory: " + name)
              with pathlib.Path(description["kernelImage"]).open("rb") as stream:
                  header = stream.read(64)
              if header[56:60] != b"ARM\x64":
                  raise SystemExit("kernelImage must be an uncompressed ARM64 Linux Image")
              with pathlib.Path(description["deviceTreeBlob"]).open("rb") as stream:
                  header = stream.read(4)
              if header != b"\xd0\x0d\xfe\xed":
                  raise SystemExit("deviceTreeBlob lacks the flattened-DT magic")
              release = description["kernelRelease"]
              modules = pathlib.Path(description["moduleRoot"]) / "lib/modules" / release
              if not modules.is_dir():
                  raise SystemExit("moduleRoot lacks lib/modules/" + release)
              module_files = list(modules.rglob("*.ko")) + list(modules.rglob("*.ko.xz")) + list(modules.rglob("*.ko.zst")) + list(modules.rglob("*.ko.gz"))
              if not module_files:
                  raise SystemExit("no modules found in the declared module tree")
              for module in module_files:
                  vermagic = subprocess.check_output(["modinfo", "-F", "vermagic", str(module)], text=True).split()
                  if not vermagic or vermagic[0] != release:
                      raise SystemExit("module release mismatch: " + module.name)
              firmware = pathlib.Path(description["firmwareRoot"]) / "lib/firmware"
              if not firmware.is_dir():
                  raise SystemExit("firmwareRoot lacks lib/firmware")
              hashes = {}
              for name in ("kernelImage", "deviceTreeBlob", "initramfs", "kernelConfig", "moduleSymvers"):
                  digest = hashlib.sha256()
                  with pathlib.Path(description[name]).open("rb") as stream:
                      for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                          digest.update(chunk)
                  hashes[name] = digest.hexdigest()
              output = pathlib.Path(sys.argv[2])
              output.mkdir()
              (output / "artifact-check.json").write_text(json.dumps({
                  "kernel_release": release,
                  "module_count": len(module_files),
                  "sha256": hashes,
                  "scope": "basic artifact format and module-release checks; no ABI, boot, firmware or hardware acceptance",
                  "hardware_tested": False,
              }, indent=2) + "\n")
              PY
            '');
        });
    };
}
