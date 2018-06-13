#!/usr/bin/env python3
from pymongo import MongoClient
import gridfs
from pprint import pprint
from mimetypes import MimeTypes
import sys
import getopt
import csv
import argparse

class Migrator():
    def __init__(self, directory, db="rocketchat", host="localhost", port=27017):
        self.outDir = directory
        self.log = list()
        self.db = db
        self.host = host
        self.port = port

    def dumpfiles(self, collection):
        mime = MimeTypes()

        db = MongoClient(host=self.host, port=self.port)[self.db]
        uploadsCollection = db[collection]
        fs = gridfs.GridFSBucket(db, bucket_name=collection)

        uploads = uploadsCollection.find({}, no_cursor_timeout=True)

        for upload in uploads:
            if upload["store"] == "GridFS:Uploads":
                if upload["complete"] is True:
                    path = upload["path"]
                    pathSegments = path.split("/")
                    gridfsId = pathSegments[3]
                    for res in fs.find({"_id": gridfsId}):
                        data = res.read()
                        fileext = ""
                        if "extension" in upload:
                            fileext = upload["extension"]
                        else:
                            fileext = mime.guess_extension(res.content_type)
                        if fileext is not None and fileext != "":
                            filename = gridfsId+"."+fileext
                        else:
                            filename = gridfsId
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
            db = MongoClient(host=self.host, port=self.port)[self.db]
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
            db = MongoClient(host=self.host, port=self.port)[self.db]
            reader = csv.reader(csvfile, delimiter=',')
            for row in reader:
                dbId = row[0]
                collectionName = row[2]
                fs = gridfs.GridFSBucket(db, bucket_name=collectionName)
                try:
                    fs.delete(dbId)
                except:
                    continue


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('-s', '--host', help='mongodb host')
    parser.add_argument('-p', '--port', help='mongodb port')
    parser.add_argument('-r', '--database', help='database')
    parser.add_argument('-c', '--command', help='[dump|updatedb|removeblobs]')
    parser.add_argument('-d', '--dir', help='files dir')

    parser.set_defaults(host="localhost", port=27017, database="rocketchat")

    args = parser.parse_args()

    obj = Migrator(args.dir, args.database, args.host, int(args.port))

    if args.command == "dump":
        obj.dumpfiles("rocketchat_uploads")

    if args.command == "updatedb":
        obj.updateDb()

    if args.command == "removeblobs":
        obj.removeBlobs()
