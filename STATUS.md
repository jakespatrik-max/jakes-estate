# STATUS — pokračování práce na druhém notebooku

Poslední aktualizace: 2026-05-18

## Stav projektu
- **Branch:** `main` — vše commitnuté a pushnuté na GitHub
- **Repo:** https://github.com/jakespatrik-max/jakes-estate
- **Posledních 5 commitů:**
  - `dacb907` mobile: zmenšení hero nadpisu a optimalizace mezer
  - `4bfc3e3` footer: přidáno DIČ CZ21411735 pod IČ
  - `ee3b621` content: doplněn popisek pod Dokončené developerské projekty
  - `a51cb7e` content: přejmenování sekce Aktuální projekty → Portfolio & Aktuální projekty
  - `888d570` mobile: opp-cards zlaté pozadí explicitně + top lišta trvale viditelná
- **Rozpracováno:** nic — bezpečný moment na přepnutí mezi stroji.

## Setup druhého notebooku (15–20 minut)

### 1. Google Disk
- Nainstaluj **Google Drive for Desktop** a přihlas se stejným účtem
- Počkej, až se zesynchronizuje složka `G:\Můj disk\1. Jakes.Estate - ALL\` (může trvat — projekt má hodně souborů)
- Nebo nech disk synchronizovat na pozadí a používej druhý zdroj (GitHub) viz níže

### 2. Claude Code
- Nainstaluj: https://docs.claude.com/claude-code
- Přihlas se **stejným Anthropic účtem** jako tady → všechny konektory (Gmail, Google Calendar, Google Drive, Vercel, Supabase) se objeví automaticky, jsou navázané na účet, ne na stroj
- Co se NEpřenese: lokální historie konverzací (sessions), `~/.claude/settings.json`, hooks. Začneš novou session — paměť a kontext jsou v tomto souboru a v git historii.

### 3. Git + GitHub CLI
- Nainstaluj **Git for Windows** (https://git-scm.com)
- Nainstaluj **GitHub CLI** (https://cli.github.com), pak `gh auth login`
- Email v gitu: `jakes.patrik@gmail.com`, GitHub username: `jakespatrik-max`

### 4. Otevři projekt
Dvě cesty — vyber jednu:

**A) Přes Google Disk (jednodušší, žádný setup navíc):**
- Otevři `G:\Můj disk\1. Jakes.Estate - ALL\0. Základní dokumenty\7. Web\1. JE - Claude code\` v Claude Code
- Pracuj přímo tam — soubory se synchronizují automaticky

**B) Přes git clone (rychlejší, nezávislé na Disku):**
```
git clone https://github.com/jakespatrik-max/jakes-estate.git
cd jakes-estate
```
- Pozor: lokální soubory mimo git (credentials.env, screenshots/, faktury/, downloads/) nebudou — jsou jen na Disku

### 5. Start v Claude Code
Po otevření složky řekni Claudovi:
> Přečti si `STATUS.md` a pokračujeme.

## Co je v projektu lokálně mimo git (jen na Disku)
- `credentials.env` — citlivé, nikdy necommitovat
- `booking_session.json`, `EXPORT_COOKIES.bat`, `SPUSTIT_*.bat`, `test_booking.py` — booking automatizace
- `screenshots/`, `screenshots_test/`, `downloads/`, `faktury/`

Tyhle soubory přijdou s Google Diskem automaticky (cesta A). U cesty B je nemáš — pokud je budeš potřebovat, počkej, až se Disk zesynchronizuje, nebo si je zkopíruj přes Disk web.

## Návrat na hlavní notebook
1. Na cestujícím laptopu před zavřením: `git add -A && git commit -m "wip z cest" && git push`
2. Tady: `git pull`
3. Aktualizuj tento `STATUS.md` o tom, co je nově rozpracované

## Tip
Pokud zjistíš, že chybí nějaký konektor (Gmail/Calendar/Drive/Vercel/Supabase), spusť `/mcp` v Claude Code a podívej se na seznam — pokud chybí, přidej ho přes Claude Code Settings → Connectors stejně jako tady.
