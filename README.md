# FidesIA

Assistant en **theologie catholique** propulse par un moteur RAG (Retrieval-Augmented Generation). FidesIA repond aux questions de foi en s'appuyant sur un corpus de documents du Magistere, indexe dans une base vectorielle.

## Architecture

```
FidesIA/
├── app.py              # Serveur FastAPI (routes, middleware, SSE streaming)
├── config.py           # Configuration centralisee (.env)
├── auth.py             # Authentification JWT (register, login, forgot password)
├── database.py         # Couche SQLite (users, conversations, analytics)
├── analytics.py        # Agregation metriques admin (KPIs, geo IP, keywords)
├── rag.py              # Pipeline RAG (LlamaIndex + ChromaDB + Ollama)
├── saints.py           # Calendrier des saints du jour
├── prompts.py          # Prompts systeme
├── email_utils.py      # Envoi d'emails (reset password)
├── data/
│   ├── fidesia.db      # Base SQLite
│   ├── corpus/         # Documents PDF/DOCX du Magistere
│   ├── chroma_db/      # Index vectoriel ChromaDB
│   └── inventaire.json # Inventaire du corpus
└── web/                # Frontend (vanilla JS, servi par FastAPI)
    ├── index.html
    ├── css/styles.css, chat.css
    └── js/
        ├── app.js      # Init, routing, modals, sidebar
        ├── api.js      # Wrapper fetch + SSE streaming
        ├── auth.js     # UI login/register/forgot
        ├── chat.js     # Chat (messages, streaming, sources)
        ├── corpus.js   # Liste du corpus documentaire
        ├── profile.js  # Profil utilisateur (age, niveau, longueur)
        ├── saints.js   # Widget saint du jour
        ├── metrics.js  # Dashboard admin (Chart.js)
        └── vendor/     # Libs tierces (marked, DOMPurify, Chart.js)
```

## Stack technique

| Composant       | Technologie                                     |
|-----------------|--------------------------------------------------|
| Backend         | Python 3.13, FastAPI, Uvicorn                    |
| LLM             | Mistral Large 3 via Ollama (localhost:11434)      |
| Embeddings      | Solon-embeddings-large-0.1 (HuggingFace)         |
| RAG             | LlamaIndex + ChromaDB                            |
| Base de donnees | SQLite (users, conversations, analytics)          |
| Frontend        | HTML/CSS/JS vanilla (pas de framework)            |
| Auth            | JWT (bcrypt, 7 jours d'expiration)                |
| Rate limiting   | slowapi                                          |
| Gestionnaire    | Poetry                                           |

## Installation

```bash
# Cloner le repo
git clone git@github.com:jbdfdb/FidesIA.git
cd FidesIA

# Installer les dependances
poetry install

# Configurer l'environnement
cp .env.example .env  # puis editer les valeurs

# Lancer Ollama avec le modele
ollama pull mistral-large-3:675b-cloud

# Demarrer le serveur
poetry run uvicorn app:app --host 0.0.0.0 --port 11438
```

## Configuration (.env)

| Variable       | Description                          | Defaut                |
|----------------|--------------------------------------|-----------------------|
| `JWT_SECRET`   | Secret JWT (min 32 caracteres)       | *requis*              |
| `OLLAMA_URL`   | URL du serveur Ollama                | http://localhost:11434|
| `OLLAMA_MODEL` | Modele LLM                           | mistral-large-3:675b-cloud |
| `CORPUS_PATH`  | Chemin vers les documents du corpus  | data/corpus           |
| `DB_PATH`      | Chemin de la base SQLite             | data/fidesia.db       |
| `ADMIN_USERS`  | Emails admin (separes par virgule)   | *(vide)*              |
| `SMTP_HOST`    | Serveur SMTP (reset password)        | *(vide)*              |
| `APP_URL`      | URL publique de l'application        | http://localhost:11438|

## Service systemd

```bash
sudo systemctl enable fidesia
sudo systemctl start fidesia
sudo systemctl status fidesia

# Logs
sudo journalctl -u fidesia -f
```

## Fonctionnalites

- **Chat RAG** : reponses en streaming (SSE) avec sources citees du Magistere
- **Profil utilisateur** : adaptation du ton (age, niveau, longueur des reponses)
- **Corpus documentaire** : consultation de l'inventaire des documents indexes
- **Saint du jour** : calendrier liturgique avec biographies
- **Conversations** : historique sauvegarde, partage, suppression
- **Dashboard admin** : KPIs, graphes (Chart.js), geolocalisation IP, mots-cles
- **Securite** : voir section dediee ci-dessous

## API

| Methode | Route                        | Auth     | Description                     |
|---------|------------------------------|----------|---------------------------------|
| POST    | `/ask/stream`                | Optionnel| Question RAG (SSE streaming)    |
| POST    | `/auth/register`             | Non      | Inscription                     |
| POST    | `/auth/login`                | Non      | Connexion                       |
| GET     | `/auth/check`                | Optionnel| Verifier la session             |
| POST    | `/auth/logout`               | Oui      | Deconnexion                     |
| POST    | `/auth/forgot-password`      | Non      | Demande reset mot de passe      |
| POST    | `/auth/reset-password`       | Non      | Reset mot de passe              |
| GET     | `/conversations`             | Oui      | Liste des conversations         |
| GET     | `/conversations/{id}/messages`| Oui     | Messages d'une conversation     |
| DELETE  | `/conversations/{id}`        | Oui      | Supprimer une conversation      |
| POST    | `/conversations/exchange`    | Oui      | Sauvegarder un echange          |
| POST    | `/rate`                      | Oui      | Noter une reponse               |
| GET     | `/corpus`                    | Non      | Inventaire du corpus            |
| GET     | `/saints/today`              | Non      | Saint du jour                   |
| POST    | `/api/track`                 | Non      | Tracking analytics              |
| GET     | `/api/admin/metrics`         | Admin    | Dashboard metriques             |

## Securite

- **OpenAPI desactive** : `/docs`, `/redoc` et `/openapi.json` ne sont pas exposes
- **Headers HTTP** : CSP, HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy
- **Header Server** supprime (Uvicorn `--no-server-header` + Caddy `defer`)
- **Rate limiting** (slowapi) sur tous les endpoints
- **JWT** : bcrypt, expiration 7 jours, secret >= 32 caracteres
- **Validation des entrees** : Pydantic `Literal` pour les types d'evenements, sanitization HTML des metadonnees
- **Erreurs generiques** : les erreurs de validation Pydantic ne revelent pas la structure interne
- **`/health` minimal** : retourne uniquement le statut, sans details techniques
- **`/corpus` filtre** : seuls les champs publics sont exposes (titre, fichier, categorie, source, annee, url)
- **`robots.txt`** : bloque les crawlers sur les routes sensibles (`/api/`, `/auth/`, `/admin/`, etc.)
- **`/.well-known/security.txt`** : contact de securite (RFC 9116)

## Licence

Projet prive.
