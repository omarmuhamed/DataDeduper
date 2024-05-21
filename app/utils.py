from flask_sqlalchemy.session import Session
from flask_login import current_user
from flask import session, abort


def get_bind_key():
    """
    Determines and returns a database binding key based on the user's session and their accessible databases.

    The function checks if the user's session contains a specific database identifier ('db') that the current user
    has access to. If so, it returns a binding key for that database. Otherwise, it defaults to the first database
    in the user's list of accessible databases. In case of errors, the function aborts the operation with a 500 error code,
    indicating an internal server error.

    Returns:
        str: A string representing the database binding key, prefixed with "db" and followed by the database identifier.
        This can either be the one specified in the session or the first one in the user's accessible databases list.

    Raises:
        HTTPError: An HTTP 500 error if an exception occurs, indicating an internal server error.

    Example:
        # Assuming a valid session and user context
        binding_key = get_bind_key()
        print(binding_key)  # Outputs: "db1" or "db2", etc., depending on the session and user's accessible databases.

    Note:
        This function assumes the existence of a global `session` object and a `current_user` object with a `dbs` attribute
        (a list of database identifiers the user has access to).
    """
    try:
        if "db" in session and int(session["db"]) in current_user.dbs:
            return "old_contacts_" + session["db"]
        else:
            return "old_contacts_" + str(current_user.dbs[0])
    except:
        return abort(500)


class MySignallingSession(Session):
    """
    A custom session class that extends the functionality of SQLAlchemy's Session to implement dynamic database binding based on specific conditions.

    This class overrides the `__init__` method to accept a database connection string or engine and optionally other arguments and keyword arguments. It also overrides the `get_bind` method to dynamically determine the database bind for operations based on the mapper's metadata.

    Attributes:
        db (str or Engine): The database connection string or engine instance that this session will use for transactions.

    Methods:
        get_bind(mapper=None, clause=None): Overrides the Session's get_bind method to dynamically select a database bind based on the mapper's metadata.
    """

    def __init__(self, db, *args, **kwargs):
        """
        Initializes a new instance of the MySignallingSession class with the specified database connection and optional arguments.

        Args:
            db (str or Engine): The database connection string or engine instance to use for this session.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(db, *args, **kwargs)
        self.db = db

    def get_bind(self, mapper=None, clause=None):
        """
        Determines and returns the appropriate database engine or connection for the current operation.

        This method overrides the default get_bind to allow for dynamic binding based on the mapper's metadata. If the mapper has metadata with a 'bind_key' of '__all__', it temporarily sets the 'bind_key' to a specific database determined by the `get_bind_key` function before reverting it back.

        Args:
            mapper (optional): The mapper involved in the operation. Default is None.
            clause (optional): The SQL clause involved in the operation. Default is None.

        Returns:
            The database engine or connection to be used for the current operation.
        """
        if mapper is not None:
            info = getattr(mapper.persist_selectable.metadata, 'info', {})
            if info.get('bind_key') == '__all__':
                info['bind_key'] = get_bind_key()
                try:
                    return super().get_bind(mapper=mapper, clause=clause)
                finally:
                    # Ensure the original '__all__' bind_key is restored after the operation
                    info['bind_key'] = '__all__'
        return super().get_bind(mapper=mapper, clause=clause)


def allowed_file(filename):
    """
    Checks if the uploaded file has an allowed extension.

    This function is designed to validate the extension of files uploaded by users to ensure they meet the application's criteria for allowed file types. Currently, it only allows files with the '.csv' extension.

    Args:
        filename (str): The name of the file to check.

    Returns:
        bool: True if the file has an allowed extension, False otherwise.

    Example:
        if allowed_file('data.csv'):
            print("File is allowed.")
        else:
            print("File is not allowed.")

    Note:
        - The function splits the filename by the '.' character to isolate the extension and checks if it exists within the allowed extensions set.
        - It is case-insensitive, ensuring that extensions in uppercase will also be accepted.
        - The function assumes that a valid file name contains at least one '.' character to separate the file name from the extension.
    """
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in {'csv'}


def match_job_meta(job, filters):
    """
    Check if a job's metadata matches all key-value pairs in the filters dictionary.

    Parameters:
    - job: The job object whose metadata is to be checked.
    - filters: A dictionary of key-value pairs to match against the job's metadata.

    Returns:
    - True if all key-value pairs in filters match the job's metadata; False otherwise.
    """
    for key, value in filters.items():
        # Check if the key exists in job.meta and the value matches
        if key not in job.meta or job.meta[key] != value:
            return False
    return True


def get_all_jobs_with_filters(queue, filters={}):
    """
    Retrieves all jobs from a given queue, filtered by specific criteria.

    This function collects jobs from different registries within a given RQ (Redis Queue) queue, such as finished,
    scheduled, started, failed, and canceled jobs. It then filters these jobs based on the user's permissions and
    additional specified filters, compiling a list of job details that match the criteria.

    Args:
        queue (Queue): The RQ queue instance from which to retrieve jobs.
        filters (dict, optional): A dictionary of filters to apply to the job selection process. Defaults to an empty dictionary.

    Returns:
        list: A list of tuples, where each tuple contains details about a job that matches the filtering criteria. Each tuple includes the job ID, its status, the job name (if available), and the job's creation timestamp.

    Note:
        - The function checks if the job was created by the current user or if the current user has administrative privileges before including it in the result.
        - It uses the `match_job_meta` function to apply additional filtering based on the job's metadata. This function is assumed to be defined elsewhere and should accept a job instance and a dictionary of filters, returning `True` if the job matches the filters.
        - Jobs are identified and fetched from various job registries (finished, scheduled, started, failed, canceled) within the specified queue.
        - If fetching a job or applying filters raises an exception, the job is skipped, and the function continues to the next job.
    """
    jobs_dict = []
    finished_jobs = queue.finished_job_registry.get_job_ids()
    scheduled_jobs = queue.scheduled_job_registry.get_job_ids()
    started_jobs = queue.started_job_registry.get_job_ids()
    failed_jobs = queue.failed_job_registry.get_job_ids()
    canceled_jobs = queue.canceled_job_registry.get_job_ids()

    # Combine all job IDs from different registries
    jobs = scheduled_jobs + started_jobs + finished_jobs + failed_jobs + canceled_jobs
    for job in jobs:
        try:
            jj = queue.fetch_job(job)
            # Filter jobs based on the user and additional criteria
            if (jj.meta['user'] == current_user.id or current_user.can_admin) and match_job_meta(jj, filters):
                job_details = (job, jj.get_status(), jj.meta['name'] if 'name' in jj.meta else "",
                               jj.created_at.strftime("%m/%d/%Y, %H:%M:%S"))
                jobs_dict.append(job_details)
        except Exception as e:
            # Skip the job if any errors occur during fetching or filtering
            continue
    return jobs_dict


def get_exception_details(exc_info):
    """
    Parses the exception information string to extract and return
    the exception type and value.
    """
    # Split the traceback into lines for analysis
    lines = exc_info.strip().split('\n')
    # The last line usually contains the exception type and message
    last_line = lines[-1] if lines else ''

    # Extract the exception type and message
    # This is simplistic and might need adjustment for complex exceptions
    exception_parts = last_line.split(':', 1)
    exception_type = exception_parts[0].strip() if exception_parts else 'UnknownException'
    exception_value = exception_parts[1].strip() if len(exception_parts) > 1 else 'No additional information'

    return exception_type, exception_value
