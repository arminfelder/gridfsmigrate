## RocketChat GridFS to Filesystem migration script

migrate [command] [targetPath] [dbname]

e.g. ./migrate dump /home/armin/rctemp/files meteor

### commands
- dump :        dumps the GridFs stored files into the given folder and writers a log(log.csv)
- updatedb :    changes the database entries to point to your stored files instead of GridFS
- removeblobs : removes migrated files from GridFS

### steps

1. for safety do a mongo backup with mongodump
2. switch RocketChat to FileSystem and set a folder to store the uploads(e.g. /app/uploads)
3. run ./migrate dump [e.g /app/uploads] [e.g. rocketchat]
4. run ./migrate updatedb [e.g /app/uploads] [e.g. rocketchat]
5. have a look, if everything looks fine e.g are files missing etc.
6. run ./migrate removeblobs [e.g /app/uploads] [e.g. rocketchat]

