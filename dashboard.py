"""Tableau de bord : chiffres clés du stock et des ventes (admin et vendeur)."""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template
from flask_user import roles_required
from sqlalchemy import func

from cart import STATUTS
from extensions import db
from models import Commande, LigneCommande, Produit, User

dashboard = Blueprint('dashboard', __name__)

SEUIL_STOCK_BAS = 5          # un produit est "à réapprovisionner" s'il en reste 5 ou moins
JOURS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']


def un_nombre(requete):
    return db.session.scalar(requete) or 0


def calculer_statistiques():
    """Retourne un dictionnaire de chiffres prêts à afficher."""
    vendue = Commande.statut != 'annulee'                      # on ignore les commandes annulées
    montant_ligne = LigneCommande.quantite * LigneCommande.prix_unitaire

    chiffre_affaires = float(un_nombre(
        db.select(func.coalesce(func.sum(montant_ligne), 0))
        .select_from(LigneCommande).join(Commande).where(vendue)))
    nb_commandes = un_nombre(db.select(func.count()).select_from(Commande).where(vendue))
    nb_annulees = un_nombre(db.select(func.count()).select_from(Commande)
                            .where(Commande.statut == 'annulee'))
    valeur_stock = float(un_nombre(
        db.select(func.coalesce(func.sum(Produit.stock * Produit.prix), 0))))

    # Commandes par statut (avec un pourcentage pour dessiner les barres)
    comptes = dict(db.session.execute(
        db.select(Commande.statut, func.count()).group_by(Commande.statut)).all())
    par_statut = [{'code': code, 'libelle': libelle, 'nombre': comptes.get(code, 0)}
                  for code, libelle in STATUTS.items()]
    maximum = max([s['nombre'] for s in par_statut] + [1])
    for s in par_statut:
        s['pct'] = round(100 * s['nombre'] / maximum)

    # Ventes des 7 derniers jours (date enregistrée en UTC)
    aujourd_hui = datetime.now(timezone.utc).date()
    premier_jour = aujourd_hui - timedelta(days=6)
    par_jour = {premier_jour + timedelta(days=i): 0.0 for i in range(7)}
    depuis = datetime.combine(premier_jour, datetime.min.time())
    for commande in Commande.query.filter(vendue, Commande.date_commande >= depuis).all():
        jour = commande.date_commande.date()
        if jour in par_jour:
            par_jour[jour] += float(commande.total)
    maximum_jour = max(list(par_jour.values()) + [1.0])
    ventes_7_jours = [{'libelle': f'{JOURS[jour.weekday()]} {jour.day}', 'montant': montant,
                       'pct': round(100 * montant / maximum_jour)}
                      for jour, montant in par_jour.items()]

    # Les 5 produits les plus vendus
    top = db.session.execute(
        db.select(Produit.nom, func.sum(LigneCommande.quantite), func.sum(montant_ligne))
        .join(LigneCommande, LigneCommande.produit_id == Produit.id)
        .join(Commande, Commande.id == LigneCommande.commande_id)
        .where(vendue).group_by(Produit.id, Produit.nom)
        .order_by(func.sum(LigneCommande.quantite).desc(), Produit.nom).limit(5)).all()
    top_produits = [{'nom': nom, 'quantite': int(quantite), 'montant': float(montant)}
                    for nom, quantite, montant in top]

    return {
        'nb_produits': un_nombre(db.select(func.count()).select_from(Produit)),
        'nb_utilisateurs': un_nombre(db.select(func.count()).select_from(User)),
        'valeur_stock': valeur_stock,
        'nb_commandes': nb_commandes,
        'nb_annulees': nb_annulees,
        'chiffre_affaires': chiffre_affaires,
        'panier_moyen': chiffre_affaires / nb_commandes if nb_commandes else 0.0,
        'par_statut': par_statut,
        'ventes_7_jours': ventes_7_jours,
        'top_produits': top_produits,
        'stock_bas': Produit.query.filter(Produit.stock <= SEUIL_STOCK_BAS)
                                  .order_by(Produit.stock, Produit.nom).limit(10).all(),
        'seuil': SEUIL_STOCK_BAS,
        'dernieres_commandes': Commande.query.order_by(
            Commande.date_commande.desc(), Commande.id.desc()).limit(5).all(),
    }


@dashboard.route('/tableau-de-bord')
@roles_required(['admin', 'vendeur'])
def tableau():
    return render_template('dashboard.html', stats=calculer_statistiques())