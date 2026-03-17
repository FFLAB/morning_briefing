# 🌅 Morning Briefing – Guida all'Installazione

Script per Raspberry Pi che ogni mattina alle 6:00 genera un audio con:
- 🚆 Treni Piacenza → Milano Lambrate (06:30–07:30)
- 📰 3 notizie internazionali
- 🌤️ Meteo Piacenza

e lo invia via **email con allegato MP3** (voce ElevenLabs).

---

## 📋 Prerequisiti

- Raspberry Pi con Raspberry Pi OS (o qualsiasi Linux)
- Python 3.8+
- Connessione internet

---

## 🔑 Step 1 – Ottieni le API Key (tutte gratuite)

### OpenWeatherMap (Meteo)
1. Vai su https://openweathermap.org/api
2. Registrati → "My API Keys" → copia la chiave
87950c0d9a8c1247598a46c69ec0962a
brief2026

3. Il piano gratuito è più che sufficiente

### ElevenLabs (Voce)
1. Vai su https://elevenlabs.io
2. Registrati (piano gratuito: ~10.000 caratteri/mese)
3. Clicca sulla tua icona in alto a destra → "Profile"
4. Copia l'**API Key**
8c242bf244d34c4c9a45899658459f31
id
5. (Opzionale) Per scegliere una voce italiana:
   - Vai su "Voice Library" → filtra per lingua "Italian"
   - Copia il **Voice ID** dalla URL (es: `abc123def456`)

### Gmail – App Password
> ⚠️ Non usare la tua password normale! Crea una "App Password":
1. Vai su https://myaccount.google.com/security
2. Attiva la **Verifica in due passaggi** (se non già attiva)
3. Cerca "Password per le app" → Crea una nuova → copiala (16 caratteri)
admq iawd qfwm vocr

---

## 💻 Step 2 – Installazione sul Raspberry Pi

```bash
# Clona o copia la cartella morning_briefing nella tua home
cd ~

# Installa le dipendenze Python
pip3 install requests feedparser

# Entra nella cartella
cd morning_briefing

# Copia e compila il file di configurazione
cp config.json.template config.json
nano config.json
```

**Compila `config.json` con le tue chiavi:**
```json
{
  "openweather_api_key": "abc123...",
  "elevenlabs_api_key":  "sk_abc123...",
  "elevenlabs_voice_id": "pNInz6obpgDQGcFmaJgB",
  "email_from":    "tua_email@gmail.com",
  "email_password": "xxxx xxxx xxxx xxxx",
  "email_to":      "dove_ricevere@email.com",
  "smtp_server":   "smtp.gmail.com",
  "smtp_port":     587
}
```

---

## 🔊 Step 3 – (Opzionale) Scegli una voce italiana

Sul sito ElevenLabs, nella Voice Library:
- **Cerca voci italiane** o multilingue
- Clic su una voce → guarda la URL del browser:
  `https://elevenlabs.io/voice-lab/voice/VOICE_ID_QUI/...`
- Copia quel `VOICE_ID` e incollalo in `config.json` → `elevenlabs_voice_id`

Voci consigliate per italiano naturale:
- `pNInz6obpgDQGcFmaJgB` – Adam (default, funziona bene con l'italiano)
- Cerca "Italian" nella libreria per voci native
F9w7aaEjfT09qV89OdY8

---

## ✅ Step 4 – Test manuale

```bash
cd ~/morning_briefing
python3 morning_briefing.py
```

Controlla l'output nel terminale e verifica che l'email arrivi con l'MP3 allegato.

---

## ⏰ Step 5 – Programmazione automatica con Cron

```bash
# Apri il crontab
crontab -e
```

Aggiungi questa riga in fondo (invia alle 06:00 ogni giorno):
```
0 6 * * * /usr/bin/python3 /home/pi/morning_briefing/morning_briefing.py >> /home/pi/morning_briefing/log.txt 2>&1
```

> 💡 Sostituisci `/home/pi/` con il tuo path reale se l'utente non è `pi`.
> Per trovarlo: digita `echo $HOME` nel terminale.

Per verificare che il cron sia attivo:
```bash
crontab -l
```

---

## 📁 Struttura file

```
morning_briefing/
├── morning_briefing.py      ← Script principale
├── config.json              ← Le tue chiavi API (NON condividere!)
├── config.json.template     ← Template di esempio
├── INSTALLAZIONE.md         ← Questa guida
└── output/                  ← Audio e testi generati (creata automaticamente)
    ├── briefing_20250304.mp3
    └── briefing_20250304.txt
```

---

## 🔧 Risoluzione problemi

| Problema | Soluzione |
|---|---|
| "Connection refused" email | Controlla che l'App Password Gmail sia corretta |
| Audio non generato | Verifica la chiave ElevenLabs e i caratteri rimasti nel piano gratuito |
| Meteo non disponibile | Attendi qualche ora dopo la registrazione su OpenWeatherMap |
| Treni non trovati | L'API ViaggiaTreno può essere instabile; riprova manualmente |
| Cron non parte | Verifica il path con `which python3` e aggiorna il crontab |

---

## 🔒 Sicurezza

- `config.json` contiene dati sensibili → non condividerlo mai
- Se il Raspberry Pi è accessibile da internet, considera di aggiungere `config.json` al `.gitignore`

---

## 📧 Supporto

Se qualcosa non funziona, esegui lo script manualmente e incolla l'output per ricevere aiuto.
