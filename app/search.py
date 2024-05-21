import zipfile
from io import BytesIO
import json
from flask import Blueprint, render_template, request, send_file, jsonify
from flask_login import login_required
from sqlalchemy import or_, and_, func
from sqlalchemy.sql.functions import coalesce
from sqlalchemy.dialects import postgresql
from .decorators import permission_required
from .models import get_data_class
from . import db
from .utils import get_bind_key
from .data_structure import column_specs

search = Blueprint('search', __name__)


@search.route('/getdata', methods=['POST'])
@login_required
@permission_required('search')
def getdata():
    """
    Handles data retrieval requests with dynamic filtering for a searchable datatable.

    This endpoint accepts POST requests containing JSON with search criteria, pagination parameters, and other
    datatable-specific parameters (like 'draw' count). It processes these requests to query the database dynamically
    based on the provided filters, paginate the results according to the request, and return a JSON response that
    the datatable can use to display the filtered and paginated data.

    Args:
        None, but expects a JSON payload in the request with parameters for filtering and pagination.

    Returns:
        A JSON object containing the datatable draw count, total number of records, number of records after filtering,
        and the paginated data set formatted for the datatable.

    Preconditions:
        - User must be authenticated and have the 'search' permission.

    Notes:
        - The 'process_filters' utility function is assumed to convert the search criteria into SQLAlchemy filters.
        - Pagination parameters ('start' and 'length') are extracted from the request to determine the page number and
          the number of records per page.
        - The 'draw' parameter from the request is used by the datatable to synchronize and track the AJAX requests.
    """
    req = request.json
    filters = []
    column_transformations = {
        column_name: column_spec['label'].replace(' ', '_').lower()
        for column_name, column_spec in column_specs.items() if column_name != 'id'
    }
    if 'sbCrit' in req and req['sbCrit']:
        filters = [process_filters(request.json['sbCrit'])]
    q = get_data_class().query.filter(*filters)
    all_rows_count = db.session.query(func.count(get_data_class().id)).scalar()
    filtered_data = q.paginate(page=1 if not req['start'] else (req['start'] / req['length']) + 1, per_page=req['length'], error_out=False)
    res = {'draw': int(req['draw']), 'recordsTotal': all_rows_count, 'recordsFiltered': filtered_data.total}
    data = []
    print(column_transformations)
    for rec in filtered_data:
        record = {
            label: getattr(rec, column_name, '') for column_name, label in column_transformations.items()
        }
        data.append(record)
    res['data'] = data
    return res


@search.route('/searchv2', methods=['GET'])
@login_required
@permission_required('search')
def search_v2():
    """
    Renders the version 2 search page.

    This route serves the updated version of the search interface, 'searchv2.html'. It ensures that only authenticated
    users with the 'search' permission can access this page, providing a layer of security and access control to
    sensitive functionalities or data presented in the search interface.

    Args:
        None

    Returns:
        The rendered 'searchv2.html' template for the user.

    Preconditions:
        - User must be authenticated.
        - User must have the 'search' permission to access this route.

    Notes:
        - The 'searchv2.html' template should be created in the templates directory and designed according to the
          application's UI/UX guidelines.
        - This function can be expanded to pass additional context or data to the template based on application needs.
    """
    columns = [{'data': spec['label'].replace(' ', '_').lower(), 'type': spec.get('filter_type', 'string')}
               for name, spec in column_specs.items() if name != 'id']
    return render_template('searchv2.html', columns=json.dumps(columns), column_specs=column_specs)


def process_filters(_data):
    """
    Dynamically constructs SQLAlchemy filter conditions from a given set of criteria.

    This function maps front-end filter criteria to corresponding SQLAlchemy model attributes
    and applies the specified filter operations. It supports both single and nested (complex)
    filter conditions, allowing for flexible and powerful querying capabilities.

    Parameters:
    - _data (dict): A dictionary representing the filtering criteria. The dictionary may contain
      simple key-value pairs for direct filtering, or a nested structure with 'criteria' and 'logic'
      keys for complex, grouped filtering conditions.

    Returns:
    - SQLAlchemy filter condition(s) that can be applied directly to a query object. If the input
      data does not match the expected format or contains unsupported filter operations, `None` is
      returned.

    Usage:
    - Single condition example: {'origData': 'email', 'condition': '=', 'value': ['example@example.com']}
    - Nested conditions example:
        {
            'logic': 'AND',
            'criteria': [
                {'origData': 'city', 'condition': 'contains', 'value': ['York']},
                {'origData': 'postcode', 'condition': 'starts', 'value': ['YO']}
            ]
        }

    Note:
    - The `COLS_DICT` dictionary maps front-end identifiers to SQLAlchemy model attributes.
    - The `FILTERS_DICT` dictionary maps filter operations to lambda functions that implement
      the corresponding SQLAlchemy expressions.
    - Nested filter conditions use logical operators ('AND', 'OR') specified in the 'logic' key
      of the criteria dictionary.
    """
    COLS_DICT = {}

    # Iterate over the column_specs to populate COLS_DICT
    for column_name, column_spec in column_specs.items():
        if column_name != 'id':  # Exclude primary_key column
            column_label = column_spec['label']
            COLS_DICT[column_label.replace(' ', '_').lower()] = getattr(get_data_class(), column_name)

    FILTERS_DICT = {'!=': lambda x, v: x != v,
                    '=': lambda x, v: x == v,
                    '!null': lambda x, v: x.isnot(None),
                    'null': lambda x, v: x.is_(None),
                    '!contains': lambda x, v: x.not_ilike(v),
                    'contains': lambda x, v: x.ilike(v),
                    '!ends': lambda x, v: ~x.iendswith(v),
                    'ends': lambda x, v: x.iendswith(v),
                    '!starts': lambda x, v: ~x.istartswith(v),
                    'starts': lambda x, v: x.istartswith(v),
                    '>': lambda x, v: x > v,
                    '<': lambda x, v: x < v,
                    '>=': lambda x, v: x >= v,
                    '<=': lambda x, v: x <= v,
                    'between': lambda x, v: x.between(*v),  # Expects v to be a tuple or list of two values
                    '!between': lambda x, v: ~x.between(*v)
                    }

    def _process_filters(data):
        filters = []
        if 'criteria' in data:
            for crt in data['criteria']:
                _filter = process_filters(crt)
                if _filter is not None:
                    filters.append(_filter)
            logic = and_ if data['logic'] == 'AND' else or_
            return logic(*filters)
        else:
            if {'value', 'condition', 'origData'}.issubset(data.keys()):
                val = data['value'][0] if len(data['value']) else ""
                if len(data['value']) == 2 and data['condition'] in ['between', '!between']:
                    val = data['value']
                    for v in val:
                        if not v:
                            return None
                return FILTERS_DICT[data['condition']](COLS_DICT[data['origData']], val)
            else:
                return None
    return _process_filters(_data)


@search.route('/downloadqueryv2', methods=['POST'])
@login_required
@permission_required('download_query')
def download_query():
    """
    Downloads query results as a CSV file based on dynamic filters provided by the user.

    This route handler processes POST requests containing dynamic filter criteria, executes the corresponding
    database query to fetch filtered results, and provides the results as a downloadable ZIP file containing
    one or more CSV files. It is designed to handle large datasets by splitting the results into chunks.

    Preconditions:
    - User must be authenticated and have 'download_query' permission.

    Postconditions:
    - A ZIP file containing the query results as CSV is generated and sent to the user for download.

    Notes:
    - This function uses raw SQL execution capabilities to efficiently export large volumes of data.
    - The CSV files are generated in chunks to manage memory usage and support large datasets.
    - Assumes PostgreSQL as the database backend for the COPY command.
    """
    filters = process_filters(json.loads(request.form['crt']))
    columns = []

    # Iterate over the column_specs to dynamically construct the query
    for column_name, column_spec in column_specs.items():
        if column_name != 'id':  # Exclude primary_key column
            column_label = column_spec['label']
            columns.append(getattr(get_data_class(), column_name).label(column_label))
    # Construct the query
    if filters is not None:
        filtered_data = db.session.query(*columns).filter(filters).order_by(get_data_class().id)
    else:
        filtered_data = db.session.query(*columns).order_by(get_data_class().id)
    sql_string = str(
        filtered_data.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    row_count = filtered_data.count()
    temp_zip = BytesIO()
    raw_conn = db.get_engine().raw_connection()
    cur = raw_conn.cursor()
    with zipfile.ZipFile(temp_zip, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
        for i in range((row_count // 1000000) + 1):
            outputquery = "COPY ({0}) TO STDOUT WITH CSV HEADER".format(sql_string + f' LIMIT 1000000 OFFSET {i * 1000000}')
            print(outputquery)
            tmp_file = BytesIO()
            cur.copy_expert(outputquery, tmp_file)
            tmp_file.seek(0)
            zip_file.writestr(f'part-{i}.csv', tmp_file.getvalue())
            tmp_file.close()
    temp_zip.seek(0)
    return send_file(temp_zip, download_name='query_result.zip')


@search.route('/deleterecords', methods=['POST'])
@login_required
@permission_required('delete')
def delete_records():
    """
    Deletes records from the database based on dynamic filter criteria provided by the user.

    This route handles POST requests containing JSON payload with filter criteria, processes these criteria to construct
    a SQLAlchemy filter, and deletes records matching these filters from the 'Data' table.

    Preconditions:
    - User must be authenticated and have 'delete' permission.

    Postconditions:
    - Records matching the filter criteria are deleted from the database.

    Returns:
    - JSON response indicating the success or failure of the delete operation.

    Notes:
    - The function uses a try-except block to catch and handle exceptions, ensuring that any database errors do not
      lead to an unhandled exception.
    - Proper error handling and logging are important to diagnose issues that may arise during the delete operation.
    """
    try:
        filters = process_filters(request.json)
        if filters is not None:
            del_stmt = get_data_class().__table__.delete().where(filters)
        else:
            get_data_class().query.delete()
            db.session.commit()
            return {'success': True}
        db.session.execute(del_stmt)
        db.session.commit()
        return {'success': True}
    except Exception as e:
        print(e)
        return {'success': False}
