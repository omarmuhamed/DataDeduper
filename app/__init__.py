from flask import Flask, request, redirect, session, render_template, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user, login_required
from .utils import MySignallingSession
from .constants import DB_USER, DB_PORT, DB_SERVER, DB_PASSWORD

# Initialize the SQLAlchemy extension with custom session options
#db = SQLAlchemy(session_options={"class_": MySignallingSession})
db = SQLAlchemy()


def create_app():
    """
    Creates and configures the Flask application, setting up the database, login manager, and application routes.

    This function initializes the Flask application with a secret key, database URIs (including binds for multiple databases), and debug mode. It sets up the SQLAlchemy database connection with custom session options to use MySignallingSession for database operations. The function also configures the Flask-Login extension for handling user authentication and session management.

    Routes for the application are defined within this function, including error handlers and a route for database selection. Additionally, it registers blueprints for modularizing authentication, search functionality, and administrative interfaces.

    Returns:
        Flask: The Flask application instance.
    """

    app = Flask(__name__)

    # Application configuration
    app.config['SECRET_KEY'] = "SECRET"
    app.config[
        'SQLALCHEMY_DATABASE_URI'] = f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}:{DB_PORT}/postgres'
    '''
    app.config['SQLALCHEMY_BINDS'] = {
        'db1': f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}:{DB_PORT}/bulkdata1',
        'db2': f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}:{DB_PORT}/bulkdata2',
        'db3': f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}:{DB_PORT}/bulkdata3'
    }
    '''

    app.config['DEBUG'] = True

    # Initialize SQLAlchemy with the app
    db.init_app(app)

    # Set up the login manager
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    # Route for database selection
    @app.route('/selectdb', methods=['GET'])
    @login_required
    def select_db():
        """Allows a logged-in user to select a database for their session."""
        try:
            sdb = request.args.get('db', str(current_user.dbs[0]))
            if int(sdb) in current_user.dbs:
                session["db"] = str(sdb)
            else:
                abort(404)
            return redirect(request.referrer)
        except:
            abort(500)

    # Error handlers
    @app.errorhandler(403)
    def access_403(e):
        """Renders a custom 403 Forbidden error page."""
        return render_template('403.html'), 403

    @app.errorhandler(404)
    def error_404(e):
        """Renders a custom 404 Not Found error page."""
        return render_template('404.html'), 404

    @app.errorhandler(423)
    def error_202(e):
        """Renders a custom 423 Locked error page."""
        return render_template('202.html'), 423

    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        """Defines how to load a user from the database."""
        from .models import User  # Importing here to avoid circular dependencies
        return User.query.get(int(user_id))

    # Register application blueprints for modularization
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .search import search as search_blueprint
    app.register_blueprint(search_blueprint)

    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .admins import admins as admins_blueprint
    app.register_blueprint(admins_blueprint)

    return app