"""Panier (stocké dans la session) et commandes."""
from decimal import Decimal

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   session, url_for)
from flask_login import current_user
from flask_user import login_required, roles_required

from extensions import db
from models import Commande, LigneCommande, Produit

cart = Blueprint('cart', __name__)

# Statuts possibles d'une commande : code stocké en base -> libellé affiché
STATUTS = {
    'en_attente': 'En attente',
    'confirmee': 'Confirmée',
    'expediee': 'Expédiée',
    'livree': 'Livrée',
    'annulee': 'Annulée',
}


# ---------- Fonctions utilitaires ----------
def lire_panier():
    """Retourne le panier de la session : {id du produit (texte): quantité}."""
    return session.get('panier', {})


def ecrire_panier(panier):
    session['panier'] = panier
    session.modified = True


def lignes_du_panier():
    """Retourne (lignes, total). Chaque ligne : produit, quantité et sous-total."""
    panier = lire_panier()
    lignes = []
    total = Decimal('0')
    for produit_id, quantite in list(panier.items()):
        produit = db.session.get(Produit, int(produit_id))
        if produit is None:              # produit supprimé entre-temps : on le retire
            panier.pop(produit_id)
            continue
        sous_total = produit.prix * quantite
        lignes.append({'produit': produit, 'quantite': quantite, 'sous_total': sous_total})
        total += sous_total
    ecrire_panier(panier)
    return lignes, total


def peut_voir(commande):
    """Le propriétaire de la commande, un admin ou un vendeur."""
    return (commande.user_id == current_user.id
            or current_user.has_roles(['admin', 'vendeur']))


def annuler_et_remettre_en_stock(commande):
    """Passe la commande en 'annulée' et rend les quantités au stock."""
    for ligne in commande.lignes:
        ligne.produit.stock += ligne.quantite
    commande.statut = 'annulee'


@cart.app_context_processor
def injecter_dans_les_pages():
    """Variables disponibles dans tous les gabarits (menu et statuts)."""
    return {'nb_panier': sum(lire_panier().values()), 'STATUTS': STATUTS}


# ---------- Le panier ----------
@cart.route('/panier')
def voir_panier():
    lignes, total = lignes_du_panier()
    return render_template('panier.html', lignes=lignes, total=total)


@cart.route('/panier/ajouter/<int:produit_id>', methods=['POST'])
def ajouter(produit_id):
    produit = db.get_or_404(Produit, produit_id)
    quantite = request.form.get('quantite', 1, type=int)
    if quantite is None or quantite < 1:
        quantite = 1

    if produit.stock <= 0:
        flash(f'« {produit.nom} » est en rupture de stock.', 'danger')
        return redirect(url_for('shop.detail', produit_id=produit.id))

    panier = lire_panier()
    voulu = panier.get(str(produit.id), 0) + quantite
    if voulu > produit.stock:
        voulu = produit.stock
        flash(f'Stock limité : il reste seulement {produit.stock} « {produit.nom} ».', 'warning')
    else:
        flash(f'« {produit.nom} » ajouté au panier.', 'success')
    panier[str(produit.id)] = voulu
    ecrire_panier(panier)
    return redirect(url_for('cart.voir_panier'))


@cart.route('/panier/modifier/<int:produit_id>', methods=['POST'])
def modifier(produit_id):
    produit = db.get_or_404(Produit, produit_id)
    quantite = request.form.get('quantite', 0, type=int)
    panier = lire_panier()
    if str(produit.id) in panier:
        if quantite is None or quantite < 1:
            panier.pop(str(produit.id))
            flash('Produit retiré du panier.', 'info')
        else:
            if quantite > produit.stock:
                quantite = produit.stock
                flash(f'Stock limité : {produit.stock} disponible(s).', 'warning')
            panier[str(produit.id)] = quantite
        ecrire_panier(panier)
    return redirect(url_for('cart.voir_panier'))


@cart.route('/panier/retirer/<int:produit_id>', methods=['POST'])
def retirer(produit_id):
    panier = lire_panier()
    panier.pop(str(produit_id), None)
    ecrire_panier(panier)
    flash('Produit retiré du panier.', 'info')
    return redirect(url_for('cart.voir_panier'))


@cart.route('/panier/vider', methods=['POST'])
def vider():
    ecrire_panier({})
    flash('Panier vidé.', 'info')
    return redirect(url_for('cart.voir_panier'))


# ---------- Passer commande ----------
@cart.route('/commander', methods=['POST'])
@login_required
def commander():
    panier = lire_panier()
    if not panier:
        flash('Votre panier est vide.', 'danger')
        return redirect(url_for('cart.voir_panier'))

    commande = Commande(user_id=current_user.id, statut='en_attente')
    problemes = []
    # On bloque les lignes produit pendant la vérification du stock, pour que
    # deux clients ne puissent pas acheter la dernière pièce en même temps.
    for produit_id in sorted(panier, key=int):
        quantite = panier[produit_id]
        produit = db.session.execute(
            db.select(Produit).where(Produit.id == int(produit_id)).with_for_update()
        ).scalar_one_or_none()
        if produit is None:
            problemes.append('Un produit du panier n’existe plus.')
        elif produit.stock < quantite:
            problemes.append(f'« {produit.nom} » : {produit.stock} disponible(s), '
                             f'vous en demandez {quantite}.')
        else:
            produit.stock -= quantite       # le stock baisse automatiquement
            commande.lignes.append(LigneCommande(produit_id=produit.id, quantite=quantite,
                                                 prix_unitaire=produit.prix))

    if problemes:
        db.session.rollback()
        for texte in problemes:
            flash(texte, 'danger')
        flash('Corrigez les quantités du panier puis recommencez.', 'info')
        return redirect(url_for('cart.voir_panier'))

    db.session.add(commande)
    db.session.commit()
    ecrire_panier({})
    flash('Commande enregistrée. Merci !', 'success')
    return redirect(url_for('cart.detail_commande', commande_id=commande.id))


# ---------- Commandes du client ----------
@cart.route('/mes-commandes')
@login_required
def mes_commandes():
    commandes = (Commande.query.filter_by(user_id=current_user.id)
                 .order_by(Commande.date_commande.desc()).all())
    return render_template('mes_commandes.html', commandes=commandes)


@cart.route('/commande/<int:commande_id>')
@login_required
def detail_commande(commande_id):
    commande = db.get_or_404(Commande, commande_id)
    if not peut_voir(commande):
        abort(403)
    return render_template('commande_detail.html', commande=commande)


@cart.route('/commande/<int:commande_id>/annuler', methods=['POST'])
@login_required
def annuler_commande(commande_id):
    commande = db.get_or_404(Commande, commande_id)
    if commande.user_id != current_user.id:
        abort(403)
    if commande.statut != 'en_attente':
        flash('Seule une commande « En attente » peut être annulée.', 'danger')
    else:
        annuler_et_remettre_en_stock(commande)
        db.session.commit()
        flash('Commande annulée.', 'success')
    return redirect(url_for('cart.detail_commande', commande_id=commande.id))


# ---------- Gestion des commandes (admin ou vendeur) ----------
@cart.route('/gestion/commandes')
@roles_required(['admin', 'vendeur'])
def gestion_commandes():
    filtre = request.args.get('statut', '')
    requete = Commande.query
    if filtre in STATUTS:
        requete = requete.filter_by(statut=filtre)
    commandes = requete.order_by(Commande.date_commande.desc()).all()
    return render_template('gestion_commandes.html', commandes=commandes, filtre=filtre)


@cart.route('/gestion/commandes/<int:commande_id>/statut', methods=['POST'])
@roles_required(['admin', 'vendeur'])
def changer_statut(commande_id):
    commande = db.get_or_404(Commande, commande_id)
    nouveau = request.form.get('statut')
    if nouveau not in STATUTS:
        abort(400)
    if commande.statut == 'annulee':
        flash('Une commande annulée ne peut plus être modifiée.', 'danger')
    elif nouveau == 'annulee':
        annuler_et_remettre_en_stock(commande)
        db.session.commit()
        flash('Commande annulée, le stock a été remis à jour.', 'success')
    else:
        commande.statut = nouveau
        db.session.commit()
        flash('Statut mis à jour.', 'success')
    return redirect(url_for('cart.gestion_commandes'))