"""API REST (JSON) de la boutique.

- Lecture publique : produits et catégories (aucun mot de passe).
- Écriture et commandes : authentification HTTP Basic (nom d'utilisateur + mot de passe).
  L'API n'utilise jamais le cookie de session du site : chaque requête s'authentifie.
"""
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request, url_for
from sqlalchemy.exc import IntegrityError

from cart import STATUTS, annuler_et_remettre_en_stock
from extensions import csrf, db
from models import Categorie, Commande, LigneCommande, Produit, User
from shop import supprimer_fichier

api = Blueprint('api', __name__, url_prefix='/api')
csrf.exempt(api)   # pas de jeton CSRF ici : l'API ne se sert pas des cookies

MESSAGES_HTTP = {
    400: 'Requête invalide.',
    401: 'Authentification requise.',
    403: 'Accès refusé.',
    404: 'Ressource introuvable.',
    405: 'Méthode non autorisée.',
}


# ---------- Réponses d'erreur en JSON ----------
def erreur(message, code, **autres):
    return jsonify({'erreur': message, **autres}), code


def erreur_http(e):
    return erreur(MESSAGES_HTTP.get(e.code, e.name), e.code)


# Un gestionnaire par code : ainsi les pages d'erreur HTML du site ne passent pas devant
for _code in MESSAGES_HTTP:
    api.register_error_handler(_code, erreur_http)


# ---------- Authentification HTTP Basic ----------
def utilisateur_api():
    """Retourne l'utilisateur identifié par l'en-tête Authorization, sinon None."""
    auth = request.authorization
    if not auth or not auth.username or not auth.password:
        return None
    utilisateur = User.query.filter_by(username=auth.username).first()
    if (utilisateur and utilisateur.active
            and current_app.user_manager.verify_password(auth.password, utilisateur.password)):
        return utilisateur
    return None


def authentification(*roles):
    """Exige un utilisateur connecté et, si roles est donné, l'un de ces rôles."""
    def decorateur(vue):
        @wraps(vue)
        def enveloppe(*args, **kwargs):
            utilisateur = utilisateur_api()
            if utilisateur is None:
                reponse, code = erreur('Authentification requise (HTTP Basic).', 401)
                reponse.headers['WWW-Authenticate'] = 'Basic realm="Boutique API"'
                return reponse, code
            if roles and not utilisateur.has_roles(list(roles)):
                return erreur('Accès refusé pour votre rôle.', 403)
            g.api_user = utilisateur
            return vue(*args, **kwargs)
        return enveloppe
    return decorateur


def est_personnel(utilisateur):
    return utilisateur.has_roles(['admin', 'vendeur'])


# ---------- Conversion des objets en JSON ----------
def categorie_json(c):
    return {'id': c.id, 'nom': c.nom, 'nb_produits': len(c.produits)}


def produit_json(p):
    photo = (url_for('static', filename='uploads/' + p.photo, _external=True)
             if p.photo else None)
    return {'id': p.id, 'nom': p.nom, 'description': p.description,
            'prix': float(p.prix), 'stock': p.stock, 'photo': photo,
            'categorie': {'id': p.categorie.id, 'nom': p.categorie.nom}}


def commande_json(c):
    return {'id': c.id, 'client': c.client.username,
            'date': c.date_commande.isoformat(),
            'statut': c.statut, 'statut_libelle': STATUTS[c.statut],
            'total': float(c.total),
            'lignes': [{'produit_id': l.produit_id, 'produit': l.produit.nom,
                        'quantite': l.quantite, 'prix_unitaire': float(l.prix_unitaire),
                        'sous_total': float(l.sous_total)} for l in c.lignes]}


def creee(objet_json, endpoint, **valeurs):
    """Réponse 201 Created avec l'adresse de la ressource dans l'en-tête Location."""
    reponse = jsonify(objet_json)
    reponse.status_code = 201
    reponse.headers['Location'] = url_for(endpoint, **valeurs)
    return reponse


# ---------- Lecture et validation du JSON reçu ----------
def lire_json():
    donnees = request.get_json(silent=True)
    return donnees if isinstance(donnees, dict) else None


def est_entier(valeur):
    return isinstance(valeur, int) and not isinstance(valeur, bool)


def valider_produit(donnees, partiel):
    """Retourne (valeurs, message). Même règles que le formulaire du site."""
    valeurs = {}
    if 'nom' in donnees or not partiel:
        nom = donnees.get('nom')
        if not isinstance(nom, str) or not 2 <= len(nom.strip()) <= 100:
            return None, 'nom : texte de 2 à 100 caractères obligatoire.'
        valeurs['nom'] = nom.strip()
    if 'description' in donnees:
        texte = donnees['description']
        if texte is not None and (not isinstance(texte, str) or len(texte) > 2000):
            return None, 'description : texte de 2000 caractères maximum.'
        valeurs['description'] = (texte or '').strip() or None
    if 'prix' in donnees or not partiel:
        brut = donnees.get('prix')
        try:
            if isinstance(brut, bool) or brut is None:
                raise InvalidOperation
            prix = Decimal(str(brut))
        except InvalidOperation:
            return None, 'prix : nombre obligatoire.'
        if not prix.is_finite() or not Decimal('0.01') <= prix <= Decimal('1000000'):
            return None, 'prix : doit être compris entre 0.01 et 1000000.'
        valeurs['prix'] = prix.quantize(Decimal('0.01'))
    if 'stock' in donnees or not partiel:
        stock = donnees.get('stock')
        if not est_entier(stock) or not 0 <= stock <= 100000:
            return None, 'stock : entier compris entre 0 et 100000 obligatoire.'
        valeurs['stock'] = stock
    if 'categorie_id' in donnees or not partiel:
        categorie_id = donnees.get('categorie_id')
        if not est_entier(categorie_id) or db.session.get(Categorie, categorie_id) is None:
            return None, 'categorie_id : identifiant d’une catégorie existante obligatoire.'
        valeurs['categorie_id'] = categorie_id
    return valeurs, None


def valider_nom_categorie(donnees, categorie_id=None):
    nom = donnees.get('nom')
    if not isinstance(nom, str) or not 2 <= len(nom.strip()) <= 80:
        return None, 'nom : texte de 2 à 80 caractères obligatoire.'
    nom = nom.strip()
    existe = Categorie.query.filter(db.func.lower(Categorie.nom) == nom.lower()).first()
    if existe and existe.id != categorie_id:
        return None, 'Cette catégorie existe déjà.'
    return nom, None


# ---------- Page d'accueil de l'API ----------
@api.route('/')
def accueil():
    return jsonify({
        'nom': 'API Boutique',
        'authentification': 'HTTP Basic (nom d’utilisateur et mot de passe) sauf lecture publique',
        'points_d_acces': {
            'GET /api/produits': 'liste (?q=texte&categorie=id) - public',
            'GET /api/produits/<id>': 'détail - public',
            'POST /api/produits': 'créer - admin ou vendeur',
            'PUT /api/produits/<id>': 'remplacer - admin ou vendeur',
            'PATCH /api/produits/<id>': 'modifier en partie - admin ou vendeur',
            'DELETE /api/produits/<id>': 'supprimer - admin ou vendeur',
            'GET /api/categories': 'liste - public',
            'GET /api/categories/<id>': 'détail - public',
            'POST /api/categories': 'créer - admin ou vendeur',
            'PUT /api/categories/<id>': 'renommer - admin ou vendeur',
            'DELETE /api/categories/<id>': 'supprimer - admin ou vendeur',
            'GET /api/commandes': 'mes commandes (toutes pour admin et vendeur) - connecté',
            'GET /api/commandes/<id>': 'détail - propriétaire, admin ou vendeur',
            'POST /api/commandes': 'passer une commande - connecté',
            'POST /api/commandes/<id>/annuler': 'annuler ma commande en attente - connecté',
            'PATCH /api/commandes/<id>/statut': 'changer le statut - admin ou vendeur',
        },
    })


# ---------- Produits ----------
@api.route('/produits')
def liste_produits():
    requete = Produit.query
    recherche = request.args.get('q', '').strip()
    categorie_id = request.args.get('categorie', type=int)
    if recherche:
        requete = requete.filter(Produit.nom.ilike(f'%{recherche}%'))
    if categorie_id:
        requete = requete.filter_by(categorie_id=categorie_id)
    return jsonify([produit_json(p) for p in requete.order_by(Produit.nom).all()])


@api.route('/produits/<int:produit_id>')
def un_produit(produit_id):
    return jsonify(produit_json(db.get_or_404(Produit, produit_id)))


@api.route('/produits', methods=['POST'])
@authentification('admin', 'vendeur')
def creer_produit():
    donnees = lire_json()
    if donnees is None:
        return erreur('Corps JSON attendu : un objet { ... }.', 400)
    valeurs, message = valider_produit(donnees, partiel=False)
    if message:
        return erreur(message, 400)
    produit = Produit(**valeurs)
    db.session.add(produit)
    db.session.commit()
    return creee(produit_json(produit), 'api.un_produit', produit_id=produit.id)


@api.route('/produits/<int:produit_id>', methods=['PUT', 'PATCH'])
@authentification('admin', 'vendeur')
def modifier_produit(produit_id):
    produit = db.get_or_404(Produit, produit_id)
    donnees = lire_json()
    if donnees is None:
        return erreur('Corps JSON attendu : un objet { ... }.', 400)
    # PUT remplace tout (tous les champs obligatoires), PATCH modifie seulement ceux envoyés
    valeurs, message = valider_produit(donnees, partiel=(request.method == 'PATCH'))
    if message:
        return erreur(message, 400)
    for champ, valeur in valeurs.items():
        setattr(produit, champ, valeur)
    db.session.commit()
    return jsonify(produit_json(produit))


@api.route('/produits/<int:produit_id>', methods=['DELETE'])
@authentification('admin', 'vendeur')
def supprimer_produit(produit_id):
    produit = db.get_or_404(Produit, produit_id)
    photo = produit.photo
    try:
        db.session.delete(produit)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return erreur('Impossible de supprimer : ce produit figure dans des commandes.', 409)
    supprimer_fichier(photo)
    return '', 204


# ---------- Catégories ----------
@api.route('/categories')
def liste_categories():
    return jsonify([categorie_json(c) for c in Categorie.query.order_by(Categorie.nom).all()])


@api.route('/categories/<int:categorie_id>')
def une_categorie(categorie_id):
    return jsonify(categorie_json(db.get_or_404(Categorie, categorie_id)))


@api.route('/categories', methods=['POST'])
@authentification('admin', 'vendeur')
def creer_categorie():
    donnees = lire_json()
    if donnees is None:
        return erreur('Corps JSON attendu : un objet { ... }.', 400)
    nom, message = valider_nom_categorie(donnees)
    if message:
        return erreur(message, 400)
    categorie = Categorie(nom=nom)
    db.session.add(categorie)
    db.session.commit()
    return creee(categorie_json(categorie), 'api.une_categorie', categorie_id=categorie.id)


@api.route('/categories/<int:categorie_id>', methods=['PUT'])
@authentification('admin', 'vendeur')
def renommer_categorie(categorie_id):
    categorie = db.get_or_404(Categorie, categorie_id)
    donnees = lire_json()
    if donnees is None:
        return erreur('Corps JSON attendu : un objet { ... }.', 400)
    nom, message = valider_nom_categorie(donnees, categorie_id)
    if message:
        return erreur(message, 400)
    categorie.nom = nom
    db.session.commit()
    return jsonify(categorie_json(categorie))


@api.route('/categories/<int:categorie_id>', methods=['DELETE'])
@authentification('admin', 'vendeur')
def supprimer_categorie(categorie_id):
    categorie = db.get_or_404(Categorie, categorie_id)
    try:
        db.session.delete(categorie)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return erreur('Impossible de supprimer : cette catégorie contient des produits.', 409)
    return '', 204


# ---------- Commandes ----------
def peut_voir_commande(commande):
    return commande.user_id == g.api_user.id or est_personnel(g.api_user)


@api.route('/commandes')
@authentification()
def liste_commandes():
    requete = Commande.query
    if not est_personnel(g.api_user):
        requete = requete.filter_by(user_id=g.api_user.id)
    statut = request.args.get('statut')
    if statut in STATUTS:
        requete = requete.filter_by(statut=statut)
    commandes = requete.order_by(Commande.date_commande.desc(), Commande.id.desc()).all()
    return jsonify([commande_json(c) for c in commandes])


@api.route('/commandes/<int:commande_id>')
@authentification()
def une_commande(commande_id):
    commande = db.get_or_404(Commande, commande_id)
    if not peut_voir_commande(commande):
        return erreur('Accès refusé : ce n’est pas votre commande.', 403)
    return jsonify(commande_json(commande))


@api.route('/commandes', methods=['POST'])
@authentification()
def creer_commande():
    """Corps attendu : {"lignes": [{"produit_id": 1, "quantite": 2}, ...]}"""
    donnees = lire_json()
    lignes = donnees.get('lignes') if donnees else None
    if not isinstance(lignes, list) or not 1 <= len(lignes) <= 50:
        return erreur('lignes : liste de 1 à 50 éléments obligatoire.', 400)

    demande = {}                     # {produit_id: quantité totale}
    for ligne in lignes:
        if not isinstance(ligne, dict):
            return erreur('Chaque ligne doit être un objet {produit_id, quantite}.', 400)
        produit_id, quantite = ligne.get('produit_id'), ligne.get('quantite')
        if not est_entier(produit_id) or not est_entier(quantite) or not 1 <= quantite <= 100000:
            return erreur('Chaque ligne : produit_id et quantite (entier >= 1) obligatoires.', 400)
        demande[produit_id] = demande.get(produit_id, 0) + quantite

    commande = Commande(user_id=g.api_user.id, statut='en_attente')
    introuvables, insuffisants = [], []
    # Lignes produit verrouillées pendant la vérification : pas de vente en double
    for produit_id in sorted(demande):
        quantite = demande[produit_id]
        produit = db.session.execute(
            db.select(Produit).where(Produit.id == produit_id).with_for_update()
        ).scalar_one_or_none()
        if produit is None:
            introuvables.append(f'produit_id {produit_id} introuvable.')
        elif produit.stock < quantite:
            insuffisants.append(f'{produit.nom} : {produit.stock} disponible(s), {quantite} demandé(s).')
        else:
            produit.stock -= quantite
            commande.lignes.append(LigneCommande(produit_id=produit.id, quantite=quantite,
                                                 prix_unitaire=produit.prix))
    if introuvables or insuffisants:
        db.session.rollback()
        if introuvables:
            return erreur('Produit introuvable.', 400, details=introuvables + insuffisants)
        return erreur('Stock insuffisant.', 409, details=insuffisants)

    db.session.add(commande)
    db.session.commit()
    return creee(commande_json(commande), 'api.une_commande', commande_id=commande.id)


@api.route('/commandes/<int:commande_id>/annuler', methods=['POST'])
@authentification()
def annuler_commande(commande_id):
    commande = db.get_or_404(Commande, commande_id)
    if commande.user_id != g.api_user.id:
        return erreur('Accès refusé : ce n’est pas votre commande.', 403)
    if commande.statut != 'en_attente':
        return erreur('Seule une commande « en_attente » peut être annulée.', 409)
    annuler_et_remettre_en_stock(commande)
    db.session.commit()
    return jsonify(commande_json(commande))


@api.route('/commandes/<int:commande_id>/statut', methods=['PATCH'])
@authentification('admin', 'vendeur')
def changer_statut(commande_id):
    """Corps attendu : {"statut": "confirmee"}"""
    commande = db.get_or_404(Commande, commande_id)
    donnees = lire_json()
    nouveau = donnees.get('statut') if donnees else None
    if nouveau not in STATUTS:
        return erreur('statut : une valeur parmi ' + ', '.join(STATUTS) + '.', 400)
    if commande.statut == 'annulee':
        return erreur('Une commande annulée ne peut plus être modifiée.', 409)
    if nouveau == 'annulee':
        annuler_et_remettre_en_stock(commande)
    else:
        commande.statut = nouveau
    db.session.commit()
    return jsonify(commande_json(commande))