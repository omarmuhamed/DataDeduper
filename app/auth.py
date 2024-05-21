from datetime import timedelta
from flask import Blueprint, render_template, redirect, url_for, flash
from werkzeug.security import check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from .models import User
from .form_validators import LoginForm


auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['POST', 'GET'])
def login():
    """
    Handles the login process for users.

    This route supports both GET and POST requests. For GET requests, it displays the login page with the login form. For POST requests, it processes the form data to authenticate the user. If authentication is successful, the user is logged in and redirected to the home page. Otherwise, appropriate error messages are flashed to the user.

    Args:
        None

    Returns:
        - The login page with the LoginForm for GET requests or if authentication fails.
        - A redirection to the 'main.home' page upon successful authentication.
        - A redirection to the 'main.home' page if the user is already authenticated.

    Notes:
        - The function checks if the user is already authenticated and redirects to the main page if so.
        - On successful login, the user is redirected to the home page or a specified 'next' page if provided in the form.
        - Error messages are provided for invalid login attempts or missing form fields.
        - The function uses Flask's `flash` function to provide feedback messages to the user.
    """
    if current_user.is_authenticated:
        # Redirect the user to the main home page if they are already logged in
        return redirect(url_for('main.home'))

    form = LoginForm()  # Instantiate the login form

    if form.validate_on_submit():
        # Form validation passed, attempt to authenticate the user
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            # User exists and password is correct, log the user in
            login_user(user, remember=form.remember.data, duration=timedelta(days=7) if form.remember.data else None)
            next_page = form.next.data or url_for('main.home')
            return redirect(next_page)
        flash('Invalid username or password.')  # Flash a message for invalid credentials

    if form.errors:
        # Handle form errors, specifically missing username or password
        k = list(form.errors.keys())[0]
        if k == 'username':
            flash('Username is required!')
        elif k == 'password':
            flash('Password is required!')

    return render_template('login.html', form=form)  # Render the login page with the form


@auth.route('/logout', methods=['POST'])
@login_required
def logout():
    """
    Handles the logout process for users.

    This route logs out the current user and redirects them to the home page. It requires that the user be authenticated to access this route (ensured by the @login_required decorator). The function uses the POST method to log out users, following best practices for logout functionality that changes the server state.

    Args:
        None

    Returns:
        A redirection to the 'main.home' page after logging out the user.

    Notes:
        - The route is protected by the @login_required decorator, ensuring that only authenticated users can access the logout functionality.
        - Using the POST method for the logout action aligns with security best practices, preventing CSRF attacks and ensuring that the logout action is intentional.
    """
    logout_user()  # Log out the current user
    return redirect(url_for('main.home'))  # Redirect to the home page after logout
