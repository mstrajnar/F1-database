import json
import re
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests

# Osnovni OpenF1 API URL
OSNOVA_URL = "https://api.openf1.org/v1"

# Mapa za lokalni predpomnilnik API odgovorov
PREDPOMNILNIK = Path("predpomnilnik_openf1")
PREDPOMNILNIK.mkdir(exist_ok=True)

# OpenF1 zgodovinski podatki
MIN_LETO = 2023

# Kratek zamik med API klici
ZAMIK = 0.6

# Podprti nameni poizvedb
NAMENI = {
    "zmage",
    "tocke",
    "stopnicke",
    "krogi",
    "vreme",
    "postanki",
    "rezultati",
    "start",
    "radio",
    "stinti",
    "prehitevanja"
}

# Vzdevki za lažji vnos voznikov
VZDEVKI = {
    "ham": "lewis hamilton",
    "hamilton": "lewis hamilton",
    "lewis": "lewis hamilton",
    "lec": "charles leclerc",
    "leclerc": "charles leclerc",
    "charles": "charles leclerc",
    "ver": "max verstappen",
    "verstappen": "max verstappen",
    "max": "max verstappen",
    "nor": "lando norris",
    "norris": "lando norris",
    "lando": "lando norris",
    "rus": "george russell",
    "russell": "george russell",
    "george": "george russell",
    "alo": "fernando alonso",
    "alonso": "fernando alonso",
    "fernando": "fernando alonso",
    "per": "sergio perez",
    "perez": "sergio perez",
    "sergio": "sergio perez",
    "pia": "oscar piastri",
    "piastri": "oscar piastri",
    "oscar": "oscar piastri",
    "sai": "carlos sainz",
    "sainz": "carlos sainz",
    "carlos": "carlos sainz",
}

def normaliziraj(besedilo):
    # Poenoti zapis besedila
    besedilo = "" if besedilo is None else str(besedilo)
    besedilo = unicodedata.normalize("NFKC", besedilo).lower().strip().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", besedilo)

def ime_datoteke_predpomnilnika(ime, parametri):
    # Ustvari varno ime datoteke za cache
    niz = "__".join([ime] + [f"{k}={parametri[k]}" for k in sorted(parametri)])
    niz = re.sub(r"[^a-zA-Z0-9_=.-]+", "_", niz)
    return PREDPOMNILNIK / f"{niz}.json"

def pridobi(ime, **parametri):
    # Najprej poskusi prebrati iz cache-a
    pot = ime_datoteke_predpomnilnika(ime, parametri)
    if pot.exists():
        return json.loads(pot.read_text(encoding="utf-8"))

    # Če ni cache-a, kliči API
    odgovor = requests.get(f"{OSNOVA_URL}/{ime}", params=parametri, timeout=30)
    odgovor.raise_for_status()
    podatki = odgovor.json()

    # Shrani odgovor lokalno
    pot.write_text(json.dumps(podatki), encoding="utf-8")
    time.sleep(ZAMIK)
    return podatki

def tabela(ime, **parametri):
    # API odgovor pretvori v DataFrame
    podatki = pridobi(ime, **parametri)
    return pd.json_normalize(podatki) if podatki else pd.DataFrame()

def uradno_ime(ime):
    # Pretvori vzdevek v uradno ime
    ime = normaliziraj(ime)
    return VZDEVKI.get(ime, ime)

def razberi_vnos(vnos):
    # Iz vnosa razbere voznika, leto in namen
    t = normaliziraj(vnos)
    besede = t.split()
    leto = next((int(b) for b in besede if b.isdigit() and len(b) == 4), None)
    namen = next((b for b in besede if b in NAMENI), None)
    voznik = uradno_ime(" ".join([b for b in besede if b not in NAMENI and b != str(leto)]))
    return voznik, leto, namen

def seje_tekme(leto):
    # Vrne samo race seje za leto
    s = tabela("sessions", year=leto)
    if s.empty:
        return s

    if "session_type" in s.columns:
        s = s[s["session_type"].fillna("") == "Race"]
    elif "session_name" in s.columns:
        s = s[s["session_name"].fillna("").str.contains("race", case=False)]

    return s.sort_values("date_start") if "date_start" in s.columns else s

def srecanja(leto):
    # Vrne meetings za izbrano leto
    return tabela("meetings", year=leto)

def poisci_voznika(iskano_ime, leto):
    # Poišče driver_number in full_name
    s = seje_tekme(leto)
    if s.empty or "session_key" not in s.columns:
        return None, None

    vozniki = tabela("drivers", session_key=int(s.iloc[0]["session_key"]))
    if vozniki.empty:
        return None, None

    q = uradno_ime(iskano_ime)

    for stolpec in ["full_name", "first_name", "last_name", "broadcast_name", "name_acronym"]:
        if stolpec in vozniki.columns:
            vozniki[stolpec + "_n"] = vozniki[stolpec].fillna("").map(normaliziraj)

    for stolpec in ["full_name_n", "last_name_n", "first_name_n", "broadcast_name_n", "name_acronym_n"]:
        if stolpec in vozniki.columns:
            ujemanje = vozniki[vozniki[stolpec] == q]
            if not ujemanje.empty:
                vrstica = ujemanje.iloc[0]
                return int(vrstica["driver_number"]), str(vrstica["full_name"])

    if "full_name_n" in vozniki.columns:
        ujemanje = vozniki[vozniki["full_name_n"].str.contains(q, na=False)]
        if not ujemanje.empty:
            vrstica = ujemanje.iloc[0]
            return int(vrstica["driver_number"]), str(vrstica["full_name"])

    return None, None

def cez_seje(leto, koncna_tocka, stevilka_voznika=None):
    # Prebere en endpoint čez vse race seje
    s = seje_tekme(leto)
    m = srecanja(leto)

    stolpci_srecanja = [c for c in ["meeting_key", "meeting_name", "country_name"] if c in m.columns]
    m = m[stolpci_srecanja].drop_duplicates() if not m.empty and stolpci_srecanja else pd.DataFrame()

    vrstice = []

    for _, seja in s.iterrows():
        parametri = {"session_key": int(seja["session_key"])}
        if stevilka_voznika is not None:
            parametri["driver_number"] = int(stevilka_voznika)

        x = tabela(koncna_tocka, **parametri)
        if x.empty:
            continue

        for c in ["session_name", "session_type", "date_start", "meeting_key"]:
            if c in seja.index:
                x[c] = seja[c]

        vrstice.append(x)

    if not vrstice:
        return pd.DataFrame()

    izhod = pd.concat(vrstice, ignore_index=True, sort=False)

    if not m.empty and "meeting_key" in izhod.columns:
        izhod = izhod.merge(m, on="meeting_key", how="left")

    return izhod

def oblikuj(naslov, okvir, stolpci=None):
    # Lep tekstovni izpis tabel
    if okvir.empty:
        return naslov + "\n" + "=" * 70 + "\nNi zadetkov."

    izhod = okvir.copy()

    if stolpci:
        izhod = izhod[[c for c in stolpci if c in izhod.columns]]

    for c in izhod.columns:
        if pd.api.types.is_float_dtype(izhod[c]):
            izhod[c] = izhod[c].round(3)

    return naslov + "\n" + "=" * 70 + "\n" + izhod.to_string(index=False)

def izpis_pomoci():
    return (
        "POMOČ\n"
        + "=" * 70
        + "\nProgram sprejme poizvedbo v obliki: IME VOZNIKA LETO NAMEN"
        + "\n\nMožni nameni:\n"
        + "- zmage         -> zmage voznika v sezoni\n"
        + "- stopnicke     -> uvrstitve med prve 3\n"
        + "- rezultati     -> rezultati vseh dirk v sezoni\n"
        + "- tocke         -> napredek točk v prvenstvu\n"
        + "- krogi         -> povzetek krogov\n"
        + "- vreme         -> vremenski povzetek po dirkah\n"
        + "- postanki      -> postanki v boksih\n"
        + "- start         -> startne pozicije\n"
        + "- radio         -> radijska sporočila ekipe\n"
        + "- stinti        -> stinti pnevmatik\n"
        + "- prehitevanja  -> prehitevanja povezana z voznikom\n"
        + "\nMožni parametri v poizvedbi:\n"
        + "- ime voznika, na primer: Lewis Hamilton, Max Verstappen, Charles Leclerc\n"
        + "- vzdevki voznikov, na primer: ham, ver, lec, nor, rus, alo, per, pia, sai\n"
        + "- leto, od 2023 dalje\n"
        + "- namen iz zgornjega seznama\n"
        + "\nPosebni ukazi:\n"
        + "- help                   -> izpiše to pomoč\n"
        + "- pocisti_predpomnilnik -> pobriše shranjene API odgovore\n"
        + "- exit                  -> zapre program\n"
        + "\nPrimeri poizvedb:\n"
        + "- Charles Leclerc 2024 stopnicke\n"
        + "- Lewis Hamilton 2024 tocke\n"
        + "- Max Verstappen 2024 zmage\n"
        + "- Lando Norris 2024 krogi\n"
        + "- Fernando Alonso 2024 radio\n"
    )

def odgovori(voznik, leto, namen):
    # Glavni usmerjevalnik poizvedb
    if not voznik or leto is None or not namen:
        return "Uporabi obliko, na primer: Charles Leclerc 2024 stopnicke"

    if leto < MIN_LETO:
        return f"Zgodovinski podatki OpenF1 so na voljo od leta {MIN_LETO}."

    stevilka, polno_ime = poisci_voznika(voznik, leto)
    if stevilka is None:
        return f"Voznik ni bil najden: {voznik}"

    if namen in {"zmage", "stopnicke", "rezultati"}:
        r = cez_seje(leto, "session_result", stevilka)
        if r.empty:
            return "Ni podatkov o rezultatih sej."

        if "position" in r.columns:
            r["position"] = pd.to_numeric(r["position"], errors="coerce")

        if namen == "zmage":
            r = r[r["position"] == 1]
            return oblikuj(
                f"{polno_ime} - zmage v {leto}: {len(r)}",
                r,
                ["meeting_name", "country_name", "session_name", "position", "number_of_laps", "duration"]
            )

        if namen == "stopnicke":
            r = r[r["position"].between(1, 3)]
            return oblikuj(
                f"{polno_ime} - stopnicke v {leto}: {len(r)}",
                r,
                ["meeting_name", "country_name", "session_name", "position", "number_of_laps", "duration"]
            )

        return oblikuj(
            f"{polno_ime} - rezultati dirk v {leto}",
            r,
            ["meeting_name", "country_name", "session_name", "position", "number_of_laps", "duration", "gap_to_leader"]
        )

    if namen == "tocke":
        c = cez_seje(leto, "championship_drivers", stevilka)
        if c.empty:
            return "Ni podatkov o prvenstvu."

        for stolpec in ["points_start", "points_current"]:
            if stolpec in c.columns:
                c[stolpec] = pd.to_numeric(c[stolpec], errors="coerce")

        if all(x in c.columns for x in ["points_start", "points_current"]):
            c["pridobljene_tocke"] = c["points_current"].fillna(0) - c["points_start"].fillna(0)

        return oblikuj(
            f"{polno_ime} - napredek tock v {leto}",
            c,
            ["session_name", "points_start", "points_current", "pridobljene_tocke", "position_start", "position_current"]
        )

    if namen == "krogi":
        k = cez_seje(leto, "laps", stevilka)
        if k.empty:
            return "Ni podatkov o krogih."

        for stolpec in ["lap_number", "lap_duration"]:
            if stolpec in k.columns:
                k[stolpec] = pd.to_numeric(k[stolpec], errors="coerce")

        povzetek = k.groupby(
            [c for c in ["meeting_name", "session_name"] if c in k.columns],
            dropna=False
        ).agg(
            skupaj_krogov=("lap_number", "max"),
            najboljsi_krog=("lap_duration", "min"),
            povprecen_krog=("lap_duration", "mean")
        ).reset_index()

        return oblikuj(f"{polno_ime} - povzetek krogov v {leto}", povzetek)

    if namen == "vreme":
        v = cez_seje(leto, "weather")
        if v.empty:
            return "Ni vremenskih podatkov."

        for stolpec in ["air_temperature", "track_temperature", "humidity", "wind_speed", "rainfall"]:
            if stolpec in v.columns:
                v[stolpec] = pd.to_numeric(v[stolpec], errors="coerce")

        povzetek = v.groupby(
            [c for c in ["meeting_name", "session_name"] if c in v.columns],
            dropna=False
        ).agg(
            povp_temp_zrak=("air_temperature", "mean"),
            povp_temp_proga=("track_temperature", "mean"),
            povp_vlaga=("humidity", "mean"),
            povp_veter=("wind_speed", "mean"),
            max_dez=("rainfall", "max")
        ).reset_index()

        return oblikuj(f"Povzetek vremena v {leto}", povzetek)

    if namen == "postanki":
        p = cez_seje(leto, "pit", stevilka)
        if p.empty:
            return "Ni podatkov o postankih."

        for stolpec in ["lap_number", "pit_duration", "lane_duration"]:
            if stolpec in p.columns:
                p[stolpec] = pd.to_numeric(p[stolpec], errors="coerce")

        return oblikuj(
            f"{polno_ime} - postanki v boksih v {leto}: {len(p)}",
            p,
            ["meeting_name", "session_name", "lap_number", "pit_duration", "lane_duration"]
        )

    if namen == "start":
        z = cez_seje(leto, "starting_grid", stevilka)
        if z.empty:
            return "Ni podatkov o startni razvrstitvi."
        return oblikuj(f"{polno_ime} - startne pozicije v {leto}", z, ["meeting_name", "session_name", "position"])

    if namen == "radio":
        r = cez_seje(leto, "team_radio", stevilka)
        if r.empty:
            return "Ni podatkov o radijskih sporocilih ekipe."
        return oblikuj(f"{polno_ime} - radio ekipe v {leto}", r, ["meeting_name", "session_name", "date", "recording_url"])

    if namen == "stinti":
        s = cez_seje(leto, "stints", stevilka)
        if s.empty:
            return "Ni podatkov o stintih."
        return oblikuj(
            f"{polno_ime} - stinti pnevmatik v {leto}",
            s,
            ["meeting_name", "session_name", "stint_number", "compound", "lap_start", "lap_end", "tyre_age_at_start"]
        )

    if namen == "prehitevanja":
        p = cez_seje(leto, "overtakes")
        if p.empty:
            return "Ni podatkov o prehitevanjih."

        if "overtaking_driver_number" in p.columns:
            p["overtaking_driver_number"] = pd.to_numeric(p["overtaking_driver_number"], errors="coerce")
        if "overtaken_driver_number" in p.columns:
            p["overtaken_driver_number"] = pd.to_numeric(p["overtaken_driver_number"], errors="coerce")

        p = p[(p.get("overtaking_driver_number") == stevilka) | (p.get("overtaken_driver_number") == stevilka)]

        return oblikuj(
            f"{polno_ime} - prehitevanja v {leto}",
            p,
            ["meeting_name", "session_name", "overtaking_driver_number", "overtaken_driver_number", "position", "date"]
        )

    return "Ta namen trenutno ni podprt."

def glavni_program():
    # Zacetni izpis
    print("openf1 database")
    print("Na začetnem zaslonu lahko vpišeš help za pomoč.")
    print("Primeri: Charles Leclerc 2024 stopnicke | Lewis Hamilton 2024 tocke")
    print("Dodatni nameni: vreme, postanki, rezultati, start, radio, stinti, prehitevanja")
    print("Vpiši help, pocisti_predpomnilnik ali exit.\n")

    print(izpis_pomoci())
    print()

    while True:
        vnos = input("Vprasanje> ").strip()

        if not vnos:
            continue

        if vnos.lower() == "exit":
            break

        if vnos.lower() == "help":
            print(izpis_pomoci())
            print()
            continue

        if vnos.lower() == "pocisti_predpomnilnik":
            for datoteka in PREDPOMNILNIK.glob("*.json"):
                datoteka.unlink()
            print("Predpomnilnik je pobrisan.\n")
            continue

        voznik, leto, namen = razberi_vnos(vnos)

        try:
            print(odgovori(voznik, leto, namen))
        except Exception as napaka:
            print(f"Napaka: {napaka}")

        print()

if __name__ == "__main__":
    glavni_program()