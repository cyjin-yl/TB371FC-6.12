{ config, lib, pkgs, ... }:

let
  nullablePath = lib.types.nullOr lib.types.path;
  artifactPath = description: lib.mkOption {
    type = nullablePath;
    default = null;
    inherit description;
  };
in
{
  options.tb371fc.artifacts = {
    kernelImage = artifactPath "Uncompressed ARM64 Image from the selected TB371FC source/configuration.";
    deviceTreeBlob = artifactPath "DTB built for that exact TB371FC kernel and panel profile.";
    initramfs = artifactPath "Audited external initramfs that mounts the NixOS root and enters its stage 2.";
    kernelConfig = artifactPath "Final .config used to build the selected kernel.";
    moduleSymvers = artifactPath "Module.symvers from that complete kernel build.";
    moduleRoot = artifactPath "Staging prefix containing lib/modules/<kernelRelease>.";
    firmwareRoot = artifactPath "Private/redistributable firmware staging prefix containing lib/firmware.";
    kernelRelease = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Exact kernel.release shared by the Image and module build.";
    };
  };

  config = {
    nixpkgs.hostPlatform = lib.mkDefault "aarch64-linux";
    system.stateVersion = "26.05";
    networking.hostName = "tb371fc-research";

    # Only NixOS stage 2/userspace is assembled here. The selected external
    # kernel, DTB, initramfs, modules and firmware remain a separate contract.
    # Turning off kernel/initrd generation is not equivalent to porting them.
    boot.kernel.enable = false;
    boot.initrd.enable = false;
    boot.loader.grub.enable = false;
    boot.loader.systemd-boot.enable = false;
    boot.loader.external.enable = true;
    boot.loader.external.installHook = pkgs.writeShellScript "tb371fc-no-boot-install" ''
      echo "No TB371FC boot installer is implemented by this userspace profile." >&2
      echo "Assemble and review the external kernel/DTB/initramfs/modules/firmware contract first." >&2
      exit 1
    '';

    # This label is a proposed rootfs contract. No filesystem or block device
    # is formatted, mounted, discovered or written by evaluating this module.
    fileSystems."/" = {
      device = "/dev/disk/by-label/tb371fc-root";
      fsType = "ext4";
    };

    hardware.graphics = {
      enable = true;
      package = pkgs.mesa;
      enable32Bit = false;
    };
    # Generic redistributable firmware does not supply every Lenovo-signed
    # GPU/remoteproc or Novatek image. No donor firmware is renamed as Lenovo.
    hardware.enableRedistributableFirmware = true;
    hardware.bluetooth.enable = true;
    services.dbus.enable = true;
    services.libinput.enable = true;
    networking.networkmanager.enable = true;

    environment.systemPackages = with pkgs; [
      mesa libdrm vulkan-loader vulkan-tools
      wayland wayland-utils weston foot
      libinput evtest networkmanager bluez
      pciutils usbutils kmod
    ];

    # No login/password, SSH key, Wi-Fi profile, automatic compositor or
    # charging-control service is provisioned by the build experiment.
    warnings = [
      "TB371FC: this is an aarch64 userspace research profile. Kernel, DT, initramfs, module ABI and exact firmware integration are not completed."
    ];
  };
}
