"""Modèles SQLAlchemy de la boutique."""
from datetime import datetime

from flask_user import UserMixin

from extensions import db


# ---------- Utilisateurs et rôles (Flask-User / Flask-Login) ----------
class User(db.Model, UserMixin):
    __tablename__ = 'users'   # "user" est un mot réservé dans PostgreSQL
    id = db.Column(db.Integer, primary_key=True)
    active = db.Column(db.Boolean(), nullable=False, server_default='1')
    username = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(255), nullable=True, unique=True)
    email_confirmed_at = db.Column(db.DateTime())
    password = db.Column(db.String(255), nullable=False, server_default='')

    roles = db.relationship('Role', secondary='user_roles',
                            backref=db.backref('users', lazy='dynamic'))
    commandes = db.relationship('Commande', back_populates='client')

    def __str__(self):
        return self.username


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)   # admin, vendeur, client

    def __str__(self):
        return self.name


class UserRoles(db.Model):
    """Table d'association utilisateur <-> rôle."""
    __tablename__ = 'user_roles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id', ondelete='CASCADE'))


# ---------- Catalogue ----------
class Categorie(db.Model):
    __tablename__ = 'categorie'
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(80), unique=True, nullable=False)

    produits = db.relationship('Produit', back_populates='categorie')

    def __str__(self):
        return self.nom


class Produit(db.Model):
    __tablename__ = 'produit'
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    prix = db.Column(db.Numeric(10, 2), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    photo = db.Column(db.String(200))   # nom du fichier dans static/uploads
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    categorie_id = db.Column(
        db.Integer,
        db.ForeignKey('categorie.id', onupdate='CASCADE', ondelete='RESTRICT'),
        nullable=False)

    categorie = db.relationship('Categorie', back_populates='produits')
    lignes = db.relationship('LigneCommande', back_populates='produit')

    def __str__(self):
        return self.nom


# ---------- Commandes ----------
class Commande(db.Model):
    __tablename__ = 'commande'
    id = db.Column(db.Integer, primary_key=True)
    date_commande = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    statut = db.Column(db.String(20), nullable=False, default='en_attente')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    client = db.relationship('User', back_populates='commandes')
    lignes = db.relationship('LigneCommande', back_populates='commande',
                             cascade='all, delete-orphan')

    @property
    def total(self):
        return sum(l.sous_total for l in self.lignes)


class LigneCommande(db.Model):
    __tablename__ = 'ligne_commande'
    id = db.Column(db.Integer, primary_key=True)
    quantite = db.Column(db.Integer, nullable=False)
    prix_unitaire = db.Column(db.Numeric(10, 2), nullable=False)   # prix au moment de l'achat
    commande_id = db.Column(db.Integer, db.ForeignKey('commande.id', ondelete='CASCADE'), nullable=False)
    produit_id = db.Column(db.Integer, db.ForeignKey('produit.id', ondelete='RESTRICT'), nullable=False)

    commande = db.relationship('Commande', back_populates='lignes')
    produit = db.relationship('Produit', back_populates='lignes')

    @property
    def sous_total(self):
        return self.quantite * self.prix_unitaire
