# Boutique : gestion de stock et de ventes

Mini-projet Flask : une boutique en ligne avec catalogue, panier, commandes, tableau de bord,
panneau d'administration et API REST.

Projet réalisé par **Mohamed Firas Laâdhari**, étudiant en ingénierie informatique
(Data Analytics) à l'Université Sesame, 2026.

## Fonctionnalités

- **Catalogue** avec photos, recherche par nom et filtre par catégorie
- **Panier** (visiteurs compris) avec contrôle du stock disponible
- **Commandes** : il faut être connecté, le **stock baisse automatiquement** et se remet à jour
  si la commande est annulée
- **Statuts de commande** : en attente, confirmée, expédiée, livrée, annulée
- **Comptes et rôles** : visiteur, client, vendeur, administrateur
- **Gestion des produits et des catégories** (vendeur et admin) avec envoi de photos
- **Tableau de bord** : chiffre d'affaires, panier moyen, commandes par statut, ventes des 7 derniers
  jours, produits à réapprovisionner, meilleures ventes
- **Panneau d'administration** (Flask-Admin) pour l'admin : produits, catégories, commandes, utilisateurs
- **API REST en JSON** : lecture publique, écriture et commandes avec mot de passe (HTTP Basic)
- **Sécurité** : voir plus bas
- **56 tests automatiques**

## Technologies

Python 3.12, Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-WTF, Flask-Login, Flask-User 1.0.2.2,
Flask-Admin, Flask-Reuploaded, PostgreSQL, python-dotenv.

## Comptes de démonstration

| Rôle | Utilisateur | Mot de passe | Ce qu'il peut faire |
|------|-------------|--------------|---------------------|
| Administrateur | `admin` | `Admin1234!` | Tout, dont le panneau `/admin/` |
| Vendeur | `vendeur` | `Vendeur1234!` | Produits, catégories, commandes, tableau de bord |
| Client | `client` | `Client1234!` | Panier, commandes, annulation d'une commande en attente |

Les visiteurs peuvent aussi créer un compte client sur la page d'inscription.

## Installation (Windows, PowerShell)

Prérequis : **Python 3.12**, **PostgreSQL** (avec pgAdmin) et **Git**.

1. Récupérer le projet :

```
git clone https://github.com/mohamedfiraslaadhari/boutique_app.git
cd boutique_app
```

2. Créer l'environnement virtuel et installer les bibliothèques :

```
python -m venv monvenv
monvenv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Créer la base de données : dans **pgAdmin**, clic droit sur **Databases**, puis
   **Create**, puis **Database...**, nom `boutique`.

4. Créer le fichier `.env` à partir du modèle :

```
Copy-Item .env.example .env
```

   Ouvrir `.env`, remplacer `votre_mot_de_passe` par le mot de passe de l'utilisateur
   `postgres`, et générer une clé secrète :

```
python -c "import secrets; print(secrets.token_hex(32))"
```

   Coller le résultat à la place de `une_longue_chaine_aleatoire` (ligne `SECRET_KEY=`).

5. Créer les tables et les données de démonstration :

```
flask db upgrade
flask seed
```

6. Lancer le site :

```
python app.py
```

Puis ouvrir http://127.0.0.1:5000

Autres adresses utiles : tableau de bord `/tableau-de-bord`, administration `/admin/`,
API `/api/`.

## Les tests

```
python -m unittest -v
```

Les 56 tests utilisent une base SQLite temporaire : la base PostgreSQL n'est jamais touchée.
Ils couvrent l'API, le panier, les commandes, le panneau d'administration, le tableau de bord,
les photos et la sécurité.

## L'API REST

La liste complète est affichée sur http://127.0.0.1:5000/api/

| Méthode et adresse | Qui peut l'utiliser |
|--------------------|---------------------|
| `GET /api/produits` et `GET /api/produits/<id>` | Tout le monde |
| `GET /api/categories` et `GET /api/categories/<id>` | Tout le monde |
| `POST`, `PUT`, `PATCH`, `DELETE` sur `/api/produits` et `/api/categories` | Vendeur ou admin |
| `GET /api/commandes` | Connecté (un client ne voit que ses commandes) |
| `POST /api/commandes` et `POST /api/commandes/<id>/annuler` | Connecté |
| `PATCH /api/commandes/<id>/statut` | Vendeur ou admin |

L'authentification est de type **HTTP Basic** (nom d'utilisateur et mot de passe).
Exemples dans PowerShell :

```
curl.exe http://127.0.0.1:5000/api/produits
curl.exe -u admin:Admin1234! http://127.0.0.1:5000/api/commandes
```

Passer une commande :

```
$acces = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes('client:Client1234!'))
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/commandes `
  -Headers @{Authorization = "Basic $acces"} -ContentType 'application/json' `
  -Body '{"lignes":[{"produit_id":1,"quantite":1}]}'
```

## Sécurité

- Mots de passe **hachés** (pbkdf2-sha256), jamais stockés en clair
- Protection **CSRF** sur tous les formulaires
- **Rôles** vérifiés côté serveur sur chaque page sensible
- Requêtes SQL **paramétrées** (SQLAlchemy) et pages protégées contre le HTML injecté
- **Clé secrète** et mot de passe de la base dans `.env`, qui n'est jamais envoyé sur GitHub
- **Limitation des connexions** : après 10 échecs en 5 minutes, l'adresse est bloquée (erreur 429)
- **En-têtes de sécurité** (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`) et cookies de session `HttpOnly` et `SameSite=Lax`
- **Photos** : images JPG, PNG, GIF ou WebP de 2 Mo maximum (les SVG sont refusés),
  enregistrées avec un nom aléatoire
- En production : mettre `FLASK_DEBUG=0` et `HTTPS=1` dans `.env`

## Organisation du projet

```
app.py             création de l'application et commande « flask seed »
config.py          configuration (lit le fichier .env)
extensions.py      outils partagés (base de données, CSRF, photos)
models.py          tables : utilisateurs, rôles, catégories, produits, commandes
forms.py           formulaires
shop.py            catalogue, produits, catégories
cart.py            panier, commandes, gestion des commandes
api.py             API REST
admin_panel.py     panneau d'administration Flask-Admin
dashboard.py       tableau de bord
securite.py        en-têtes de sécurité et limitation des connexions
reduire_images.py  outil pour alléger les photos (nécessite Pillow : pip install Pillow)
templates/         pages HTML
static/            styles, images de démonstration (demo) et photos envoyées (uploads)
migrations/        historique de la structure de la base
test_*.py          tests automatiques
```

## Photos

Les photos de démonstration viennent d'[Unsplash](https://unsplash.com) (licence Unsplash).
Elles sont dans `static/demo/` et la commande `flask seed` les associe aux produits.