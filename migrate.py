#!/usr/bin/env python3
from pymongo import MongoClient
import gridfs
from pprint import pprint
from mimetypes import MimeTypes
import sys
import getopt
import csv
import argparse
import urllib.parse


class FileSystemStore():
    def __init__(self, migrator, directory):
        self.migrator = migrator
        self.outDir = directory

    def put(self, filename, data, entry):
        file = open(self.outDir + "/" + filename, "wb")
        file.write(data)
        file.close()
        return ""


class AmazonS3Store():
    def __init__(self, migrator, bucket):
        self.migrator = migrator
        self.bucket = bucket

        import boto3
        self.s3 = boto3.resource('s3')
        self.uniqueID = migrator.uniqueid()

    def encodeURI(self, str):
        return urllib.parse.quote(str, safe='~@#$&()*!+=:;,.?/\'')

    def put(self, filename, data, entry):
        key = self.uniqueID + "/uploads/" + entry['rid'] + "/" + entry[
            'userId'] + "/" + entry['_id']
        self.s3.Object(self.bucket, key).put(
            Body=data,
            ContentType=entry['type'],
            ContentDisposition='inline; filename="' + self.encodeURI(
                entry['name']) + '"')
        return key


class Migrator():
    def __init__(self,
                 db="rocketchat",
                 host="localhost",
                 port=27017,
                 logfile='./log.csv'):
        self.logfile = logfile
        self.log = list()
        self.db = db
        self.host = host
        self.port = port

    def getdb(self):
        return MongoClient(host=self.host, port=self.port)[self.db]

    def dumpfiles(self, collection, store):
        mime = MimeTypes()

        db = self.getdb()
        uploadsCollection = db[collection]
        fs = gridfs.GridFSBucket(db, bucket_name=collection)

        uploads = uploadsCollection.find({}, no_cursor_timeout=True)

        i = 0
        for upload in uploads:
            if upload["store"] == "GridFS:Uploads":
                if "complete" in upload and upload["complete"] is True:
                    gridfsId = upload['_id']
                    for res in fs.find({"_id": gridfsId}):
                        data = res.read()
                        filename = gridfsId
                        fileext = ""

                        if "extension" in upload and upload["extension"] != "":
                            fileext = "." + upload["extension"]
                        else:
                            fileext = mime.guess_extension(res.content_type)

                        if fileext is not None and fileext != "":
                            filename = filename + fileext

                        i += 1
                        print("%i. Dumping %s %s" % (i, gridfsId,
                                                     upload['name']))
                        key = store.put(filename, data, upload)

                        self.addtolog({
                            "id": gridfsId,
                            "file": filename,
                            "collection": collection,
                            "md5": res.md5,
                            "key": key
                        })
                else:
                    print(upload)
        self.writelog()

    def addtolog(self, entry):
        self.log.append(entry)

    def writelog(self):
        file = open(self.logfile, "a")
        for entry in self.log:
            line = entry["id"] + "," + entry["file"] + "," + entry[
                "collection"] + ",log" + entry["md5"] + "," + entry[
                    "key"] + "\n"
            file.write(line)
        file.close()

    def dedup(self):
        pass

    def uniqueid(self):
        db = self.getdb()
        row = db.rocketchat_settings.find_one({"_id": "uniqueID"})
        return row['value']

    def updateDb(self, target):
        with open(self.logfile) as csvfile:
            db = MongoClient(host=self.host, port=self.port)[self.db]
            reader = csv.reader(csvfile, delimiter=',')

            i = 0
            for row in reader:
                dbId = row[0]
                filename = row[1]
                collectionName = row[2]
                md5 = row[3]
                key = row[4]

                collection = db[collectionName]
                update_data = {
                    "store":
                    target + ":Uploads",
                    "path":
                    "/ufs/" + target + ":Uploads/" + dbId + "/" + filename,
                    "url":
                    "/ufs/" + target + ":Uploads/" + dbId + "/" + filename
                }

                if target == "AmazonS3":
                    update_data['AmazonS3'] = {"path": key}

                i += 1
                print("%i. Updating record %s" % (i, dbId))

                collection.update_one({"_id": dbId}, {"$set": update_data})

    def removeBlobs(self):
        with open(self.logfile) as csvfile:
            db = MongoClient(host=self.host, port=self.port)[self.db]
            reader = csv.reader(csvfile, delimiter=',')

            i = 0
            for row in reader:
                dbId = row[0]
                collectionName = row[2]
                fs = gridfs.GridFSBucket(db, bucket_name=collectionName)

                i += 1
                print("%i. Removing blob %s" % (i, dbId))

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
    parser.add_argument(
        '-t', '--target', help='AmazonS3|FileSystem', default='FileSystem')
    parser.add_argument(
        '-d', '--destination', help='s3 bucket|output directory')
    parser.add_argument(
        '-l', '--log-file', help='log file path', default='./log.csv')

    parser.set_defaults(host="localhost", port=27017, database="rocketchat")

    args = parser.parse_args()

    obj = Migrator(args.database, args.host, int(args.port), args.log_file)

    if args.command == "dump":
        if args.target == "AmazonS3":
            if args.destination == None:
                raise Exception("S3 bucket name cannot be empty")
            store = AmazonS3Store(obj, args.destination)
        else:
            if args.destination == None or os.path.isdir(
                    args.destination) == False:
                raise Exception(
                    "An existing directory is required for saving files")
            store = FileSystemStore(obj, args.destination)

        obj.dumpfiles("rocketchat_uploads", store)

    if args.command == "updatedb":
        obj.updateDb(args.target)

    if args.command == "removeblobs":
        obj.removeBlobs()
