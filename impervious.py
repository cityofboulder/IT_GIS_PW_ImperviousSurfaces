import functools
import json
import logging.config
import shelve
import time
from hashlib import sha256
from pathlib import Path

import geopandas as gpd
import keyring
import sqlalchemy as sa
from arcpy import Append_management, TruncateTable_management
from shapely.geometry import Polygon
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
    def __init__(self, sql_file: Path,
                 db_user: str,
                 db_pass: str) -> None:
        self.sql_file = sql_file
        self.db_user = db_user
        self.db_pass = db_pass
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
        # Check if the user and password are provided
        if self.db_user and self.db_pass:
            conn_str = (f'mssql+pyodbc://{self.db_user}:{self.db_pass}'
                        f'@sqlprod19gis/GISPROD3'
                        '?driver=SQL Server')
        else:
            # Use the default connection string with trusted connection
            # for Windows authentication
            # Note: This assumes that the user has the necessary permissions
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


class Parcel(Surface):
    def __init__(self, sql_file: Path,
                 db_user: str,
                 db_pass: str) -> None:
        super().__init__(sql_file, db_user=db_user, db_pass=db_pass)
        self._cleansed = self.cleansed

    @functools.cached_property
    def cleansed(self) -> gpd.GeoDataFrame:
        """Removes parcels, such as condo boxes, which are completely contained
        in other parcels.

        Note: Converts all geometries to singlepart.

        Returns
        -------
        geopandas.GeoDataFrame
        """
        # Explode the geos so they are singlepart and easier to manipulate
        log.debug('Exploding parcel geometries.')
        exploded = self.gdf.explode(ignore_index=True)

        # Add a flag for whether a geometry contains other geometries
        log.debug('Labelling container parcels.')
        exploded['CONTAINER'] = exploded.geometry.apply(
            lambda x: len(x.interiors) > 0)

        # Create a geodataframe of parcel exteriors
        log.debug('Saving exteriors.')
        exteriors = gpd.GeoDataFrame(
            data=exploded.drop(['geometry'], axis=1),
            geometry=exploded.geometry.exterior.apply(lambda x: Polygon(x))
        )

        # Separate containers and non-containers into their own geodataframes
        log.debug('Parsing containers and non-containers.')
        container_cond = (exteriors['CONTAINER'] == 1)
        containers = exteriors[container_cond]
        compares = exteriors[~container_cond]

        # Perform a spatial join to help find the parcels that are not
        # parcelitos or containers
        log.debug('Identifying parcelitos.')
        sjoin = compares.sjoin(containers,
                               predicate='within',
                               how='left',
                               lsuffix='parcel',
                               rsuffix='container')
        idx = sjoin[sjoin['index_container'].isna()].index

        # Combine containers and non-parcelito parcels
        log.debug('Combinging containers and non-parcelito parcels.')
        cleansed = gpd.pd.concat([containers, exteriors.loc[idx]])
        return cleansed

    def impervious_metrics(self, surfaces: gpd.GeoDataFrame):
        """Enrich each parcel with information about pervious and imperious
        coverage.

        Parameters
        ----------
        surfaces : gpd.GeoDataFrame
            The geodataframe containing impervious surfaces

        Returns
        -------
        geopandas.GeoDataFrame
        """
        # Spatial join of parcels and impervious surfaces
        log.debug('Joining surfaces to cleansed parcels.')
        parcels = self._cleansed.copy()
        parcels['geoms'] = parcels.geometry
        sjoin = surfaces.sjoin(parcels,
                               lsuffix='imperv',
                               rsuffix='parcel')

        # Intersect parcel boundaries with srface boundaries
        log.debug('Finding intersecting geometries.')
        geoms = sjoin['geoms'].buffer(0)
        sjoin['intersection'] = sjoin.geometry.intersection(geoms)

        # Calculate impervious area per parcel
        log.debug('Calculating the area of every intersected geometry.')
        sjoin['IMPERVAREA'] = round(sjoin['intersection'].area)

        # Create new parcel layer with impervious area
        log.debug('Enriching parcels with impervious area.')
        parcel_enrich = gpd.GeoDataFrame(
            data=sjoin[['GUID', 'SURFTYPE', 'IMPERVAREA', 'COBPIN']],
            geometry=sjoin['geoms']
        )

        # Dissolve by COBPIN
        log.debug('Dissolving features by COBPIN.')
        dissolve = parcel_enrich.dissolve(by=['COBPIN'],
                                          aggfunc={
                                              'IMPERVAREA': 'sum'}
                                          ).reset_index()
        log.debug('Calculating pervious area.')
        dissolve['PERVAREA'] = round(
            dissolve['geometry'].area) - dissolve['IMPERVAREA']

        return dissolve


class GeoSQL:
    def __init__(self, server, db, user, pwd, schema, table, sde_conn=None):
        self.server = server
        self.db = db
        self.user = user
        self.pwd = pwd
        self.schema = schema
        self.table = table
        self.sde_conn = sde_conn
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

    @measure_time
    def insert_arcpy(self, input):
        if self.sde_conn:
            # Get the full SDE path to the layer
            sde_name = Path(self.sde_conn,
                            f'{self.db}.{self.user}.{self.table}')

            # Convert the file path to a string
            if isinstance(input, Path):
                input = str(input.absolute())

            append_opts = {
                'inputs': input,
                'target': str(sde_name.absolute()),
                'schema_type': 'NO_TEST'
            }
            return Append_management(**append_opts)
        else:
            log.warning('No sde connection file provided. Skipping insert.')

    @measure_time
    def truncate_arcpy(self):
        if self.sde_conn:
            # Get the full SDE path to the layer
            sde_name = Path(self.sde_conn,
                            f'{self.db}.{self.user}.{self.table}')

            return TruncateTable_management(in_table=str(sde_name.absolute()))
        else:
            log.warning('No sde connection file provided. Skipping truncate.')

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
