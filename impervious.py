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

read_conn = config['connection']['read']
edit_conn = config['connection']['edit']
arcpy.env.workspace = read_conn

fcs = arcpy.ListFeatureClasses(feature_dataset='PW.PWAREA')
