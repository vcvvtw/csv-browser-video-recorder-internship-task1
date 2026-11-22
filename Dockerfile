FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install Apache, system mod_wsgi, Python 3, venv, and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    apache2 \
    libapache2-mod-wsgi-py3 \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set up dedicated Python virtual environment
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files and Apache configuration
COPY . /app/
RUN cp /app/apache.conf /etc/apache2/sites-available/000-default.conf && \
    a2enmod wsgi rewrite headers && \
    chmod +x /app/entrypoint.sh && \
    mkdir -p /app/uploads && \
    chown -R www-data:www-data /app/uploads && \
    chmod 775 /app/uploads && \
    ln -sf /dev/stdout /var/log/apache2/access.log && \
    ln -sf /dev/stderr /var/log/apache2/error.log

EXPOSE 80

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["apachectl", "-D", "FOREGROUND"]
