"""Objets partagés, créés sans application pour éviter les imports circulaires."""
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_uploads import UploadSet
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()

# Ensemble d'envois "photos". On autorise seulement des images "sûres" (pas de SVG,
# qui peut contenir du code exécutable).
photos = UploadSet('photos', ('jpg', 'jpeg', 'png', 'gif', 'webp'))
