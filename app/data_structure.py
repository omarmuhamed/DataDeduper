from . import db


column_specs = {
    'id': {
        'type': db.Integer,
        'specs': {'primary_key': True, 'nullable': False},
        'label': 'ID',
        'required': False,
        'cleaning_rules': {}
    },
    'title': {
        'type': db.String(10),
        'specs': {},
        'label': 'Title',
        'required': False,
        'cleaning_rules': {'remove_zeros': True, 'remove_special_chars': True}

    },

    'first_name': {
        'type': db.String(50),
        'specs': {},
        'label': 'First Name',
        'required': False,
        'cleaning_rules': {'valid_first_name': True}
    },
    'last_name': {
        'type': db.String(50),
        'specs': {},
        'label': 'Last Name',
        'required': False,
        'cleaning_rules': {'valid_last_name': True}

    },
    'phone': {
        'type': db.BigInteger,
        'specs': {'nullable': False},
        'label': 'Phone',
        'required': True,
        'target': True,
        'cleaning_rules': {'exact_length': 10, 'starts_with': '7'},
        'filter_type': 'num'
    },
    'email': {
        'type': db.Text,
        'specs': {},
        'label': 'Email',
        'required': False,
        'cleaning_rules': {'valid_email': True}
    },
    'address': {
        'type': db.Text,
        'specs': {},
        'label': 'Address',
        'required': False,
        'cleaning_rules': {'allowed_special_chars': " .'\-/\\\\"}
    },
    'city': {
        'type': db.Text,
        'specs': {},
        'label': 'City',
        'required': False,
        'cleaning_rules': {'allowed_special_chars': " .'\-/\\\\"}
    },
    'postcode': {
        'type': db.String(10),
        'specs': {},
        'label': 'Postcode',
        'required': False,
        'cleaning_rules': {'max_length': 8, 'min_length': 5, 'alphanumeric_only': True, 'remove_spaces': True}
    },
    'dob': {
        'type': db.Date,
        'specs': {},
        'label': 'DOB',
        'required': False,
        #'cleaning_rules': {'min_length': 4, 'max_length': 10, 'allowed_special_chars': '/\-'},
        'cleaning_rules': {'valid_dob': True},
        'filter_type': 'date'
    },
    'supplier_name': {
        'type': db.Text,
        'specs': {'nullable': False},
        'label': 'Supplier',
        'required': True,
        'cleaning_rules': {'min_length': 1, 'alphanumeric_only': True}
    },
    'bsc': {
        'type': db.String(10),
        'specs': {},
        'label': 'BSC',
        'required': False,
        'cleaning_rules': {'max_length': 8}
    },
    'delivery': {
        'type': db.String(10),
        'specs': {},
        'label': 'Delivery',
        'required': False,
        'cleaning_rules': {}
    }
}