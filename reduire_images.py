"""Réduit les images de static/demo : 1200 pixels de large au maximum, qualité 85.

Lancement :   python reduire_images.py
(nécessite Pillow : pip install Pillow)
Les fichiers déjà légers (moins de 500 Ko et moins de 1200 pixels de large) ne sont pas touchés.
"""
import io
from pathlib import Path

from PIL import Image, ImageOps

DOSSIER = Path(__file__).resolve().parent / 'static' / 'demo'
LARGEUR_MAX = 1200
TAILLE_MAX = 500 * 1024

for chemin in sorted(DOSSIER.iterdir()):
    extension = chemin.suffix.lower()
    if extension not in ('.jpg', '.jpeg', '.png', '.webp'):
        continue
    avant = chemin.stat().st_size
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(chemin.read_bytes())))
    if avant <= TAILLE_MAX and image.width <= LARGEUR_MAX:
        print(f'{chemin.name} : déjà léger ({avant // 1024} Ko), inchangé')
        continue
    if image.width > LARGEUR_MAX:
        hauteur = round(image.height * LARGEUR_MAX / image.width)
        image = image.resize((LARGEUR_MAX, hauteur), Image.LANCZOS)
    if extension in ('.jpg', '.jpeg'):
        image.convert('RGB').save(chemin, 'JPEG', quality=85, optimize=True)
    elif extension == '.png':
        image.save(chemin, 'PNG', optimize=True)
    else:
        image.save(chemin, 'WEBP', quality=85)
    print(f'{chemin.name} : {avant // 1024} Ko -> {chemin.stat().st_size // 1024} Ko')