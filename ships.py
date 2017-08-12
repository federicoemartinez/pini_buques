import os
import pickle
import json
import requests
# Import smtplib for the actual sending function
import smtplib

# Import the email modules we'll need
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from json2html import *
from bs4 import BeautifulSoup


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


class ExolganTable(ShipTable):
    COLUMNS = ("Buque", "Armador", "Servicio",
                "Inicio de Recepcion Expo", "Cut Off",
                "ETA", "ATD", "Fin Free Storage", "Cierre Malvina")
    ID_COLUMN = "Buque"
    TEXT_TO_STATE = {"Finalizado":"Arribado", "Operando":"Operando", "Estimado":"Esperado", "Cancelado":"Cancelado"}
    data_url = "http://apps.exolgan.com/scheduleout/content.jsp"

    def get_status(self, row):
        return ExolganTable.TEXT_TO_STATE[row["class"][0]]


class TRPTable(ShipTable):
    COLUMNS = ("Servicio","Agencia", "E.T.A.", "Buque")
    ID_COLUMN = "Buque"
    data_url = "http://www.trp.com.ar/cronogramas/buques"

    def get_status(self, row):
        return None

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

if __name__ == "__main__":
        
        with open("buques.txt", 'r') as buques:
            names = [x.strip() for x in buques.readlines()]
        cd = ChangeDectector(names)
        changes = cd.get_changes()
        output = open("output.html", 'w')
        html = json2html.convert(json = json.dumps(changes, sort_keys=True))
        output.write(html)
        output.close()
        

        smtp_ssl_host = "smtp.mail.yahoo.com"
        smtp_ssl_port = 465
        username = 'YAHOO_ADDRESS'
        password = 'PASSWORD'
        sender = 'YAHOO_ADDRESS'
        targets = ["SOME_EMAILS"]

        msg = MIMEMultipart()
        msg['Subject'] = 'Actualizaciones en los buques'
        msg['From'] = sender
        msg['To'] = ', '.join(targets)

        txt = MIMEText('Te paso la data')
        msg.attach(txt)
        img = MIMEText(html, 'html')

        img.add_header('Content-Disposition',
                       'attachment',
                       filename=os.path.basename("output.html"))
        msg.attach(img)

        server = smtplib.SMTP_SSL(smtp_ssl_host, smtp_ssl_port)
        server.login(username, password)
        server.sendmail(sender, targets, msg.as_string())
        server.quit()




