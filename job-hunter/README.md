# Job Hunter — Architecture & Implémentation

> Outil full-stack de veille d'emploi : scraping Playwright, scoring IA OpenAI, génération de CV/LM LaTeX, interface web Next.js 14.

---

## Architecture du projet

```mermaid
graph TD
    subgraph Frontend["Frontend — Next.js 14 (web/)"]
        LOGIN["Login<br/>code d'accès"]
        DASH["Dashboard<br/>offres + scores"]
        PROF["Profil<br/>compétences, bio"]
        SETT["Paramètres<br/>clé API, critères"]
    end

    subgraph APILayer["API Routes (Next.js)"]
        R_AUTH["/api/auth"]
        R_SCRAPE["/api/scrape"]
        R_SCORE["/api/score → /api/llm"]
        R_GEN["/api/generate"]
        R_OFFERS["/api/offers"]
        R_PROFILE["/api/profile"]
    end

    subgraph PythonEngine["Moteur Python (job-hunter/)"]
        BRIDGE_S["bridge_scrape.py<br/>entrée: config JSON via stdin"]
        BRIDGE_G["bridge_generate.py<br/>entrée: offre + profil JSON via stdin"]
        CRAWLER["Crawler Playwright<br/>navigation headless + stealth"]
        EXTRACTOR["Extracteur HTML<br/>sites/ LinkedIn, Indeed, WTTJ, HW"]
        MATCHER["Matcher IA<br/>GPT-4o → score 0-100"]
        CVGEN["cv_generator.py<br/>LaTeX personnalisé"]
        LMGEN["lettre_generator.py<br/>LM personnalisée"]
    end

    subgraph Storage["Stockage"]
        JSON_FS["Filesystem JSON<br/>data/users/{code}/"]
        V_BLOB["Vercel Blob<br/>(production)"]
    end

    LOGIN --> R_AUTH
    DASH --> R_SCRAPE & R_SCORE & R_GEN & R_OFFERS
    PROF --> R_PROFILE
    SETT --> R_OFFERS

    R_SCRAPE -->|spawn process + stdin/stdout| BRIDGE_S
    R_GEN -->|spawn process + stdin/stdout| BRIDGE_G
    R_SCORE -->|OpenAI API HTTP| MATCHER
    BRIDGE_S --> CRAWLER --> EXTRACTOR
    BRIDGE_G --> CVGEN & LMGEN

    R_OFFERS --> JSON_FS & V_BLOB
```

---

## Pipeline de traitement — Séquence complète

```mermaid
sequenceDiagram
    participant U as Utilisateur
    participant N as Next.js
    participant B as bridge_scrape.py
    participant P as Playwright (Chromium)
    participant E as Extracteur HTML
    participant G as GPT-4o (OpenAI)
    participant S as Stockage JSON

    rect rgb(230, 245, 255)
        Note over U,S: Phase 1 — Scraping
        U->>N: Lance le scraping (via dashboard)
        N->>B: spawn process, envoie config JSON (stdin)
        B->>P: Lance Chromium headless + stealth
        loop Pour chaque source (LinkedIn, Indeed, WTTJ…)
            P->>P: Navigation, scroll, fermeture cookies
            P-->>B: HTML de la page de résultats
            B->>E: Parse les offres (titre, entreprise, url)
            loop Pour chaque offre
                P->>P: Fetch page de détail
                P-->>B: Description complète
            end
        end
        B-->>N: JSON array des offres enrichies (stdout)
        N->>S: Sauvegarde offers.json
    end

    rect rgb(255, 245, 230)
        Note over U,S: Phase 2 — Scoring IA
        U->>N: Scorer toutes les offres
        loop Pour chaque offre
            N->>G: {profil + description} → prompt de scoring
            G-->>N: {score, justification, competences_matchées, lacunes}
            N->>S: Met à jour l'offre avec le score
        end
    end

    rect rgb(230, 255, 230)
        Note over U,S: Phase 3 — Génération documents
        U->>N: Génère CV + Lettre pour une offre
        N->>B: spawn bridge_generate.py (offre + profil)
        B->>G: Génération contenu personnalisé
        G-->>B: Texte adapté au poste
        B->>B: Construction LaTeX, formatage
        B-->>N: JSON {cv: "...", lettre: "..."}
        N->>S: Sauvegarde dans generated/
        N-->>U: Affiche le document dans le navigateur
    end
```

---

## Anti-détection — Stratégie Playwright

```mermaid
flowchart LR
    A["Début crawl"] --> B["User-Agent aléatoire<br/>(pool de 5 UA)"]
    B --> C["playwright-stealth<br/>(masque les traces headless)"]
    C --> D["Viewport 1920×1080<br/>locale fr-FR"]
    D --> E["Navigation goto()"]
    E --> F["Délai humain aléatoire<br/>2–5 secondes"]
    F --> G["Fermeture popups cookies<br/>(sélecteurs CSS multiples)"]
    G --> H["Scroll progressif<br/>(lazy-load images)"]
    H --> I["Extraction HTML"]
```

---

## Système d'authentification

```mermaid
flowchart TD
    REQ["Requête entrante"] --> MW["middleware.ts<br/>(Next.js Edge)"]
    MW --> CHK{"Cookie access_code<br/>présent et valide ?"}
    CHK -- Non --> LOGIN["Redirect → /login"]
    CHK -- Oui --> VALID{"Regex [a-zA-Z0-9_-]{3,64}<br/>+ allowlist optionnelle"}
    VALID -- Invalide --> ERR["401 Unauthorized"]
    VALID -- Valide --> ISOLATE["Données isolées<br/>users/{code}/"]
    ISOLATE --> OFFERS["offers.json"]
    ISOLATE --> PROFILE["profile.json"]
    ISOLATE --> SETTINGS["settings.json"]
    ISOLATE --> GEN["generated/*.txt"]
```

---

## Adaptateur de stockage — Abstraction locale/Blob

```mermaid
graph TD
    APP["Routes API"] --> ADAPTER["StorageAdapter<br/>(lib/storage/)"]
    ADAPTER --> ENV{"STORAGE_ADAPTER=?"}
    ENV -- local --> FS["LocalAdapter<br/>fs/promises<br/>data/users/{code}/"]
    ENV -- blob --> BLOB["BlobAdapter<br/>@vercel/blob<br/>BLOB_READ_WRITE_TOKEN"]
```

---

## Stack technique complète

| Couche | Techno | Choix technique |
|---|---|---|
| UI | **Next.js 14** App Router | SSR + API routes dans un seul projet |
| Style | **Tailwind CSS** | Utility-first, aucun composant externe |
| Scraping | **Playwright** + **playwright-stealth** | Contourne les détections headless |
| Parsing HTML | **BeautifulSoup4** | Extraction robuste par sélecteurs CSS/XPath |
| IA | **OpenAI GPT-4o** | Scoring sémantique + génération de texte |
| Documents | **LaTeX** | PDF professionnels reproductibles |
| Stockage | **JSON fichier** / **Vercel Blob** | Zéro dépendance DB, multi-provider |
| Auth | **Cookie httpOnly** + code d'accès | Stateless, sans base d'utilisateurs |
| IPC Python↔Node | **spawn + stdin/stdout** | Bridge léger, pas de serveur Python dédié |
| Deploy | **Docker**, **Railway**, **Vercel** | Flexible selon l'environnement |

---

---

## Architecture

```
job-hunter/
├── scraper/            → Scrapers Playwright (LinkedIn, Indeed, WTTJ, HelloWork)
├── ai/                 → Scoring IA + génération CV/lettre (OpenAI)
├── latex/              → Template CV source (cv_base.tex)
├── db/                 → Base SQLite (dashboard Flask legacy)
├── dashboard/          → Dashboard Flask (interface legacy)
├── bridge_scrape.py    → Bridge Python → appelé par l'API Next.js pour scraper
├── bridge_generate.py  → Bridge Python → appelé par l'API Next.js pour générer LaTeX
├── config.yaml         → Config principale (profil, sources, OpenAI, critères de recherche)
├── run.py              → Point d'entrée CLI (scraping, scoring, génération)
└── web/                → Application web Next.js (interface principale)
    ├── src/
    │   ├── app/        → Pages et routes API (App Router)
    │   ├── components/ → Composants React
    │   └── lib/        → Types, auth, storage adapter
    └── data/
        └── users/      → Données utilisateurs (JSON, isolées par code d'accès)
```

---

## Prérequis

| Outil | Version minimale |
|---|---|
| Node.js | 18+ |
| Python | 3.11+ |
| npm | 9+ |

---

## Installation

### 1. Cloner le projet

```bash
git clone <repo-url>
cd job-hunter
```

### 2. Installer les dépendances Python

```bash
pip install -r requirements.txt
```

Installer aussi les navigateurs Playwright (nécessaire pour le scraping réel) :

```bash
playwright install chromium
```

### 3. Installer les dépendances Node.js

```bash
cd web
npm install
```

### 4. Configurer

#### config.yaml (scraper Python)

Copier l'exemple et l'adapter :

```bash
cp config.example.yaml config.yaml
```

Les champs importants :

```yaml
openai:
  api_key: "sk-..."       # Votre clé OpenAI

sources:
  - nom: "LinkedIn"
    url: "https://www.linkedin.com/jobs/search/?keywords=..."
    actif: true
  - nom: "Indeed"
    url: "https://fr.indeed.com/jobs?q=..."
    actif: true
```

#### Variables d'environnement Next.js (optionnel)

Créer `web/.env.local` si besoin :

```env
# Stockage : "local" (filesystem) ou "blob" (Vercel Blob)
STORAGE_ADAPTER=local

# Codes d'accès autorisés (vide = tout code valide accepté)
ALLOWED_CODES=
```

Par défaut, tout code alphanumérique est accepté et les données sont stockées dans `web/data/users/{code}/`.

---

## Lancer en local

### Interface web (Next.js)

```bash
cd web
npm run dev
```

Ouvrir **http://localhost:3000**

### Flux d'utilisation dans l'interface

1. **Se connecter** — saisir un code d'accès (ex : `Abde`)
2. **Profil** — remplir nom, compétences, expérience
3. **Paramètres** — coller sa clé OpenAI, configurer les critères de recherche et éventuellement ajouter des URLs de sites supplémentaires
4. **Dashboard → Lancer le scraping** — scrape les sites configurés dans `config.yaml` + les URLs ajoutées dans l'interface
5. **Scorer les offres** — scoring IA 0-100 pour chaque offre par rapport au profil
6. **Cliquer sur une offre** — ouvrir le panneau de détail : infos complètes, score, lien source, génération CV LaTeX et lettre de motivation

---

## Lancer le scraper en CLI (sans interface web)

Toutes les commandes depuis le dossier `job-hunter/` :

```bash
# Toutes les phases (scraping + scoring + génération CV)
python run.py

# Phase 1 uniquement : scraping
python run.py scrape

# Phase 2 uniquement : scoring IA
python run.py match

# Phase 3 : génération CV LaTeX
python run.py cv

# Phase 3b : génération lettres de motivation
python run.py lettre

# Lancer l'ancien dashboard Flask (port 5000)
python run.py dashboard
```

---

## Génération LaTeX

Les CVs et lettres générés sont des fichiers `.tex` compilables avec `pdflatex` ou `latexmk`.

Pour compiler manuellement un `.tex` en PDF :

```bash
latexmk -pdf latex/generated/CV_Entreprise_Poste.tex
# ou
pdflatex latex/generated/CV_Entreprise_Poste.tex
```

Installer TeX Live (Linux/macOS) ou MiKTeX (Windows) si nécessaire.

---

## Déploiement Vercel (production)

1. Pousser le dossier `web/` sur un repo Git
2. Connecter à Vercel
3. Définir les variables d'environnement :

```
STORAGE_ADAPTER=blob
BLOB_READ_WRITE_TOKEN=<votre token Vercel Blob>
ALLOWED_CODES=alice,bob   # optionnel
```

4. Déployer

> En production, le scraping Python ne s'exécute pas sur Vercel (serverless). Utiliser le CLI ou un serveur dédié pour le scraping, et pointer vers les données via le Blob Storage.

---

## Variables d'environnement récapitulatif

| Variable | Valeur par défaut | Description |
|---|---|---|
| `STORAGE_ADAPTER` | `local` | `local` = filesystem, `blob` = Vercel Blob |
| `BLOB_READ_WRITE_TOKEN` | — | Token Vercel Blob (production uniquement) |
| `ALLOWED_CODES` | *(vide)* | Liste de codes autorisés séparés par virgule. Vide = tous acceptés |
