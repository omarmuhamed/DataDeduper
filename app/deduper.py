import pandas as pd
import psycopg2
import os
from rq import get_current_job
from io import StringIO
from .exceptions import *
import numpy as np
from typing import List, AnyStr
import re


def task(**kwargs):
    """
    Executes a deduplication task based on the provided keyword arguments.

    This function is designed to instantiate and utilize the Deduper class to perform data deduplication tasks.
    It takes a flexible set of keyword arguments that are passed directly to the Deduper class constructor,
    allowing for customized deduplication processes based on the specific needs of each task.

    Parameters:
    - **kwargs: Arbitrary keyword arguments. These are passed directly to the Deduper class and can include
                parameters such as 'required_columns', 'optional_columns', 'db_string', 'data_file_path',
                'add_to_db', and 'target_column' among others.

    Returns:
    - The result of the deduplication process, typically a summary report generated by the Deduper class's
      `dedupe` method. The structure and content of the report can vary depending on the implementation of
      the `dedupe` method within the Deduper class.

    Usage Example:
    - To execute a deduplication task with specific parameters, you can call the task function like so:
      `task(required_columns=['Phone', 'Email'], data_file_path='path/to/data.csv', db_string='postgresql://...')`

    Note:
    - It's essential to ensure that the Deduper class is properly defined and that its `dedupe` method is
      implemented to handle the deduplication logic as expected. The **kwargs passed to this function should
      match the parameters accepted by the Deduper class constructor.
    """
    d = Deduper(**kwargs)
    return d.dedupe()


class Deduper:
    def __init__(self,
                 column_specs,
                 db_string: AnyStr = '',
                 table_name: AnyStr = '',
                 data_file_path: AnyStr = '',
                 add_to_db: bool = False,
                 target_column: AnyStr = 'Phone'
                 ):
        """
        A class designed to perform deduplication of data, specifically targeting contact information such as phone numbers.

        This class processes a dataset to identify and handle duplicate entries based on specified criteria, with the
        option to insert deduplicated data into a database.

        Attributes:
            job_id (str): The unique identifier for the current job, derived from RQ's job context.
            add_to_db (bool): Flag indicating whether deduplicated data should be added to the database.
            db_string (str): Database connection string.
            dataframe (pd.DataFrame): The DataFrame holding the original dataset.
            dataframe_to_insert (pd.DataFrame): The DataFrame prepared for database insertion after deduplication.
            data_file_path (str): The file path of the dataset to be processed.
            target_column (str): The column name to check for duplicates, defaulting to 'Phone'.
            temp_file (StringIO): Temporary file used for processing data for database insertion.
            required_columns (set): Set of column names required for the deduplication process.
            optional_columns (list): List of column names that are optional in the dataset.
            optional_columns_db (list): List of optional column names formatted for database insertion.
            connection_params (dict): Parsed database connection parameters.
            connection (psycopg2.connection): Database connection object.
            cursor (psycopg2.cursor): Database cursor for executing SQL commands.
            duplicates (pd.DataFrame): DataFrame containing identified duplicate entries.

        Methods:
            dedupe(): Orchestrates the deduplication process and returns a summary report.
            __create_job_dir(): Creates a directory for storing job-related files.
            __read_data_file(): Reads the dataset from the specified file path into a DataFrame.
            __check_required_columns(): Ensures all required columns are present in the dataset.
            __check_optional_columns(): Adds missing optional columns to the DataFrame with default values.
            __remove_extra_columns(): Removes columns from the DataFrame that are not required or optional.
            __parse_database_uri(): Parses the database connection string into connection parameters.
            __get_duplicates(): Identifies duplicate entries in the dataset based on the target column.
            __prepare_data(): Prepares the dataset for deduplication and/or database insertion.
            __initialize_database_connection(): Initializes the database connection.
            __execute_sql(sql): Executes a given SQL command using the database connection.
            __insert_temp_data(): Inserts processed data into a temporary database table.
            __join_tables(): Joins temporary data with the main dataset to identify duplicates.
            __remove_duplicates_from_temp_table(): Removes duplicates from the temporary table.
            __insert_into_main_data_table(): Inserts deduplicated data from the temporary table into the main dataset table.
            __reset_temp_data_table(): Resets the temporary table for subsequent operations.
            __get_duplicates_table(): Retrieves duplicate entries from the database.
            __save_clean_data(): Saves the processed and deduplicated data to a file.
            __generate_report(): Generates a report summarizing the deduplication results.
        """
        self.job_id = get_current_job().id
        self.add_to_db = add_to_db
        self.db_string = db_string
        self.dataframe: pd.DataFrame = pd.DataFrame({})
        self.dataframe_to_insert: pd.DataFrame = pd.DataFrame({})
        self.data_file_path = data_file_path
        self.target_column = target_column
        self.temp_file = StringIO()
        self.column_specs = column_specs
        self.required_columns = []
        self.required_labels = []
        self.optional_labels = []
        self.total_rows = 0
        self.target_label = None
        self.optional_columns = []
        self.target_column = None
        self.primary_key = None
        self.table_name = table_name
        for column_name, details in column_specs.items():
            if details.get('specs', {}).get('primary_key', False):
                self.primary_key = column_name
            else:
                if details.get('required', False):
                    self.required_columns.append(column_name)
                    self.required_labels.append(details.get('label', ''))
                else:
                    self.optional_columns.append(column_name)
                    self.optional_labels.append(details.get('label', ''))

            if details.get('target', False):
                self.target_column = column_name
                self.target_label = details.get('label', '')
        print(self.required_labels, self.required_columns, self.required_labels, self.required_columns, self.target_label, self.target_column, self.primary_key, sep='\n')
        self.optional_columns_db = []
        self.__create_job_dir()
        self.__read_data_file()
        self.__clean_data_v2()
        self.dataframe_to_insert = self.dataframe.copy()
        self.__initialize_database_connection()

    def dedupe(self):
        self.__check_required_columns()

        self.__check_optional_columns()

        self.__prepare_data()

        self.__insert_temp_data()

        self.__join_tables()

        if self.add_to_db:
            self.__remove_duplicates_from_temp_table()
            self.__insert_into_main_data_table()
            self.__save_clean_data()

        self.__reset_temp_data_table()

        return self.__generate_report()

    def __create_job_dir(self):
        try:
            os.mkdir('/jobs/' + self.job_id)
        except Exception as e:
            raise ErrorCreatingJobDir(e)

    def __read_data_file(self):
        try:
            self.dataframe = pd.read_csv(self.data_file_path, dtype=str)
            self.dataframe = self.dataframe.dropna(how='all')
            self.dataframe_to_insert = self.dataframe.copy()
        except Exception as e:
            raise ErrorReadingDataFile(e)

    def __clean_data_v2(self):
        """Cleans the DataFrame according to predefined rules in column_specs using vectorized operations."""
        # Initialize a Series to mark rows for deletion
        self.dataframe['_delete'] = False
        self.total_rows = len(self.dataframe)
        invalid_first_names = 0
        invalid_last_names = 0
        for column_name, specs in self.column_specs.items():
            label = specs.get('label')
            if label not in self.dataframe.columns:
                continue  # Skip if column not in DataFrame

            rules = specs.get('cleaning_rules', {})
            required = specs.get('required', False)

            # Start applying rules vectorized over the whole column
            column_data = self.dataframe[label].fillna('')  # Replace NaN with empty string

            # Vectorized application of rules
            if rules.get('remove_zeros'):
                column_data = column_data.str.replace('0', '')
            if rules.get('remove_spaces'):
                column_data = column_data.str.replace(' ', '')
            if 'allowed_special_chars' in rules:
                allowed = rules['allowed_special_chars']  # Add alphabets to allowed characters
                regex_pattern = f'[^{allowed}\\w]'
                column_data = column_data.str.replace(regex_pattern, '', regex=True)
            if rules.get('remove_special_chars'):
                column_data = column_data.str.replace(r'[^\w\s]', '', regex=True)
            if rules.get('alphanumeric_only'):
                column_data = column_data.str.replace(r'[^\w]', '', regex=True)
            if rules.get('valid_email'):
                # Applying email validation rule (example using str.match, adjust as needed)
                valid_emails = column_data.str.match(r"^[\w\-\.]+@([\w\-]+\.)+[\w\-]{2,4}$")
                column_data = column_data.where(valid_emails, '')
            '''
            # Apply custom functions for more complex rules (like valid_first_name)
            if rules.get('valid_first_name'):
                column_data = column_data.apply(self.apply_valid_first_name_rule)
            if rules.get('valid_last_name'):
                column_data = column_data.str.replace(r"[^a-zA-Z \-']", '', regex=True)
            '''
            if rules.get('valid_first_name'):
                # Define your custom conditions for valid first names here
                # Example: length conditions and allowed characters (modify according to your rules)
                is_valid = column_data.str.len() >= 3 | column_data.isin(['Jo', 'Ed'])
                is_valid &= column_data.str.match(r'^[a-zA-Z \-]+$')  # Only letters and spaces allowed
                invalid_first_names += (~is_valid).sum()
                column_data = column_data.where(is_valid, '')

            if rules.get('valid_last_name'):
                # Define your custom conditions for valid last names here
                # Example: allowed characters
                is_valid = column_data.str.match(r"^[a-zA-Z \-']+$")  # Only letters, spaces, hyphens, and apostrophes allowed
                invalid_last_names += (~is_valid).sum()
                column_data = column_data.where(is_valid, '')
            # Enforce length constraints vectorized
            if rules.get('valid_dob'):
                valid_dates = pd.to_datetime(column_data, errors='coerce', exact=False)
                # Format valid dates to 'YYYY-MM-DD'. Invalid dates remain as NaT
                formatted_dates = valid_dates.dt.strftime('%Y-%m-%d')
                # Replace NaT with None for compatibility with PostgreSQL NULL
                column_data = formatted_dates.where(valid_dates.notna() & (column_data != ''), r"\N")
                print(column_data)
            if 'exact_length' in rules:
                column_data = column_data.where(column_data.str.len() == rules['exact_length'], '')
            if 'min_length' in rules:
                column_data = column_data.where(column_data.str.len() >= rules['min_length'], '')
            if 'max_length' in rules:
                column_data = column_data.where(column_data.str.len() <= rules['max_length'], '')
            if 'starts_with' in rules:
                column_data = column_data.where(column_data.str.startswith(rules['starts_with']), '')

            # Assign cleaned data back to DataFrame
            self.dataframe[label] = column_data

            # Mark rows for deletion where required fields are empty
            if required:
                self.dataframe['_delete'] |= self.dataframe[label].eq('')

        # Finally, delete marked rows and drop the marker column
        self.dataframe = self.dataframe.loc[~self.dataframe['_delete']]
        self.dataframe.drop(columns=['_delete'], inplace=True)
        if (invalid_first_names) / (
                self.total_rows) > 0.1:  # Check total percentage against threshold
            #raise ValueError("File rejected: More than 10% of names are invalid.")
            pass

    def apply_valid_first_name_rule(self, cell_value):
        """Applies specific rules for validating first names."""
        cell_value = re.sub(r'[^a-zA-Z ]', '', cell_value)  # Only allow letters and spaces
        if len(cell_value) < 3 and cell_value not in ['Jo', 'Ed']:
            return ''  # Invalidate name if it does not meet exceptions
        return cell_value

    def is_valid_email(self, email):
        """Validates if the given string is a valid email."""
        # You can enhance this function as needed
        print('test')
        return re.match(r"[^@]+@[^@]+\.[^@]+", email) is not None

    def __check_required_columns(self):
        print(self.required_labels)
        if not set(self.required_labels).issubset(self.dataframe):
            raise MissingRequiredColumns("Required columns missing: " + ", ".join(self.required_labels))

    def __check_optional_columns(self):
        for column in self.optional_labels:
            if column not in self.dataframe_to_insert:
                self.dataframe_to_insert[column] = ''

    def __remove_extra_columns(self):
        cols = self.dataframe_to_insert.columns
        cols_to_insert = self.optional_labels + self.required_labels
        difference = [x for x in cols if x not in cols_to_insert]
        self.dataframe_to_insert.drop(columns=difference, inplace=True)

    def __parse_database_uri(self):
        """
        Parses a PostgreSQL URI and returns the connection parameters as a dictionary.

        Parameters:
        uri (str): The PostgreSQL connection URI.
        """
        # Remove the 'postgresql+psycopg2://' prefix
        uri_body = self.db_string.split("://")[1]

        # Extract user:password, host:port, and dbname
        user_password, host_port_dbname = uri_body.split("@")
        user, password = user_password.split(":")
        host_port, dbname = host_port_dbname.split("/")
        host, port = host_port.split(":")

        # Construct the dictionary
        self.connection_params = {
            "database": dbname,
            "host": host,
            "user": user,
            "password": password,
            "port": port
        }

    def __get_duplicates(self):
        duplicates_indexes = self.dataframe.duplicated(subset=self.target_label, keep='first')
        duplicates = self.dataframe[duplicates_indexes.values].copy()
        self.duplicates = duplicates[self.required_labels]

    def __prepare_data(self):
        self.__remove_extra_columns()
        if self.add_to_db:
            self.dataframe_to_insert.drop_duplicates(subset=self.target_label, keep='first', inplace=True)
        else:
            self.dataframe_to_insert = self.dataframe_to_insert[[self.target_label]]
        self.dataframe_to_insert.replace('\n', '\t', inplace=True, regex=True)

    def __initialize_database_connection(self):
        self.__parse_database_uri()
        self.connection = psycopg2.connect(**self.connection_params)
        self.cursor = self.connection.cursor()

    def __execute_sql(self, sql):
        self.cursor.execute(sql)
        self.connection.commit()

    def __get_columns(self):
        return self.optional_columns + self.required_columns

    def __get_labels(self):
        return self.optional_labels + self.required_labels
    def __insert_temp_data(self):
        self.dataframe_to_insert[self.__get_labels() if self.add_to_db else self.target_label].to_csv(self.temp_file, index=False, header=False, na_rep='', mode='w', line_terminator='\n')
        self.temp_file.seek(0)
        if self.add_to_db:
            print(self.dataframe_to_insert['DOB'])
            self.cursor.copy_from(self.temp_file, table='temp_data', sep=',', columns=tuple(self.__get_columns()))
        else:
            self.cursor.copy_from(self.temp_file, table='temp_data', sep=',', columns=(self.target_column,))
        self.temp_file.truncate(0)
        self.temp_file.close()
        self.connection.commit()
        del self.dataframe_to_insert

    def __join_tables(self):
        sql_parts = []
        for column in self.required_columns:
            sql_parts.append(f"public.temp_data.{column}")
        select_clause = ', '.join(sql_parts)
        sql = f'''select {select_clause} into duplicates from public.temp_data inner join public.{self.table_name} on public.temp_data.{self.target_column} = public.{self.table_name}.{self.target_column}'''
        self.__execute_sql(sql)

    def __remove_duplicates_from_temp_table(self):
        sql = f'''delete from public.temp_data where public.temp_data.{self.target_column} in (select public.duplicates.{self.target_column} from public.duplicates)'''
        self. __execute_sql(sql)

    def __insert_into_main_data_table(self):
        sql = f"insert into public.{self.table_name} ({', '.join(self.__get_columns())}) (select {', '.join(self.__get_columns())} from public.temp_data)"
        self.__execute_sql(sql)

    def __reset_temp_data_table(self):
        sql = 'truncate table public.temp_data RESTART IDENTITY'
        self.__execute_sql(sql)

    def __get_duplicates_table(self):
        sql = f'select {self.target_column} as "{self.target_label}" from public.duplicates'
        self.cursor.execute(sql)
        return self.cursor.fetchall()

    def __save_clean_data(self):
        outfile = open('/jobs/' + get_current_job().id + '/result.csv', 'w')
        self.cursor.copy_to(outfile, table='temp_data', sep=',', columns=tuple(self.__get_columns()))
        outfile.close()

    def __generate_report(self):
        data = [str(row[0]) for row in self.__get_duplicates_table()]
        self.dataframe['Result'] = np.where(self.dataframe.duplicated(subset=self.target_label, keep=False), 2, 0)
        self.dataframe['Result'] = np.where(self.dataframe[self.target_label].isin(data) & (self.dataframe['Result'] == 0), 1, self.dataframe['Result'])
        self.dataframe['Result'] = np.where(self.dataframe[self.target_label].isin(data) & (self.dataframe['Result'] == 2), 3, self.dataframe['Result'])
        self.dataframe['Result'].replace({0: "Unique", 1: "Duplicate", 2: "In-file", 3: "In-file & DB"}, inplace=True)
        self.dataframe.to_csv('/jobs/' + get_current_job().id + '/report.csv', index=False, na_rep='', mode='w')
        self.__execute_sql('drop table if exists duplicates')
        indicator_counts = self.dataframe['Result'].value_counts().to_dict()
        indicator_percentages = (self.dataframe['Result'].value_counts(normalize=True) * 100).to_dict()
        total_rows = len(self.dataframe)
        unique_infile_count = self.dataframe[self.dataframe['Result'] == "In-file"].duplicated(subset=self.target_label, keep='first').sum()
        unique_infile_db_count = self.dataframe[self.dataframe['Result'] == "In-file & DB"].duplicated(subset=self.target_label, keep='first').sum()
        print([indicator_counts, indicator_percentages, total_rows, unique_infile_count, unique_infile_db_count, self.total_rows])
        return (get_current_job().meta['name'] if 'name' in get_current_job().meta else "",
                [indicator_counts, indicator_percentages, total_rows, unique_infile_count, unique_infile_db_count, self.total_rows])


