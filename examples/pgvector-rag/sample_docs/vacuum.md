category: performance
# Vacuum and bloat
Updates and deletes leave dead tuples behind. Autovacuum reclaims that space for reuse and updates visibility information. If autovacuum cannot keep up on a hot table, tune its per table settings and watch for long running transactions that hold back cleanup. VACUUM FULL rewrites the table under an exclusive lock and should be a last resort.
