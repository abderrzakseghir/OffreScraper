# Job Hunter 🎯

Outil de veille d'offres d'emploi automatisé avec scraping, scoring IA et génération de CV/lettre de motivation personnalisés en LaTeX.

## Fonctionnalités

- **Scraping automatique** des offres LinkedIn, Indeed et Welcome to the Jungle via Playwright
- **Scoring IA** de chaque offre par rapport à votre profil (OpenAI GPT)
- **Génération de CV** LaTeX personnalisé par offre
- **Génération de lettre de motivation** LaTeX par offre
- **Dashboard web** pour visualiser, filtrer et gérer vos offres
- **Authentification par code d'accès**
- **Déploiement Docker** (local ou Railway)

---

## Prérequis

- [Docker](https://www.docker.com/get-started) + [Docker Compose](https://docs.docker.com/compose/) — pour le lancement via conteneur
- **OU** Python 3.10+ — pour le lancement en local sans Docker
- Une clé API [OpenAI](https://platform.openai.com/api-keys) (pour le scoring et la génération)

---

## Lancement avec Docker (recommandé)

### 1. Cloner le projet

```bash
git clone https://github.com/abderrzakseghir/OffreScraper.git
cd OffreScraper
```

### 2. Configurer le profil

Copiez le fichier de configuration exemple et éditez-le avec vos informations :

```bash
cp job-hunter/config.example.yaml job-hunter/config.yaml
```

Ouvrez `job-hunter/config.yaml` et remplissez :
- **`profil`** : vos nom, titre, compétences, expériences et formations
- **`openai.api_key`** : votre clé API OpenAI
- **`recherche.mots_cles`** : les mots-clés de vos recherches d'emploi
- **`sources`** : les URLs des recherches LinkedIn/Indeed/WTTJ (optionnel)

### 3. Définir un secret Flask (optionnel mais recommandé)

Créez un fichier `.env` à la racine :

```env
FLASK_SECRET_KEY=une-chaine-aleatoire-longue-et-secrete
```

### 4. Lancer le conteneur

```bash
docker compose up -d
```

L'application démarre sur **http://localhost:5000**

Pour voir les logs en temps réel :
```bash
docker compose logs -f
```

Pour arrêter :
```bash
docker compose down
```

---

## Lancement en local (sans Docker)

### 1. Cloner le projet

```bash
git clone https://github.com/abderrzakseghir/OffreScraper.git
cd OffreScraper/job-hunter
```

### 2. Créer un environnement virtuel et installer les dépendances

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Installer le navigateur Playwright (requis pour le scraping)

```bash
playwright install chromium
```

### 4. Configurer le profil

```bash
cp config.example.yaml config.yaml
# Éditez config.yaml avec vos informations
```

### 5. Lancer le dashboard

```bash
python api/index.py
```

L'application est accessible sur **http://localhost:5000**

---

## Première utilisation

### Connexion

Lors de votre premier accès, connectez-vous avec l'un des codes d'accès par défaut :

| Code | Utilisateur |
|------|-------------|
| `ALPHA-2024` | Utilisateur Alpha |
| `BETA-9876` | Utilisateur Beta |
| `ADMIN-0000` | Administrateur |

> **Important** : Changez ou supprimez ces codes dès la première connexion via la page **Codes d'accès**.

### Configurer votre profil

1. Cliquez sur **⚙️ Paramètres** dans le header
2. Renseignez votre **clé API OpenAI**
3. Remplissez votre profil : nom, titre, compétences, expériences, formations
4. Ajoutez vos **mots-clés de recherche** (ex: `développeur full stack, .NET, C#`)
5. Cliquez **Sauvegarder**

### Lancer le scraping

1. Retournez sur la page **Accueil**
2. Dans le panneau **Scraping**, sélectionnez :
   - Les **sources** à scraper (LinkedIn, Indeed, Welcome to the Jungle)
   - La **fraîcheur** des offres (24h, 48h, 7 jours...)
3. Cliquez **Lancer le scraping**
4. Le scraping s'exécute en arrière-plan — la progression s'affiche en temps réel

### Analyser une offre

1. Depuis la liste, cliquez sur une offre pour ouvrir sa page de détail
2. Cliquez **Analyser avec l'IA** pour obtenir :
   - Un **score** de correspondance (0–100)
   - Les **compétences matchées**
   - Les **lacunes** identifiées
   - Un **conseil de candidature**
3. Cliquez **Générer le CV** pour obtenir un CV LaTeX personnalisé pour cette offre
4. Cliquez **Générer la lettre** pour obtenir une lettre de motivation LaTeX
5. Copiez le LaTeX généré et compilez-le avec [Overleaf](https://www.overleaf.com) ou `pdflatex`

### Gérer les codes d'accès

1. Cliquez sur **🔑 Codes** dans le header
2. **Ajoutez** de nouveaux codes pour partager l'accès
3. **Supprimez** les codes par défaut pour sécuriser l'application

---

## Déploiement en production (Railway)

Railway est une plateforme cloud qui supporte Docker et donc Playwright.

1. Créez un compte sur [railway.app](https://railway.app)
2. **New Project** → **Deploy from GitHub** → sélectionnez `OffreScraper`
3. Railway détecte automatiquement le `Dockerfile`
4. Dans **Settings → Variables**, ajoutez :
   ```
   FLASK_SECRET_KEY=une-chaine-aleatoire-tres-longue
   ```
5. Railway déploie automatiquement à chaque push sur `main`

---

## Structure du projet

```
OffreScraper/
├── Dockerfile              # Image Docker pour Railway / Docker Compose
├── docker-compose.yml      # Lancement local via Docker
├── railway.toml            # Configuration Railway
├── vercel.json             # Configuration Vercel (scraping désactivé)
└── job-hunter/
    ├── api/
    │   └── index.py        # Application Flask (routes, auth, API)
    ├── ai/
    │   ├── matcher.py      # Scoring IA (OpenAI)
    │   ├── cv_generator.py # Génération CV LaTeX
    │   └── lettre_generator.py
    ├── db/
    │   └── blob_storage.py # Stockage JSON local (ou Vercel Blob)
    ├── scraper/
    │   ├── crawler.py      # Orchestrateur de scraping
    │   ├── detail_fetcher.py
    │   └── sites/
    │       ├── linkedin.py
    │       ├── indeed.py
    │       └── welcometothejungle.py
    ├── dashboard/
    │   └── templates/      # Templates HTML (index, detail, settings, login, codes)
    ├── latex/
    │   └── cv_base.tex     # CV LaTeX de base à personnaliser
    ├── codes.json          # Codes d'accès
    ├── config.yaml         # Configuration (à créer depuis config.example.yaml)
    └── config.example.yaml # Template de configuration
```

---

## Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `FLASK_SECRET_KEY` | Clé secrète Flask (sessions) | `job-hunter-secret-key-change-me` |
| `PORT` | Port d'écoute | `5000` |
| `VERCEL` | Défini automatiquement sur Vercel | — |
| `BLOB_READ_WRITE_TOKEN` | Token Vercel Blob (si déployé sur Vercel) | — |

---

## Notes importantes

- **Le scraping nécessite Playwright** — il est désactivé sur Vercel (serverless). Utilisez Docker/Railway ou le lancement local.
- **Les offres sont isolées par code d'accès** — chaque utilisateur voit uniquement ses propres offres.
- **Les données sont persistées** dans `_local_blob/` (local) ou via Docker volume (conteneur).
- **Ne commitez jamais** `config.yaml` ni `_local_blob/` — ils sont dans `.gitignore`.
