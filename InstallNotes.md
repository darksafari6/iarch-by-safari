# Install Notes

This file is a companion to the main README. It explains the installer flow in simple terms and covers common setup details before and after install.

## ⚠️ Important Notes

- This setup is intended for fresh, vanilla Arch Linux installs.
- Run the script from your normal user account with sudo, not from a root shell.
- Internet and correct system time are required for package keys, mirrors, and AUR operations.
- Existing configs that are replaced are backed up with a `.bak.<timestamp>` suffix.

## 🌐 Arch ISO Wi-Fi Setup (Before Archinstall)

If you are in the Arch ISO and need Wi-Fi before running archinstall, use this quick flow.

### Step 1: Find Your Wireless Interface

```bash
ip link
```

Look for an interface like `wlan0` or `wlp2s0`.

### Step 2: Unblock Wi-Fi (If Needed)

```bash
rfkill list
rfkill unblock wifi
```

### Step 3: Connect Using `iwd`

```bash
iwctl
```

Inside `iwctl`:

```bash
device list
station YOUR_INTERFACE scan
station YOUR_INTERFACE get-networks
station YOUR_INTERFACE connect YOUR_SSID
exit
```

### Step 4: Verify Internet Access

```bash
ping -c 3 archlinux.org
```

### Step 5: Sync Time

```bash
timedatectl set-ntp true
timedatectl status
```

### Step 6: Start `archinstall`

```bash
archinstall
```

## ⚙️ Before Running install.sh

- From repository root, run: `sudo ./install.sh`
- Make sure network is stable for long package operations.
- Verify time sync with `timedatectl status`.
- Do not close the terminal while installation is running.

## 🧭 Installer Prompt Flow (What You Will Be Asked)

This is the current prompt order in `install.sh`:

1. Proceed confirmation
2. Printer support option (y/n)
3. Gaming package option (y/n)
4. Audio mode (EasyEffects or Dolby)
5. Optional package bundle (y/n)
6. Browser selection
7. ddcutil setup (y/n)
8. Backup config restore (y/n)
9. Reboot confirmation loop

## 📦 What Each Option Does

These options control what gets installed and configured.

### Printer Support = Yes

- Installs CUPS and printer-related packages.
- Enables and starts CUPS with `systemctl enable --now cups`.
- If this step fails, the script continues and prints a warning.

### Gaming Packages = Yes

- Installs gaming tools such as Steam, Lutris, Heroic, Wine, Winetricks, ProtonPlus, MangoHud, and related dependencies.
- This step is interactive (no `--noconfirm`) so you can review prompts before confirming.

### Audio Option 1: EasyEffects

- Installs EasyEffects + plugin stack.
- No Dolby PipeWire profile is copied.

### Audio Option 2: Dolby Atmos

- Skips the EasyEffects plugin stack.
- Copies repo `pipewire` profile into user config after main config deployment.

### Optional Package Bundle = Yes

- Installs smaller optional extras listed at runtime (for example: mission-center, deadbeef, VS Code).
- ProtonPlus is no longer in this optional bundle because it is now part of gaming install.

### ddcutil Setup = Yes

- Installs `ddcutil`.
- Attempts to install `ddcutil-service` via `yay`.
- Loads and persists `i2c-dev` module.
- Reloads udev rules.
- Adds your user to the `i2c` group.
- Enables Noctalia DDC support in settings.

## 🔆 DDC / Brightness Behavior (Noctalia)

For brightness control to work:

- Monitor must support DDC/CI and have it enabled in monitor OSD.
- I2C devices must exist (`/dev/i2c-*`).
- User must be in the `i2c` group.
- Log out/in or reboot after group changes.

Important: `ddcutil-service` is D-Bus activated, not a normal systemd unit you manually enable with `systemctl enable`.

## 🧩 What the Installer Changes

Main places touched:

- `/etc/pacman.conf` (chaotic + multilib handling)
- `/etc/pacman.d/chaotic-mirrorlist`
- `/etc/modules-load.d/i2c-dev.conf` (if ddcutil option selected)
- `~/.config` deployment from repo config
- `~/.config/*.bak.<timestamp>` backups when replacing existing configs

## ✅ Post-Install Validation Checklist

After reboot/login, check the parts you selected:

```bash
systemctl status bluetooth
systemctl status cups
groups | grep i2c
ddcutil detect
ddcutil-client detect
ddcutil-client -d 1 getvcp 0x10
```

Notes:

- `cups` check is only relevant if printer support was selected.
- `i2c` and `ddcutil` checks are only relevant if ddcutil setup was selected.

## 🛠️ Common Failure Cases

- Running from a root shell instead of sudo from a normal user.
- Unstable network during pacman/yay operations.
- DDC/CI disabled in monitor OSD.
- Expecting `ddcutil-service` to be a standard systemd service unit.
- Running the script outside repository root.

## 🔁 Final Step

The reboot question loops intentionally. Reboot is strongly recommended so group, module, and config changes fully apply before normal use.


## minimaOS Glass Profile

The repository now ships an optional Noctalia v5+ glass-first profile in `.config/noctalia/`. The current installer already deploys repository `.config` entries and backs up an existing `~/.config/noctalia` before copying. Do not apply this TOML profile to Noctalia v4.

Before a live-session test:

~~~bash
noctalia config validate
bash scripts/minimaos-healthcheck.sh
~~~

Shortcuts: `SUPER + I` opens Control Center; `SUPER + SHIFT + N` opens notification history; `SUPER + SHIFT + A` audio controls; `SUPER + SHIFT + W` network; `SUPER + SHIFT + B` Bluetooth. `SUPER + T` continues to open Settings.

The profile uses Noctalia's own notification daemon and Freedesktop sound theme. It does not add a second notification daemon or claim to use a custom twinkle file. A custom sound should only be added through a version-supported API and tested with Do Not Disturb and notification replacement behavior.

If Noctalia validation fails, restore the timestamped backup of `~/.config/noctalia` before restarting the shell. Keep the backup until the new profile has survived logout/login and all required hardware controls have been checked.
