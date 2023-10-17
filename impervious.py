import functools
import shelve
from hashlib import sha256
from pathlib import Path

import geopandas as gpd
from sqlalchemy import create_engine

# Data path to hashes from previous runs
HASH_FILE = Path('data', 'hashes')


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
            equals_prev = True if hash(self) == previous else False
        # Store the current hash value if it has never been stored
        except KeyError:
            equals_prev = False

        return equals_prev
