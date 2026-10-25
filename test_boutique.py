"""Tests automatiques de la boutique (API REST, panier, commandes).

Lancement :   python -m unittest -v

Les tests utilisent une base SQLite temporaire : ta base PostgreSQL "boutique"
n'est JAMAIS touchée.
"""
import base64
import os
import re
import tempfile
import unittest

# La base de test doit être choisie AVANT d'importer l'application.
FICHIER_BASE = os.path.join(tempfile.gettempdir(), 'boutique_test.db')
if os.path.exists(FICHIER_BASE):
    os.remove(FICHIER_BASE)
os.environ['DATABASE_URL'] = 'sqlite:///' + FICHIER_BASE.replace('\\', '/')

from sqlalchemy import event  # noqa: E402

from app import app  # noqa: E402
from extensions import db  # noqa: E402
from models import Categorie, Commande, Produit  # noqa: E402

app.config['WTF_CSRF_ENABLED'] = False   # les formulaires du site sont testés sans jeton

# Les photos des tests vont dans un dossier temporaire (jamais dans static/uploads)
DOSSIER_PHOTOS = tempfile.mkdtemp()
app.config['UPLOADED_PHOTOS_DEST'] = DOSSIER_PHOTOS
app.upload_set_config['photos'].destination = DOSSIER_PHOTOS


def setUpModule():
    # Sécurité : on refuse de continuer si on n'est pas sur la base de test.
    assert app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'), 'Mauvaise base !'
    with app.app_context():
        @event.listens_for(db.engine, 'connect')
        def activer_cles_etrangeres(connexion, _):
            connexion.execute('PRAGMA foreign_keys=ON')   # SQLite comme PostgreSQL


def entete(utilisateur, mot_de_passe):
    """En-tête HTTP Basic : Authorization: Basic base64(nom:mot_de_passe)."""
    jeton = base64.b64encode(f'{utilisateur}:{mot_de_passe}'.encode()).decode()
    return {'Authorization': 'Basic ' + jeton}


ADMIN = entete('admin', 'Admin1234!')
VENDEUR = entete('vendeur', 'Vendeur1234!')
CLIENT = entete('client', 'Client1234!')
MAUVAIS = entete('admin', 'faux-mot-de-passe')


class BaseTest(unittest.TestCase):
    def setUp(self):
        with app.app_context():
            db.drop_all()
            db.create_all()
        app.test_cli_runner().invoke(args=['seed'])   # rôles, comptes, produits de démo
        self.client = app.test_client()

    def stock(self, produit_id):
        with app.app_context():
            return db.session.get(Produit, produit_id).stock


# ======================= API : produits et catégories =======================
class TestApiCatalogue(BaseTest):
    def test_accueil_de_l_api(self):
        r = self.client.get('/api/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('GET /api/produits', r.get_json()['points_d_acces'])

    def test_liste_publique_des_produits(self):
        r = self.client.get('/api/produits')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()), 4)

    def test_recherche_et_filtre(self):
        self.assertEqual(len(self.client.get('/api/produits?q=souris').get_json()), 1)
        self.assertEqual(len(self.client.get('/api/produits?categorie=1').get_json()), 2)

    def test_detail_et_404_json(self):
        r = self.client.get('/api/produits/1')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['nom'], 'Clavier sans fil')
        r = self.client.get('/api/produits/999')
        self.assertEqual(r.status_code, 404)
        self.assertIn('erreur', r.get_json())

    def test_liste_des_categories(self):
        r = self.client.get('/api/categories')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()), 3)


class TestApiEcritureProduits(BaseTest):
    NOUVEAU = {'nom': 'Casque audio', 'description': 'Casque Bluetooth', 'prix': 89.9,
               'stock': 10, 'categorie_id': 1}

    def test_creer_sans_authentification_401(self):
        r = self.client.post('/api/produits', json=self.NOUVEAU)
        self.assertEqual(r.status_code, 401)
        self.assertIn('WWW-Authenticate', r.headers)

    def test_mauvais_mot_de_passe_401(self):
        self.assertEqual(self.client.post('/api/produits', json=self.NOUVEAU,
                                          headers=MAUVAIS).status_code, 401)

    def test_client_refuse_403(self):
        self.assertEqual(self.client.post('/api/produits', json=self.NOUVEAU,
                                          headers=CLIENT).status_code, 403)

    def test_vendeur_cree_201(self):
        r = self.client.post('/api/produits', json=self.NOUVEAU, headers=VENDEUR)
        self.assertEqual(r.status_code, 201)
        self.assertIn('/api/produits/5', r.headers['Location'])
        self.assertEqual(r.get_json()['prix'], 89.9)
        self.assertEqual(len(self.client.get('/api/produits').get_json()), 5)

    def test_validation_400(self):
        for mauvais in ({**self.NOUVEAU, 'nom': 'A'}, {**self.NOUVEAU, 'prix': -5},
                        {**self.NOUVEAU, 'prix': 'abc'}, {**self.NOUVEAU, 'stock': -1},
                        {**self.NOUVEAU, 'stock': 1.5}, {**self.NOUVEAU, 'categorie_id': 99}):
            r = self.client.post('/api/produits', json=mauvais, headers=ADMIN)
            self.assertEqual(r.status_code, 400, mauvais)
        r = self.client.post('/api/produits', data='pas du json', headers=ADMIN)
        self.assertEqual(r.status_code, 400)

    def test_patch_modifie_une_partie(self):
        r = self.client.patch('/api/produits/1', json={'prix': 50}, headers=ADMIN)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['prix'], 50.0)
        self.assertEqual(r.get_json()['nom'], 'Clavier sans fil')   # inchangé

    def test_put_exige_tous_les_champs(self):
        self.assertEqual(self.client.put('/api/produits/1', json={'prix': 50},
                                         headers=ADMIN).status_code, 400)
        r = self.client.put('/api/produits/1', json=self.NOUVEAU, headers=ADMIN)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['nom'], 'Casque audio')

    def test_supprimer_204_puis_404(self):
        self.assertEqual(self.client.delete('/api/produits/2', headers=ADMIN).status_code, 204)
        self.assertEqual(self.client.get('/api/produits/2').status_code, 404)

    def test_supprimer_produit_deja_commande_409(self):
        self.client.post('/api/commandes', json={'lignes': [{'produit_id': 1, 'quantite': 1}]},
                         headers=CLIENT)
        r = self.client.delete('/api/produits/1', headers=ADMIN)
        self.assertEqual(r.status_code, 409)

    def test_categories_creer_doublon_supprimer(self):
        r = self.client.post('/api/categories', json={'nom': 'Jardin'}, headers=ADMIN)
        self.assertEqual(r.status_code, 201)
        categorie_id = r.get_json()['id']
        self.assertEqual(self.client.post('/api/categories', json={'nom': 'jardin'},
                                          headers=ADMIN).status_code, 400)   # doublon
        self.assertEqual(self.client.delete('/api/categories/1', headers=ADMIN).status_code, 409)
        self.assertEqual(self.client.delete(f'/api/categories/{categorie_id}',
                                            headers=ADMIN).status_code, 204)


# ============================ API : commandes ============================
class TestApiCommandes(BaseTest):
    def commander(self, lignes, headers=CLIENT):
        return self.client.post('/api/commandes', json={'lignes': lignes}, headers=headers)

    def test_commandes_exigent_une_authentification(self):
        self.assertEqual(self.client.get('/api/commandes').status_code, 401)

    def test_commande_baisse_le_stock_et_calcule_le_total(self):
        r = self.commander([{'produit_id': 1, 'quantite': 2}, {'produit_id': 4, 'quantite': 3}])
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()['total'], 181.5)         # 2 x 45.90 + 3 x 29.90
        self.assertEqual(r.get_json()['statut'], 'en_attente')
        self.assertEqual((self.stock(1), self.stock(4)), (18, 0))

    def test_stock_insuffisant_409_et_rien_n_est_ecrit(self):
        r = self.commander([{'produit_id': 1, 'quantite': 2}, {'produit_id': 4, 'quantite': 9}])
        self.assertEqual(r.status_code, 409)
        self.assertEqual((self.stock(1), self.stock(4)), (20, 3))
        with app.app_context():
            self.assertEqual(Commande.query.count(), 0)

    def test_produit_inconnu_et_corps_invalide_400(self):
        self.assertEqual(self.commander([{'produit_id': 99, 'quantite': 1}]).status_code, 400)
        self.assertEqual(self.commander([]).status_code, 400)
        self.assertEqual(self.commander([{'produit_id': 1, 'quantite': 0}]).status_code, 400)
        self.assertEqual(self.commander([{'produit_id': 1, 'quantite': 'x'}]).status_code, 400)

    def test_un_client_ne_voit_que_ses_commandes(self):
        self.commander([{'produit_id': 1, 'quantite': 1}], headers=CLIENT)
        self.commander([{'produit_id': 2, 'quantite': 1}], headers=ADMIN)
        self.assertEqual(len(self.client.get('/api/commandes', headers=CLIENT).get_json()), 1)
        self.assertEqual(len(self.client.get('/api/commandes', headers=ADMIN).get_json()), 2)
        # la commande n°2 appartient à l'admin : le client n'y a pas accès
        self.assertEqual(self.client.get('/api/commandes/2', headers=CLIENT).status_code, 403)
        self.assertEqual(self.client.get('/api/commandes/2', headers=ADMIN).status_code, 200)

    def test_le_client_annule_sa_commande_et_le_stock_revient(self):
        self.commander([{'produit_id': 1, 'quantite': 2}])
        self.assertEqual(self.stock(1), 18)
        r = self.client.post('/api/commandes/1/annuler', headers=CLIENT)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['statut'], 'annulee')
        self.assertEqual(self.stock(1), 20)
        self.assertEqual(self.client.post('/api/commandes/1/annuler',
                                          headers=CLIENT).status_code, 409)

    def test_changement_de_statut_par_le_personnel(self):
        self.commander([{'produit_id': 1, 'quantite': 1}])
        corps = {'statut': 'confirmee'}
        self.assertEqual(self.client.patch('/api/commandes/1/statut', json=corps,
                                           headers=CLIENT).status_code, 403)
        r = self.client.patch('/api/commandes/1/statut', json=corps, headers=VENDEUR)
        self.assertEqual(r.get_json()['statut'], 'confirmee')
        self.assertEqual(self.client.patch('/api/commandes/1/statut', json={'statut': 'zzz'},
                                           headers=ADMIN).status_code, 400)
        # une commande confirmée n'est plus annulable par le client
        self.assertEqual(self.client.post('/api/commandes/1/annuler',
                                          headers=CLIENT).status_code, 409)

    def test_annulation_par_le_personnel_remet_le_stock(self):
        self.commander([{'produit_id': 1, 'quantite': 5}])
        self.client.patch('/api/commandes/1/statut', json={'statut': 'annulee'}, headers=ADMIN)
        self.assertEqual(self.stock(1), 20)
        r = self.client.patch('/api/commandes/1/statut', json={'statut': 'livree'}, headers=ADMIN)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.stock(1), 20)


# ====================== Site web : panier et commandes ======================
def jeton(html):
    """Retourne le jeton CSRF caché dans une page (ou '' s'il n'y en a pas)."""
    m = re.search(r'name="csrf_token"[^>]*value="([^"]*)"', html) \
        or re.search(r'value="([^"]*)"[^>]*name="csrf_token"', html)
    return m.group(1) if m else ''


def se_connecter(client, nom, mot_de_passe):
    """Connexion par le formulaire, comme dans un navigateur (jeton CSRF et champ 'next')."""
    page = client.get('/user/sign-in').data.decode()
    suivant = re.search(r'name="next"[^>]*value="([^"]*)"', page) \
        or re.search(r'value="([^"]*)"[^>]*name="next"', page)
    return client.post('/user/sign-in', follow_redirects=True, data={
        'csrf_token': jeton(page), 'username': nom, 'password': mot_de_passe,
        'next': suivant.group(1) if suivant else '/', 'reg_next': '/'})


class TestPanierWeb(BaseTest):
    def test_panier_stock_limite_et_connexion_pour_commander(self):
        self.client.post('/panier/ajouter/4', data={'quantite': 5})      # il n'en reste que 3
        with self.client.session_transaction() as s:
            self.assertEqual(s['panier'], {'4': 3})
        r = self.client.post('/commander')                                # pas connecté
        self.assertEqual(r.status_code, 302)
        self.assertIn('sign-in', r.headers['Location'])

    def test_commande_complete_puis_annulation(self):
        self.client.post('/panier/ajouter/1', data={'quantite': 2})
        se_connecter(self.client, 'client', 'Client1234!')                # le panier est gardé
        r = self.client.post('/commander', follow_redirects=True)
        self.assertIn('Commande enregistr'.encode(), r.data)
        self.assertEqual(self.stock(1), 18)
        self.assertIn(b'En attente', self.client.get('/mes-commandes').data)
        r = self.client.post('/commande/1/annuler', follow_redirects=True)
        self.assertIn(b'Commande annul', r.data)
        self.assertEqual(self.stock(1), 20)

    def test_page_de_gestion_interdite_au_client(self):
        se_connecter(self.client, 'client', 'Client1234!')
        r = self.client.get('/gestion/commandes')
        self.assertIn(r.status_code, (302, 403))
        self.assertNotIn(b'Gestion des commandes', r.data)

    def test_admin_gere_les_commandes(self):
        self.commande_api = app.test_client().post(
            '/api/commandes', json={'lignes': [{'produit_id': 3, 'quantite': 2}]}, headers=CLIENT)
        se_connecter(self.client, 'admin', 'Admin1234!')
        self.assertEqual(self.client.get('/gestion/commandes').status_code, 200)
        r = self.client.post('/gestion/commandes/1/statut', data={'statut': 'livree'},
                             follow_redirects=True)
        self.assertIn('Statut mis à jour'.encode(), r.data)


# ====================== Panneau d'administration (Flask-Admin) ======================
class TestAdmin(BaseTest):
    def setUp(self):
        super().setUp()
        app.config['WTF_CSRF_ENABLED'] = True        # ici on teste aussi la protection CSRF

    def tearDown(self):
        app.config['WTF_CSRF_ENABLED'] = False

    def admin(self):
        navigateur = app.test_client()
        se_connecter(navigateur, 'admin', 'Admin1234!')
        return navigateur

    def formulaire(self, navigateur, adresse, **champs):
        """Ouvre un formulaire pour récupérer son jeton CSRF, puis l'envoie."""
        jeton_csrf = jeton(navigateur.get(adresse).data.decode())
        return navigateur.post(adresse, data={'csrf_token': jeton_csrf, **champs})

    def test_acces_reserve_au_role_admin(self):
        self.assertEqual(self.client.get('/admin/').status_code, 302)          # pas connecté
        for nom, mot_de_passe in (('client', 'Client1234!'), ('vendeur', 'Vendeur1234!')):
            navigateur = app.test_client()
            se_connecter(navigateur, nom, mot_de_passe)
            self.assertEqual(navigateur.get('/admin/').status_code, 403, nom)
            self.assertEqual(navigateur.get('/admin/produit/').status_code, 403, nom)

    def test_pages_de_l_admin(self):
        navigateur = self.admin()
        for adresse in ('/admin/', '/admin/produit/', '/admin/categorie/', '/admin/commande/',
                        '/admin/user/', '/admin/produit/?search=clavier'):
            self.assertEqual(navigateur.get(adresse).status_code, 200, adresse)

    def test_creer_modifier_supprimer_un_produit(self):
        navigateur = self.admin()
        valeurs = dict(nom='Casque audio', description='Bluetooth', prix='89.90', stock='10',
                       categorie='1')
        r = self.formulaire(navigateur, '/admin/produit/new/', **valeurs)
        self.assertEqual(r.status_code, 302)
        with app.app_context():
            self.assertEqual(Produit.query.filter_by(nom='Casque audio').count(), 1)
        valeurs['stock'] = '7'
        self.formulaire(navigateur, '/admin/produit/edit/?id=5', **valeurs)
        self.assertEqual(self.stock(5), 7)
        jeton_csrf = jeton(navigateur.get('/admin/produit/').data.decode())
        navigateur.post('/admin/produit/delete/', data={
            'csrf_token': jeton_csrf, 'id': '5', 'url': '/admin/produit/'})
        with app.app_context():
            self.assertIsNone(db.session.get(Produit, 5))

    def test_prix_negatif_refuse(self):
        r = self.formulaire(self.admin(), '/admin/produit/new/', nom='Mauvais', description='',
                            prix='-3', stock='1', categorie='1')
        self.assertEqual(r.status_code, 200)         # le formulaire est ré-affiché avec l'erreur
        with app.app_context():
            self.assertEqual(Produit.query.count(), 4)

    def test_formulaire_sans_jeton_csrf_refuse(self):
        r = self.admin().post('/admin/produit/new/', data={
            'nom': 'SansJeton', 'prix': '5', 'stock': '1', 'categorie': '1'})
        self.assertEqual(r.status_code, 400)
        with app.app_context():
            self.assertEqual(Produit.query.count(), 4)

    def test_un_produit_deja_commande_ne_se_supprime_pas(self):
        app.test_client().post('/api/commandes', headers=CLIENT,
                               json={'lignes': [{'produit_id': 1, 'quantite': 1}]})
        navigateur = self.admin()
        jeton_csrf = jeton(navigateur.get('/admin/produit/').data.decode())
        r = navigateur.post('/admin/produit/delete/', follow_redirects=True, data={
            'csrf_token': jeton_csrf, 'id': '1', 'url': '/admin/produit/'})
        self.assertIn('figure dans des commandes'.encode(), r.data)    # message clair
        with app.app_context():
            self.assertIsNotNone(db.session.get(Produit, 1))

    def test_categories_vide_supprimable_pleine_protegee(self):
        navigateur = self.admin()
        self.formulaire(navigateur, '/admin/categorie/new/', nom='Jardin')       # id 4, vide
        jeton_csrf = jeton(navigateur.get('/admin/categorie/').data.decode())
        r = navigateur.post('/admin/categorie/delete/', follow_redirects=True, data={
            'csrf_token': jeton_csrf, 'id': '1', 'url': '/admin/categorie/'})   # Informatique
        self.assertIn('contient des produits'.encode(), r.data)
        navigateur.post('/admin/categorie/delete/', data={
            'csrf_token': jeton_csrf, 'id': '4', 'url': '/admin/categorie/'})
        with app.app_context():
            self.assertIsNotNone(db.session.get(Categorie, 1))
            self.assertIsNone(db.session.get(Categorie, 4))

    def test_les_commandes_sont_en_lecture_seule(self):
        app.test_client().post('/api/commandes', headers=CLIENT,
                               json={'lignes': [{'produit_id': 1, 'quantite': 2}]})
        navigateur = self.admin()
        self.assertEqual(navigateur.get('/admin/commande/new/').status_code, 302)
        self.assertEqual(navigateur.get('/admin/commande/edit/?id=1').status_code, 302)
        detail = navigateur.get('/admin/commande/details/?id=1')
        self.assertEqual(detail.status_code, 200)
        self.assertIn('Clavier sans fil'.encode(), detail.data)

    def test_un_admin_ne_peut_pas_se_retirer_son_acces(self):
        navigateur = self.admin()
        r = self.formulaire(navigateur, '/admin/user/edit/?id=1', username='admin',
                            email='admin@boutique.tn', active='y', roles='2')   # rôle vendeur seul
        self.assertEqual(r.status_code, 200)
        with app.app_context():
            from models import User
            self.assertTrue(db.session.get(User, 1).has_roles('admin'))


if __name__ == '__main__':
    unittest.main()
    unittest.main()