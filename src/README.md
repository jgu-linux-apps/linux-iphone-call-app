# Linux iPhone Calls

Answer and make **iPhone calls on Ubuntu** over Bluetooth. Your laptop acts as a hands-free
kit (like a car): see who is calling, answer on the laptop, keep the call on the iPhone or
decline it, and call anyone from your iPhone contacts.

**Version 0.1.8** · 2026-11-14

**Created by: JGu**  
**Supported by Claude**

Part of the series: linux-icloud-photos · linux-icloud-mail · linux-apple-music-player ·
linux-imessage · **linux-iphone-call-app**.

> 🇵🇱 Odbieranie i wykonywanie połączeń z iPhone'a na Ubuntu przez Bluetooth. Interfejs
> PL/EN według języka systemu. Opis po polsku na dole.

## Features

- **Incoming call** popup + notification with three choices:
  **Answer** (on the laptop) · **On iPhone** (stop ringing here, answer on the phone) · **Decline**
- Caller name from your iPhone contacts (matched on the last 9 digits, so `+48`, `0048`
  and local numbers all match)
- In-call: mute, keypad (DTMF), **move audio to iPhone ⇄ laptop**, end call, call timer
- **Mic echo & noise cancellation** (free WebRTC audio processing built into PipeWire:
  echo cancel + noise suppression + automatic gain), on by default, toggle in the menu
- **Keypad** with contact autocomplete, **Contacts** with search, **Recents** (iPhone call
  history incl. missed calls)
- Missed-call notification with **Call back**
- **Tray** icon with status colors (idle / ringing / in call / missed / offline) and menu;
  closing the window keeps it in the tray, quit from the tray menu
- **Light/dark theme** following the system, with matching app icon
- **Aurora theme** (menu → Theme): the shared look of the JGu Linux Apps series, violet-to-cyan gradients and glow, light and dark
- **PL / EN** UI following the system language
- Option **“Keep iPhone app audio on the iPhone”**: games, YouTube, music stay on the
  phone; only calls come to the laptop (enabled by default)
- **3 chill ringtones** to choose from (Morning – marimba, Wave – lo-fi keys, Droplet – kalimba;
  original, synthesized by `tools/make_ringtones.py`) or the system one; preview on select
- Optional ringtone on the laptop, start at login (enabled on first run)
- Version and build date shown bottom-left; **About** (Created by: JGu · Supported by Claude) and **Diagnostics** dialogs

## Privacy

Everything stays on your machine. Contacts and call history are pulled from the iPhone over
Bluetooth (PBAP), cached in `~/.local/share/linux-iphone-call-app/` with `0600`
permissions, and never sent anywhere. No network access is used at all.

## Requirements

- Ubuntu with **PipeWire ≥ 1.4** (Bluetooth telephony service `org.pipewire.Telephony`),
  e.g. Ubuntu 25.10. Ubuntu 24.04 ships PipeWire 1.0, which does not have it — the app
  shows a warning and the Diagnostics dialog explains it.
- WirePlumber 0.4 or 0.5, BlueZ with `bluez-obexd`
- iPhone paired with the laptop. For contacts/history on the iPhone:
  **Settings → Bluetooth → (i) next to the laptop → Sync Contacts**

Check your version:

```bash
pipewire --version
```

## Install

Download the newest `linux-iphone-call-app_<version>_all.deb` from the [Releases page](https://github.com/jgu-linux-apps/linux-iphone-call-app/releases/latest), then:

```bash
sudo apt install ./linux-iphone-call-app_<version>_all.deb
linux-iphone-call-app            # or from the app grid: “Linux iPhone Calls”
```

Update: quit from the tray (or `pkill -f linux_iphone_call_app`), install the new `.deb`,
start again.

## Run from source

The source code is in the `src/` folder of this repository; the `.deb` packages are not kept in git but
attached to [GitHub Releases](https://github.com/jgu-linux-apps/linux-iphone-call-app/releases). Pushing a tag `vX.Y.Z` that matches `VERSION` in
`src/src/linux_iphone_call_app/__init__.py` makes GitHub Actions (`.github/workflows/release.yml`) build the
package and publish the release. Run the commands below inside `src/`:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 \
                 bluez-obexd pipewire-bin wireplumber librsvg2-common
PYTHONPATH=src python3 -m linux_iphone_call_app.app
```

Build the package: `packaging/build-deb.sh` → `dist/linux-iphone-call-app_<ver>_all.deb`

UI test against mocked BlueZ / PipeWire telephony (screenshots in `/tmp/lica-shots`):

```bash
dbus-run-session -- xvfb-run -a -s "-screen 0 1000x780x24" tests/run_ui_test.sh
```

## How it works

| Part | Technology |
|---|---|
| Call control (ring, answer, decline, dial, DTMF) | PipeWire Bluetooth telephony D-Bus API (`org.pipewire.Telephony`, HFP hands-free role) |
| Call audio | HFP/SCO via PipeWire; bridged to speakers/mic with `pw-loopback` if WirePlumber hasn't linked it |
| Mic quality | PipeWire `module-echo-cancel` with WebRTC (AEC, noise suppression, AGC) in a helper `pipewire -c` process during the call |
| Audio to iPhone / laptop | to iPhone: `RejectSCO` + phone sound card profile *off* (audio link released, control link kept, so the iPhone doesn't pull the call back); to laptop: profile back on + `Activate` |
| Contacts, call history | Bluetooth PBAP via `bluez-obexd` |
| Connect / disconnect | BlueZ `Device1.ConnectProfile` for the Hands-Free Audio Gateway only (no media) |
| App audio stays on iPhone | WirePlumber drop-in removing the `a2dp_sink` role, then a WirePlumber restart (postponed until no call is active) |
| Ringtones | Bundled in the package (`/usr/share/linux-iphone-call-app/sounds/`), played with `pw-play`; nothing is downloaded |
| UI | Python 3 + GTK 3, Ayatana AppIndicator tray, freedesktop notifications |

Files written to your config:

- `~/.config/linux-iphone-call-app/config.json`
- `~/.config/autostart/linux-iphone-call-app.desktop` (toggle in the menu)
- `~/.config/wireplumber/wireplumber.conf.d/51-linux-iphone-call-app-no-phone-media.conf`
  (WirePlumber 0.5) or `~/.config/wireplumber/bluetooth.lua.d/51-linux-iphone-call-app-no-phone-media.lua`
  (0.4), only while the option is on

## Limitations

- Regular cellular calls only (no FaceTime / WhatsApp audio)
- Hands-free audio quality (mSBC 16 kHz, like a car kit; CVSD 8 kHz if the Bluetooth adapter
  can't do mSBC — see *Audio transport codec* in Diagnostics)
- One phone at a time (choose it in the menu if several are paired)
- “Keep iPhone app audio on the iPhone” applies to every phone: no phone can use the
  laptop as a Bluetooth speaker while it is on

## Troubleshooting

- **“Bluetooth telephony service missing”** → PipeWire is older than 1.4.
- **No contacts** → enable *Sync Contacts* on the iPhone for this laptop, then menu →
  *Refresh contacts and history*.
- **Bad microphone quality** → make sure *Mic echo & noise cancellation* is on; check the codec
  in Diagnostics (CVSD = narrowband); a headset with a mic is always better than laptop speakers + mic.
- **Move to iPhone didn't work** → on the iPhone: call screen → *Audio* → *iPhone* always works.
- **App audio still on the laptop** → toggle Bluetooth on the iPhone once; check the
  Diagnostics line *App audio stays on iPhone*.
- Run `linux-iphone-call-app` from a terminal to see logs, and include the Diagnostics text
  in bug reports.

---

## Po polsku

**Linux iPhone Calls** – laptop jako zestaw głośnomówiący dla iPhone'a. Gdy ktoś dzwoni,
widzisz kto, i wybierasz: **Odbierz** (na laptopie), **Na iPhonie** albo **Odrzuć**. W trakcie
rozmowy: wyciszenie, klawiatura, przenoszenie dźwięku iPhone ⇄ laptop. Dzwonisz z klawiatury
(z podpowiadaniem kontaktów), z listy kontaktów albo z historii połączeń. Tray, powiadomienia,
motyw i ikona jasna/ciemna, interfejs PL/EN. Opcja „Dźwięk aplikacji iPhone'a zostaje na
iPhonie” sprawia, że gry i YouTube grają na telefonie, a na laptopa trafiają tylko rozmowy.
Redukcja echa i szumów mikrofonu (WebRTC, wbudowane w PipeWire) jest domyślnie włączona.
Do wyboru 3 spokojne dzwonki: Poranek (marimba), Fala (lo-fi pianino), Kropla (kalimba)
albo systemowy – menu ☰ → „Dźwięk dzwonka”. Dzwonki są w paczce, nic nie jest pobierane.

Wymaga PipeWire 1.4+. Wszystkie dane zostają lokalnie na laptopie.

## Changelog

- **0.1.8** (2026-11-14) – new **Aurora** theme (menu → Theme), the same look as the other apps in the series; light and dark follow the system. The green and red call buttons keep their colours.
- **0.1.7** (2026-11-12) – license: the app is now published under the Freeware License (No Modifications), see `LICENSE`; free to use and share unmodified, modification is not permitted. No other changes in the app.
- **0.1.6** (2026-11-12) – no changes in the app: the repository now keeps the source code in `src/`,
  and the `.deb` is published on the GitHub Releases page (built by GitHub Actions for every version tag)
- **0.1.5** (2026-11-07) – 3 bundled chill ringtones (Morning, Wave, Droplet) + system; choice in
  the menu with instant preview
- **0.1.4** (2026-11-07) – mic echo & noise cancellation (WebRTC in PipeWire, on by default);
  “Move to iPhone” is immediate and no longer jumps back to the laptop (no Bluetooth re-connect);
  codec shown in Diagnostics
- **0.1.3** (2026-11-06) – About dialog: Created by: JGu · Supported by Claude
- **0.1.2** (2026-11-04) – option “Keep iPhone app audio on the iPhone”; README, LICENSE
- **0.1.1** (2026-11-04) – fix: window title bar was missing (window couldn't be moved, tabs and
  menu were hidden)
- **0.1.0** (2026-11-04) – first version: incoming calls (answer on laptop / on iPhone / decline),
  dialing, contacts, recents, tray, notifications, light/dark theme and icon, PL/EN

## License

Freeware License (No Modifications) — free to use and to share unmodified; modification is not permitted. See [LICENSE](LICENSE). Versions before 0.1.7 were published under the MIT License. Created by: JGu · Supported by Claude. The phone handset glyph in the icons is based on Material
Icons “call” (Apache License 2.0, © Google).
