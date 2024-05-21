import subprocess
import zipfile
from io import BytesIO
from flask import current_app, request, send_file, render_template, redirect, url_for, Blueprint, abort
from flask_login import login_required, current_user
from flask_paginate import Pagination, get_page_parameter
from rq.job import Job
from rq.exceptions import NoSuchJobError
from sqlalchemy import func
from math import ceil
import uuid
import os
import pandas as pd
from .models import get_data_class
from .redis_conn import redis_conn as conn, queues as q
from . import db
from .decorators import permission_required
from .deduper import task
from .error_reporter import failure_callback
from .utils import get_bind_key, allowed_file, get_all_jobs_with_filters, get_exception_details
from .data_structure import column_specs
main = Blueprint('main', __name__)


@main.route('/', methods=['GET'])
@login_required
@permission_required('add_file')
def home():
    """
    Home route that displays the upload page, restricted to users with 'add_file' permission.

    This view function queries the job queue for jobs related to the 'add_file' method and passes these jobs to the
    upload.html template for display. It demonstrates the integration of user permissions with job queue filtering
    to provide a tailored view based on the user's permissions and actions they're allowed to perform.

    Args:
        None

    Returns:
        Rendered template ('upload.html') with the filtered list of jobs related to the 'add_file' action.

    Notes:
        - The function uses the @login_required decorator from Flask-Login to ensure that only authenticated users
          can access this route.
        - The @permission_required('add_file') decorator checks that the current user has the 'add_file' permission
          before allowing access to this route.
        - It assumes there is a list of RQ queues named 'q' from which it selects the first queue to filter jobs.
        - The 'get_all_jobs_with_filters' function is used to retrieve and filter jobs from the selected queue based
          on a criteria dictionary, in this case, filtering by jobs related to the 'add_file' method.
    """
    primary_key_column = next(
        (name for name, spec in column_specs.items() if spec.get('specs', {}).get('primary_key', False)), None)
    # Exclude primary key column from the mapping
    column_mappings = {k: v for k, v in column_specs.items() if k != primary_key_column}
    jobs_dict = get_all_jobs_with_filters(q[0], {'method': 'add_file'})
    return render_template('upload.html', jobs=jobs_dict, column_mappings=column_mappings)


@main.route('/report', methods=['GET'])
@login_required
@permission_required('dedup')
def report():
    """
    Report route that displays the report upload page, restricted to users with 'dedup' permission.

    This view function queries the job queue for jobs related to the 'dedup' method and passes these jobs to the
    report_upload.html template for display. It showcases how user permissions integrate with job queue filtering
    to provide a view tailored to the user's permissions and the actions they are allowed to perform.

    Args:
        None

    Returns:
        Rendered template ('report_upload.html') with a filtered list of jobs related to the 'dedup' action.

    Notes:
        - Utilizes @login_required decorator from Flask-Login to ensure access is limited to authenticated users.
        - The @permission_required('dedup') decorator checks if the current user has 'dedup' permission before
          allowing access to the route.
        - Assumes existence of a list of RQ queues named 'q', selecting the first queue for job filtering.
        - Employs 'get_all_jobs_with_filters' to retrieve and filter jobs from the selected queue based on the
          criteria dictionary, specifically filtering by jobs associated with the 'dedup' method.
        """
    primary_key_column = next(
        (name for name, spec in column_specs.items() if spec.get('specs', {}).get('primary_key', False)), None)
    # Exclude primary key column from the mapping
    column_mappings = {k: v for k, v in column_specs.items() if k != primary_key_column}
    jobs_dict = get_all_jobs_with_filters(q[0], {'method': 'dedup'})
    return render_template('test_report.html', jobs=jobs_dict, column_mappings=column_mappings)


@main.route('/add', methods=['POST'])
@login_required
@permission_required('add_file|dedup')
def add_task():
    """
    Route to add a task for either file upload or deduplication, depending on user permissions and form input.

    This view function handles POST requests to add tasks related to file uploads or deduplication. It checks if the
    current user has the necessary permission for the requested action (add_file or dedup), verifies the file upload,
    and enqueues a job to the background task queue with the appropriate parameters.

    Args:
        None

    Returns:
        Redirect to the report upload page if the 'dedup' method was requested, or the home page otherwise.

    Notes:
        - This route requires authentication and checks for specific permissions (add_file or dedup) dynamically based on form input.
        - Validates the uploaded file against a set of allowed file types before proceeding with task addition.
        - Utilizes RQ (Redis Queue) for task queuing, specifying a failure callback function for job failure handling.
        - The file is saved with a new filename generated using UUID to avoid naming conflicts and stored in a designated directory.
    """
    method = None
    if request.method == 'POST':
        method = request.form.get('method')
        if method in ['add_file', 'dedup'] and getattr(current_user, f'can_{method}', False):
            if 'uploaded_file' in request.files:
                file = request.files['uploaded_file']
                if file:
                    oldfilename = request.files['uploaded_file'].filename
                    if allowed_file(oldfilename):
                        df = pd.read_csv(file.stream, dtype=str)  # Use .stream to read directly from the uploaded file

                        # Initialize processed_data DataFrame
                        processed_data = pd.DataFrame()

                        for column_name, spec in column_specs.items():
                            if 'label' in spec:  # Ensure there is a label defined
                                form_key = f'mapping_{column_name}'
                                mapped_columns = request.form.getlist(form_key)  # Get the mapped columns from the form
                                separator = request.form.get(f'separator_{column_name}', '')  # Get the separator

                                # Check if this column should be included in the processing (not primary and has mappings)
                                if spec.get('specs', {}).get('primary_key', False):
                                    continue  # Skip primary key column

                                if mapped_columns:  # If there are columns mapped to this one
                                    if len(mapped_columns) > 1 and separator:  # Multiple columns with a separator
                                        combined_column = df[mapped_columns].astype(str).agg(separator.join, axis=1)
                                        processed_data[spec['label']] = combined_column
                                    elif len(mapped_columns) == 1:  # Single column mapped directly
                                        processed_data[spec['label']] = df[mapped_columns[0]]
                        newfilename = str(uuid.uuid4()) + os.path.splitext(oldfilename)[1]
                        processed_data.to_csv('/uploaded_files/' + newfilename, index=False)
                        q[0].enqueue(task, kwargs={'data_file_path': '/uploaded_files/' + newfilename, 'db_string': current_app.config['SQLALCHEMY_DATABASE_URI'], 'table_name': get_bind_key(), 'add_to_db': True if method == "add_file" else False, 'column_specs': column_specs}, meta={'name': oldfilename, "user": current_user.id, 'method': method}, result_ttl=2628288, on_failure=failure_callback)
        else:
            abort(403)
    return redirect(url_for('main.report')) if method == "dedup" else redirect(url_for('main.home'))


@main.route('/report/<job_key>')
@login_required
@permission_required('add_file|dedup')
def get_report(job_key):
    """
    Fetches and displays the report for a completed job based on the job key.

    This route retrieves job details from RQ using the provided job key and displays the report for jobs originated from 'deduper'. Access to the report is restricted based on user permissions and the job's metadata. It supports pagination for large reports and handles job status checks to respond appropriately if the job is still running or has failed.

    Args:
        job_key (str): The unique identifier for the job whose report is to be fetched.

    Returns:
        Rendered template ('report.html') with the job report, including pagination if applicable.
        In case of a failed job, renders an 'error.html' template.
        Aborts with 404 if the job does not exist or with 423 if the job is still in progress.

    Notes:
        - Pagination is handled to display reports in chunks of 500 rows per page.
        - The job result is expected to contain statistics about the deduplication process, which are displayed in the template.
        - The route ensures that only users with the appropriate permissions can access the report for security and privacy reasons.
    """
    try:
        page = request.args.get(get_page_parameter(), type=int, default=1)
        args = request.args.to_dict()
        job = Job.fetch(job_key, connection=conn)
        if job.origin == "deduper" and getattr(current_user, f'can_{job.meta["method"]}', False):
            if job.is_finished:
                df = pd.read_csv('/jobs/' + job_key + '/report.csv')
                total = df.shape[0]
                if total > 0:
                    if page > ceil(total / 500):
                        args['page'] = ceil(total / 500)
                        return redirect(url_for('main.get_report', job_key=job_key, **args))
                    df = df[(page - 1)*500: (page - 1) * 500 + 500]
                    df.fillna('', inplace=True)
                pagination = Pagination(page=page, per_page=500, total=total, search=False, css_framework='bootstrap5', inner_window=1, outer_window=1)
                job_result = job.return_value()[1]
                job_result[0].setdefault('Unique', 0)
                job_result[0].setdefault('Duplicate', 0)
                job_result[0].setdefault('In-file', 0)
                job_result[0].setdefault('In-file & DB', 0)
                print(job_result)
                return render_template('report.html', df=df, res=job_result, pagination=pagination, headers=df.columns.tolist())
            else:
                if job.is_failed:
                    return render_template('error.html', error=get_exception_details(job.latest_result().exc_string)[1]), 500
                else:
                    return abort(423)
        else:
            return abort(404)
    except NoSuchJobError:
        abort(404)


@main.route("/result/<job_key>/download", methods=['GET'])
@login_required
@permission_required('add_file')
def download_results(job_key):
    """
    Route to download the results of a completed job.

    This function allows users to download the result file of a completed job if they have the necessary permissions.
    It checks if the job has finished and originates from a specific queue ('deduper'). If these conditions are met,
    the function serves the result file for download. Otherwise, it aborts the request with a 404 Not Found status.

    Args:
        job_key (str): The unique identifier for the job whose results are to be downloaded.

    Returns:
        A file download response if the job is finished and the file exists.
        Aborts with a 404 Not Found status if the job is not finished, does not exist, or does not meet the specified conditions.

    Notes:
        - The route is protected with @login_required and @permission_required('add_file') decorators to ensure only
          authenticated users with the appropriate permissions can access this functionality.
        - This implementation assumes that the result files are stored in a directory accessible to the application
          and that the path construction '/jobs/' + job_key + '/result.csv' correctly points to the desired file.
    """
    job = Job.fetch(job_key, connection=conn)
    if job.is_finished and job.origin == 'deduper':
        return send_file('/jobs/' + job_key + '/result.csv')
    else:
        return abort(404)


@main.route('/report/<job_key>/download')
@login_required
@permission_required('dedup|add_file')
def download_report(job_key):
    """
    Route to download the report file for a completed job.

    This function checks if a specified job, identified by its job_key, has completed its execution and originates
    from a specific queue ('deduper'). If these conditions are satisfied, it allows the user to download the generated
    report file. Access is granted based on user permissions, specifically allowing users with either 'dedup' or
    'add_file' permissions. If the job is not completed, does not exist, or does not meet the criteria, the function
    aborts the request with a 404 Not Found status.

    Args:
        job_key (str): The unique identifier for the job whose report file is to be downloaded.

    Returns:
        A file download response if the job is finished and the report file exists.
        Aborts with a 404 Not Found status if the job does not meet the necessary conditions or if the file does not exist.

    Notes:
        - The function is protected with @login_required and @permission_required('dedup|add_file') decorators to
          ensure that only authenticated users with appropriate permissions can access this feature.
        - Assumes that the report files are stored in a directory accessible to the application and that the constructed
          path '/jobs/' + job_key + '/report.csv' correctly points to the intended file.
    """
    job = Job.fetch(job_key, connection=conn)
    if job.is_finished and job.origin == 'deduper':
        return send_file('/jobs/' + job_key + '/report.csv')
    else:
        return abort(404)


@main.route('/cancel/<job_key>', methods=['GET'])
@login_required
def cancel_job(job_key):
    """
    Cancels a specific job and deletes it from the queue.

    This route allows authenticated users to cancel a job identified by its job key. If the job exists, it will be
    deleted from the Redis queue. This functionality is crucial for managing long-running or unnecessary tasks,
    providing users with the ability to clean up resources and manage job execution dynamically.

    Args:
        job_key (str): The unique identifier for the job to be canceled.

    Returns:
        Redirect to the referring page, allowing users to continue their workflow seamlessly after canceling the job.

    Notes:
        - The function is protected with @login_required decorator to ensure that only authenticated users can access
          this feature.
        - If the specified job does not exist, the function will silently ignore the delete request, assuming the job
          might have already been completed or canceled. For more strict handling, consider adding explicit checks
          and feedback for such cases.
    """
    job = Job.fetch(job_key, connection=conn)
    if job:
        job.delete()
    return redirect(request.referrer)


def generate_sql_query(column_specs, table_name_func, limit=1000000, offset_multiplier=0):
    # Constructs the SELECT part of the SQL query based on the provided column specs
    select_parts = []
    for db_column, spec in column_specs.items():
        friendly_name = spec.get('label')  # Get user-friendly name from the spec
        select_parts.append(f"{db_column} as \"{friendly_name}\"")

    select_clause = ", ".join(select_parts)

    # Constructs the full SQL query using the table name provided by the table_name_func
    table_name = table_name_func()  # Call the function to get the table name
    offset = offset_multiplier * limit
    sql = f"SELECT {select_clause} FROM public.{table_name} ORDER BY id LIMIT {limit} OFFSET {offset}"

    return sql


@main.route('/downloaddb', methods=['GET'])
@login_required
@permission_required('download_db')
def download_database():
    """
    Downloads the database in parts as a ZIP file.

    This route facilitates the downloading of database content by dynamically generating CSV files for segments of
    the database and compressing them into a ZIP file. It's designed to handle large datasets by splitting the data
    into manageable parts, each containing up to 1,000,000 rows, to avoid memory issues.

    Returns:
        A ZIP file containing parts of the database as CSV files, allowing for efficient data transfer and handling
        of large datasets.

    Notes:
        - The route is protected with @login_required and @permission_required('download_db') decorators to ensure
          only authenticated users with the appropriate permissions can download the database.
        - Uses raw SQL queries and the COPY command for efficient data export from PostgreSQL.
        - Assumes the use of PostgreSQL as the database backend.
        - This implementation may need adjustments based on the actual database schema and requirements.
    """
    # Establish raw connection to the database using the current bind key
    raw_conn = db.get_engine().raw_connection()
    cur = raw_conn.cursor()

    # Determine the total number of rows to decide the number of parts needed
    all_rows_count = db.session.query(func.count(get_data_class().id)).scalar()

    # Initialize a BytesIO object for the ZIP file
    temp_zip = BytesIO()

    # Create and add CSV files to the ZIP file
    with zipfile.ZipFile(temp_zip, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
        for i in range((all_rows_count // 1000000) + 1):
            #sql = f'select title as "Title",firstname as "First Name",lastname as "Last Name", address as "Address", city as "City", postcode as "Postcode", email as "Email", phone_number as "Phone", dob as "DOB", supplier_name as "Supplier", bsc as "BSC", delivery_stat as "Delivery Status" from public.{get_bind_key()} ORDER BY id LIMIT 1000000 OFFSET {i * 1000000}'
            sql = generate_sql_query(column_specs, get_bind_key, offset_multiplier=i)
            outputquery = "COPY ({0}) TO STDOUT WITH CSV HEADER".format(sql)

            # Temporary file to store CSV content
            tmp_file = BytesIO()
            cur.copy_expert(outputquery, tmp_file)
            tmp_file.seek(0)

            # Add CSV content to the ZIP file
            zip_file.writestr(f'part-{i}.csv', tmp_file.getvalue())
            tmp_file.close()

    # Prepare the ZIP file for downloading
    temp_zip.seek(0)
    return send_file(temp_zip, download_name='database.zip')

