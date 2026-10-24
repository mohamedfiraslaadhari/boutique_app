"""Application Flask : Boutique (Mini-projet).

Lancement :  python app.py   puis   http://127.0.0.1:5000
"""
import shutil
import uuid
from pathlib import Path

from flask import Flask, render_template
from flask_uploads import configure_uploads
from flask_user import UserManager
from flask_user.signals import user_registered

from config import Config
from extensions import csrf, db, migrate, photos
from models import Categorie, Produit, Role, User
from admin_panel import init_admin
from api import api
from cart import cart
from dashboard import dashboard
from shop import shop

app = Flask(__name__)
app.config.from_object(Config)
app.json.ensure_ascii = False      # l'API affiche les accents (é, è, ’) tels quels

# --- Initialisation des extensions ---
db.init_app(app)
migrate.init_app(app, db)
csrf.init_app(app)                 # protection CSRF de tous les formulaires POST
configure_uploads(app, photos)     # Flask-Uploads : dossier static/uploads
user_manager = UserManager(app, db, User)   # Flask-User (utilise Flask-Login en interne)

app.register_blueprint(shop)
app.register_blueprint(cart)
app.register_blueprint(dashboard)
app.register_blueprint(api)
init_admin(app)                    # Flask-Admin : http://127.0.0.1:5000/admin/


# ---------- Rôle par défaut à l'inscription ----------
@user_registered.connect_via(app)
def donner_role_client(sender, user, **extra):
    """Tout nouvel inscrit reçoit le rôle 'client'."""
    role = Role.query.filter_by(name='client').first()
    if role is None:
        role = Role(name='client')
        db.session.add(role)
    user.roles.append(role)
    db.session.commit()


# ---------- Pages d'erreur ----------
@app.errorhandler(403)
def erreur_403(e):
    return render_template('erreur.html', code=403, message="Accès refusé."), 403


@app.errorhandler(404)
def erreur_404(e):
    return render_template('erreur.html', code=404, message="Page introuvable."), 404


@app.errorhandler(413)
def erreur_413(e):
    return render_template('erreur.html', code=413,
                           message="Fichier trop volumineux (2 Mo maximum)."), 413


# ---------- Images de démonstration ----------
# nom du produit -> nom du fichier (sans extension) à placer dans le dossier static/demo
PHOTOS_DEMO = {
    'Clavier sans fil': 'clavier',
    'Souris optique': 'souris',
    'Lampe de bureau': 'lampe',
    'Ballon de football': 'ballon',
}
EXTENSIONS_PHOTOS = ('.jpg', '.jpeg', '.png', '.webp')


def trouver_image_demo(nom_fichier):
    """Cherche static/demo/<nom_fichier>.jpg (ou .jpeg, .png, .webp), majuscules ou non.

    Retourne None si l'image n'existe pas.
    """
    dossier = Path(app.static_folder) / 'demo'
    if dossier.is_dir():
        for chemin in sorted(dossier.iterdir()):
            if chemin.stem.lower() == nom_fichier and chemin.suffix.lower() in EXTENSIONS_PHOTOS:
                return chemin
    return None


def ajouter_photos_demo():
    """Donne une image aux produits de démonstration qui n'en ont pas encore.

    L'image est copiée dans static/uploads (comme une photo envoyée par le formulaire).
    Retourne le nombre d'images ajoutées. On peut relancer sans risque : un produit
    qui a déjà une photo n'est jamais modifié.
    """
    dossier_photos = Path(app.config['UPLOADED_PHOTOS_DEST'])
    dossier_photos.mkdir(parents=True, exist_ok=True)
    ajoutees = 0
    for nom, nom_fichier in PHOTOS_DEMO.items():
        produit = Produit.query.filter(Produit.nom == nom, Produit.photo.is_(None)).first()
        source = trouver_image_demo(nom_fichier)
        if produit and source:
            nouveau_nom = f'{uuid.uuid4().hex}{source.suffix.lower()}'
            shutil.copy(source, dossier_photos / nouveau_nom)
            produit.photo = nouveau_nom
            ajoutees += 1
    db.session.commit()
    return ajoutees


# ---------- Commande : flask seed (données de démonstration) ----------
@app.cli.command('seed')
def seed():
    """Crée les rôles, 3 comptes de démonstration, des catégories et des produits."""
    for nom in ('admin', 'vendeur', 'client'):
        if not Role.query.filter_by(name=nom).first():
            db.session.add(Role(name=nom))
    db.session.commit()

    comptes = [('admin', 'admin@boutique.tn', 'Admin1234!', 'admin'),
               ('vendeur', 'vendeur@boutique.tn', 'Vendeur1234!', 'vendeur'),
               ('client', 'client@boutique.tn', 'Client1234!', 'client')]
    for username, email, mot_de_passe, role in comptes:
        if not User.query.filter_by(username=username).first():
            utilisateur = User(username=username, email=email, active=True,
                               password=user_manager.hash_password(mot_de_passe))
            utilisateur.roles.append(Role.query.filter_by(name=role).first())
            db.session.add(utilisateur)
    db.session.commit()

    if Categorie.query.count() == 0:
        informatique = Categorie(nom='Informatique')
        maison = Categorie(nom='Maison')
        sport = Categorie(nom='Sport')
        db.session.add_all([informatique, maison, sport])
        db.session.flush()
        db.session.add_all([
            Produit(nom='Clavier sans fil', description='Clavier AZERTY, 12 mois de garantie.',
                    prix=45.90, stock=20, categorie_id=informatique.id),
            Produit(nom='Souris optique', description='Souris USB 1600 DPI.',
                    prix=19.50, stock=35, categorie_id=informatique.id),
            Produit(nom='Lampe de bureau', description='Lampe LED réglable.',
                    prix=39.00, stock=12, categorie_id=maison.id),
            Produit(nom='Ballon de football', description='Taille 5, cousu main.',
                    prix=29.90, stock=3, categorie_id=sport.id),
        ])
        db.session.commit()
    nb_images = ajouter_photos_demo()
    print(f'Données de démonstration créées : admin / vendeur / client ({nb_images} image(s) ajoutée(s)).')


if __name__ == '__main__':
    app.run(debug=True)