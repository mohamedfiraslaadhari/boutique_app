"""Configuration de l'application Boutique."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Lit le fichier .env (jamais envoyé sur GitHub : il contient le mot de passe)
load_dotenv(BASE_DIR / '.env', override=True)

# --- Paramètres PostgreSQL ---
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'YOUR_PASSWORD')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'boutique')


class Config:
    # DATABASE_URL (facultatif) permet de remplacer la base, par exemple pour des tests
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL') or (
        f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Clé secrète : signe les sessions et les formulaires (CSRF). Elle vient du fichier .env
    # (jamais écrite dans le code). Sans clé dans .env, on en invente une au hasard : le site
    # fonctionne, mais les connexions sont perdues à chaque redémarrage.
    SECRET_KEY = os.getenv('SECRET_KEY') or secrets.token_hex(32)

    # --- Cookies de session ---
    SESSION_COOKIE_HTTPONLY = True          # inaccessible au JavaScript de la page
    SESSION_COOKIE_SAMESITE = 'Lax'         # non envoyé par les sites tiers (limite le CSRF)
    SESSION_COOKIE_SECURE = os.getenv('HTTPS') == '1'      # HTTPS = 1 dans .env en production
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = os.getenv('HTTPS') == '1'

    # --- Téléchargement des photos (Flask-Uploads / Flask-Reuploaded) ---
    UPLOADED_PHOTOS_DEST = str(BASE_DIR / 'static' / 'uploads')
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024   # 2 Mo maximum par fichier

    # --- Flask-User (connexion, inscription, rôles) ---
    USER_APP_NAME = 'Boutique'
    USER_ENABLE_EMAIL = False              # pas de serveur d'e-mails pour ce projet
    USER_ENABLE_USERNAME = True            # connexion avec un nom d'utilisateur
    USER_ENABLE_CONFIRM_EMAIL = False
    USER_ENABLE_FORGOT_PASSWORD = False
    USER_REQUIRE_RETYPE_PASSWORD = True
    USER_AUTO_LOGIN_AFTER_REGISTER = True
    USER_PASSLIB_CRYPTCONTEXT_SCHEMES = ['pbkdf2_sha256']   # hachage des mots de passe
    USER_AFTER_LOGIN_ENDPOINT = 'shop.catalogue'
    USER_AFTER_LOGOUT_ENDPOINT = 'shop.catalogue'
    USER_AFTER_REGISTER_ENDPOINT = 'shop.catalogue'
    USER_AFTER_CONFIRM_ENDPOINT = 'shop.catalogue'