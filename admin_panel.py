"""Panneau d'administration (Flask-Admin) réservé au rôle 'admin'.

Adresse : http://127.0.0.1:5000/admin/
"""
from decimal import Decimal

from flask import abort, flash, redirect, request, url_for
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.menu import MenuLink
from flask_login import current_user
from markupsafe import Markup, escape
from wtforms.validators import Length, NumberRange, ValidationError

from cart import STATUTS
from dashboard import calculer_statistiques
from extensions import db
from models import Categorie, Commande, Produit, User


class AccesAdmin:
    """Accès réservé aux utilisateurs connectés qui ont le rôle 'admin'."""

    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_roles('admin')

    def inaccessible_callback(self, name, **kwargs):
        if current_user.is_authenticated:
            abort(403)                      # connecté mais pas admin
        return redirect(url_for('user.login', next=request.url))


class VueAccueil(AccesAdmin, AdminIndexView):
    @expose('/')
    def index(self):
        return self.render('admin/accueil.html', stats=calculer_statistiques())


class VueModele(AccesAdmin, ModelView):
    page_size = 20
    can_view_details = True


# ---------- Produits ----------
class VueProduit(VueModele):
    column_list = ('nom', 'categorie', 'prix', 'stock')
    column_labels = {'nom': 'Nom', 'categorie': 'Catégorie', 'prix': 'Prix (DT)',
                     'stock': 'Stock', 'description': 'Description'}
    column_searchable_list = ('nom', 'description')
    column_sortable_list = ('nom', ('categorie', 'categorie.nom'), 'prix', 'stock')
    column_filters = ('categorie.nom', 'prix', 'stock')
    column_default_sort = 'nom'
    form_columns = ('nom', 'description', 'prix', 'stock', 'categorie')
    form_args = {
        'nom': {'validators': [Length(min=2, max=100)]},
        'prix': {'validators': [NumberRange(min=Decimal('0.01'), max=Decimal('1000000'))]},
        'stock': {'validators': [NumberRange(min=0, max=100000)]},
    }

    def delete_model(self, modele):
        if modele.lignes:     # le produit figure dans des commandes : on le garde
            flash(f'Impossible de supprimer « {modele.nom} » : ce produit figure dans des commandes.',
                  'error')
            return False
        return super().delete_model(modele)


# ---------- Catégories ----------
class VueCategorie(VueModele):
    column_list = ('nom', 'produits')
    column_labels = {'nom': 'Nom', 'produits': 'Nombre de produits'}
    column_formatters = {'produits': lambda vue, contexte, modele, nom: len(modele.produits)}
    column_searchable_list = ('nom',)
    column_default_sort = 'nom'
    form_columns = ('nom',)
    form_args = {'nom': {'validators': [Length(min=2, max=80)]}}

    def delete_model(self, modele):
        if modele.produits:   # une catégorie qui contient des produits ne se supprime pas
            flash(f'Impossible de supprimer « {modele.nom} » : cette catégorie contient des produits.',
                  'error')
            return False
        return super().delete_model(modele)


# ---------- Commandes (lecture seule : les statuts se gèrent depuis le site) ----------
def lignes_en_html(vue, contexte, commande, nom):
    morceaux = [f'{escape(l.produit.nom)} × {l.quantite} à {l.prix_unitaire:.2f} DT'
                for l in commande.lignes]
    return Markup('<br>'.join(morceaux))


class VueCommande(VueModele):
    can_create = False
    can_edit = False
    can_delete = False        # annuler une commande remet le stock : on le fait depuis le site
    column_list = ('id', 'client', 'date_commande', 'statut', 'total')
    column_labels = {'id': 'N°', 'client': 'Client', 'date_commande': 'Date',
                     'statut': 'Statut', 'total': 'Total (DT)', 'lignes': 'Produits commandés'}
    column_choices = {'statut': list(STATUTS.items())}
    column_formatters = {'total': lambda vue, contexte, modele, nom: f'{modele.total:.2f}'}
    column_filters = ('statut', 'date_commande', 'client.username')
    column_default_sort = ('date_commande', True)
    column_details_list = ('id', 'client', 'date_commande', 'statut', 'total', 'lignes')
    column_formatters_detail = {
        'lignes': lignes_en_html,
        'total': lambda vue, contexte, modele, nom: f'{modele.total:.2f} DT',
    }


# ---------- Utilisateurs (le mot de passe ne se modifie pas ici) ----------
class VueUtilisateur(VueModele):
    can_create = False        # les clients s'inscrivent eux-mêmes sur le site
    can_delete = False        # on désactive un compte au lieu de le supprimer
    column_list = ('username', 'email', 'active', 'roles')
    column_labels = {'username': 'Utilisateur', 'email': 'E-mail', 'active': 'Actif',
                     'roles': 'Rôles'}
    column_searchable_list = ('username', 'email')
    column_filters = ('active',)
    form_columns = ('username', 'email', 'active', 'roles')

    def on_model_change(self, form, model, is_created):
        # Garde-fou : un admin ne peut pas se retirer lui-même l'accès.
        if model.id == current_user.id and (not model.active or not model.has_roles('admin')):
            raise ValidationError("Vous ne pouvez pas vous retirer l'accès administrateur.")


def init_admin(app):
    admin = Admin(app, name='Boutique - Administration',
                  index_view=VueAccueil(name='Accueil'))
    vues = [VueProduit(Produit, db.session, name='Produits'),
            VueCategorie(Categorie, db.session, name='Catégories'),
            VueCommande(Commande, db.session, name='Commandes'),
            VueUtilisateur(User, db.session, name='Utilisateurs')]
    for vue in vues:
        admin.add_view(vue)          # la protection CSRF du site (Flask-WTF) s'applique aussi ici
    admin.add_link(MenuLink('Tableau de bord complet', endpoint='dashboard.tableau'))
    admin.add_link(MenuLink('Gérer les statuts des commandes', endpoint='cart.gestion_commandes'))
    admin.add_link(MenuLink('Retour au site', endpoint='shop.catalogue'))
    return admin