"""Tests de sécurité : en-têtes HTTP, cookies, clé secrète et limitation des connexions.

Lancement :   python -m unittest -v
"""
import os
import unittest

import securite
import test_boutique as base
from test_boutique import ADMIN, CLIENT, MAUVAIS, app, jeton, se_connecter

DOSSIER_PROJET = os.path.dirname(os.path.abspath(__file__))


class TestSecurite(base.BaseTest):
    def setUp(self):
        super().setUp()
        securite.reinitialiser()          # on repart de zéro : aucun échec noté

    def tearDown(self):
        securite.reinitialiser()

    def mauvaise_connexion(self):
        page = self.client.get('/user/sign-in').data.decode()
        return self.client.post('/user/sign-in', data={
            'csrf_token': jeton(page), 'username': 'admin', 'password': 'mauvais-mot-de-passe',
            'next': '/', 'reg_next': '/'})

    def test_en_tetes_de_securite_sur_toutes_les_pages(self):
        for adresse in ('/', '/api/', '/user/sign-in'):
            reponse = self.client.get(adresse)
            self.assertEqual(reponse.headers['X-Content-Type-Options'], 'nosniff', adresse)
            self.assertEqual(reponse.headers['X-Frame-Options'], 'SAMEORIGIN', adresse)
            self.assertIn('Referrer-Policy', reponse.headers, adresse)
            self.assertIn('Permissions-Policy', reponse.headers, adresse)

    def test_le_cookie_de_session_est_protege(self):
        page = self.client.get('/user/sign-in').data.decode()
        reponse = self.client.post('/user/sign-in', data={
            'csrf_token': jeton(page), 'username': 'client', 'password': 'Client1234!',
            'next': '/', 'reg_next': '/'})
        cookies = [c for c in reponse.headers.getlist('Set-Cookie') if c.startswith('session=')]
        self.assertTrue(cookies)
        self.assertIn('HttpOnly', cookies[0])
        self.assertIn('SameSite=Lax', cookies[0])

    def test_la_cle_secrete_n_est_pas_ecrite_dans_le_code(self):
        with open(os.path.join(DOSSIER_PROJET, 'config.py'), encoding='utf-8') as f:
            self.assertNotIn('changez-moi', f.read())
        self.assertGreaterEqual(len(app.config['SECRET_KEY']), 32)

    def test_le_fichier_env_n_est_pas_suivi_par_git(self):
        with open(os.path.join(DOSSIER_PROJET, '.gitignore'), encoding='utf-8') as f:
            lignes = [ligne.strip() for ligne in f]
        self.assertIn('.env', lignes)

    def test_blocage_apres_10_echecs_de_connexion_sur_le_site(self):
        for _ in range(securite.MAX_ECHECS):
            self.assertEqual(self.mauvaise_connexion().status_code, 200)
        bloque = self.mauvaise_connexion()
        self.assertEqual(bloque.status_code, 429)
        self.assertIn('Retry-After', bloque.headers)
        # même avec le bon mot de passe, l'adresse reste bloquée un moment
        self.assertEqual(se_connecter(self.client, 'client', 'Client1234!').status_code, 429)
        # les pages publiques restent accessibles
        self.assertEqual(self.client.get('/').status_code, 200)
        securite.reinitialiser()
        self.assertIn(b'Bonjour', se_connecter(self.client, 'client', 'Client1234!').data)

    def test_une_connexion_reussie_remet_le_compteur_a_zero(self):
        for _ in range(5):
            self.mauvaise_connexion()
        se_connecter(self.client, 'client', 'Client1234!')
        self.client.get('/user/sign-out')
        for _ in range(securite.MAX_ECHECS - 1):
            self.assertEqual(self.mauvaise_connexion().status_code, 200)

    def test_blocage_apres_10_echecs_sur_l_api(self):
        for _ in range(securite.MAX_ECHECS):
            self.assertEqual(self.client.get('/api/commandes', headers=MAUVAIS).status_code, 401)
        bloque = self.client.get('/api/commandes', headers=ADMIN)       # bon mot de passe
        self.assertEqual(bloque.status_code, 429)
        self.assertIn('erreur', bloque.get_json())

    def test_les_requetes_sans_mot_de_passe_ne_comptent_pas(self):
        for _ in range(30):
            self.assertEqual(self.client.get('/api/commandes').status_code, 401)
        self.assertEqual(self.client.get('/api/commandes', headers=CLIENT).status_code, 200)


if __name__ == '__main__':
    unittest.main()