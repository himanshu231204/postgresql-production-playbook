category: operations
# Backup and restore basics
Take logical backups with pg_dump in custom format so pg_restore can restore selectively. Test every backup by restoring it into a scratch database. For point in time recovery, archive WAL continuously and keep a base backup. A backup that has never been restored is not a verified backup.
