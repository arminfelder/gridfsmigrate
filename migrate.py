#!/usr/bin/env python3
"""
This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.
This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
"""

__author__ = "Armin Felder"
__contact__ = "armin.felder@osalliance.com"
__copyright__ = "Copyright 2019, Armin Felder"
__credits__ = ["all contributors"]
__date__ = "2019.05.05"
__deprecated__ = False
__email__ = "armin.felder@osalliance.com"
__license__ = "GPLv3"
__maintainer__ = "Armin Felder"
__status__ = "Production"
__version__ = "1.1.0"

import argparse
import csv
import logging
import os
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from mimetypes import MimeTypes
from pathlib import Path
from time import perf_counter
from typing import Dict, Optional

import gridfs
from pymongo import MongoClient
from tqdm import tqdm

class FileSystemStore:
    def __init__(self, migrator, directory: str):
        self.migrator = migrator
        self.outDir = Path(directory)
        self.outDir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized FileSystemStore with directory: {self.outDir}")

    def put(self, filename: str, data: bytes, entry: Dict) -> str:
        # Improved filename sanitization
        safe_filename = "".join(c for c in filename if c.isalnum() or c in " .-_%").rstrip()
        file_path = self.outDir / safe_filename
        try:
            with open(file_path, "wb") as file:
                file.write(data)
            logger.debug(f"Saved file: {safe_filename}")
            return str(file_path)
        except Exception as e:
            logger.error(f"Failed to save file {safe_filename}: {e}")
            return ""

class AmazonS3Store:
    def __init__(self, migrator, bucket: str):
        self.migrator = migrator
        self.bucket = bucket
        import boto3
        self.s3 = boto3.resource("s3")
        self.uniqueID = migrator.uniqueid()
        logger.info(f"Initialized AmazonS3Store with bucket: {self.bucket}")

    def encodeURI(self, string: str) -> str:
        return urllib.parse.quote(string, safe="~@#$&()*!+=:;,.?/'")

    def put(self, filename: str, data: bytes, entry: Dict) -> str:
        key = f"{self.uniqueID}/Uploads/{entry['rid']}/{entry['userId']}/{entry['_id']}"
        try:
            obj = self.s3.Object(self.bucket, key)
            params = {
                "Body": data,
                "ContentDisposition": f'inline; filename="{self.encodeURI(entry["name"])}"',
            }
            if "type" in entry:
                params["ContentType"] = entry["type"]
            obj.put(**params)
            logger.debug(f"Uploaded to S3: {key}")
            return key
        except Exception as e:
            logger.error(f"Failed to upload {key} to S3: {e}")
            return ""

class Migrator:
    def __init__(
        self,
        db: str = "rocketchat",
        host: str = "localhost",
        username: str = None,
        password: str = None,
        port: int = 27017,
        logfile: Optional[str] = None,
        max_workers: int = 4,
    ):
        self.logfile = Path(logfile) if logfile else None
        self.log = []
        self.db = db
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.max_workers = max_workers
        logger.info(
            f"Initialized Migrator: db={db}, host={host}, port={port}, logfile={logfile}"
        )

    def getdb(self):
        try:
            client_args = {
                "host": self.host,
                "port": self.port,
                "retryWrites": False,
            }
            if self.username is not None and self.password is not None:
                client_args["username"] = self.username
                client_args["password"] = self.password
            client = MongoClient(**client_args)
            return client[self.db]
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    def _process_upload(self, upload: Dict, fs: gridfs.GridFSBucket, store, mime: MimeTypes, collection: str) -> Optional[Dict]:
        if upload.get("store") != "GridFS:Uploads":
            logger.debug(f"Skipping non-GridFS upload: {upload['_id']}")
            return None
        gridfsId = upload["_id"]
        if upload.get("complete", False):
            try:
                with fs.find({"_id": gridfsId}) as cursor:
                    for res in cursor:
                        data = res.read()
                        filename = gridfsId
                        if upload.get("extension"):
                            filename += f".{upload['extension']}"
                        key = store.put(filename, data, upload)
                        return {
                            "id": gridfsId,
                            "file": filename,
                            "collection": collection,  # Use collection name instead of fs.bucket_name
                            "key": key,
                        }
            except Exception as e:
                logger.error(f"Error processing upload {gridfsId}: {e}")
                return None
        else:
            logger.warning(f"Skipping incomplete upload: {gridfsId}")
            return None

    def dumpfiles(self, collection: str, store):
        start_time = perf_counter()
        mime = MimeTypes()
        db = self.getdb()
        uploads_collection = db[collection]
        fs = gridfs.GridFSBucket(db, bucket_name=collection)

        uploads = uploads_collection.find({}, no_cursor_timeout=True).batch_size(50)
        total = uploads_collection.count_documents({})
        failed_uploads = []

        logger.info(f"Starting dump of {total} files from collection: {collection}")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for upload in uploads:
                futures.append(
                    executor.submit(self._process_upload, upload, fs, store, mime, collection)
                )

            processed = 0
            for future in tqdm(as_completed(futures), total=total, desc="Dumping files"):
                result = future.result()
                if result:
                    self.addtolog(result)
                    processed += 1
                else:
                    failed_uploads.append(upload["_id"])

        self.writelog()
        duration = perf_counter() - start_time
        logger.info(f"Dumped {processed}/{total} files in {duration:.2f} seconds")
        if failed_uploads:
            logger.warning(f"Failed to process {len(failed_uploads)} uploads: {failed_uploads}")

    def addtolog(self, entry: Dict):
        self.log.append(entry)

    def writelog(self):
        try:
            with open(self.logfile, "a", newline="") as file:
                writer = csv.writer(file)
                for entry in self.log:
                    writer.writerow(
                        [entry["id"], entry["file"], entry["collection"], entry["key"]]
                    )
            logger.info(f"Wrote {len(self.log)} entries to log file: {self.logfile}")
            self.log.clear()
        except Exception as e:
            logger.error(f"Failed to write log file: {e}")

    def uniqueid(self) -> str:
        db = self.getdb()
        row = db.rocketchat_settings.find_one({"_id": "uniqueID"})
        if not row:
            logger.error("UniqueID not found in database")
            raise ValueError("UniqueID not found")
        return row["value"]

    def _update_record(self, row: list, db, target: str):
        try:
            dbId, filename, collectionName, key = row
            collection = db[collectionName]
            update_data = {
                "store": f"{target}:Uploads",
                "path": f"/ufs/{target}:Uploads/{dbId}/{filename}",
                "url": f"/ufs/{target}:Uploads/{dbId}/{filename}",
            }
            if target == "AmazonS3":
                update_data["AmazonS3"] = {"path": key}
            collection.update_one({"_id": dbId}, {"$set": update_data})
            return dbId, True
        except Exception as e:
            logger.error(f"Failed to update record {dbId}: {e}")
            return dbId, False

    def updateDb(self, target: str):
        start_time = perf_counter()
        db = self.getdb()
        with open(self.logfile, newline="") as csvfile:
            reader = list(csv.reader(csvfile))
            total = len(reader)
            logger.info(f"Updating {total} database records for target: {target}")

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [
                    executor.submit(self._update_record, row, db, target)
                    for row in reader
                ]
                updated = 0
                for future in tqdm(as_completed(futures), total=total, desc="Updating DB"):
                    dbId, success = future.result()
                    if success:
                        updated += 1

        duration = perf_counter() - start_time
        logger.info(f"Updated {updated}/{total} records in {duration:.2f} seconds")

    def _remove_blob(self, row: list, db):
        try:
            dbId, _, collectionName, _ = row
            fs = gridfs.GridFSBucket(db, bucket_name=collectionName)
            fs.delete(dbId)
            return dbId, True
        except Exception as e:
            logger.warning(f"Failed to remove blob {dbId}: {e}")
            return dbId, False

    def removeBlobs(self):
        start_time = perf_counter()
        db = self.getdb()
        with open(self.logfile, newline="") as csvfile:
            reader = list(csv.reader(csvfile))
            total = len(reader)
            logger.info(f"Removing {total} blobs")

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [executor.submit(self._remove_blob, row, db) for row in reader]
                removed = 0
                for future in tqdm(as_completed(futures), total=total, desc="Removing blobs"):
                    dbId, success = future.result()
                    if success:
                        removed += 1

        duration = perf_counter() - start_time
        logger.info(f"Removed {removed}/{total} blobs in {duration:.2f} seconds")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate Rocket.Chat files from GridFS to FileSystem or Amazon S3."
    )
    parser.add_argument("-s", "--host", default="localhost", help="MongoDB host (default: %(default)s)")
    parser.add_argument("-p", "--port", type=int, default=27017, help="MongoDB port (default: %(default)s)")
    parser.add_argument("-r", "--database", default="rocketchat", help="Database name (default: %(default)s)")
    parser.add_argument(
        "-c",
        "--command",
        choices=["dump", "updatedb", "removeblobs"],
        required=True,
        help="Command to execute: dump, updatedb, or removeblobs"
    )
    parser.add_argument(
        "-t",
        "--target",
        choices=["AmazonS3", "FileSystem"],
        default="FileSystem",
        help="Storage target: AmazonS3 or FileSystem (default: %(default)s)"
    )
    parser.add_argument(
        "-d", "--destination", help="S3 bucket name or output directory (required for dump)"
    )
    default_logfile = f"{Path(sys.argv[0]).stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    parser.add_argument(
        "-l", "--log-file", default=default_logfile, help="Log file path (default: %(default)s)"
    )
    parser.add_argument("--user", default=None, help="MongoDB username (default: %(default)s)")
    parser.add_argument("--password", default=None, help="MongoDB password (default: %(default)s)")
    parser.add_argument(
        "--max-workers", type=int, default=4, help="Number of parallel workers (default: %(default)s)"
    )

    args = parser.parse_args()

    if args.command == "dump" and not args.destination:
        parser.error("The --destination argument is required for the dump command")

    # Configurar logging somente se uma ação for executada
    log_filename = f"{Path(sys.argv[0]).stem}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler(sys.stdout),
        ],
    )
    global logger
    logger = logging.getLogger(__name__)

    obj = Migrator(
        db=args.database,
        host=args.host,
        username=args.user,
        password=args.password,
        port=args.port,
        logfile=args.log_file,
        max_workers=args.max_workers,
    )

    if args.command == "dump":
        if args.target == "AmazonS3":
            store = AmazonS3Store(obj, args.destination)
        else:
            if not Path(args.destination).is_dir():
                parser.error(f"Destination directory does not exist: {args.destination}")
            store = FileSystemStore(obj, args.destination)
        obj.dumpfiles("rocketchat_uploads", store)
    elif args.command == "updatedb":
        obj.updateDb(args.target)
    elif args.command == "removeblobs":
        obj.removeBlobs()
