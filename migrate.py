#!/usr/bin/env python3
from pymongo import MongoClient
import gridfs
from pprint import pprint
from mimetypes import MimeTypes
import sys
import getopt
import csv

class Migrator():
    def __init__(self, directory, db="rocketchat"):
        self.outDir = directory
        self.log = list()
        self.db = db

    def dumpfiles(self, collection):

        db = MongoClient()[self.db]
        uploadsCol = db[collection]
        fs = gridfs.GridFSBucket(db, collection)

        uploads = uploadsCol.find({})

        for upload in uploads:
            if upload["store"] == "GridFS:Uploads":
                path = upload["path"]
                pathSegments = path.split("/")
                gridfsId = pathSegments[3]
                for res in fs.find({"_id": gridfsId}):
                    data = res.read()
                    fileext = upload["extension"]
                    filename = gridfsId+"."+fileext
                    file = open(self.outDir+"/"+filename, "wb")
                    file.write(data)
                    file.close()
                    self.addtolog(gridfsId, filename, collection, res.md5)
        self.writelog()

    def addtolog(self, dbId, filename, collection, md5):
        entry = dict()
        entry["file"] = filename
        entry["id"] = dbId
        entry["collection"] = collection
        entry["md5"] = md5
        self.log.append(entry)

    def writelog(self):
        file = open(self.outDir+"/log.csv", "a")
        for entry in self.log:
            line = entry["id"]+","+entry["file"]+","+entry["collection"]+",log"+entry["md5"]+"\n"
            file.write(line)
        file.close()

    def dedup(self):
        pass

    def updateDb(self):
        with open(self.outDir+"/log.csv") as csvfile:
            db = MongoClient()[self.db]
            reader = csv.reader(csvfile, delimiter=',')
            for row in reader:
                dbId = row[0]
                filename = row[1]
                collectionName = row[2]
                md5 = row[3]
                collection = db[collectionName]
                collection.update_one({
                    "_id": dbId
                }, {
                    "$set": {
                        "store": "FileSystem:Uploads",
                        "path": "/ufs/FileSystem:Uploads/"+dbId+"/"+filename,
                        "url": "/ufs/FileSystem:Uploads/"+dbId+"/"+filename
                    }
                })

    def removeBlobs(self):
        with open(self.outDir + "/log.csv") as csvfile:
            db = MongoClient()[self.db]
            reader = csv.reader(csvfile, delimiter=',')
            for row in reader:
                dbId = row[0]
                filename = row[1]
                collectionName = row[2]
                md5 = row[3]
                collection = db[collectionName]
                fs = gridfs.GridFSBucket(db, collectionName)
                try:
                    fs.delete(dbId)
                except:
                    continue



if __name__ == "__main__":
    if len(sys.argv) > 1:
        if len(sys.argv) > 2 and sys.argv[1] == "dump":
            obj = None
            if len(sys.argv) == 4:
                obj = Migrator(sys.argv[2],sys.argv[3])
            else:
                obj = Migrator(sys.argv[2])
            obj.dumpfiles("rocketchat_uploads")
            #obj.dumpfiles("custom_emoji")
            #obj.dumpfiles("assets")
        elif len(sys.argv) >2 and sys.argv[1] == "dedup":
            if len(sys.argv) == 4:
                obj = Migrator(sys.argv[2], sys.argv[3])
            else:
                obj = Migrator(sys.argv[2])
            obj.dedup()
        elif len(sys.argv) >2 and sys.argv[1] == "updatedb":
            if len(sys.argv) == 4:
                obj = Migrator(sys.argv[2], sys.argv[3])
            else:
                obj = Migrator(sys.argv[2])
            obj.updateDb()
        elif len(sys.argv) >2 and sys.argv[1] == "removeblobs":
            if len(sys.argv) == 4:
                obj = Migrator(sys.argv[2], sys.argv[3])
            else:
                obj = Migrator(sys.argv[2])
            obj.removeBlobs()
