#!/bin/bash
# Drives the app against the mocks and takes screenshots into $OUT. Run under:
#   dbus-run-session -- xvfb-run -s "-screen 0 1100x800x24" tests/run_ui_test.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${OUT:-/tmp/lica-shots}"
DARK="${DARK:-0}"
mkdir -p "$OUT"
export HOME=$(mktemp -d)
export XDG_CONFIG_HOME=$HOME/.config XDG_DATA_HOME=$HOME/.local/share
mkdir -p "$XDG_DATA_HOME/linux-iphone-call-app" "$XDG_CONFIG_HOME/linux-iphone-call-app"
echo '{"first_run_done": true}' > "$XDG_CONFIG_HOME/linux-iphone-call-app/config.json"
NOW=$(date +%s)
cat > "$XDG_DATA_HOME/linux-iphone-call-app/contacts.json" <<EOF
{"ts": $NOW, "contacts": [
 {"name": "Anna Kowalska", "numbers": [["mobile", "+48 601 234 567"]]},
 {"name": "Bartek Nowak", "numbers": [["mobile", "+48 512 000 111"], ["work", "22 555 01 02"]]},
 {"name": "Mama", "numbers": [["mobile", "+48 600 700 800"]]},
 {"name": "Piotr Wiśniewski", "numbers": [["mobile", "+48 698 765 432"]]}]}
EOF
cat > "$XDG_DATA_HOME/linux-iphone-call-app/recents.json" <<EOF
{"items": [
 {"name": "Mama", "number": "+48600700800", "type": "missed", "time": $((NOW-3600))},
 {"name": "", "number": "+48512000111", "type": "dialed", "time": $((NOW-7200))},
 {"name": "Anna Kowalska", "number": "+48601234567", "type": "received", "time": $((NOW-90000))}]}
EOF
export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"
export LANG=pl_PL.UTF-8 NO_AT_BRIDGE=1
[ "$DARK" = 1 ] && export GTK_THEME=Adwaita:dark
python3.12 "$ROOT/tests/mock_services.py" > "$OUT/mock.log" 2>&1 &
sleep 1.5
PYTHONPATH="$ROOT/src" python3.12 -u -m linux_iphone_call_app.app > "$OUT/app.log" 2>&1 &
APP=$!
sleep 3
shot(){ import -window root "$OUT/$1.png"; }
M="gdbus call --session --dest org.lica.Mock --object-path /mock --method org.lica.Mock"
act(){ gdbus call --session --dest io.github.jaro.LinuxIphoneCallApp --object-path /io/github/jaro/LinuxIphoneCallApp \
  --method org.gtk.Actions.Activate "$1" "${2:-[]}" {} >/dev/null; }
shot 01-keypad
act search '[<"bar">]'; sleep 0.6; shot 02-contacts
act tab '[<"recents">]'; sleep 0.6; shot 03-recents
act tab '[<"keypad">]'
$M.Ring "+48601234567" >/dev/null; sleep 1.5; shot 04-incoming
act answer; sleep 2.5; shot 05-incall-laptop
act route; sleep 4.5; shot 06-moved-to-iphone
sleep 6; shot 06b-after-reconnect
act route; sleep 1.5; shot 06c-back-to-laptop
act hangup; sleep 1.5; shot 07-after-hangup
$M.Ring "+48555123456" >/dev/null; sleep 1.2
act answer-iphone; sleep 1; shot 08-ringing-on-iphone
$M.RemoteHangup >/dev/null; sleep 1.5; shot 09-missed
act dial '[<"+48600700800">]'; sleep 2.5; shot 10-outgoing
act hangup; sleep 1
act about; sleep 1; shot 11-about
gdbus call --session --dest io.github.jaro.LinuxIphoneCallApp --object-path /io/github/jaro/LinuxIphoneCallApp --method org.gtk.Actions.SetState ringtone-sound "<\"droplet\">" {} >/dev/null; sleep 0.5
cat "$XDG_CONFIG_HOME/linux-iphone-call-app/config.json"; echo
kill $APP; sleep 0.5
echo "--- done"
