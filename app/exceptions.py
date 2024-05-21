class ErrorCreatingJobDir(Exception):
    """
    Custom exception for errors encountered while creating a job directory.

    This exception is raised when the system fails to create a directory intended for job-related files or data.
    It can be used to signal issues with file system permissions, unavailable storage, or other problems related to
    directory creation operations.
    """


class ErrorReadingDataFile(Exception):
    """
    Custom exception for errors encountered while reading a data file.

    This exception is raised when there is an issue with reading data from a file. This could be due to the file not
    existing, being corrupted, lacking the necessary permissions to read the file, or other issues that prevent
    successful reading of the file's contents.
    """


class MissingRequiredColumns(Exception):
    """
    Custom exception for missing required columns in a data file.

    This exception is raised when a data file does not contain all the required columns expected by the application.
    It can be used to signal data validation failures and ensure that the incoming data files meet the expected
    format and schema requirements.
    """
