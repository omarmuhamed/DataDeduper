from flask_login import UserMixin, current_user
from sqlalchemy.ext.hybrid import hybrid_property
from flask import session, abort
from . import db
from .data_structure import column_specs

'''
class Data(db.Model):
    """
    Data model for storing detailed contact information along with data batch details.

    This model captures individual contact details provided by data batch suppliers, including personal information and contact details. It also includes fields for managing and tracking the data batch itself, such as the batch source and SMS delivery status.

    Attributes:
        id (Integer): A unique identifier for each record, serving as the primary key.
        supplier_name (String): Name of the data batch supplier.
        phone_number (String): Contact phone number of the individual.
        firstname (String): First name of the contact person.
        lastname (String): Last name of the contact person.
        address (Text): Full address of the contact person.
        dob (String): Date of birth of the contact person.
        email (Text): Email address of the contact person.
        bsc (String): Batch Source Code, indicating the source of the data batch.
        postcode (String): Postal code of the contact person's address.
        delivery_stat (String): SMS delivery status, indicating the status of SMS delivery for the batch.
        title (String): Title of the contact person (e.g., Mr, Mrs, Dr).
        city (Text): City of the contact person's address.

    Notes:
        - The `__bind_key__` attribute is set to '__all__', indicating that this model should be available across all database binds if multiple databases are used.
        - The model is structured to facilitate comprehensive data management for contact information sourced from various suppliers, accommodating a range of data completeness scenarios.
    """

    __tablename__ = 'data'
    __bind_key__ = '__all__'

    id = db.Column(db.Integer, primary_key=True, nullable=False)
    supplier_name = db.Column(db.String(50), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    firstname = db.Column(db.String(50))
    lastname = db.Column(db.String(50))
    address = db.Column(db.Text)
    dob = db.Column(db.String(20))
    email = db.Column(db.Text)
    bsc = db.Column(db.String(10))
    postcode = db.Column(db.String(10))
    delivery_stat = db.Column(db.String(10))
    title = db.Column(db.String(10))
    city = db.Column(db.Text)
'''


def create_dynamic_model(table_name, columns, bind_key=None, base=db.Model):
    """
    Dynamically creates a SQLAlchemy model with the given table name, columns, and base class.

    Parameters:
    - table_name (str): Name of the table.
    - columns (dict): Dictionary where keys are column names and values are dictionaries containing
                      the column's SQLAlchemy type under 'type', additional specifications under 'specs',
                      and optionally a 'label' for CSV operations.
    - base (db.Model): Base class for the model, typically `db.Model` from Flask-SQLAlchemy.

    Returns:
    - A dynamically created SQLAlchemy model class.
    """
    attrs = {'__tablename__': table_name, '__bind_key__': bind_key, '_column_labels': {}}
    for column_name, config in columns.items():
        column_type = config['type']
        column_specs = config.get('specs', {})
        column_label = config.get('label', column_name)  # Default to column name if no label is provided

        # Create the column with its specifications
        attrs[column_name] = db.Column(column_type, **column_specs)

        # Store the column's label for CSV operations
        attrs['_column_labels'][column_name] = column_label

    # Create the model class
    model_class = type(table_name, (base,), attrs)

    # Optionally, add a method or property to get column labels
    def get_column_labels(cls):
        """Returns a dictionary of column labels."""
        return cls._column_labels

    model_class.get_column_labels = classmethod(get_column_labels)

    return model_class


Data1 = create_dynamic_model('old_contacts_1', column_specs)
Data2 = create_dynamic_model('old_contacts_2', column_specs)
Data3 = create_dynamic_model('old_contacts_3', column_specs)
Data4 = create_dynamic_model('old_contacts_4', column_specs)


def get_data_class():
    try:
        if "db" in session and int(session["db"]) in current_user.dbs:
            return globals()["Data" + session["db"]]
        else:
            return globals()["Data" + str(current_user.dbs[0])]
    except:
        return abort(500)


class User(UserMixin, db.Model):
    """
    User model for a Flask application with extended permissions.

    Inherits from UserMixin to integrate with Flask-Login for handling user sessions.
    Uses SQLAlchemy for ORM capabilities.

    Attributes:
        id (Integer): Unique identifier for the user, serves as the primary key.
        username (String): Unique username for the user, used for login.
        password (String): Hashed password for the user.
        fname (String): First name of the user.
        lname (String): Last name of the user.
        active (Boolean): Status indicating if the user account is active.
        permissions (JSON): JSON field storing user permissions as key-value pairs.

    Hybrid Properties:
        Each permission (e.g., can_delete, can_download_db) is exposed as a hybrid property,
        making it easy to access individual permissions directly from the user object.
    """

    __tablename__ = 'old_platform_users'

    id = db.Column(db.Integer, primary_key=True, nullable=False)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(300), nullable=False)
    fname = db.Column(db.String(20), nullable=False)
    lname = db.Column(db.String(20), nullable=False)
    active = db.Column(db.Boolean(), nullable=False, default=True)
    permissions = db.Column(db.JSON)

    @hybrid_property
    def can_delete(self):
        return self.permissions.get('delete', False)

    @hybrid_property
    def can_download_db(self):
        return self.permissions.get('download_db', False)

    @hybrid_property
    def can_download_query(self):
        return self.permissions.get('download_query', False)

    @hybrid_property
    def can_admin(self):
        return self.permissions.get('admin', False)

    @hybrid_property
    def can_dedup(self):
        return self.permissions.get('dedup', False)

    @hybrid_property
    def can_add_file(self):
        return self.permissions.get('add_file', False)

    @hybrid_property
    def can_update_sheet(self):
        return self.permissions.get('update_sheet', False)

    @hybrid_property
    def can_search(self):
        return self.permissions.get('search', False)

    @hybrid_property
    def dbs(self):
        return self.permissions.get('dbs', [1])