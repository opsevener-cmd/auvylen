#!/bin/sh
set -eu
# Generate once, retain across rebuilds; never rotate credentials for an existing DB.
secret_dir=/run/auvylen-preview-secrets
secret_file="$secret_dir/postgres-password"
if [ ! -s "$secret_file" ]; then
    if [ -s "${PGDATA}/PG_VERSION" ]; then
        echo 'Existing preview database has lost its credentials; restore its matching backup.' >&2
        exit 1
    fi
    mkdir -p "$secret_dir"
    chmod 700 "$secret_dir"
    od -An -N48 -tx1 /dev/urandom | tr -d ' \n' > "$secret_file"
    chmod 600 "$secret_file"
    chown 1000:1000 "$secret_dir" "$secret_file"
fi
exec /usr/local/bin/docker-entrypoint.sh postgres
