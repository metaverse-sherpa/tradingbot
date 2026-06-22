# Gunicorn configuration file for Metaverse Sherpa WebAPI
import multiprocessing

# Bind to localhost on port 5001 (proxied by Nginx)
bind = "127.0.0.1:5001"

# Worker configuration (matches README recommendation)
workers = 4
worker_class = "gthread"
threads = 10

# Timeout settings (seconds)
# Max time a worker is allowed to process a single request before Gunicorn restarts it.
timeout = 60

# Graceful worker shutdown timeout. During reload (SIGHUP), Gunicorn allows active
# workers this many seconds to finish serving their active requests before being terminated.
graceful_timeout = 30

# Socket backlog (max number of pending connections). Helps queue incoming connections during reload.
backlog = 2048

# Keepalive connection timeout (seconds) for persistent HTTP/1.1 connections.
keepalive = 5
