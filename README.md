## RocketChat GridFS to FileSystem/AmazonS3 Migration

This script migrates files uploaded to [RocketChat](https://rocket.chat/) from the default `GridFS` storage to FileSystem or AmazonS3.

    migrate -c [command] -d [s3 bucket|output directory] -r [dbname] -t [target]

### Help

Run `./migrate.py -h` to see all available options.

### Commands

- **dump**:        Exports files from GridFS to the specified folder/S3 bucket and generates a log file.
- **updatedb**:    Updates database entries to point to the new storage instead of GridFS.
- **removeblobs**: Removes migrated files from GridFS.

### Requirements

#### Installing Dependencies

- python3 (e.g. `sudo apt install python3 python3-pip`)

- Install dependencies with:

      pip install -r requirements.txt

  Or manually:

      pip install pymongo gridfs tqdm boto3

#### Environment

- If using Amazon S3, set credentials as environment variables ([Boto3 configuration guide](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html)).
- Export `PYTHONIOENCODING=utf-8` to avoid issues with non-ASCII filenames.

#### Recommended MongoDB Index

To speed up file lookups in GridFS, create the following index in your Rocket.Chat database:

      db.rocketchat_uploads.chunks.createIndex({ files_id: 1, n: 1 }, { unique: true })

Not having this index can make migration very slow on large databases.

#### Default Rocket.Chat Database Name

- When installed via snap, the default database name is `parties` and usually there is no username or password.
- Example usage:

      ./migrate.py -c dump -r parties -t FileSystem -d /app/uploads

### Multi-threaded Execution

To speed up migration, you can configure the script to use multiple workers. Adjust according to your CPU core count. Example:

      ./migrate.py -c dump -r parties -t FileSystem -d /app/uploads --max-workers 8

### Steps

1. **Backup your MongoDB database** so you don't lose any data in case of issues. ([MongoDB Backup Methods](https://docs.mongodb.com/manual/core/backups/))

2. **Change the Storage Type** in Rocket.Chat under `Administration > File Upload` to `FileSystem` or `AmazonS3`. Update the relevant configuration settings.

3. **Start copying files to the new storage:**

   - **File System**

         ./migrate.py -c dump -r rocketchat -t FileSystem -d /app/uploads

   - **S3**

         ./migrate.py -c dump -r rocketchat -t AmazonS3 -d S3bucket_name

4. **Update the database to use the new storage** (use `-t AmazonS3` if migrating to S3):

      ./migrate.py -c updatedb -d /app/uploads -r rocketchat -t FileSystem

5. **Check if everything is working correctly** and ensure there are no missing files.

6. **Remove obsolete data from GridFS:**

      ./migrate.py -c removeblobs -d /app/uploads -r rocketchat

### Troubleshooting

In some configurations, it may help to add the parameters `directconnection=True` and `connect=False` to the MongoClient constructor, for example:

      MongoClient(..., retryWrites=False, directconnection=True, connect=False)[self.db]

This ensures the connection uses Single topology.

