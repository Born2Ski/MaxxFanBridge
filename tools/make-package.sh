#!/bin/sh
# Builds .build/MaxxFanBridge-latest.tar.gz, the SetupHelper package for installing without
# GitHub: copy it, unopened, to the top folder of a USB stick or SD card and put that in the
# Venus device. PackageManager copies it to /data/MaxxFanBridge and lists it under
# Settings → PackageManager. See venus/README.md.
#
#   tools/make-package.sh                 GitHub details from ./gitHubInfo, if there is one
#   tools/make-package.sh <github-user>   writes gitHubInfo as <github-user>:latest, so
#                                         PackageManager checks that repository for updates
# The package carries AUTO_INSTALL: PackageManager installs each new version by itself (also
# without its menus, which exist only in the classic UI), unless it was uninstalled by hand.
set -e
cd "$(dirname "$0")/.."
name=MaxxFanBridge
dir=.build/package/$name-latest
rm -rf .build/package
mkdir -p "$dir/venus/dbus-maxxfan-bridge"
cp -R setup version firstCompatibleVersion AUTO_INSTALL services README.md "$dir/"
[ -f gitHubInfo ] && cp gitHubInfo "$dir/"
cp venus/README.md "$dir/venus/"
mkdir -p "$dir/gui-plugin"
cp gui-plugin/MaxxFanBridge.json "$dir/gui-plugin/"
cp venus/dbus-maxxfan-bridge/*.py venus/dbus-maxxfan-bridge/config.default.ini "$dir/venus/dbus-maxxfan-bridge/"
[ -n "$1" ] && echo "$1:latest" > "$dir/gitHubInfo"
find .build/package -name .DS_Store -delete
chmod +x "$dir/setup" "$dir/services/dbus-maxxfan-bridge/run" "$dir/services/dbus-maxxfan-bridge/log/run" \
    "$dir/venus/dbus-maxxfan-bridge/dbus-maxxfan-bridge.py"
if tar --version 2>/dev/null | grep -q bsdtar; then
    owner="--uid 0 --gid 0"          # macOS
else
    owner="--owner=0 --group=0"      # GNU tar
fi
# COPYFILE_DISABLE keeps macOS from adding ._ files
COPYFILE_DISABLE=1 tar -czf ".build/$name-latest.tar.gz" $owner -C .build/package "$name-latest"
echo "built .build/$name-latest.tar.gz, package version $(cat version)"
