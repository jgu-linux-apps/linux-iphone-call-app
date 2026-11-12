"""Tiny PL/EN translation table, language follows the system locale."""
import locale
import os

def _detect():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var, "")
        if v:
            return "pl" if v.lower().startswith("pl") else "en"
    try:
        loc = locale.getlocale()[0] or ""
        return "pl" if loc.lower().startswith("pl") else "en"
    except Exception:
        return "en"

LANG = _detect()

_T = {
    "keypad": ("Klawiatura", "Keypad"),
    "contacts": ("Kontakty", "Contacts"),
    "recents": ("Ostatnie", "Recents"),
    "search": ("Szukaj kontaktu…", "Search contacts…"),
    "number_hint": ("Numer lub nazwa", "Number or name"),
    "call": ("Zadzwoń", "Call"),
    "incoming": ("Połączenie przychodzące", "Incoming call"),
    "incoming_waiting": ("Drugie połączenie przychodzące", "Call waiting"),
    "answer_laptop": ("Odbierz na laptopie", "Answer on laptop"),
    "answer_short": ("Odbierz", "Answer"),
    "on_iphone": ("Na iPhonie", "On iPhone"),
    "on_iphone_long": ("Odbierz na iPhonie", "Answer on iPhone"),
    "reject": ("Odrzuć", "Decline"),
    "hangup": ("Rozłącz", "End"),
    "mute": ("Wycisz", "Mute"),
    "unmute": ("Wyciszony", "Muted"),
    "dtmf": ("Klawiatura", "Keypad"),
    "to_iphone": ("Przenieś na iPhone", "Move to iPhone"),
    "to_laptop": ("Przenieś na laptop", "Move to laptop"),
    "audio_laptop": ("Dźwięk: laptop", "Audio: laptop"),
    "audio_iphone": ("Dźwięk: iPhone", "Audio: iPhone"),
    "state_incoming": ("Dzwoni…", "Ringing…"),
    "state_waiting": ("Czeka…", "Waiting…"),
    "state_dialing": ("Wybieranie…", "Dialing…"),
    "state_alerting": ("Łączenie…", "Calling…"),
    "state_active": ("Rozmowa", "Active"),
    "state_held": ("Wstrzymane", "On hold"),
    "state_disconnected": ("Zakończono", "Ended"),
    "ringing_on_iphone": ("Dzwoni na iPhonie — odbierz na telefonie", "Ringing on iPhone — answer on the phone"),
    "call_on_iphone": ("Rozmowa trwa na iPhonie", "Call continues on iPhone"),
    "missed": ("Nieodebrane połączenie", "Missed call"),
    "call_back": ("Oddzwoń", "Call back"),
    "unknown": ("Nieznany numer", "Unknown number"),
    "private": ("Numer prywatny", "Private number"),
    "connected_to": ("Połączono: {}", "Connected: {}"),
    "not_connected": ("iPhone niepołączony", "iPhone not connected"),
    "connecting": ("Łączenie z iPhone…", "Connecting to iPhone…"),
    "connect": ("Połącz z iPhone", "Connect iPhone"),
    "disconnect": ("Rozłącz iPhone", "Disconnect iPhone"),
    "no_iphone": ("Nie znaleziono sparowanego iPhone'a", "No paired iPhone found"),
    "show": ("Pokaż", "Show"),
    "quit": ("Zakończ", "Quit"),
    "settings": ("Ustawienia", "Settings"),
    "ringtone": ("Dzwonek na laptopie", "Ringtone on laptop"),
    "autostart": ("Uruchamiaj przy logowaniu", "Start at login"),
    "media_on_iphone": ("Dźwięk aplikacji iPhone'a zostaje na iPhonie", "Keep iPhone app audio on the iPhone"),
    "ringtone_sound": ("Dźwięk dzwonka", "Ringtone sound"),
    "tone_morning": ("Poranek (marimba)", "Morning (marimba)"),
    "tone_wave": ("Fala (lo-fi pianino)", "Wave (lo-fi keys)"),
    "tone_droplet": ("Kropla (kalimba)", "Droplet (kalimba)"),
    "tone_system": ("Systemowy", "System"),
    "aec": ("Redukcja echa i szumów mikrofonu", "Mic echo & noise cancellation"),
    "route_hint": ("Nie udało się oddać dźwięku automatycznie. Na iPhonie: ekran rozmowy → Audio → iPhone.",
                   "Could not hand the audio over automatically. On the iPhone: call screen → Audio → iPhone."),
    "about": ("O aplikacji", "About"),
    "about_desc": ("Połączenia z iPhone'a na Ubuntu przez Bluetooth", "iPhone calls on Ubuntu over Bluetooth"),
    "refresh_contacts": ("Odśwież kontakty i historię", "Refresh contacts and history"),
    "diagnostics": ("Diagnostyka", "Diagnostics"),
    "choose_iphone": ("Wybierz iPhone", "Choose iPhone"),
    "contacts_count": ("{} kontaktów", "{} contacts"),
    "contacts_loading": ("Pobieranie kontaktów z iPhone…", "Fetching contacts from iPhone…"),
    "contacts_failed": ("Nie udało się pobrać kontaktów. Na iPhonie: Ustawienia → Bluetooth → (i) przy laptopie → włącz „Synchronizuj kontakty”.",
                        "Could not fetch contacts. On iPhone: Settings → Bluetooth → (i) next to the laptop → enable “Sync Contacts”."),
    "no_contacts": ("Brak kontaktów", "No contacts"),
    "no_recents": ("Brak historii połączeń", "No call history"),
    "today": ("Dziś", "Today"),
    "yesterday": ("Wczoraj", "Yesterday"),
    "telephony_missing_title": ("Brak usługi telefonii Bluetooth", "Bluetooth telephony service missing"),
    "telephony_missing": (
        "Aplikacja używa usługi telefonii z PipeWire (wersja 1.4 lub nowsza). "
        "Wykryta wersja PipeWire: {}. Kliknij „Diagnostyka”, aby zobaczyć szczegóły.",
        "The app uses PipeWire's telephony service (version 1.4 or newer). "
        "Detected PipeWire version: {}. Open “Diagnostics” for details."),
    "dial_failed": ("Nie udało się zadzwonić: {}", "Call failed: {}"),
    "close": ("Zamknij", "Close"),
    "copy": ("Kopiuj", "Copy"),
    "mobile": ("komórka", "mobile"),
    "home": ("dom", "home"),
    "work": ("praca", "work"),
    "other": ("inny", "other"),
    "main": ("główny", "main"),
    "iphone_label": ("iPhone", "iPhone"),
}

def _(key, *args):
    pair = _T.get(key)
    s = key if pair is None else (pair[0] if LANG == "pl" else pair[1])
    return s.format(*args) if args else s
