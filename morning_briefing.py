#!/usr/bin/env python3
"""
Morning Briefing - Rassegna mattutina automatica
Treni Piacenza → Milano Lambrate + Notizie internazionali + Meteo Piacenza
Genera audio MP3 con gTTS (Google Text-to-Speech) e lo invia via email
"""

import re
import json
import smtplib
import calendar
import requests
import feedparser
from gtts import gTTS
from datetime import datetime
from email.utils import formatdate
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# ── Carica configurazione ──────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json"
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

OPENWEATHER_KEY     = CONFIG["openweather_api_key"]
EMAIL_FROM    = CONFIG["email_from"]
EMAIL_PASSWORD = CONFIG["email_password"]
EMAIL_TO      = CONFIG["email_to"]
SMTP_SERVER   = CONFIG.get("smtp_server", "smtp.gmail.com")
SMTP_PORT     = CONFIG.get("smtp_port", 587)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


# ── 1. TRENI ──────────────────────────────────────────────────────────────────

# Categorie ammesse: solo regionali e regioexpress Trenord/Trenitalia
CATEGORIE_OK = {"REG", "RE", "RV", "R"}

# Categorie da escludere esplicitamente (alta velocità, intercity, ecc.)
CATEGORIE_NO = {"FR", "FA", "FB", "IC", "ICN", "ITA", "EC", "EN", "ES", "AV"}

# Stazioni sulla linea via Pavia: se il treno ferma in una di queste
# vuol dire che percorre la linea sbagliata e va escluso.
# Verifica via API: /fermate/{codiceVettore}/{numeroTreno}/{dataPartenza}
STAZIONI_VIA_PAVIA = {
    "S01604",  # Pavia
    "S01609",  # Voghera
    "S01703",  # Stradella
    "S01656",  # Broni
}


def _percorre_via_pavia(numero: str, cod_vettore: str, data_ms: str) -> bool:
    """
    Controlla se un treno percorre la linea via Pavia interrogando
    l'endpoint /fermate dell'API ViaggiaTreno.
    Restituisce True se trova una delle stazioni della linea Pavia tra le fermate.
    """
    base = "http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno"
    try:
        url = f"{base}/fermate/{cod_vettore}/{numero}/{data_ms}"
        r   = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return False
        fermate = r.json()
        for f in fermate:
            id_stazione = f.get("id", "")
            if id_stazione in STAZIONI_VIA_PAVIA:
                return True
    except Exception:
        pass
    return False


def get_treni() -> str:
    """
    Recupera treni Piacenza→Milano Lambrate (linea via Lodi) nelle prossime 2 ore.

    Filtri applicati:
    - Solo categorie regionali: REG, RE, RV, R (no IC, FR, FA, ITA, ecc.)
    - Solo linea via Lodi: esclusi i treni che fermano a Pavia/Voghera/Stradella
    - Destinazione Milano (Lambrate o altra stazione milanese)
    """
    from datetime import timedelta

    base     = "http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno"
    stazione = "S05000"  # Piacenza

    now           = datetime.now()
    fine          = now + timedelta(hours=2)
    ora_inizio_hm = now.hour * 60 + now.minute
    ora_fine_hm   = fine.hour * 60 + fine.minute

    ts_now   = calendar.timegm(now.timetuple())
    data_str = formatdate(ts_now, usegmt=True)
    url      = f"{base}/partenze/{stazione}/{requests.utils.quote(data_str)}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        partenze = resp.json()

        treni_filtrati  = []
        treni_esclusi   = []   # per debug/log

        for treno in partenze:
            ts_ms = treno.get("orarioPartenza")
            if not ts_ms:
                continue
            ora_dt = datetime.fromtimestamp(int(ts_ms) / 1000)
            ora_hm = ora_dt.hour * 60 + ora_dt.minute

            # Finestra temporale
            if not (ora_inizio_hm <= ora_hm <= ora_fine_hm):
                continue

            # Destinazione Milano
            dest = treno.get("destinazione", "").upper()
            if "LAMBRATE" not in dest and "MILANO" not in dest:
                continue

            numero     = str(treno.get("numeroTreno", ""))
            categoria  = (treno.get("categoriaDescrizione") or
                          treno.get("categoria", "")).strip().upper()
            cod_vett   = str(treno.get("codiceCliente") or
                             treno.get("codOrigine") or "")
            data_ms_tr = str(treno.get("dataPartenzaTreno") or
                             treno.get("millisDataPartenza") or int(ts_ms))

            # ── Filtro 1: solo regionali ──────────────────────────────────────
            cat_norm = categoria.replace(" ", "")
            if cat_norm in CATEGORIE_NO:
                treni_esclusi.append(f"{categoria} {numero} (alta velocità/IC)")
                continue
            # Accetta esplicitamente le categorie OK, o qualsiasi altra non-AV
            # (per sicurezza escludiamo solo le categorie NO conosciute)

            # ── Filtro 2: linea via Lodi (non via Pavia) ──────────────────────
            if _percorre_via_pavia(numero, cod_vett, data_ms_tr):
                treni_esclusi.append(f"{categoria} {numero} (linea via Pavia)")
                continue

            ritardo = int(treno.get("ritardo") or 0)
            binario = (treno.get("binarioEffettivoPartenzaDescrizione")
                       or treno.get("binarioProgrammatoPartenzaDescrizione")
                       or "?")

            ritardo_txt = f", ⚠️ RITARDO {ritardo} min" if ritardo > 0 else ", in orario"
            treni_filtrati.append(
                f"  • {categoria} {numero} alle {ora_dt.strftime('%H:%M')}"
                f" – binario {binario}{ritardo_txt}"
            )

        ora_inizio_str = now.strftime('%H:%M')
        ora_fine_str   = fine.strftime('%H:%M')

        intestazione = (f"Treni regionali Piacenza→Milano Lambrate via Lodi "
                        f"dalle {ora_inizio_str} alle {ora_fine_str}:")

        if treni_filtrati:
            testo = intestazione + "\n" + "\n".join(treni_filtrati)
            if treni_esclusi:
                testo += (f"\n  (esclusi: {len(treni_esclusi)} treni "
                          f"via Pavia o alta velocità)")
            return testo
        else:
            nota = ""
            if treni_esclusi:
                nota = (f" Trovati {len(treni_esclusi)} treni esclusi perché "
                        f"via Pavia o alta velocità.")
            return (f"Nessun treno regionale via Lodi da Piacenza verso Milano "
                    f"nella fascia {ora_inizio_str}-{ora_fine_str}.{nota} "
                    f"Verifica su Trenord o Trenitalia.")

    except Exception as e:
        return f"Impossibile recuperare gli orari dei treni: {e}"


# ── 2. NOTIZIE ────────────────────────────────────────────────────────────────

# Notizia 1 — Italia: cronaca, politica, legislazione (no notizie estere)
RSS_ITALIA = [
    "https://www.ansa.it/sito/notizie/politica/politica_rss.xml",
    "https://www.ansa.it/sito/notizie/cronaca/cronaca_rss.xml",
    "https://www.corriere.it/rss/politica.xml",
    "https://www.corriere.it/rss/cronache.xml",
    "https://www.repubblica.it/rss/politica/rss2.0.xml",
    "https://www.rainews.it/rss/rss-rai-news24.xml",
]
KEYWORDS_ITALIA_ESCLUDI = [
    "trump", "usa", "stati uniti", "cina", "russia", "ucraina", "iran",
    "israele", "gaza", "brasile", "messico", "argentina", "venezuela",
    "colombia", "cile", "perù", "ecuador", "bolivia", "siria", "yemen",
]

# Notizia 2 — Conflitti e guerre in atto
RSS_GUERRE = [
    "https://www.ansa.it/sito/notizie/mondo/mondo_rss.xml",
    "https://www.corriere.it/rss/esteri.xml",
    "https://www.repubblica.it/rss/esteri/rss2.0.xml",
    "https://www.rainews.it/rss/rss-rai-news24.xml",
]
KEYWORDS_GUERRA = [
    "ucraina", "russia", "guerra", "iran", "israele", "gaza", "libano",
    "conflitto", "attacco", "missili", "bombardamento", "medio oriente",
    "nato", "zelensky", "putin", "siria", "yemen", "hamas", "hezbollah",
    "offensiva", "tregua", "soldati", "fronte", "nucleare", "droni",
    "raid", "ostaggio", "cessate il fuoco",
]

# Notizia 3 — Cronaca locale Piacenza
RSS_PIACENZA = [
    "https://www.liberta.it/feed/",
    "https://www.ilpiacenza.it/feed/",
    "https://piacenzasera.it/feed/",
    "https://www.piacenzaonline.info/feed/",
]

# Feed per verifica stato Trump
RSS_TRUMP_CHECK = [
    "https://www.ansa.it/sito/notizie/mondo/mondo_rss.xml",
    "https://www.rainews.it/rss/rss-rai-news24.xml",
    "https://www.corriere.it/rss/esteri.xml",
    "https://www.repubblica.it/rss/esteri/rss2.0.xml",
]


def _pulisci(testo: str) -> str:
    import html as _html
    testo = re.sub(r"<[^>]+>", "", testo)
    testo = _html.unescape(testo)
    testo = re.sub(r"\s+", " ", testo).strip()
    return testo


def _prima_da_feed(feeds: list, seen: set, keywords: list = None,
                   escludi: list = None) -> str | None:
    """
    Restituisce il primo titolo+sommario non già visto dai feed.
    keywords: almeno una deve comparire nel testo (whitelist).
    escludi:  nessuna deve comparire nel testo (blacklist).
    """
    for feed_url in feeds:
        try:
            for entry in feedparser.parse(feed_url).entries[:10]:
                titolo   = _pulisci(entry.get("title", ""))
                sommario = _pulisci(entry.get("summary",
                           entry.get("description", "")))[:280]
                if not titolo or titolo in seen:
                    continue
                testo_check = (titolo + " " + sommario).lower()
                if keywords and not any(k in testo_check for k in keywords):
                    continue
                if escludi and any(k in testo_check for k in escludi):
                    continue
                seen.add(titolo)
                return f"{titolo}. {sommario}"
        except Exception:
            continue
    return None


def _stato_trump() -> str:
    """
    Cerca nei feed italiani se Trump è morto.
    Se non trova notizie di decesso restituisce 'Trump è ancora vivo.'
    """
    keywords_morte = [
        "trump morto", "trump è morto", "morte di trump",
        "trump dead", "trump dies", "trump passed away",
    ]
    for feed_url in RSS_TRUMP_CHECK:
        try:
            for entry in feedparser.parse(feed_url).entries[:20]:
                testo = (entry.get("title", "") + " " +
                         entry.get("summary", "")).lower()
                if any(k in testo for k in keywords_morte):
                    return "⚠️ ATTENZIONE: Trump è morto."
        except Exception:
            continue
    return "Trump è ancora vivo."


def get_notizie() -> str:
    seen    = set()
    sezioni = []

    # 1. Italia
    it = _prima_da_feed(RSS_ITALIA, seen, escludi=KEYWORDS_ITALIA_ESCLUDI)
    sezioni.append(f"Notizia dall'Italia: {it}" if it
                   else "Notizia dall'Italia: non disponibile al momento.")

    # 2. Conflitti in corso
    guerra = _prima_da_feed(RSS_GUERRE, seen, keywords=KEYWORDS_GUERRA)
    sezioni.append(f"Conflitti nel mondo: {guerra}" if guerra
                   else "Conflitti nel mondo: nessun aggiornamento disponibile.")

    # 3. Cronaca locale Piacenza
    pc = _prima_da_feed(RSS_PIACENZA, seen)
    sezioni.append(f"Da Piacenza: {pc}" if pc
                   else "Da Piacenza: notizie locali non disponibili al momento.")

    # 4. Trump — vivo o morto
    sezioni.append(_stato_trump())

    return "\n\n".join(sezioni)


# ── 3. METEO ──────────────────────────────────────────────────────────────────
def get_meteo() -> str:
    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?q=Piacenza,IT&appid={OPENWEATHER_KEY}&units=metric&lang=it"
        )
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        d = r.json()

        desc      = d["weather"][0]["description"].capitalize()
        temp      = round(d["main"]["temp"])
        temp_min  = round(d["main"]["temp_min"])
        temp_max  = round(d["main"]["temp_max"])
        umidita   = d["main"]["humidity"]
        vento_kmh = round(d["wind"]["speed"] * 3.6)

        url_f = (
            f"https://api.openweathermap.org/data/2.5/forecast"
            f"?q=Piacenza,IT&appid={OPENWEATHER_KEY}&units=metric&lang=it&cnt=8"
        )
        rf      = requests.get(url_f, timeout=10)
        rf.raise_for_status()
        pioggia = any(
            "rain" in item["weather"][0]["main"].lower()
            for item in rf.json()["list"]
        )
        pioggia_txt = " È consigliato portare l'ombrello." if pioggia else ""

        return (
            f"Meteo a Piacenza per oggi: {desc}. "
            f"Temperatura attuale {temp}°C, minima {temp_min}°C, massima {temp_max}°C. "
            f"Umidità {umidita}%, vento a {vento_kmh} km/h.{pioggia_txt}"
        )
    except Exception as e:
        return f"Impossibile recuperare le previsioni meteo: {e}"


# ── 4. TESTO ──────────────────────────────────────────────────────────────────
def componi_testo(treni: str, notizie: str, meteo: str) -> str:
    giorni_it = ["lunedì","martedì","mercoledì","giovedì","venerdì","sabato","domenica"]
    mesi_it   = ["","gennaio","febbraio","marzo","aprile","maggio","giugno",
                 "luglio","agosto","settembre","ottobre","novembre","dicembre"]
    now     = datetime.now()
    data_it = f"{giorni_it[now.weekday()]} {now.day} {mesi_it[now.month]} {now.year}"
    ora_it  = now.strftime("%H:%M")
    return (
        f"Briefing di {data_it}, ore {ora_it}.\n\n"
        f"{meteo}\n\n"
        f"{treni}\n\n"
        f"{notizie}\n\n"
        f"Buona giornata!"
    )


# ── 5. AUDIO gTTS ────────────────────────────────────────────────────────────
def genera_audio(testo: str, percorso_output: Path) -> bool:
    try:
        tts = gTTS(text=testo, lang="it", slow=False)
        tts.save(str(percorso_output))
        return True
    except Exception as e:
        print(f"[gTTS] Errore: {e}")
        return False


# ── 6. EMAIL ──────────────────────────────────────────────────────────────────
def invia_email(percorso_audio: Path, testo: str) -> bool:
    data_str = datetime.now().strftime("%d/%m/%Y")
    msg = MIMEMultipart()
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg["Subject"] = f"🌅 Briefing Mattutino – {data_str}"

    msg.attach(MIMEText(testo, "plain", "utf-8"))

    if percorso_audio.exists():
        with open(percorso_audio, "rb") as f:
            part = MIMEBase("audio", "mpeg")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="briefing_{datetime.now().strftime("%Y%m%d")}.mp3"',
        )
        msg.attach(part)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print("[Email] Inviata con successo.")
        return True
    except Exception as e:
        print(f"[Email] Errore: {e}")
        return False


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Avvio briefing mattutino...")

    print("  → Recupero orari treni...")
    treni = get_treni()
    print(f"     {treni[:80]}...")

    print("  → Recupero notizie...")
    notizie = get_notizie()

    print("  → Recupero meteo...")
    meteo = get_meteo()

    print("  → Composizione testo...")
    testo = componi_testo(treni, notizie, meteo)
    print("\n" + testo + "\n")  # log locale

    testo_path = OUTPUT_DIR / f"briefing_{datetime.now().strftime('%Y%m%d')}.txt"
    testo_path.write_text(testo, encoding="utf-8")

    audio_path = OUTPUT_DIR / f"briefing_{datetime.now().strftime('%Y%m%d')}.mp3"
    print("  → Generazione audio gTTS...")
    audio_ok = genera_audio(testo, audio_path)
    print(f"  {'✓' if audio_ok else '✗'} Audio {'salvato in ' + str(audio_path) if audio_ok else 'non generato, invio solo testo'}")

    print("  → Invio email...")
    invia_email(audio_path, testo)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Briefing completato.")


if __name__ == "__main__":
    main()
