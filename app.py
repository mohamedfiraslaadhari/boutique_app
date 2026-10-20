"""Application Flask : Boutique (Mini-projet).

Lancement :  python app.py   puis   http://127.0.0.1:5000
"""
from flask import Flask, render_template
from flask_uploads import configure_uploads
from flask_user import UserManager
from flask_user.signals import user_registered

from config import Config
from extensions import csrf, db, migrate, photos
from models import Categorie, Produit, Role, User
from shop import shop

app = Flask(__name__)
app.config.from_object(Config)

# --- Initialisation des extensions ---
db.init_app(app)
migrate.init_app(app, db)
csrf.init_app(app)                 # protection CSRF de tous les formulaires POST
configure_uploads(app, photos)     # Flask-Uploads : dossier static/uploads
user_manager = UserManager(app, db, User)   # Flask-User (utilise Flask-Login en interne)

app.register_blueprint(shop)


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
    print('Données de démonstration créées : admin / vendeur / client.')


if __name__ == '__main__':
    app.run(debug=True)
