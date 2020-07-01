import os
import shelve
import getpass
import logging
import logging.config
import logging.handlers
import smtplib
from time import sleep
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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
        fc = arcpy.CreateFeatureclass_management("temp.gdb",
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


def send_email(password: str, insert: str, recipients: list, *attachments):
    """
    Sends an email notification.

    Parameters
    ----------
    password : str
        The password for the City's noreply email
    insert : str
        The main body of the email
    recipients : list
        A list of recipients for which the email is intended
    attatchments : str
        Unlimited and optional number of file paths to attachments
    """

    # from/to addresses
    sender = 'noreply@bouldercolorado.gov'

    # message
    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['To'] = "; ".join(recipients)
    msg['Subject'] = "\N{Motorway} Impervious Surfaces \N{Motorway}"

    if attachments:
        for item in attachments:
            a = open(item, 'rb')
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(a.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment',
                            filename=item.split(os.sep).pop())
            msg.attach(part)

    body = f"""\
            <html>
                <body>
                    <p>
                    Dear Human,<br><br>
                    {insert}
                    </p>
                    <p>
                    Beep Boop Beep,<br><br>
                    End Transmission
                    </p>
                </body>
            </html>
            """

    msg.attach(MIMEText(body, 'html'))

    # create SMTP object
    server = smtplib.SMTP(host='smtp.office365.com', port=587)
    server.ehlo()
    server.starttls()
    server.ehlo()

    # log in
    server.login(sender, password)

    # send email
    server.sendmail(sender, recipients, msg.as_string())
    server.quit()


def main(lyrs, check, connection):
    """Main function of the scriptt

    This function analyzes a list of layers in order to update the
    Impervious surface feature in PROD3. If none of the component layers
    have changed since the last script run, the layer will not be
    updated.

    Parameters
    ----------
    lyrs : list
        List of dicts, where each dict is a {"feature class name": "query"}
        pair
    check : boolean
        A flag that triggers comparison to the previous script run
    connection : str
        A file path to the edit SDE connection

    Returns
    -------
    str
        The main email body message based on the results of the function
    """

    # Define the output layer
    original = os.path.join(edit_conn, "GISPROD3.PW.ImperviousSurface")

    # Instantiate each layer as an Impervious class
    impervious_features = [Impervious(layer) for layer in lyrs]
    equals_previous = [imp.equals_previous() for imp in impervious_features]

    # See if any changes have been made to the layers involved
    if check and all(equals_previous):
        log.info("None of the layers have changed since the previous run...")
        msg = ("Impervious surfaces do not need to be updated because "
               "none of its component layers have changed.")
    else:
        # Update features based on the assigned hierarchy
        log.info("Creating a new ImperviousSurface layer...")
        temp = impervious_features[0].memory_fc(original)
        for surf in impervious_features[1:]:
            log.info(f"Updating ImperviousSurface with {surf.name}...")
            temp = arcpy.Update_analysis(
                temp, surf.memory_fc(original),
                f"temp.gdb\\{surf.name.split('.')[-1]}Update")

        # Remove old records from the table, make three attempts in case of
        # unknown error
        for x in range(3):
            log.info(f"Attempt #{x+1} for removing old data...")
            try:
                editor = arcpy.da.Editor(connection)
                editor.startEditing(False, True)
                editor.startOperation()
                with arcpy.da.UpdateCursor(original, ['GLOBALID']) as cursor:
                    for row in cursor:
                        cursor.deleteRow()
                editor.stopOperation()
                editor.stopEditing(True)

                log.info("Loading new impervious surfaces...")
                arcpy.Append_management(temp, original, "NO_TEST")

                msg = ("The derived layer has been updated.")
                break
            except Exception:
                if x < 2:
                    log.info(f"Attempt #{x+1} failed, rertrying...")
                    sleep(20)  # sleep for 20 seconds before retrying
                else:
                    log.info("Final attempt failed...")
                    msg = "The script failed to make edits."
            finally:
                del editor

    # Return the email message notifying users of script run
    return msg


if __name__ == '__main__':
    # Initialize configurations
    with open(r'.\config.yaml') as config_file:
        config = yaml.safe_load(config_file.read())
        logging.config.dictConfig(config['logging'])

    read_conn = config['connections']['read']
    edit_conn = config['connections']['edit']
    check_previous = config['check_previous']
    email_recipients = config['recipients']

    # Initialize the logger for this file
    log = logging.getLogger(__name__)

    username = getpass.getuser()
    log.info(f"Started by {username}...")

    # Define order for intersecting layers, and relevant queries for each
    # Dicts within a list helps enforce ordering
    layers = [{"GISPROD3.PW.ImperviousMisc": "LIFECYCLE = 'Active'"},
              {"GISPROD3.PW.SidewalkArea": ""},
              {"GISPROD3.PW.Driveway": "LIFECYCLE = 'Active'"},
              {"GISPROD3.PW.ParkingLot":
               "LIFECYCLE = 'Active' AND SURFACETYPE = 'Impervious'"},
              {"GISPROD3.PW.RoadArea": "LIFECYCLE = 'Active'"},
              {"GISPROD3.PW.Building": "LIFECYCLE = 'Active'"},
              {"GISPROD3.PW.PWMaintenanceArea":
               ("LIFECYCLE = 'Active' AND FACILITYTYPE = 'Median' "
                "AND SURFTYPE = 'Hard'")}]
    try:
        # Define the workspace
        arcpy.env.workspace = 'temp.gdb'
        # Remove old layers from workspace
        log.info("Removing old temporary derived data from temp.gdb...")
        for l in arcpy.ListFeatureClasses():
            arcpy.Delete_management(l)
        # Perform main task
        message = main(layers, check_previous, edit_conn)
        password = config['password']
        send_email(password, message, email_recipients)
    except Exception:
        log.exception("Something prevented the script from running")
