#!/bin/sh
# Archived: replaced by the SetupHelper package MaxxFanBridge (setup, services/, venus/README.md).
# Run on the Venus OS device after copying this folder to /data/dbus-maxxfan-bridge.
# /data survives Venus OS updates; /service does not, so rc.local re-links it at each boot.
set -e
DIR=/data/dbus-maxxfan-bridge
LINK="ln -sfn $DIR/service /service/dbus-maxxfan-bridge"

chmod +x "$DIR/dbus-maxxfan-bridge.py" "$DIR/service/run" "$DIR/service/log/run"

BACKENDS=$(python3 - "$DIR/config.ini" <<'EOF'
import configparser, sys
c = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
c.read(sys.argv[1])
fans = [s for s in c.sections() if s not in ("mqtt", "presets", "gui") and not s.lower().startswith("preset ")]
print(" ".join(sorted({c.get(s, "backend", fallback="mqtt") for s in fans})))
EOF
)
echo "Backends in config.ini: $BACKENDS"

[ -f /data/rc.local ] || { echo "#!/bin/sh" > /data/rc.local; chmod +x /data/rc.local; }

case " $BACKENDS " in *" mqtt "*|*" vanturtle-wifi "*|*" vanturtle-esp32 "*)
    if ! python3 -c "import paho.mqtt.client" 2>/dev/null; then
        echo "paho-mqtt is missing on this Venus OS version. See venus/README.md, troubleshooting."
        exit 1
    fi
esac

case " $BACKENDS " in *" vanturtle-wifi "*|*" vanturtle-esp32 "*)
    echo "The devices at the fans connect to this device's MQTT broker on port 1883."
    echo "Check Settings -> Integrations -> MQTT Access is on (see the hardware document)."
    echo "This device's addresses (put the one on the van WiFi in the controllers' MQTT page):"
    ip -4 -o addr show 2>/dev/null | awk '$2 != "lo" {print "    " $2 ": " $4}' || true
esac

case " $BACKENDS " in *" vanturtle "*)
    [ -e /dev/i2c-1 ] || modprobe i2c-dev 2>/dev/null || true
    if [ ! -e /dev/i2c-1 ]; then
        echo "I2C bus 1 not found. Add this line to /u-boot/config.txt, reboot, and run install.sh again:"
        echo "    dtparam=i2c_arm=on"
        echo "(A Venus OS update may replace that file; if the fans go offline after an update, check it.)"
        exit 1
    fi
    grep -qF "modprobe i2c-dev" /data/rc.local || echo "modprobe i2c-dev 2>/dev/null" >> /data/rc.local
    if [ -f /etc/venus/gpio_list ] && grep -qE '^[[:space:]]*(2|3)[[:space:]]' /etc/venus/gpio_list; then
        echo "WARNING: /etc/venus/gpio_list claims GPIO2 or GPIO3, which are the I2C pins."
    fi
    if command -v i2cdetect >/dev/null; then
        echo "Devices on I2C bus 1 (expect 27, and 26 if you fitted the RJ11 board):"
        i2cdetect -y 1
    fi
esac

grep -qF "$LINK" /data/rc.local || echo "$LINK" >> /data/rc.local
$LINK
echo "Installed. Log: tail -f /var/log/dbus-maxxfan-bridge/current | tai64nlocal"
