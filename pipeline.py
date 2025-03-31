import argparse
import json
import logging.config
import sys
from pathlib import Path

import numpy as np

from impervious import GeoSQL, Parcel, Surface, get_creds

DATA_PATH = Path('data')
QUERY_PATH = DATA_PATH / 'queries'
LAYER_ORDER = ('maintenance_areas',
               'buildings',
               'road_areas',
               'parking_lots',
               'driveways',
               'sidewalk_areas',
               'impervious_misc')
IMPERVIOUS_OUT = DATA_PATH / 'ImperviousSurfaces.shp'
PARCEL_OUT = DATA_PATH / 'ImperviousParcels.shp'

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

# Create parser with a description and arguments
description = (
    "Update an impervious surface topology in the GISReferenceData "
    "database. Update metrics about impervious coverage on parcel "
    "areas."
)
parser = argparse.ArgumentParser(
    description=description
)

# Add arguments
parser.add_argument(
    '-u', '--user',
    type=str,
    default=None,
    help=(
        "The username for database access. Default is None."
    )
)
parser.add_argument(
    '-p', '--password',
    type=str,
    default=None,
    help=(
        "The password for database access. Default is None."
    )
)
parser.add_argument(
    "-s", "--sde",
    type=str,
    help=(
        "The file path of the desired ESRI sde connection. The connection "
        "needs to have truncate and insert permissions to the feature "
        "classes in GISReferenceData."
    )
)

if __name__ == '__main__':
    try:
        # Retreive credentials from keyring
        db_creds = get_creds('gis', 'pw')

        # Parse arguments
        args = parser.parse_args()

        # Check that the sde connection file exists
        sde = Path(args.sde)
        if not sde.exists():
            log.critical('The SDE connection file cannot be found. Exiting.\n')
            sys.exit()

        # Get all surfaces into one list ordered by importance
        log.info('Starting SQL queries')
        surfaces = []
        for lyr in LAYER_ORDER:
            surface = Surface(QUERY_PATH / f'{lyr}.sql',
                              db_user=args.user,
                              db_pass=args.password)
            surfaces.append(surface)

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
            del union
            del secondary

        # Dissolve by the attribute fields
        log.info('Dissolving features buy guid and surftype.')
        dissolved = primary.dissolve(by=['guid', 'surftype']).reset_index()
        final = dissolved.explode(ignore_index=True)
        final['shape'] = final['geometry'].to_wkt(rounding_precision=-1)

        # Save to disk
        log.info('Saving ImperviousSurfaces to disk.')
        final.rename(columns={'guid': 'GUID', 'surftype': 'SURFTYPE'},
                     inplace=True)
        final_fields = ['GUID', 'SURFTYPE', 'geometry']
        final[final_fields].to_file(IMPERVIOUS_OUT)

        # Save to SQL
        log.info('Saving outputs to GISReferenceData.PW.ImperviousSurfaces.')
        db_kwargs = {
            'server': 'sqlprod19gis',
            'db': 'GISReferenceData',
            'user': db_creds['username'],
            'pwd': db_creds['password'],
            'schema': 'PW',
            'table': 'ImperviousSurfaces',
            'sde_conn': sde
        }
        sql_imperv = GeoSQL(**db_kwargs)
        sql_imperv.truncate_arcpy()
        sql_imperv.insert_arcpy(IMPERVIOUS_OUT)

        # Enrich parcels with impervious surface coverage
        log.info('Enriching parcels with impervious coverage info.')
        parcels_lyr = Parcel(QUERY_PATH / 'parcels.sql')
        parcels = parcels_lyr.impervious_metrics(final)
        log.info('Saving ImperviousParcels to disk.')
        parcels.to_file(PARCEL_OUT)

        # Save to SQL
        log.info('Saving outputs to GISReferenceData.PW.UtilityBillingAreas.')
        db_kwargs = {
            'server': 'sqlprod19gis',
            'db': 'GISReferenceData',
            'user': db_creds['username'],
            'pwd': db_creds['password'],
            'schema': 'PW',
            'table': 'UtilityBillingAreas',
            'sde_conn': sde
        }
        sql_parcels = GeoSQL(**db_kwargs)
        sql_parcels.truncate_arcpy()
        sql_parcels.insert_arcpy(PARCEL_OUT)

        # Store changes for next run
        log.info('Storing hashes for next run')
        stored = [s.store_hash() for s in surfaces]
        log.info('Finished\n')
    except Exception:
        log.exception('Something prevented the script from running.\n')
