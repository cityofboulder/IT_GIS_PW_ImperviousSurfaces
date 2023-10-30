import json
import logging.config
import numpy as np
import sys
from pathlib import Path

from impervious import Surface, GeoSQL, get_creds

DATA_PATH = Path('data')
QUERY_PATH = DATA_PATH / 'queries'
LAYER_ORDER = ('maintenance_areas',
               'buildings',
               'road_areas',
               'parking_lots',
               'driveways',
               'sidewalk_areas',
               'impervious_misc')

# Read in the logging configuration
email_creds = get_creds('email', 'noreply-gis')
with open('config.json', 'r') as config_file:
    cfg = json.load(config_file)
    cfg['handlers']['email']['credentials'] = [
        f"{email_creds['username']}@bouldercolorado.gov",
        email_creds['password']
    ]
    logging.config.dictConfig(cfg)
    log = logging.getLogger(__name__)

if __name__ == '__main__':
    try:
        # Retreive credentials from keyring
        db_creds = get_creds('gis', 'pw')

        # Get all surfaces into one list ordered by importance
        log.info('Starting SQL queries')
        surfaces = [Surface(QUERY_PATH / f'{lyr}.sql') for lyr in LAYER_ORDER]

        # Check if any of the layers changed
        log.info('Checking current layers against previous hashes')
        changes = list(filter(lambda x: not x.equals_previous(), surfaces))
        if not changes:
            log.info('No changes detected in impervious surfaces. Exiting.\n')
            sys.exit()

        # Start with the initial seed primary surface
        primary = surfaces[0].gdf
        log.info(f'Seeding the unioned geometry with {surfaces[0].name}')
        for surface in surfaces[1:]:
            log.info(f'Adding {surface.name} to the union')
            secondary = surface.gdf
            # Perform the overlay
            union = primary.overlay(secondary, how='union',
                                    keep_geom_type=True)

            # In places where the primary exists, we label the geometry with
            # the primary's attributes, otherwise, we label with the
            # secondary's attrs
            for attribute in ('guid', 'surftype'):
                union[attribute] = np.where(~union[f'{attribute}_1'].isna(),
                                            union[f'{attribute}_1'],
                                            union[f'{attribute}_2'])

            # Replace the primary layer with the unioned layer
            primary = union[['guid', 'surftype', 'geometry']].copy()
            primary.make_valid()
            del union
            del secondary

        # Dissolve by the attribute fields
        dissolved = primary.dissolve(by=['guid', 'surftype']).reset_index()
        final = dissolved.explode(ignore_index=True)
        final['shape'] = final['geometry'].to_wkt(rounding_precision=-1)

        # Save to disk
        final_fields = ['guid', 'surftype', 'geometry']
        final[final_fields].to_file(DATA_PATH / 'PseudoTopology.shp')

        # Load the gdf to SQL Server
        db_kwargs = {
            'server': 'sqlprod19gis',
            'db': 'GISReferenceData',
            'user': db_creds['username'],
            'pwd': db_creds['password'],
            'schema': 'PW',
            'table': 'ImperviousSurfaces'
        }
        ref_db = GeoSQL(**db_kwargs)

        # Remove all rows currently in the table
        ref_db.truncate()

        # Load the new ones in
        ref_db.insert(gdf=final)

        # Store changes for next run
        log.info('Storing hashes for next run')
        stored = [s.store_hash() for s in surfaces]
        log.info('Finished\n')
    except Exception:
        log.exception('Something prevented the script from running.\n')
