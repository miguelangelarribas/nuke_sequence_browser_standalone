import sys
import getpass
import uuid
import pymongo
import datetime


SERVER = pymongo.MongoClient('mongodb://127.0.0.1:27017/')
DB = SERVER["SEQ_DB"]

# creamos dos collections en la base de datos clipboard userCollections y clipboardCollections
SEQ_COLLECTION = DB['sequences']

#todo antes de salvar mirar que no exista ya esa secuencia
def save_to_db(sequence):
    SEQ_COLLECTION.insert_one(sequence)