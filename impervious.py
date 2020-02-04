import os
import shelve
import getpass
import logging
import logging.config
import logging.handlers

import yaml
import arcpy


class Impervious:
    def __init__(self, lyr):
        self.name = list(lyr)[0]
        self.location = os.path.join(read_conn, "PW.PWAREA")
        self.path = os.path.join(self.location, self.name)
        self.query = lyr[self.name]
        self.rows = self.rows()
        self._desc = arcpy.Describe(self.path)

    def __getattr__(self, item):
        """Pass any other attribute or method calls through to the
        underlying Describe object"""
        return getattr(self._desc, item)

    def __hash__(self):
        return hash(self.__key())

    def __key(self):
        """Creates a tuple ordered by GLOBALIDs, used for hash comparisons."""

        attributes = [(r["GLOBALID"], r["SHAPE@WKT"]) for r in self.rows]
        key = tuple(sorted(attributes, key=lambda y: y[0]))
        return key

    def rows(self):
        """Returns a list of tuples representing (GLOBALID, SHAPE) pairs."""

        fields = ["GLOBALID", "SHAPE@WKT"]
        rows = []

        with arcpy.da.SearchCursor(self.path, fields, self.query) as cursor:
            for row in cursor:
                r = {fields[i]: row[i] for i in range(len(fields))}
                rows.append(r)

        return rows

    def store_current(self):
        """Stores the __key() of a table for hash comparisons."""
        with shelve.open('.\\log\\previous_run', 'c') as db:
            db[self.name] = self.__key()

    def equals_previous(self):
        """Compares the current table to the previous run to ID changes."""
        try:
            with shelve.open('.\\log\\previous_run', 'c') as db:
                previous = db[self.name]
            if hash(self) == hash(previous):
                return True
            else:
                return False
        except KeyError:
            self.store_current()

    def memory_fc(self, template_fc):
        """Creates a feature class in memory based off of template schema."""
        fc = arcpy.CreateFeatureclass_management("in_memory",
                                                 self.name.split('.')[-1],
                                                 "POLYGON",
                                                 template=template_fc)
        arcpy.Append_management(
            self.path, fc, "NO_TEST", expression=self.query)

        with arcpy.da.UpdateCursor(fc, ["ORIGIN"]) as cursor:
            for row in cursor:
                row[0] = self.name
                cursor.updateRow(row)

        return fc


def main(lyrs):
    # Define the output layer
    original = os.path.join(edit_conn, "GISPROD3.PW.ImperviousSurface")

    # Instantiate each layer as an Impervious class
    impervious_features = [Impervious(layer) for layer in lyrs]
    equals_previous = [imp.equals_previous() for imp in impervious_features]

    # See if any changes have been made to the layers involved
    if all(equals_previous):
        log.info("None of the layers have changed since the previous run...")
    else:
        log.info("Creating a new ImperviousSurface layer...")
        temp = impervious_features[0].memory_fc(original)
        for surf in impervious_features[1:]:
            log.info(f"Updating ImperviousSurface with {surf.name}...")
            temp = arcpy.Update_analysis(
                temp, surf.memory_fc(original),
                f"memory\\{surf.name.split('.')[-1]}Update")

        log.info("Loading new impervious surfaces into feature class...")
        with arcpy.da.UpdateCursor(original, ['GLOBALID']) as cursor:
            for row in cursor:
                cursor.deleteRow()

        arcpy.Append_management(temp, original, "NO_TEST")


if __name__ == '__main__':
    # Initialize configurations
    with open(r'.\config.yaml') as config_file:
        config = yaml.safe_load(config_file.read())
        logging.config.dictConfig(config['logging'])

    read_conn = config['connections']['read']
    edit_conn = config['connections']['edit']

    # Initialize the logger for this file
    log = logging.getLogger(__name__)

    username = getpass.getuser()
    log.info(f"Started by {username}...")

    # Define order for intersecting layers, and relevant queries for each
    # Dicts within a list helps enforce ordering
    layers = [{"GISPROD3.PW.ImperviousMisc": ""},
              {"GISPROD3.PW.SidewalkArea": ""},
              {"GISPROD3.PW.Driveway": "LIFECYCLE = 'Active'"},
              {"GISPROD3.PW.ParkingLot":
               "LIFECYCLE = 'Active' AND SURFACETYPE = 'Impervious'"},
              {"GISPROD3.PW.RoadArea": "LIFECYCLE = 'Active'"},
              {"GISPROD3.PW.Building": "LIFECYCLE = 'Active'"},
              {"GISPROD3.PW.PWMaintenanceArea":
               "LIFECYCLE = 'Active' AND FACILITYTYPE = 'Median' AND SURFTYPE = 'Hard'"}]
    try:
        main(layers)
    except Exception:
        log.exception("Something prevented the script from running")
