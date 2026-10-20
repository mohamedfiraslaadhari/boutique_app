"""Pages de la boutique : catalogue public et gestion (admin / vendeur)."""
import os
import uuid

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, url_for)
from flask_user import roles_required
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import FileStorage

from extensions import db, photos
from forms import CategorieForm, ProduitForm
from models import Categorie, Produit

shop = Blueprint('shop', __name__)


# ---------- Fonctions utilitaires ----------
def sauver_photo(fichier):
    """Enregistre la photo envoyée dans static/uploads et retourne son nom.

    Le nom est remplacé par un identifiant aléatoire : pas de collision de noms
    et pas de nom de fichier fourni par l'utilisateur sur le disque.
    """
    # En modification, le champ peut contenir l'ancien nom (texte) : on n'accepte
    # qu'un vrai fichier envoyé (FileStorage) avec un nom non vide.
    if isinstance(fichier, FileStorage) and fichier.filename:
        return photos.save(fichier, name=f'{uuid.uuid4().hex}.')
    return None


def supprimer_fichier(nom):
    """Supprime une photo du disque (sans erreur si elle n'existe plus)."""
    if nom:
        chemin = os.path.join(current_app.config['UPLOADED_PHOTOS_DEST'], nom)
        if os.path.isfile(chemin):
            os.remove(chemin)


def remplir_categories(form):
    form.categorie_id.choices = [
        (c.id, c.nom) for c in Categorie.query.order_by(Categorie.nom).all()]


# ---------- Pages publiques ----------
@shop.route('/')
def catalogue():
    """Liste des produits, avec recherche par nom et filtre par catégorie."""
    recherche = request.args.get('q', '').strip()
    categorie_id = request.args.get('categorie', type=int)

    requete = Produit.query
    if recherche:
        requete = requete.filter(Produit.nom.ilike(f'%{recherche}%'))
    if categorie_id:
        requete = requete.filter_by(categorie_id=categorie_id)

    produits = requete.order_by(Produit.nom).all()
    categories = Categorie.query.order_by(Categorie.nom).all()
    return render_template('catalogue.html', produits=produits, categories=categories,
                           recherche=recherche, categorie_id=categorie_id)


@shop.route('/produit/<int:produit_id>')
def detail(produit_id):
    produit = db.get_or_404(Produit, produit_id)
    return render_template('produit_detail.html', produit=produit)


# ---------- Gestion des produits (admin ou vendeur) ----------
@shop.route('/gestion/produits')
@roles_required(['admin', 'vendeur'])   # admin OU vendeur
def gestion_produits():
    produits = Produit.query.order_by(Produit.nom).all()
    return render_template('gestion_produits.html', produits=produits)


@shop.route('/gestion/produits/ajouter', methods=['GET', 'POST'])
@roles_required(['admin', 'vendeur'])
def ajouter_produit():
    form = ProduitForm()
    remplir_categories(form)
    if not form.categorie_id.choices:
        flash("Créez d'abord une catégorie.", 'danger')
        return redirect(url_for('shop.categories'))

    if form.validate_on_submit():
        produit = Produit(nom=form.nom.data.strip(),
                          description=(form.description.data or '').strip() or None,
                          prix=form.prix.data, stock=form.stock.data,
                          categorie_id=form.categorie_id.data,
                          photo=sauver_photo(form.photo.data))
        db.session.add(produit)
        db.session.commit()
        flash('Produit ajouté.', 'success')
        return redirect(url_for('shop.gestion_produits'))
    return render_template('produit_form.html', form=form, titre='Ajouter un produit')


@shop.route('/gestion/produits/<int:produit_id>/modifier', methods=['GET', 'POST'])
@roles_required(['admin', 'vendeur'])
def modifier_produit(produit_id):
    produit = db.get_or_404(Produit, produit_id)
    form = ProduitForm(obj=produit)
    remplir_categories(form)

    if form.validate_on_submit():
        produit.nom = form.nom.data.strip()
        produit.description = (form.description.data or '').strip() or None
        produit.prix = form.prix.data
        produit.stock = form.stock.data
        produit.categorie_id = form.categorie_id.data
        nouvelle_photo = sauver_photo(form.photo.data)
        if nouvelle_photo:                       # remplace l'ancienne photo
            supprimer_fichier(produit.photo)
            produit.photo = nouvelle_photo
        db.session.commit()
        flash('Produit modifié.', 'success')
        return redirect(url_for('shop.gestion_produits'))
    return render_template('produit_form.html', form=form, produit=produit,
                           titre='Modifier le produit')


@shop.route('/gestion/produits/<int:produit_id>/supprimer', methods=['POST'])
@roles_required(['admin', 'vendeur'])
def supprimer_produit(produit_id):
    produit = db.get_or_404(Produit, produit_id)
    photo = produit.photo
    try:
        db.session.delete(produit)
        db.session.commit()
        supprimer_fichier(photo)
        flash('Produit supprimé.', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('Impossible de supprimer : ce produit figure dans des commandes.', 'danger')
    return redirect(url_for('shop.gestion_produits'))


# ---------- Gestion des catégories (admin ou vendeur) ----------
@shop.route('/gestion/categories', methods=['GET', 'POST'])
@roles_required(['admin', 'vendeur'])
def categories():
    form = CategorieForm()
    if form.validate_on_submit():
        db.session.add(Categorie(nom=form.nom.data.strip()))
        db.session.commit()
        flash('Catégorie ajoutée.', 'success')
        return redirect(url_for('shop.categories'))
    liste = Categorie.query.order_by(Categorie.nom).all()
    return render_template('categories.html', form=form, categories=liste)


@shop.route('/gestion/categories/<int:categorie_id>/supprimer', methods=['POST'])
@roles_required(['admin', 'vendeur'])
def supprimer_categorie(categorie_id):
    categorie = db.get_or_404(Categorie, categorie_id)
    try:
        db.session.delete(categorie)
        db.session.commit()
        flash('Catégorie supprimée.', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('Impossible de supprimer : cette catégorie contient des produits.', 'danger')
    return redirect(url_for('shop.categories'))
