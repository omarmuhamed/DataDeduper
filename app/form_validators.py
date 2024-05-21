from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired


class LoginForm(FlaskForm):
    """
    A form class for user login, using Flask-WTF.

    This form is designed to capture the necessary fields for a user login process, including username, password,
    and an optional 'remember me' feature for sessions persistence. Additionally, it includes a field to redirect
    the user to a next page after successful login, improving user experience by taking them directly to their
    intended destination.

    Attributes:
        username (StringField): Input field for the username. This field is required.
        password (PasswordField): Input field for the password. This field is required.
        remember (BooleanField): Checkbox to allow the user to stay logged in across sessions.
        next (StringField): Hidden field to store the URL to redirect to after login.
        submit (SubmitField): Button to submit the form.

    Usage:
        To use this form in a Flask view, instantiate it and pass it to your template. In the template, you can render
        the form fields and handle form submission. Upon submission, validate the form in your view and perform the
        login logic.
    """
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    next = StringField('Next')
    submit = SubmitField('Login')
