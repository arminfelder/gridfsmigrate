from pymongo import MongoClient
import gridfs
from pprint import pprint
from mimetypes import MimeTypes
import sys
import getopt
import csv

class Migrator():
    def __init__(self, directory):
        print("test")
        self.outDir = directory
        self.log = list()

    def dumpfiles(self, collection):
        mime = MimeTypes()
        db = MongoClient().rocketchat
        fs = gridfs.GridFSBucket(db, collection)
        for grid_out in fs.find({}, no_cursor_timeout=True):
            data = grid_out.read()
            pprint(grid_out.filename)
            pprint(grid_out._id)
            fileext = mime.guess_extension(grid_out.content_type)
            filename = grid_out.filename
            filename = '.'.join(filename.split('.')[:1])
            if fileext:
                filename = filename+fileext

            print(filename)
            file = open(self.outDir+"/"+filename, "wb")
            file.write(data)
            file.close()
            self.addtolog(grid_out._id, filename, collection, grid_out.md5)
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
            db = MongoClient().rocketchat
            reader = csv.reader(csvfile, delimiter=',')
            for row in reader:
                dbId = row[0]
                filename = row[1]
                collection = row[2]
                md5 = row[3]
                collection = db[collection]
                collection.update_one({
                    "id": dbId
                }, {
                    "$set": {
                        "store": "FileSystems:Uploads",
                        "path": "/ufs/Filesystem:Uploads/"+dbId+"/"+filename,
                        "url": "/ufs/Filesystem:Uploads/"+dbId+"/"+filename
                    }
                })


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if len(sys.argv) == 3 and sys.argv[1] == "dump":
            obj = Migrator(sys.argv[2])
            obj.dumpfiles("rocketchat_uploads")
            #obj.dumpfiles("custom_emoji")
            #obj.dumpfiles("assets")
        elif len(sys.argv) == 3 and sys.argv[1] == "dedup":
            obj = Migrator(sys.argv[2])
            obj.dedup()
        elif len(sys.argv) == 3 and sys.argv[1] == "updatedb":
            obj = Migrator(sys.argv[2])
            obj.updateDb()
