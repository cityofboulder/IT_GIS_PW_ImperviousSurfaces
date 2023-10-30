import functools
import logging.config
import json
import keyring
import shelve
import time
from hashlib import sha256
from pathlib import Path

import geopandas as gpd
import sqlalchemy as sa
from sqlalchemy import create_engine

# Data path to hashes from previous runs
HASH_FILE = Path('data', 'hashes')

# Read in the logging configuration
with open('config.json', 'r') as config_file:
    cfg = json.load(config_file)
    logging.config.dictConfig(cfg)
    log = logging.getLogger(__name__)


def measure_time(func):
    def wrapper(*args, **kwargs):
        log.debug(f"Entering '{func.__name__}'")
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        log.debug((f"Function '{func.__name__}' executed in "
                   f"{execution_time:.1f} seconds"))
        return result
    return wrapper


class Surface:
    def __init__(self, sql_file: Path) -> None:
        self.sql_file = sql_file
        self.name = self.sql_file.stem
        self._query = self.query
        self._cnxn = self.cnxn
        self._gdf = self.gdf

    def __hash__(self) -> int:
        """Create a unique hash value for the table"""
        serial_obj = self.__key()
        sha256_hash = sha256(str(serial_obj).encode()).hexdigest()
        return int(sha256_hash, 16)

    def __key(self) -> tuple:
        """Create a hashable object representing the SQL table."""
        # Extract the each record's polygon coordinates as text
        to_hash = self.gdf.copy()
        to_hash['wkb'] = to_hash.geometry.to_wkb()

        # Create a tuple of tuples, sorted by uid with wkt as an attribute
        tmp = list(to_hash[['guid', 'wkb']].itertuples(index=False, name=None))
        key = tuple(sorted(tmp, key=lambda x: x[0]))

        return key

    @property
    def query(self):
        """Return the query written in the surface's sql file."""
        with open(self.sql_file, "r") as f:
            query = f.read()
        return query

    @property
    def cnxn(self):
        """Create a SQLAlchemy engine to facilitate a database connection."""
        conn_str = ('mssql+pyodbc://sqlprod19gis/GISPROD3'
                    '?driver=SQL Server'
                    '&Trusted_Connection=yes')
        engine = create_engine(conn_str)
        return engine

    @functools.cached_property
    def gdf(self):
        """
        Retrieve a GeoDataFrame from a SQL database.

        This property connects to a SQL database using SQLAlchemy. The
        property assumes that the geometry column is called 'geometry' within
        the query. A connections is automatically opened and closed for each
        call to this property.

        Returns:
        geopandas.GeoDataFrame: The GeoDataFrame containing the queried data.
        """
        with self._cnxn.connect() as con:
            sql_kwargs = {
                'sql': self._query,
                'con': con,
                'geom_col': 'geometry',
                'crs': 2876
            }
            gdf = gpd.read_postgis(**sql_kwargs)
        log.info(f'Extracted {len(gdf):,} records from {self.name}')
        return gdf

    def store_hash(self):
        """Store the hash value to a file on disk"""
        with shelve.open(str(HASH_FILE), 'c') as db:
            db[self.name] = hash(self)

    def equals_previous(self):
        """Compare this hash to the previous, if it exists."""
        # Retrieve previous hash value if it was stored previously
        try:
            with shelve.open(str(HASH_FILE), 'c') as db:
                previous = db[self.name]
            if hash(self) == previous:
                equals_prev = True
            else:
                log.info(f'Changes detected in {self.name}')
                equals_prev = False
        except KeyError:
            log.warning(f'Missing stored hashes for {self.name}')
            equals_prev = False

        return equals_prev


class GeoSQL:
    def __init__(self, server, db, user, pwd, schema, table) -> None:
        self.server = server
        self.db = db
        self.user = user
        self.pwd = pwd
        self.schema = schema
        self.table = table
        self._cnxn = self.cnxn

    # Decorator to handle SQL transactions
    def sql_transaction(func):
        def wrapper(self, *args, **kwargs):
            with self._cnxn.connect() as con:
                try:
                    result = func(self, con, *args, **kwargs)
                    con.commit()
                    log.info('Successfully committed the transaction')
                    return result
                except Exception:
                    con.rollback()
                    log.exception("An error occurred")
        return wrapper

    @property
    def cnxn(self):
        """Create a SQLAlchemy engine to facilitate a database connection."""
        conn_str = (f'mssql+pyodbc://{self.user}:{self.pwd}'
                    f'@{self.server}/{self.db}'
                    '?driver=SQL Server')
        engine = create_engine(conn_str)
        return engine

    @sql_transaction
    @measure_time
    def insert(self, con, gdf) -> None:
        """
        Inserts values into the table.

        Parameters:
            con (sa.Connection): SQLAlchemy database connection.
            gdf (gpd.GeoDataFrame): A GeoDataFrame with a column named 'shape'
                containing the geometry as WKT.

        Returns:
            None
        """
        # Get rows as dicts
        rows = gdf.to_dict(orient='records')
        log.info(f'Attempting to add {len(rows):,} to the target table')

        # Initialize the insert statement
        insert = (f"INSERT INTO {self.schema}.{self.table} "
                  "(OBJECTID, GUID, SURFTYPE, SHAPE) VALUES ")

        # Obtain values to add
        values = []
        for idx, row in enumerate(rows):
            value = (f"({idx + 1}, '{row['guid']}', '{row['surftype']}', "
                     f"geometry::STGeomFromText('{row['shape']}', 2876))")
            values.append(value)
            if (idx + 1) % 1000 == 0 or (idx + 1) == len(gdf):
                # Build the insert statement and execute
                log.debug(f'Inserting rows up to record {idx + 1:,}')
                sql_stmt = sa.text(insert + ', '.join(values))
                con.execute(sql_stmt)
                values = []

    @sql_transaction
    @measure_time
    def truncate(self, con):
        """
        Truncates the table.

        Parameters:
            con (sa.Connection): SQLAlchemy database connection.

        Returns:
            None
        """
        log.info('Truncating the destination SQL table')
        sql_stmt = sa.text(f"TRUNCATE TABLE {self.schema}.{self.table};")
        con.execute(sql_stmt)


def get_creds(service: str, acct: str) -> dict:
    """
    Check and store account credentials.

    Parameters:
    -----------
    service: str
        The account's service name in keyring.
    acct: str
        The account name.

    Returns:
    --------
    dict
        A dictionary containing the username and password. Retreives the
        password from the keyring for the given account. If the account is
        not provided or the password for the account could not be found in
        the keyring, it will return None.
    """
    creds = dict()
    creds["username"] = acct

    if acct:
        kring = keyring.get_password(service, acct)
        if not kring:
            log.critical(("The password for this account could "
                          "not be found in the keyring under the service "
                          f"named '{service}'. Try again."))
            return None
        creds['password'] = kring
    else:
        msg = ("You did not provide an account to log in to the",
               f"{service} service. Try again.")
        log.critical(*msg)
        return None

    return creds
