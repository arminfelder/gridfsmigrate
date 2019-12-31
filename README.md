## RocketChat GridFS to FileSystem/AmazonS3 Migration

This is a script for migrating files uploaded to [RocketChat](https://rocket.chat/) from the default `GridFS` upload store to FileSystem/AmazonS3.

    migrate -c [command] -d [s3 bucket|output directory] -r [dbname] -t [target]

### Help

Run `./migrate -h` to see all available options

### Commands
- **dump** :        dumps the GridFs stored files into the given folder/s3 bucket and writes a log files
- **updatedb** :    changes the database entries to point to the new store instead of GridFS
- **removeblobs** : removes migrated files from GridFS

### Requirements

#### Dependencies
- python3 (e.g. apt install python3 python3-pip) 
- packages (pip3 install ...): 
  - pymongo 
  - boto3

#### Environment
- if you use Amazon S3, make sure that the credentials are available as environment variables(https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html)
- export PYTHONIOENCODING=utf-8 , to prevent issue with non ASCII filenames


### Steps

1. Backup your MongoDB database so that you won't loose any data in case of any issues. ([MongoDB Backup Methods](https://docs.mongodb.com/manual/core/backups/))
2. Change `Storage Type` in RocketChat under `Administration> File Upload` to `FileSystem` or `AmazonS3`. Update the relevant configuration under the corresponding head in configuration page.
3. Start copying files to the new store  
   - **File System**

            ./migrate.py -c dump -r rocketchat -t FileSystem -d ./uploads

   - **S3**

            ./migrate.py -c dump -r rocketchat -t AmazonS3 -d S3bucket_name

4. Update the database to use new store (use `-t AmazonS3` if you are migrating to S3)

        ./migrate.py -c updatedb -d /app/uploads -r rocketchat -t FileSystem

5. Check if everything is working correctly. Ensure that there are no files missing.
6. Remove obsolete data from GridFS

        ./migrate.py -c removeblobs -d /app/uploads -r rocketchat
