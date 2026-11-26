#!/bin/sh
# Builds gui-plugin/MaxxFanBridge.json: the gui-v2 plugin with the MaxxFan card for the switch
# pane, from the QML and icons in gui-plugin/MaxxFanBridge/. Commit the result: the Pi needs no
# compiler, the package's setup script only copies it into /data/apps.
#
#   tools/make-plugin.sh
#
# Uses gui-v2's own plugin compiler (pinned below) and Qt's rcc, lupdate and lrelease from
# PySide6, all inside .build/ (a Python environment in .build/qtvenv; nothing is installed
# elsewhere). Run tests/test_plugin.py after changing the QML.
set -e
cd "$(dirname "$0")/.."
GUIV2=v1.4.6           # the gui-v2 release that added switch-pane cards for plugins
PYSIDE=6.8.1
root=$PWD
build=$root/.build/plugin
venv=$root/.build/qtvenv

if [ ! -x "$venv/bin/python" ]; then
    python3 -m venv "$venv"
    PIP_CACHE_DIR="$root/.build/pip-cache" "$venv/bin/pip" install -q --no-cache-dir "PySide6-Essentials==$PYSIDE"
fi
qt=$("$venv/bin/python" -c 'import os, PySide6; print(os.path.dirname(PySide6.__file__))')

mkdir -p "$build/compiler-$GUIV2"
for f in gui-v2-plugin-compiler.py guiplugins-api.json; do
    [ -f "$build/compiler-$GUIV2/$f" ] || curl -sSfL -o "$build/compiler-$GUIV2/$f" \
        "https://raw.githubusercontent.com/victronenergy/gui-v2/$GUIV2/tools/$f"
done

# The compiler packs every file in the folder it runs in, and writes its work files there.
rm -rf "$build/MaxxFanBridge"
cp -R gui-plugin/MaxxFanBridge "$build/"
version=$(sed 's/^v//' version)
(
    cd "$build/MaxxFanBridge"
    PATH="$qt/Qt/libexec:$qt:$PATH" "$venv/bin/python" "$build/compiler-$GUIV2/gui-v2-plugin-compiler.py" \
        --name MaxxFanBridge --version "$version" --min-required-version "$GUIV2" \
        --card MaxxFanBridge_Card.qml 2
)
cp "$build/MaxxFanBridge/MaxxFanBridge.json" gui-plugin/MaxxFanBridge.json
# What it was built from, so tests/test_package.py notices a QML change without a rebuild.
(cd gui-plugin/MaxxFanBridge && shasum -a 256 $(ls | sort)) > gui-plugin/MaxxFanBridge.sources
echo "built gui-plugin/MaxxFanBridge.json (plugin version $version, needs gui-v2 $GUIV2 or later)"
