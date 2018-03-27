import os
import pickle
import json
import requests
# Import smtplib for the actual sending function
import smtplib

# Import the email modules we'll need
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from json2html import *
from bs4 import BeautifulSoup

import time
from threading import Timer
from Queue import Queue, Empty
import pystray
import PIL.Image
import sys

class ShipTable(object):
    def save(self, filename):
        with open(filename, "wb") as fp:
            pickle.dump(self.rows, fp)

    @classmethod
    def load(cls, filename):
        with open(filename, "rb") as fp:
            rows = pickle.load(fp)
            return cls(rows)


    def __cmp__(self, other):
        return cmp(self.rows, other.rows)

    def get_difference(self, other):
        res = {}
        other_rows = other.rows
        for ship, ship_data in self.rows.items():
            res[ship] = {}
            if ship in other_rows:
                new_ship = other_rows[ship]
                for data_key, data_value in ship_data.items():
                    if data_key in new_ship and data_value != new_ship[data_key]:
                        res[ship][data_key] = {"OLD": data_value, "NEW": new_ship[data_key]}
                        res[ship]["CHANGED"] = "MODIFIED"
                if len(res[ship]) == 0:
                    del res[ship]
            else:
                res[ship] = {"CHANGED": "DELETED"}

        for ship, ship_data in other.rows.items():
            if ship in self.rows: continue
            res[ship] = ship_data
            res[ship]["CHANGED"] = "ADDED"

        return res

    def __init__(self, rows = None):
        if rows is None:
            self.load_from_url()
        else:
            self.rows = rows

    def load_from_url(self):
        self.rows = {}

        resp = requests.get(self.data_url)
        if resp.ok:
            html_doc = resp.content
            soup = BeautifulSoup(html_doc, 'html.parser')
            table = soup.table
            for row in table.find_all("tr"):
                exolgan_row = {}
                status = self.get_status(row)
                if status:
                    exolgan_row["Status"] = status
                i = 0
                columns = row.find_all("td")
                for col in columns:
                    exolgan_row[self.COLUMNS[i]] = col.text.strip()
                    i+=1
                if columns:
                    if exolgan_row[self.ID_COLUMN] in self.rows: 
                        continue
                    self.rows[exolgan_row[self.ID_COLUMN]] = exolgan_row
        self.post_process()

    def post_process(self):
        return



class ExolganTable(ShipTable):
    COLUMNS = ("Buque", "Armador", "Servicio",
                "Inicio de Recepcion Expo", "Cut Off",
                "ETA", "ATD", "Fin Free Storage", "Cierre Malvina")
    ID_COLUMN = "Buque"
    TEXT_TO_STATE = {"Finalizado":"Arribado", "Operando":"Operando", "Estimado":"Esperado", "Cancelado":"Cancelado"}
    data_url = "http://apps.exolgan.com/scheduleout/content.jsp"

    def get_status(self, row):
        return ExolganTable.TEXT_TO_STATE.get(row["class"][0], None)


class TRPTable(ShipTable):
    COLUMNS = ("Servicio","Agencia", "E.T.A.", "Buque", "Vencimiento free storage")
    ID_COLUMN = "Buque"
    data_url = "http://www.trp.com.ar/cronogramas/buques"
    free_storage_url = "http://www.trp.com.ar/cronogramas/importacion"

    def get_status(self, row):
        return None

    def post_process(self):
        resp = requests.get(self.free_storage_url)
        if resp.ok:
            html_doc = resp.content
            soup = BeautifulSoup(html_doc, 'html.parser')
            table = soup.table
            for row in table.find_all("tr"):
                if row.find_all("th"):
                    continue
                buque, storage = map(lambda col: col.text.strip(), row.find_all("td"))
                if buque in self.rows:
                    self.rows[buque][self.COLUMNS[-1]] = storage


def test_difference():
    et = ExolganTable().load("exolg")
    et2 = ExolganTable().load("exolg")
    del(et.rows["E.R. SEOUL V.1724"])
    del(et2.rows["MSC LUISA V.729"])
    et2.rows["PERITO MORENO V.010"]["ETA"] = "13-07-2017"
    exptected_diff = {u'MSC LUISA V.729': {'CHANGED': 'DELETED'},
 u'PERITO MORENO V.010': {'ETA': {'NEW': '13-07-2017', 'OLD': u'18-07-2017 12:00'}, 'CHANGED': 'MODIFIED'}, 
 u'E.R. SEOUL V.1724': {'status': 'Arribo', 'Servicio': u'SDG', 'ATD': u'25-07-2017', 'Inicio de Recepcion': u'06-07-2017', 'Armador': u'HL', 'Buque': u'E.R. SEOUL V.1724', 'CHANGED': 'ADDED', 'Fin Free Storage': u'21-07-2017', 'ETA': u'20-07-2017 23:00', 'Expo': u'12-07-2017 18:00', 'Cut Off': u'19-07-2017 17:30'}}
    if not(exptected_diff == et.get_difference(et2)):
        raise Exception(str(et.get_difference(et2)))
    

class ChangeDectector(object):

    exolgan_file = "exolgan_data"
    trp_file = "trp_data"

    def __init__(self, names):
        self.names = names


    def get_changes(self):
        exolgan = self.get_exolgan_changes()
        trp = self.get_trp_changes()
        res = {name:exolgan[name] for name in self.names if name in exolgan}
        res.update({name:trp[name] for name in self.names if name in trp})
        return res

    def get_exolgan_changes(self):
        return self.__get_changes_changes(ExolganTable, self.exolgan_file)

    def get_trp_changes(self):
        changes = self.__get_changes_changes(TRPTable, self.trp_file)
        return changes

    def __get_changes_changes(self, table_class, table_file):
        if not os.path.isfile(table_file):
            et1 = table_class(rows = {})
        else:
            et1 = table_class.load(table_file)
        et2 = table_class()
        changes = et1.get_difference(et2)
        et2.save(table_file)
        return changes

def process():
    print "procesando"

    with open("buques.txt", 'r') as buques:
        names = [x.strip() for x in buques.readlines()]
    cd = ChangeDectector(names)
    changes = cd.get_changes()
    if len(changes) == 0:
        print "NO changes"
        return
    output = open("output.html", 'w')
    html = json2html.convert(json = json.dumps(changes, sort_keys=True))
    output.write(html)
    output.close()
    
    with open("config.json", "r") as raw_config:
        config = json.load(raw_config)
        smtp_ssl_host = config["smtp_ssl_host"]
        smtp_ssl_port = config["smtp_ssl_port"]
        username = config["username"]
        password = config["password"]
        sender = config["sender"]
        targets = config["targets"]
    msg = MIMEMultipart()
    msg['Subject'] = 'Nueva data sobre buques'
    msg['From'] = sender
    msg['To'] = ', '.join(targets)

    txt = MIMEText('Te paso la data')
    msg.attach(txt)
    img = MIMEText(html, 'html')

    img.add_header('Content-Disposition',
                   'attachment',
                   filename=os.path.basename("output.html"))
    msg.attach(img)
    print "going to send email"
    server = smtplib.SMTP_SSL(smtp_ssl_host, smtp_ssl_port)
    server.login(username, password)
    x = server.sendmail(sender, targets, msg.as_string())
    print(x)
    server.quit()


if __name__ == "__main__":

    icon = pystray.Icon('test name', icon = PIL.Image.open('buque.png'))

    icon.icon = PIL.Image.open('buque.png')

    queue = Queue()
    def setup(icon):
        icon.visible = True
        try:
            process()
        except Exception, e:
            # Deberiamos hacer algo
            print e
            pass
        while True:
            try:
                queue.get(True, 3600)
                icon.stop()
                sys.exit(0)
            except Empty:
                process()

    def do_exit(self):
        queue.put(1)
        sys.exit(0)


    menuItem = pystray.MenuItem("Exit", do_exit)
    icon.menu = pystray.Menu(menuItem)
    icon.run(setup)
