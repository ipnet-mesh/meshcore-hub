# Maintenance

This document covers operational maintenance tasks for MeshCore Hub. For routine data-retention cleanup of old events and inactive nodes, see [configuration.md → Data Retention](configuration.md#data-retention).

## Backup & Restore

### Using Makefile

```bash
# Back up all volumes to backup/
make backup

# Restore a specific volume
make restore FILE=backup/hub_data-20260414-120000.tar.gz
```

### Using shell commands

```bash
# Back up the database volume
source .env 2>/dev/null || true
mkdir -p backup
vol=${COMPOSE_PROJECT_NAME:-hub}_data
docker run --rm -v $vol:/data -v $(pwd)/backup:/backup \
  alpine tar czf /backup/$vol-$(date +%Y%m%d-%H%M%S).tar.gz -C / data

# Restore a specific volume (volume name derived from tarball filename)
source .env 2>/dev/null || true
FILE=backup/${COMPOSE_PROJECT_NAME:-hub}_data-20260414-120000.tar.gz
vol=$(basename "$FILE" | sed 's/-[0-9]\{8\}-[0-9]\{6\}\.tar\.gz//')
docker run --rm -v $vol:/data -v $(pwd)/backup:/backup \
  alpine sh -c "cd / && tar xzf /backup/$(basename $FILE)"
```

> **Note:** Replace `hub` with your `COMPOSE_PROJECT_NAME` if using a different instance name. Monitoring infrastructure (Prometheus, Alertmanager) manages its own data — consult your monitoring stack's documentation for backup procedures.
