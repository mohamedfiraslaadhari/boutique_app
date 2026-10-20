"""Formulaires Flask-WTF avec validation."""
from decimal import Decimal

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (DecimalField, IntegerField, SelectField, StringField,
                     SubmitField, TextAreaField)
from wtforms.validators import (DataRequired, InputRequired, Length, NumberRange,
                                Optional, ValidationError)

from extensions import db, photos
from models import Categorie


class CategorieForm(FlaskForm):
    nom = StringField('Nom de la catégorie', validators=[
        DataRequired(message='Champ obligatoire'),
        Length(min=2, max=80, message='Entre 2 et 80 caractères')])
    submit = SubmitField('Ajouter la catégorie')

    def validate_nom(self, champ):
        """Refuse une catégorie qui existe déjà (sans tenir compte des majuscules)."""
        existe = Categorie.query.filter(
            db.func.lower(Categorie.nom) == champ.data.strip().lower()).first()
        if existe:
            raise ValidationError('Cette catégorie existe déjà')


class ProduitForm(FlaskForm):
    nom = StringField('Nom du produit', validators=[
        DataRequired(message='Champ obligatoire'),
        Length(min=2, max=100, message='Entre 2 et 100 caractères')])
    description = TextAreaField('Description (facultatif)', validators=[
        Optional(), Length(max=2000, message='2000 caractères maximum')])
    prix = DecimalField('Prix (DT)', places=2, validators=[
        InputRequired(message='Prix obligatoire'),
        NumberRange(min=Decimal('0.01'), max=Decimal('1000000'),
                    message='Le prix doit être supérieur à 0')])
    stock = IntegerField('Quantité en stock', validators=[
        InputRequired(message='Stock obligatoire'),
        NumberRange(min=0, max=100000, message='Le stock ne peut pas être négatif')])
    categorie_id = SelectField('Catégorie', coerce=int, validators=[
        InputRequired(message='Choisissez une catégorie')])
    photo = FileField('Photo (facultatif)', validators=[
        FileAllowed(photos, 'Images uniquement (jpg, png, gif, webp)')])
    submit = SubmitField('Enregistrer')
