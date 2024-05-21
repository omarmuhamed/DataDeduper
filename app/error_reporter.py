from rq.job import Job
import requests
from urllib.parse import quote
from rq import Queue


def send_error(job_id):
    """
    Sends an error message to a specified Telegram chat when a job fails.

    This function fetches a failed job by its ID, constructs an error message containing the job's ID and the exception
    message, and sends this message to a Telegram chat using the Telegram Bot API. It requires an API key for the bot
    and the chat ID where the message should be sent.

    Args:
        job_id (str): The ID of the failed job.

    Notes:
        - The `API_KEY` and `CHAT` variables should be replaced with your actual Telegram Bot API key and the target
          chat ID, respectively.
        - The `Job.fetch` method is used to retrieve the job instance from Redis.
        - The `exc_string` property of the job's result is used to get the string representation of the exception that
          caused the job to fail.
        - The error message is URL-encoded before being sent to ensure that it is transmitted correctly via HTTP GET.
        - Ensure that the 'requests' library is installed in your environment to use the `requests.get` method for
          sending the HTTP request to the Telegram API.
        - This function does not handle errors that may occur while sending the message to Telegram, such as network
          issues or invalid API keys/chat IDs.
    """

    job = Job.fetch(job_id)
    API_KEY = 'KEY'
    CHAT = 'CHATID'
    message = job.id + '\n' + "-" * 5 + '\n' + job.latest_result().exc_string
    url = f"https://api.telegram.org/bot{API_KEY}/sendMessage?chat_id={CHAT}&text={quote(message)}"
    requests.get(url)


def failure_callback(job, connection, type, value, traceback):
    """
    A callback function to handle job failures in RQ (Redis Queue).

    This function is intended to be used as a failure callback for RQ jobs. When a job fails, it enqueues a new job
    to a dedicated error queue ('error') to handle or report the error. This approach allows for centralized error
    handling and the ability to retry or log errors as needed.

    Args:
        job (Job): The job instance that has failed.
        connection (Redis): The Redis connection used by RQ.
        type (Type[BaseException]): The type of the exception that caused the job to fail.
        value (BaseException): The exception instance that caused the job to fail.
        traceback (Traceback): The traceback object for the exception.

    Notes:
        - The function enqueues a job to the 'error' queue, which should have a worker listening to process such error jobs.
        - The `send_error` function (assumed to be defined elsewhere) is enqueued with the failed job's ID as an argument.
          This function could, for example, send an email notification, log the error to a file or database, or attempt
          a job retry depending on the implementation.
        - The `result_ttl` is set to 300 seconds for the error job, meaning the job's result will be kept for 5 minutes
          after completion. Adjust this value as needed based on how long you need to access the error job's result.
    """

    error_q = Queue(name='error', connection=connection)
    error_q.enqueue('app.error_reporter.send_error', args=(job.id,), result_ttl=300)
