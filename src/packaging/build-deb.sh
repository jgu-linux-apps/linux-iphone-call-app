#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER=$(python3 -c "exec(open('$ROOT/src/linux_iphone_call_app/__init__.py').read()); print(VERSION)")
PKG=linux-iphone-call-app
B=$(mktemp -d)/${PKG}_${VER}_all
mkdir -p $B/DEBIAN $B/usr/bin $B/usr/lib/$PKG $B/usr/share/$PKG/icons $B/usr/share/applications \
         $B/usr/share/icons/hicolor/scalable/apps $B/usr/share/icons/hicolor/256x256/apps $B/usr/share/icons/hicolor/48x48/apps
cp -r $ROOT/src/linux_iphone_call_app $B/usr/lib/$PKG/
find $B -name __pycache__ -prune -exec rm -rf {} +
cp $ROOT/data/icons/*.svg $B/usr/share/$PKG/icons/
mkdir -p $B/usr/share/$PKG/sounds && cp $ROOT/data/sounds/*.wav $B/usr/share/$PKG/sounds/
for n in linux-iphone-call-app linux-iphone-call-app-dark; do
  cp $ROOT/data/icons/$n.svg $B/usr/share/icons/hicolor/scalable/apps/
  rsvg-convert -w 256 -h 256 $ROOT/data/icons/$n.svg -o $B/usr/share/icons/hicolor/256x256/apps/$n.png
  rsvg-convert -w 48 -h 48 $ROOT/data/icons/$n.svg -o $B/usr/share/icons/hicolor/48x48/apps/$n.png
done
cat > $B/usr/bin/$PKG <<'EOS'
#!/bin/sh
export PYTHONPATH=/usr/lib/linux-iphone-call-app${PYTHONPATH:+:$PYTHONPATH}
exec /usr/bin/python3 -m linux_iphone_call_app.app "$@"
EOS
chmod 755 $B/usr/bin/$PKG
cat > $B/usr/share/applications/$PKG.desktop <<EOS
[Desktop Entry]
Type=Application
Name=Linux iPhone Calls
GenericName=Phone
Comment=Answer and make iPhone calls on this laptop over Bluetooth
Comment[pl]=Odbieraj i wykonuj połączenia z iPhone'a na laptopie przez Bluetooth
Exec=$PKG
Icon=$PKG
Categories=Network;Telephony;GTK;
Keywords=phone;call;iphone;bluetooth;telefon;połączenie;
StartupWMClass=linux-iphone-call-app
StartupNotify=true
EOS
mkdir -p $B/usr/share/doc/$PKG && cp $ROOT/README.md $B/usr/share/doc/$PKG/ && cp $ROOT/LICENSE $B/usr/share/doc/$PKG/copyright
SIZE=$(du -sk $B/usr | cut -f1)
cat > $B/DEBIAN/control <<EOS
Package: $PKG
Version: $VER
Section: comm
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, bluez, bluez-obexd, pipewire-bin, wireplumber, libspa-0.2-bluetooth, librsvg2-common
Recommends: gir1.2-ayatanaappindicator3-0.1, libspa-0.2-modules, sound-theme-freedesktop, pipewire (>= 1.4)
Maintainer: JGu <jaroslawguza83@gmail.com>
Description: Linux iPhone Calls - iPhone calls on Ubuntu over Bluetooth
 Shows who is calling your iPhone, lets you answer on the laptop, send the
 call to the iPhone or decline it, and make calls from your iPhone contacts.
 Uses Bluetooth hands-free (PipeWire telephony) and PBAP. Everything stays local.
 .
 Created by: JGu
 Supported by Claude
EOS
cat > $B/DEBIAN/postinst <<'EOS'
#!/bin/sh
set -e
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -f /usr/share/icons/hicolor || true
command -v update-desktop-database >/dev/null && update-desktop-database -q || true
exit 0
EOS
chmod 755 $B/DEBIAN/postinst
mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build $B "$ROOT/dist/${PKG}_${VER}_all.deb"
