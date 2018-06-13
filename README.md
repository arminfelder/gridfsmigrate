## RocketChat GridFS to Filesystem migration script

migrate -c [command] -d [targetPath] -r [dbname]

e.g. ./migrate -c dump -d /app/uploads -r meteor

### commands
- dump :        dumps the GridFs stored files into the given folder and writers a log(log.csv)
- updatedb :    changes the database entries to point to your stored files instead of GridFS
- removeblobs : removes migrated files from GridFS

### steps

1. for safety do a mongo backup with mongodump
2. switch RocketChat to FileSystem and set a folder to store the uploads(e.g. /app/uploads)
3. run ./migrate -c dump -d /app/uploads -r rocketchat
4. run ./migrate -c updatedb -d /app/uploads -r rocketchat
5. have a look, if everything looks fine e.g are files missing etc.
6. run ./migrate -c removeblobs -d /app/uploads -r rocketchat

