import getpass
import logging
import logging.config
import logging.handlers

import yaml
import arcpy

# Initialize configurations
username = getpass.getuser()
user_email = f"{username}@bouldercolorado.gov"

with open(r'.\impervious-surfaces\config.yaml') as config_file:
    config = yaml.safe_load(config_file.read())
    logging.config.dictConfig(config['logging'])

read_conn = config['connections']['read']
edit_conn = config['connections']['edit']
arcpy.env.workspace = read_conn

# Define order for intersecting layers, and relevant queries for each
layers = {'GISPROD3.PW.PWMaintenanceArea': {
    'order': 0,
    'query': "FACILITYTYPE = 'Median' AND SURFTYPE = 'Hard'"
        },
    'GISPROD3.PW.Building': {'order': 1, 'query': ''},
    'GISPROD3.PW.RoadArea': {'order': 2, 'query': ''},
    'GISPROD3.PW.ParkingLot': {
    'order': 3, 'query': "SURFACETYPE = 'Impervious'"
        },
    'GISPROD3.PW.Driveway': {'order': 4, 'query': ''},
    'GISPROD3.PW.SidewalkArea': {'order': 5, 'query': ''},
    'GISPROD3.PW.ImperviousMisc': {'order': 6, 'query': ''}
}

# Move through each layer
for layer in sorted(layers, key=lambda x: layers[x]['order']):
    query = "LIFECYCLE = 'Active'"
    if layers[layer]['query']:
        query += ' AND ' + layers[layer]['query']
