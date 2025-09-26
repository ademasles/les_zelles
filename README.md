# Analyse IA d’Appels d’Offres (CCTP) – Analyse-DCE

Ce projet propose une application complète d’analyse intelligente des documents d’appels d’offres (CCTP), permettant :
- L’import et l’analyse de documents PDF ou DOCX (y compris scannés avec OCR)
- L’extraction, le résumé et la génération de questions/réponses sur le contenu
- Une interface web interactive avec Streamlit pour l’analyse et la gestion des projets

---

## Structure du projet

```bash
analyse-dce/
|   .env
|   docker-compose.yml
|   README.md
|
+---backend/     # Backend FastAPI et logique métier
|   |   Dockerfile      # Image docker backend
|   |   main.py     # Point d’entrée FastAPI
|   |   queries.json        # Cache des requêtes traitées
|   |   requirements.txt        # Dépendances backend
|   |
|   +---database/
|   |       database.py     # Gestion base de données
|   |
|   +---nlp/     # Modules NLP (QA, résumé, filtering)
|   |       filtering.py
|   |       qa.py       # Gestion des LLM pour le Q&A
|   |       summarization.py        # Gestion des LLM pour la synthèse
|   |       train_cross_encoder.py      # Gestion de l'entraînement du CrossEncoder
|   |
|   +---preprocessing/       # Nettoyage, extraction, chunking
|   |       chunking.py
|   |       cleaning.py
|   |       extraction.py
|   |       loading.py
|   |
|   +---utils/       # Utilitaires
|   |       highlight.py        # Surlignage segment dans doc
|   |
|
\---frontend/        # Interface utilisateur Streamlit
        app.py      # Code frontend Streamlit
        Dockerfile      # Image docker frontend
        requirements.txt        # Dépendances frontend
```
## Installation et lancement

### 1. Prérequis
Python 3.10+

Docker et Docker Compose (optionnel mais recommandé)

libreoffice pour convertir DOCX en PDF (nécessaire sur backend)

```bash
sudo apt install libreoffice tesseract-ocr
```

### 2. Installation manuelle
Cloner le dépôt :

```bash
git clone https://ton-repo/analyse-dce.git
cd analyse-dce
```
- Créer et activer un environnement virtuel Python :

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
.\venv\Scripts\activate   # Windows
```
- Installer les dépendances backend :

```bash
pip install -r backend/requirements.txt
```
- Installer les dépendances frontend :

```bash
pip install -r frontend/requirements.txt
```
### 3. Lancer l’application
- Backend (FastAPI)

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
- Frontend (Streamlit)
```bash
streamlit run frontend/app.py
```
### 4. Lancer avec Docker (optionnel)
Build et lancement via docker-compose :

bash
Copier
Modifier
docker-compose up --build
Cela démarre backend et frontend avec leurs images respectives.

## Fichiers importants
```bash
backend/main.py # API REST principale avec gestion upload, QA, feedback, etc.

frontend/app.py # interface utilisateur avec menu, upload, questions, historique

backend/preprocessing/ # extraction de texte, nettoyage, découpage en chunks

backend/nlp/ # modules pour résumé, questions/réponses, filtrage

backend/utils/highlight.py # génération PDF surligné

backend/database/ # connexion base de données (SQLAlchemy)

backend/queries.json # exemple de résultats
```
## Fonctionnalités clés
- Import de documents PDF/DOCX (support OCR pour documents scannés)

- Analyse automatique avec NLP (résumé, extraction de critères techniques)

- Génération et réponses aux questions en langage naturel

- Interface Streamlit pour consultation, feedback et gestion de projets

- Sauvegarde des projets et questions dans base SQL locale

- Surlignage dynamique des extraits dans PDF générés

## Technologies utilisées
- Backend : Python, FastAPI, Uvicorn, PyMuPDF, Tesseract, SQLAlchemy, Hugging Face Transformers, Faiss

- Frontend : Streamlit, streamlit-option-menu, streamlit-tags

- OCR : Tesseract OCR

- Conversion DOCX ➔ PDF : LibreOffice

- Modèle LLM : Mistral 7B (via Ollama ou autre)

## Prérequis système
- Tesseract OCR (https://github.com/tesseract-ocr/tesseract)

- LibreOffice en ligne de commande (pour conversion DOCX en PDF)

## Notes
- Veiller à ce que les chemins de fichiers et variables d’environnement soient correctement configurés (ex: dossier data/)

- La taille et qualité des documents peuvent impacter la rapidité et pertinence des analyses

- Le modèle LLM utilisé doit être adapté à la machine (GPU recommandé)

## Contact
Anton Demasles
✉️ demaslesa@gmail.com



*N’hésite pas à contribuer, signaler des bugs ou proposer des améliorations !*