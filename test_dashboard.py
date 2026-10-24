"""Tests du tableau de bord (chiffres du stock et des ventes).

Lancement :   python -m unittest -v
(ce fichier réutilise la base de test SQLite de test_boutique.py)
"""
import unittest

import test_boutique as base
from dashboard import calculer_statistiques
from test_boutique import ADMIN, CLIENT, app, se_connecter


class TestTableauDeBord(base.BaseTest):
    def commander(self, lignes, headers=CLIENT):
        return app.test_client().post('/api/commandes', json={'lignes': lignes}, headers=headers)

    def test_reserve_au_personnel(self):
        self.assertEqual(self.client.get('/tableau-de-bord').status_code, 302)   # pas connecté
        navigateur = app.test_client()
        se_connecter(navigateur, 'client', 'Client1234!')
        refus = navigateur.get('/tableau-de-bord')
        self.assertIn(refus.status_code, (302, 403))
        self.assertNotIn("Chiffre d'affaires".encode(), refus.data)
        for nom, mot_de_passe in (('vendeur', 'Vendeur1234!'), ('admin', 'Admin1234!')):
            navigateur = app.test_client()
            se_connecter(navigateur, nom, mot_de_passe)
            self.assertEqual(navigateur.get('/tableau-de-bord').status_code, 200, nom)

    def statistiques(self):
        with app.app_context():
            return calculer_statistiques()

    def test_chiffres_sans_commande(self):
        stats = self.statistiques()
        self.assertEqual(stats['nb_produits'], 4)
        self.assertEqual(stats['chiffre_affaires'], 0)
        self.assertEqual(stats['panier_moyen'], 0)
        self.assertEqual(stats['top_produits'], [])
        self.assertEqual([p.nom for p in stats['stock_bas']], ['Ballon de football'])  # 3 en stock

    def test_chiffres_apres_commandes_et_annulation(self):
        self.commander([{'produit_id': 1, 'quantite': 2}, {'produit_id': 2, 'quantite': 1}])
        self.commander([{'produit_id': 3, 'quantite': 1}], headers=ADMIN)
        self.client.post('/api/commandes/2/annuler', headers=ADMIN)       # la 2e est annulée
        stats = self.statistiques()
        self.assertEqual(stats['nb_commandes'], 1)
        self.assertEqual(stats['nb_annulees'], 1)
        self.assertAlmostEqual(stats['chiffre_affaires'], 2 * 45.90 + 19.50)   # 111.30
        self.assertAlmostEqual(stats['panier_moyen'], 111.30)
        self.assertEqual(stats['top_produits'][0]['nom'], 'Clavier sans fil')
        self.assertEqual(stats['top_produits'][0]['quantite'], 2)
        self.assertAlmostEqual(stats['ventes_7_jours'][-1]['montant'], 111.30)  # aujourd'hui
        statuts = {s['code']: s['nombre'] for s in stats['par_statut']}
        self.assertEqual((statuts['en_attente'], statuts['annulee']), (1, 1))

    def test_stock_bas_apres_une_vente(self):
        self.commander([{'produit_id': 3, 'quantite': 8}])                # lampe : 12 -> 4
        noms = [p.nom for p in self.statistiques()['stock_bas']]
        self.assertEqual(noms, ['Ballon de football', 'Lampe de bureau'])

    def test_pages_affichees(self):
        self.commander([{'produit_id': 1, 'quantite': 1}])
        navigateur = app.test_client()
        se_connecter(navigateur, 'admin', 'Admin1234!')
        page = navigateur.get('/tableau-de-bord')
        self.assertIn("Chiffre d'affaires".encode(), page.data)
        self.assertIn('Ballon de football'.encode(), page.data)             # stock bas
        accueil = navigateur.get('/admin/')
        self.assertEqual(accueil.status_code, 200)
        self.assertIn('Tableau de bord'.encode(), accueil.data)


if __name__ == '__main__':
    unittest.main()