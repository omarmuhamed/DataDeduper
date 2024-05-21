from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required
import json
from flask_paginate import Pagination, get_page_parameter
from werkzeug.security import generate_password_hash
from .decorators import permission_required
from .models import User
from . import db

admins = Blueprint('admins', __name__)


@admins.route('/Users', methods=['GET'])
@login_required
@permission_required('admin')
def admins_page():
    """
    Admins page route to list users with pagination.

    This route is accessible only to users with 'admin' permission. It displays a paginated list of users, allowing
    the admin to navigate through pages of user accounts. The pagination is managed by the Flask-Paginate extension,
    providing a seamless user interface for page navigation.

    Args:
        None

    Returns:
        A rendered template ('admins.html') with the current page of users and pagination controls.

    Notes:
        - The 'permission_required' decorator is assumed to check if the current user has the required permissions.
        - Pagination parameters (page number, items per page) are fetched from the request's query parameters.
        - If the requested page number exceeds the total number of pages and is greater than or equal to 1, the request is redirected to the last available page.
        - The 'Pagination' object is configured to use Bootstrap 5 for styling. Adjust the 'css_framework' argument as necessary to match your application's styling framework.
    """
    page = request.args.get(get_page_parameter(), type=int, default=1)
    users_query = User.query.paginate(page=page, per_page=10, error_out=False)

    # Redirect to the last page if the current page number exceeds the total number of pages
    if page > users_query.pages >= 1:
        args = request.args.to_dict()
        args['page'] = users_query.pages
        return redirect(url_for('admins.admins_page', **args))

    pagination = Pagination(page=page, total=users_query.total, search=False, css_framework='bootstrap5',
                            inner_window=1, outer_window=1)

    return render_template('admins.html', users=users_query, pagination=pagination, json=json)


@admins.route('/EditAdmin/<admin_id>', methods=['POST'])
@login_required
@permission_required('admin')
def edit_admin(admin_id):
    """
    Route to edit an admin's details.

    This endpoint allows for the modification of an existing admin's details including their name, password, and permissions.
    It is secured to be accessible only to users with 'admin' permissions. The function fetches the admin user by ID, then updates their information based on form data provided in the request.

    Args:
        admin_id (str): The ID of the admin to be edited.

    Returns:
        A redirection to the referring page upon completion of the update process.

    Notes:
        - The permissions are updated based on the presence of specific keys in the request form.
        - If a new password is provided, it is hashed before being stored.
        - The route uses POST method to ensure that the update request is submitted securely.
        - The databases permissions are updated based on the list provided in the form. If no databases are selected, a default value is used.
    """
    admin = User.query.filter_by(id=admin_id).first()
    fname = request.form.get('firstname', '')
    lname = request.form.get('lastname', '')
    password = request.form.get('password', '')
    databases = request.form.getlist('dbs', type=int)

    if admin and fname and lname:
        perms = {
            'delete': 'delete' in request.form,
            'download_db': 'downloaddb' in request.form,
            'download_query': 'downloadquery' in request.form,
            'admin': 'admin' in request.form,
            'update_sheet': 'update_sheet' in request.form,
            'dedup': 'dedup' in request.form,
            'add_file': 'add_file' in request.form,
            'search': 'search' in request.form,
            'dbs': databases if databases else [1]
        }
        admin.fname = fname
        admin.lname = lname
        admin.permissions = perms
        if password:
            # Hash the new password before storing it
            admin.password = generate_password_hash(password)
        db.session.commit()  # Commit changes to the database

    return redirect(request.referrer)  # Redirect back to the previous page


@admins.route('/DeleteAdmin', methods=['POST'])
@login_required
@permission_required('admin')
def delete_admin():
    """
    Deletes an admin user from the database based on the provided ID in the form data.

    This function handles the deletion of an admin user. It looks up the admin by the ID provided in the form data. If
    an admin with the specified ID exists, it deletes the admin from the database and commits the change.

    Args:
        None, but expects 'id' to be provided in the form data.

    Returns:
        dict: A dictionary indicating the success status of the operation.

    Notes:
        - The function expects to receive the admin ID as part of the form data submitted to the route it's associated with.
        - It performs a lookup in the User table for the admin with the given ID. If found, it deletes the admin record.
        - After successfully deleting the admin, the function commits the changes to the database to ensure the deletion is persisted.
        - Returns a dictionary with a 'success' key. The value is True if the deletion was successful, or False if the admin ID was not provided or no admin with the provided ID was found.
        - This function does not directly handle response sending; the returned dictionary should be used by the caller to generate an appropriate HTTP response, possibly using `jsonify` for AJAX requests.
    """
    admin_id = request.form.get('id', '')
    if admin_id:
        admin_id = int(admin_id)  # Ensure admin_id is an integer
        admin = User.query.filter_by(id=admin_id).first()  # Fetch the admin to delete

        if admin:
            db.session.delete(admin)  # Prepare the admin record for deletion
            db.session.commit()  # Commit the change to the database
            return {'success': True}  # Indicate successful deletion

    return {'success': False}  # Indicate failure to delete an admin


@admins.route('/AddAdmin', methods=['POST'])
@login_required
@permission_required('admin')
def add_admin():
    """
    Route to add a new admin to the system.

    This endpoint allows for the creation of new admin users with specific permissions. It checks for required fields including first name, last name, username, and password, as well as ensures that the username does not already exist in the database. Additional permissions and database access can be configured via the form data.

    Args:
        None

    Returns:
        A redirection to the admin page upon successful creation of the new admin, or if the admin could not be created (e.g., if the username already exists).

    Notes:
        - Permissions are determined based on the form data, with a default set of permissions applied if specific permissions are not provided.
        - The password is hashed before storing to ensure security.
        - The route uses the POST method to securely submit the data for the creation of a new admin.
        - Database access permissions are determined based on the selected databases in the form. A default value is used if no selection is made.
    """
    fname = request.form.get('firstname', '')
    lname = request.form.get('lastname', '')
    username = request.form.get('username', '')
    password = request.form.get('password', '')
    databases = request.form.getlist('dbs', type=int)  # Ensure proper type conversion
    check_user_exists = User.query.filter_by(username=username).first()  # Check if the username already exists

    if fname and lname and username and password and not check_user_exists:
        perms = {
            'delete': 'delete' in request.form,
            'download_db': 'downloaddb' in request.form,
            'download_query': 'downloadquery' in request.form,
            'admin': 'admin' in request.form,
            'update_sheet': 'update_sheet' in request.form,
            'dedup': 'dedup' in request.form,
            'add_file': 'add_file' in request.form,
            'search': 'search' in request.form,
            'dbs': databases if databases else [1]  # Apply default database access if none specified
        }
        new_admin = User(username=username, fname=fname, lname=lname, password=generate_password_hash(password),
                         permissions=perms, active=True)
        db.session.add(new_admin)
        db.session.commit()  # Save the new admin to the database

    return redirect(url_for('admins.admins_page'))  # Redirect to the admin page
