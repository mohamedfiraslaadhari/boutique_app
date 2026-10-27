"""Protections de sécurité : en-têtes HTTP et limitation des tentatives de connexion.

- Après 10 échecs de connexion (site ou API) en 5 minutes, la même adresse IP reçoit
  une erreur 429 « Too Many Requests » pendant le reste de la fenêtre.
- Chaque réponse porte des en-têtes qui limitent les attaques courantes.
"""
import time
from collections import defaultdict, deque

from flask import jsonify, request

FENETRE = 300        # durée de la fenêtre, en secondes (5 minutes)
MAX_ECHECS = 10      # échecs de connexion autorisés par adresse IP dans la fenêtre

_echecs = defaultdict(deque)        # adresse IP -> instants des échecs récents


def _echecs_recents(ip):
    maintenant = time.monotonic()
    instants = _echecs[ip]
    while instants and maintenant - instants[0] > FENETRE:
        instants.popleft()
    return instants


def trop_d_echecs(ip):
    return len(_echecs_recents(ip)) >= MAX_ECHECS


def noter_echec(ip):
    _echecs_recents(ip).append(time.monotonic())


def oublier(ip):
    _echecs.pop(ip, None)


def reinitialiser():
    """Efface tous les compteurs (utile pour les tests)."""
    _echecs.clear()


def est_une_connexion():
    """Vrai pour le formulaire de connexion du site ou pour une requête d'API authentifiée."""
    if request.method == 'POST' and request.path == '/user/sign-in':
        return True
    return request.path.startswith('/api/') and request.authorization is not None


def init_securite(app):
    @app.before_request
    def limiter_les_tentatives():
        if est_une_connexion() and trop_d_echecs(request.remote_addr):
            message = 'Trop de tentatives de connexion. Réessayez dans quelques minutes.'
            if request.path.startswith('/api/'):
                reponse = jsonify({'erreur': message})
            else:
                reponse = app.response_class(message, mimetype='text/plain')
            reponse.status_code = 429
            reponse.headers['Retry-After'] = str(FENETRE)
            return reponse

    @app.after_request
    def surveiller_et_proteger(reponse):
        # --- Comptage des échecs de connexion ---
        if request.method == 'POST' and request.path == '/user/sign-in':
            if reponse.status_code == 200:            # le formulaire est ré-affiché : échec
                noter_echec(request.remote_addr)
            elif reponse.status_code in (302, 303):   # connexion réussie
                oublier(request.remote_addr)
        elif (request.path.startswith('/api/') and request.authorization is not None
              and reponse.status_code == 401):
            noter_echec(request.remote_addr)

        # --- En-têtes de sécurité ---
        reponse.headers.setdefault('X-Content-Type-Options', 'nosniff')
        reponse.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        reponse.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        reponse.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        return reponse