import re
from functools import wraps
from flask_login import current_user
from flask import abort


def permission_required(permission):
    """
   Decorator to enforce permission requirements on Flask routes.

   This decorator takes a permission string which can include logical operators ('|' for OR, '&' for AND) to compose
   complex permission requirements. It evaluates the current user's permissions against the specified requirements
   and either allows the route function to execute or aborts the request with a 403 Forbidden status if the permissions
   are not met.

   Args:
       permission (str): A string representing the required permission(s), which can include logical operators.

   Returns:
       The decorated function if permission requirements are met; otherwise, aborts with a 403 error.

   Usage:
       @app.route('/some-protected-route')
       @login_required
       @permission_required('admin|search')
       def protected_route():
           return 'This is a protected route'

   Notes:
       - The decorator splits the permission string on logical operators while keeping these operators for later evaluation.
       - It dynamically checks the current user's permissions based on the specified requirements.
       - Supports complex permission logic using 'and' (&) and 'or' (|) operators.
       - Requires that the `current_user` object (typically provided by Flask-Login) has boolean attributes matching the
         permission names prefixed with 'can_', e.g., 'can_edit' for the 'edit' permission.
   """
    def decorator(func):
        @wraps(func)
        def wrapper_func(*args, **kwargs):
            # Split the permission string by logical operators while keeping the operators for later use
            parts = re.split('(\||&)', permission)
            result = None

            for part in parts:
                if part in {'|', '&'}:
                    continue  # Skip the operator for now

                # Dynamically get the permission value
                has_permission = getattr(current_user, f'can_{part}', False)

                if result is None:
                    result = has_permission
                elif parts[parts.index(part) - 1] == '|':  # Previous part is or
                    result = result or has_permission
                elif parts[parts.index(part) - 1] == '&':  # Previous part is and
                    result = result and has_permission

            if result:
                return func(*args, **kwargs)
            else:
                return abort(403)

        return wrapper_func

    return decorator
