import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from F1_baza.py import (
    MIN_LETO, PREDPOMNILNIK,
    poisci_voznika, cez_seje, normaliziraj, uradno_ime,
)

import pandas as pd
import dash
from dash import dcc, html, dash_table, Input, Output, State, ctx
import dash_bootstrap_components as dbc

# ---------------------------------------------------------------------------
# Konstante
# ---------------------------------------------------------------------------

BARVE = {
    "ozadje":   "#15151e",
    "panel":    "#1e1e2e",
    "rdeca":    "#e8002d",
    "bela":     "#ffffff",
    "siva":     "#9a9a9a",
    "meja":     "#2a2a3e",
    "vrstica2": "#252535",
}

NAMENI_OZNAKE = {
    "zmage":        "Zmage (Wins)",
    "tocke":        "Točke (Points)",
    "stopnicke":    "Stopničke (Podiums)",
    "krogi":        "Krogi (Laps)",
    "vreme":        "Vreme (Weather)",
    "postanki":     "Postanki (Pit Stops)",
    "rezultati":    "Rezultati (Results)",
    "start":        "Start (Grid)",
    "radio":        "Radio (Team Radio)",
    "stinti":       "Stinti (Tyre Stints)",
    "prehitevanja": "Prehitevanja (Overtakes)",
}

STOLPCI = {
    "zmage":        ["meeting_name", "country_name", "session_name", "position", "number_of_laps", "duration"],
    "stopnicke":    ["meeting_name", "country_name", "session_name", "position", "number_of_laps", "duration"],
    "rezultati":    ["meeting_name", "country_name", "session_name", "position", "number_of_laps", "duration", "gap_to_leader"],
    "tocke":        ["session_name", "points_start", "points_current", "pridobljene_tocke", "position_start", "position_current"],
    "krogi":        ["meeting_name", "session_name", "skupaj_krogov", "najboljsi_krog", "povprecen_krog"],
    "vreme":        ["meeting_name", "session_name", "povp_temp_zrak", "povp_temp_proga", "povp_vlaga", "povp_veter", "max_dez"],
    "postanki":     ["meeting_name", "session_name", "lap_number", "pit_duration", "lane_duration"],
    "start":        ["meeting_name", "session_name", "position"],
    "radio":        ["meeting_name", "session_name", "date", "recording_url"],
    "stinti":       ["meeting_name", "session_name", "stint_number", "compound", "lap_start", "lap_end", "tyre_age_at_start"],
    "prehitevanja": ["meeting_name", "session_name", "overtaking_driver_number", "overtaken_driver_number", "position", "date"],
}

ZNANI_VOZNIKI = [
    "Lewis Hamilton", "Max Verstappen", "Charles Leclerc", "Lando Norris",
    "George Russell", "Fernando Alonso", "Sergio Perez", "Oscar Piastri",
    "Carlos Sainz", "Lance Stroll", "Esteban Ocon", "Pierre Gasly",
    "Valtteri Bottas", "Zhou Guanyu", "Yuki Tsunoda", "Logan Sargeant",
    "Kevin Magnussen", "Nico Hulkenberg", "Alexander Albon", "Nyck de Vries",
    "Daniel Ricciardo", "Liam Lawson", "Oliver Bearman", "Franco Colapinto",
    "Andrea Kimi Antonelli", "Jack Doohan", "Isack Hadjar", "Gabriel Bortoleto",
]

VZDEVKI_OPIS = (
    "Vzdevki: ham, ver, lec, nor, rus, alo, per, pia, sai — "
    "ali vpišite polno ime voznika."
)

# ---------------------------------------------------------------------------
# Backend: vrne (naslov, DataFrame)
# ---------------------------------------------------------------------------

def _zaokrozi(df):
    for c in df.columns:
        if pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].round(3)
    return df


def _filtriraj_stolpce(df, namen):
    cols = STOLPCI.get(namen, [])
    return df[[c for c in cols if c in df.columns]] if cols else df


def _napaka(sporocilo):
    return sporocilo, pd.DataFrame({"Sporočilo": [sporocilo]})


def odgovori_df(voznik_vnos, leto, namen):
    voznik = uradno_ime(normaliziraj(voznik_vnos))
    if not voznik or leto is None or not namen:
        return _napaka("Izpolni vsa polja: voznik, leto in namen.")

    if leto < MIN_LETO:
        return _napaka(f"Podatki OpenF1 so na voljo od leta {MIN_LETO}.")

    stevilka, polno_ime = poisci_voznika(voznik, leto)
    if stevilka is None:
        return _napaka(f"Voznik ni bil najden: {voznik_vnos}")

    # --- zmage / stopnicke / rezultati ---
    if namen in {"zmage", "stopnicke", "rezultati"}:
        r = cez_seje(leto, "session_result", stevilka)
        if r.empty:
            return _napaka("Ni podatkov o rezultatih sej.")
        if "position" in r.columns:
            r["position"] = pd.to_numeric(r["position"], errors="coerce")
        if namen == "zmage":
            r = r[r["position"] == 1]
            naslov = f"{polno_ime} — zmage v {leto}: {len(r)}"
        elif namen == "stopnicke":
            r = r[r["position"].between(1, 3)]
            naslov = f"{polno_ime} — stopničke v {leto}: {len(r)}"
        else:
            naslov = f"{polno_ime} — rezultati dirk v {leto}"
        return naslov, _zaokrozi(_filtriraj_stolpce(r, namen))

    # --- tocke ---
    if namen == "tocke":
        c = cez_seje(leto, "championship_drivers", stevilka)
        if c.empty:
            return _napaka("Ni podatkov o točkovnem stanju.")
        for col in ["points_start", "points_current"]:
            if col in c.columns:
                c[col] = pd.to_numeric(c[col], errors="coerce")
        if all(x in c.columns for x in ["points_start", "points_current"]):
            c["pridobljene_tocke"] = c["points_current"].fillna(0) - c["points_start"].fillna(0)
        return f"{polno_ime} — napredek točk v {leto}", _zaokrozi(_filtriraj_stolpce(c, namen))

    # --- krogi ---
    if namen == "krogi":
        k = cez_seje(leto, "laps", stevilka)
        if k.empty:
            return _napaka("Ni podatkov o krogih.")
        for col in ["lap_number", "lap_duration"]:
            if col in k.columns:
                k[col] = pd.to_numeric(k[col], errors="coerce")
        povzetek = k.groupby(
            [c for c in ["meeting_name", "session_name"] if c in k.columns], dropna=False
        ).agg(
            skupaj_krogov=("lap_number", "max"),
            najboljsi_krog=("lap_duration", "min"),
            povprecen_krog=("lap_duration", "mean"),
        ).reset_index()
        return f"{polno_ime} — povzetek krogov v {leto}", _zaokrozi(povzetek)

    # --- vreme ---
    if namen == "vreme":
        v = cez_seje(leto, "weather")
        if v.empty:
            return _napaka("Ni vremenskih podatkov.")
        for col in ["air_temperature", "track_temperature", "humidity", "wind_speed", "rainfall"]:
            if col in v.columns:
                v[col] = pd.to_numeric(v[col], errors="coerce")
        povzetek = v.groupby(
            [c for c in ["meeting_name", "session_name"] if c in v.columns], dropna=False
        ).agg(
            povp_temp_zrak=("air_temperature", "mean"),
            povp_temp_proga=("track_temperature", "mean"),
            povp_vlaga=("humidity", "mean"),
            povp_veter=("wind_speed", "mean"),
            max_dez=("rainfall", "max"),
        ).reset_index()
        return f"Povzetek vremena v {leto}", _zaokrozi(povzetek)

    # --- postanki ---
    if namen == "postanki":
        p = cez_seje(leto, "pit", stevilka)
        if p.empty:
            return _napaka("Ni podatkov o postankih v boksih.")
        for col in ["lap_number", "pit_duration", "lane_duration"]:
            if col in p.columns:
                p[col] = pd.to_numeric(p[col], errors="coerce")
        return f"{polno_ime} — postanki v boksih v {leto}: {len(p)}", _zaokrozi(_filtriraj_stolpce(p, namen))

    # --- start ---
    if namen == "start":
        z = cez_seje(leto, "starting_grid", stevilka)
        if z.empty:
            return _napaka("Ni podatkov o startni razvrstitvi.")
        return f"{polno_ime} — startne pozicije v {leto}", _filtriraj_stolpce(z, namen)

    # --- radio ---
    if namen == "radio":
        r = cez_seje(leto, "team_radio", stevilka)
        if r.empty:
            return _napaka("Ni podatkov o radijskih sporočilih.")
        return f"{polno_ime} — radio ekipe v {leto}", _filtriraj_stolpce(r, namen)

    # --- stinti ---
    if namen == "stinti":
        s = cez_seje(leto, "stints", stevilka)
        if s.empty:
            return _napaka("Ni podatkov o stintih.")
        return f"{polno_ime} — stinti pnevmatik v {leto}", _zaokrozi(_filtriraj_stolpce(s, namen))

    # --- prehitevanja ---
    if namen == "prehitevanja":
        p = cez_seje(leto, "overtakes")
        if p.empty:
            return _napaka("Ni podatkov o prehitevanjih.")
        for col in ["overtaking_driver_number", "overtaken_driver_number"]:
            if col in p.columns:
                p[col] = pd.to_numeric(p[col], errors="coerce")
        ot = p.get("overtaking_driver_number")
        od = p.get("overtaken_driver_number")
        maska = (ot == stevilka) if ot is not None else False
        maska2 = (od == stevilka) if od is not None else False
        p = p[maska | maska2]
        return f"{polno_ime} — prehitevanja v {leto}", _filtriraj_stolpce(p, namen)

    return _napaka("Ta namen trenutno ni podprt.")


# ---------------------------------------------------------------------------
# Stili
# ---------------------------------------------------------------------------

SLOG_OZADJE = {"backgroundColor": BARVE["ozadje"], "minHeight": "100vh", "padding": "0"}
SLOG_GLAVA = {
    "backgroundColor": BARVE["rdeca"],
    "padding": "18px 32px",
    "display": "flex",
    "alignItems": "center",
    "gap": "16px",
}
SLOG_VSEBINA = {"padding": "24px 32px", "backgroundColor": BARVE["ozadje"]}
SLOG_KARTICA = {
    "backgroundColor": BARVE["panel"],
    "borderRadius": "8px",
    "padding": "20px",
    "border": f"1px solid {BARVE['meja']}",
    "marginBottom": "20px",
}
SLOG_OZNAKA = {"color": BARVE["siva"], "fontSize": "12px", "fontWeight": "600",
               "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "6px"}
SLOG_VNOSNIK = {
    "backgroundColor": BARVE["ozadje"],
    "color": BARVE["bela"],
    "border": f"1px solid {BARVE['meja']}",
    "borderRadius": "6px",
    "padding": "8px 12px",
    "width": "100%",
    "fontSize": "14px",
    "outline": "none",
}
SLOG_GUMB = {
    "backgroundColor": BARVE["rdeca"],
    "color": BARVE["bela"],
    "border": "none",
    "borderRadius": "6px",
    "padding": "10px 24px",
    "fontWeight": "700",
    "fontSize": "14px",
    "cursor": "pointer",
    "letterSpacing": "0.05em",
    "marginRight": "10px",
}
SLOG_GUMB_IZPRAZNI = {**SLOG_GUMB, "backgroundColor": BARVE["meja"]}

SLOG_TABELA_GLAVA = [
    {"if": {"header_index": 0},
     "backgroundColor": BARVE["rdeca"],
     "color": BARVE["bela"],
     "fontWeight": "700",
     "fontSize": "12px",
     "textTransform": "uppercase",
     "letterSpacing": "0.06em",
     "border": "none"},
]
SLOG_TABELA_CELICA = [
    {"if": {"row_index": "odd"},  "backgroundColor": BARVE["vrstica2"]},
    {"if": {"row_index": "even"}, "backgroundColor": BARVE["panel"]},
]

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

dropdown_style = {
    "backgroundColor": BARVE["ozadje"],
    "color": BARVE["bela"],
}
dropdown_container = {
    "backgroundColor": BARVE["ozadje"],
    "border": f"1px solid {BARVE['meja']}",
    "borderRadius": "6px",
}

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG],
    title="OpenF1 Baza",
)

app.layout = html.Div(style=SLOG_OZADJE, children=[

    # Glava
    html.Div(style=SLOG_GLAVA, children=[
        html.Span("F1", style={"fontSize": "28px", "fontWeight": "900",
                               "color": BARVE["bela"], "letterSpacing": "-1px"}),
        html.H1("OpenF1 Baza Podatkov",
                style={"margin": "0", "fontSize": "20px", "fontWeight": "700",
                       "color": BARVE["bela"], "letterSpacing": "0.02em"}),
    ]),

    html.Div(style=SLOG_VSEBINA, children=[

        # Nadzorna plošča
        html.Div(style=SLOG_KARTICA, children=[
            dbc.Row([
                # Voznik
                dbc.Col([
                    html.Div("Voznik", style=SLOG_OZNAKA),
                    dcc.Dropdown(
                        id="voznik-dropdown",
                        options=[{"label": v, "value": v} for v in ZNANI_VOZNIKI],
                        placeholder="Izberi ali vpiši voznika / vzdevek...",
                        searchable=True,
                        clearable=True,
                        style={"fontSize": "14px"},
                        className="dark-dropdown",
                    ),
                    html.Div(VZDEVKI_OPIS,
                             style={"color": BARVE["siva"], "fontSize": "11px", "marginTop": "4px"}),
                ], md=4),

                # Leto
                dbc.Col([
                    html.Div("Leto", style=SLOG_OZNAKA),
                    dcc.Dropdown(
                        id="leto-dropdown",
                        options=[{"label": str(l), "value": l} for l in range(2023, 2027)],
                        value=2024,
                        clearable=False,
                        style={"fontSize": "14px"},
                    ),
                ], md=2),

                # Namen
                dbc.Col([
                    html.Div("Namen poizvedbe", style=SLOG_OZNAKA),
                    dcc.Dropdown(
                        id="namen-dropdown",
                        options=[{"label": NAMENI_OZNAKE[n], "value": n}
                                 for n in sorted(NAMENI_OZNAKE)],
                        placeholder="Izberi namen...",
                        clearable=False,
                        style={"fontSize": "14px"},
                    ),
                ], md=3),

                # Gumbi
                dbc.Col([
                    html.Div(" ", style=SLOG_OZNAKA),
                    html.Div([
                        html.Button("Poišči", id="btn-poisci", n_clicks=0, style=SLOG_GUMB),
                        html.Button("Počisti predpomnilnik", id="btn-cache", n_clicks=0,
                                    style=SLOG_GUMB_IZPRAZNI),
                    ]),
                ], md=3, style={"display": "flex", "alignItems": "center"}),
            ]),
        ]),

        # Obvestilo predpomnilnika
        html.Div(id="cache-sporocilo",
                 style={"color": BARVE["siva"], "marginBottom": "12px", "fontSize": "13px"}),

        # Rezultati
        dcc.Loading(
            id="loading",
            type="circle",
            color=BARVE["rdeca"],
            children=html.Div(id="rezultati-vsebina"),
        ),

        # Pomoč
        html.Div(style={**SLOG_KARTICA, "marginTop": "10px"}, children=[
            html.Details([
                html.Summary("Navodila za uporabo",
                             style={"color": BARVE["rdeca"], "fontWeight": "700",
                                    "cursor": "pointer", "fontSize": "14px"}),
                html.Div(style={"marginTop": "14px", "color": BARVE["siva"], "fontSize": "13px",
                                "lineHeight": "1.7"}, children=[
                    html.P("Izpolni vsa tri polja (voznik, leto, namen) in pritisni Poišči."),
                    html.P("Vzdevki voznikov: ham, ver, lec, nor, rus, alo, per, pia, sai"),
                    html.P("Zgodovinski podatki so na voljo od leta 2023 dalje."),
                    html.Hr(style={"borderColor": BARVE["meja"]}),
                    html.B("Nameni:"),
                    html.Ul([
                        html.Li(f"{k} — {v}") for k, v in sorted(NAMENI_OZNAKE.items())
                    ]),
                    html.Hr(style={"borderColor": BARVE["meja"]}),
                    html.B("Primeri:"),
                    html.Ul([
                        html.Li("Charles Leclerc, 2024, Stopničke"),
                        html.Li("Lewis Hamilton, 2024, Točke"),
                        html.Li("Max Verstappen, 2023, Zmage"),
                        html.Li("Lando Norris, 2024, Stinti"),
                        html.Li("Fernando Alonso, 2024, Radio"),
                    ]),
                ]),
            ]),
        ]),
    ]),
])

# ---------------------------------------------------------------------------
# CSS za dcc.Dropdown dark mode
# ---------------------------------------------------------------------------

app.index_string = app.index_string.replace(
    "</head>",
    """<style>
    .dark-dropdown .Select-control,
    .Select-control { background-color: #15151e !important; border-color: #2a2a3e !important; color: #fff !important; }
    .Select-menu-outer { background-color: #1e1e2e !important; border-color: #2a2a3e !important; }
    .Select-option { background-color: #1e1e2e !important; color: #fff !important; }
    .Select-option.is-focused { background-color: #e8002d !important; }
    .Select-value-label { color: #fff !important; }
    .Select-placeholder { color: #9a9a9a !important; }
    .Select-arrow { border-top-color: #9a9a9a !important; }
    .VirtualizedSelectFocusedOption { background-color: #e8002d !important; }
    body { font-family: 'Segoe UI', Arial, sans-serif; }
    summary::-webkit-details-marker { color: #e8002d; }
    </style></head>""",
)

# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@app.callback(
    Output("cache-sporocilo", "children"),
    Input("btn-cache", "n_clicks"),
    prevent_initial_call=True,
)
def pocisti_predpomnilnik(n):
    if not n:
        return ""
    odstranjeno = 0
    for datoteka in PREDPOMNILNIK.glob("*.json"):
        datoteka.unlink()
        odstranjeno += 1
    return f"Predpomnilnik počiščen. Odstranjenih datotek: {odstranjeno}."


@app.callback(
    Output("rezultati-vsebina", "children"),
    Input("btn-poisci", "n_clicks"),
    State("voznik-dropdown", "value"),
    State("leto-dropdown", "value"),
    State("namen-dropdown", "value"),
    prevent_initial_call=True,
)
def poisci(n_clicks, voznik, leto, namen):
    if not n_clicks:
        return ""

    if not voznik:
        return _kartica_napake("Izberi ali vpiši ime voznika.")
    if not namen:
        return _kartica_napake("Izberi namen poizvedbe.")
    if not leto:
        return _kartica_napake("Izberi leto.")

    try:
        naslov, df = odgovori_df(voznik, int(leto), namen)
    except Exception as e:
        return _kartica_napake(f"Napaka pri pridobivanju podatkov: {e}")

    if df.empty:
        return _kartica_napake("Ni zadetkov za izbrano poizvedbo.")

    stolpci = [{"name": c.replace("_", " ").title(), "id": c} for c in df.columns]
    podatki = df.to_dict("records")

    return html.Div(style=SLOG_KARTICA, children=[
        html.H4(naslov, style={"color": BARVE["bela"], "marginTop": "0",
                               "marginBottom": "16px", "fontSize": "16px",
                               "fontWeight": "700"}),
        html.Div(f"{len(df)} vrstic",
                 style={"color": BARVE["siva"], "fontSize": "12px", "marginBottom": "12px"}),
        dash_table.DataTable(
            columns=stolpci,
            data=podatki,
            page_size=25,
            sort_action="native",
            filter_action="native",
            style_table={"overflowX": "auto", "borderRadius": "6px", "border": "none"},
            style_header={
                "backgroundColor": BARVE["rdeca"],
                "color": BARVE["bela"],
                "fontWeight": "700",
                "fontSize": "12px",
                "textTransform": "uppercase",
                "letterSpacing": "0.06em",
                "border": "none",
                "padding": "10px 14px",
            },
            style_data={
                "backgroundColor": BARVE["panel"],
                "color": BARVE["bela"],
                "border": f"1px solid {BARVE['meja']}",
                "fontSize": "13px",
                "padding": "8px 14px",
            },
            style_data_conditional=[
                {"if": {"row_index": "odd"}, "backgroundColor": BARVE["vrstica2"]},
                {"if": {"state": "selected"},
                 "backgroundColor": "#e8002d22",
                 "border": f"1px solid {BARVE['rdeca']}"},
                {"if": {"filter_query": '{position} = 1'},
                 "color": "#ffd700", "fontWeight": "700"},
            ],
            style_filter={
                "backgroundColor": BARVE["ozadje"],
                "color": BARVE["bela"],
                "border": f"1px solid {BARVE['meja']}",
            },
            style_as_list_view=True,
        ),
    ])


def _kartica_napake(sporocilo):
    return html.Div(style={**SLOG_KARTICA, "borderLeft": f"4px solid {BARVE['rdeca']}"}, children=[
        html.P(sporocilo, style={"color": BARVE["bela"], "margin": "0", "fontSize": "14px"}),
    ])


# ---------------------------------------------------------------------------
# Zagon
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Zaganjam OpenF1 Dash aplikacijo na http://127.0.0.1:8050/")
    app.run(debug=False, port=8050)
