"""Tests des images de produits (images de démonstration et envoi par formulaire).

Lancement :   python -m unittest -v
"""
import io
import os
import re
import unittest

import test_boutique as base
from app import PHOTOS_DEMO, trouver_image_demo
from extensions import db
from models import Produit
from test_boutique import app, se_connecter

# Un minuscule fichier PNG valide (1 pixel) pour tester l'envoi d'une photo
PNG_1_PIXEL = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
    '0000000d4944415478da63f8ffff3f0005fe02fea7d6c3a50000000049454e44ae426082')


def est_une_image(debut):
    """Reconnaît JPEG, PNG et WebP d'après les premiers octets du fichier."""
    return (debut.startswith(b'\xff\xd8\xff')                       # JPEG
            or debut.startswith(b'\x89PNG\r\n\x1a\n')               # PNG
            or (debut[:4] == b'RIFF' and debut[8:12] == b'WEBP'))   # WebP


class TestImagesProduits(base.BaseTest):
    def produits(self):
        with app.app_context():
            return [(p.nom, p.photo) for p in Produit.query.order_by(Produit.id).all()]

    def test_les_4_images_de_demonstration_sont_presentes_et_valides(self):
        for nom_fichier in PHOTOS_DEMO.values():
            chemin = trouver_image_demo(nom_fichier)
            self.assertIsNotNone(chemin, f'Image introuvable : static/demo/{nom_fichier}.jpg')
            with open(chemin, 'rb') as f:
                self.assertTrue(est_une_image(f.read(12)), f'{chemin.name} n\'est pas une image')
            self.assertLess(chemin.stat().st_size, 2 * 1024 * 1024, f'{chemin.name} dépasse 2 Mo')

    def test_le_seed_donne_une_image_a_chaque_produit(self):
        for nom, photo in self.produits():
            self.assertIsNotNone(photo, nom)
            self.assertTrue(os.path.isfile(os.path.join(app.config['UPLOADED_PHOTOS_DEST'], photo)))

    def test_relancer_le_seed_ne_change_pas_les_photos(self):
        avant = self.produits()
        resultat = app.test_cli_runner().invoke(args=['seed'])
        self.assertIn('0 image(s)', resultat.output)
        self.assertEqual(self.produits(), avant)

    def test_le_catalogue_et_la_fiche_affichent_les_images(self):
        page = self.client.get('/').data.decode()
        self.assertEqual(len(re.findall(r'<img [^>]*static/uploads/', page)), 4)
        self.assertNotIn('Pas de photo', page)
        self.assertIn('static/uploads/', self.client.get('/produit/1').data.decode())

    def test_un_produit_sans_photo_affiche_le_texte_de_remplacement(self):
        with app.app_context():
            db.session.get(Produit, 1).photo = None
            db.session.commit()
        self.assertEqual(self.client.get('/').data.decode().count('Pas de photo'), 1)

    def envoyer(self, navigateur, fichier, nom_fichier):
        return navigateur.post('/gestion/produits/ajouter', content_type='multipart/form-data',
                               follow_redirects=True, data={
            'nom': 'Casque audio', 'description': '', 'prix': '89.90', 'stock': '10',
            'categorie_id': '1', 'photo': (io.BytesIO(fichier), nom_fichier)})

    def test_envoi_d_une_photo_par_le_formulaire(self):
        navigateur = app.test_client()
        se_connecter(navigateur, 'vendeur', 'Vendeur1234!')
        r = self.envoyer(navigateur, PNG_1_PIXEL, 'casque.png')
        self.assertIn('Produit ajouté'.encode(), r.data)
        photo = dict(self.produits())['Casque audio']
        self.assertTrue(photo.endswith('.png'))
        self.assertNotIn('casque', photo)                    # le nom envoyé n'est pas gardé
        self.assertTrue(os.path.isfile(os.path.join(app.config['UPLOADED_PHOTOS_DEST'], photo)))

    def test_les_fichiers_qui_ne_sont_pas_des_images_sont_refuses(self):
        navigateur = app.test_client()
        se_connecter(navigateur, 'vendeur', 'Vendeur1234!')
        for contenu, nom in ((b'<svg xmlns="http://www.w3.org/2000/svg"/>', 'x.svg'),
                             (b'print("pirate")', 'script.py'), (b'texte', 'notes.txt')):
            r = self.envoyer(navigateur, contenu, nom)
            self.assertNotIn('Produit ajouté'.encode(), r.data, nom)
        self.assertNotIn('Casque audio', dict(self.produits()))


if __name__ == '__main__':
    unittest.main()