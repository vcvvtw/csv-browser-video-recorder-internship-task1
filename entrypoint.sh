#!/bin/bash
set -e

# Ensure uploads folder exists and is writable by Apache
mkdir -p /app/uploads
chown -R www-data:www-data /app/uploads
chmod 775 /app/uploads

# Export container environment variables into Apache envvars
# so WSGI daemon process reliably inherits them
{
    [ -n "$DB_HOST" ] && echo "export DB_HOST=\"$DB_HOST\""
    [ -n "$DB_PORT" ] && echo "export DB_PORT=\"$DB_PORT\""
    [ -n "$DB_NAME" ] && echo "export DB_NAME=\"$DB_NAME\""
    [ -n "$DB_USER" ] && echo "export DB_USER=\"$DB_USER\""
    [ -n "$DB_PASSWORD" ] && echo "export DB_PASSWORD=\"$DB_PASSWORD\""
    [ -n "$UPLOADS_DIR" ] && echo "export UPLOADS_DIR=\"$UPLOADS_DIR\""
} >> /etc/apache2/envvars

exec "$@"
