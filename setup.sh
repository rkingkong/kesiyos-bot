#!/bin/bash
# =============================================================================
# Kesiyos Bot — Server Setup Script
# Run this once on your Odoo server to set up the bot environment.
# Execute as root or with sudo.
# =============================================================================

set -e

echo "=== Kesiyos Bot — Initial Setup ==="

# 1. Create system user (no login shell)
echo "[1/7] Creating system user..."
if ! id "kesiyos-bot" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin kesiyos-bot
    echo "  Created user: kesiyos-bot"
else
    echo "  User kesiyos-bot already exists"
fi

# 2. Create log directory
echo "[2/7] Creating log directory..."
mkdir -p /var/log/kesiyos-bot
chown kesiyos-bot:kesiyos-bot /var/log/kesiyos-bot

# 3. Create PostgreSQL database and user
echo "[3/7] Setting up PostgreSQL database..."
echo "  Enter a strong password for the kesiyos_bot database user:"
read -s DB_PASSWORD
echo

sudo -u postgres psql <<EOF
-- Create user if not exists
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'kesiyos_bot') THEN
        CREATE ROLE kesiyos_bot WITH LOGIN PASSWORD '${DB_PASSWORD}';
    END IF;
END
\$\$;

-- Create database
SELECT 'CREATE DATABASE kesiyos_bot OWNER kesiyos_bot'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'kesiyos_bot')\gexec

-- Ensure extensions
\c kesiyos_bot
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
EOF
echo "  Database kesiyos_bot ready"

# 4. Copy project files
echo "[4/7] Setting up project directory..."
mkdir -p /opt/kesiyos-bot
cp -r . /opt/kesiyos-bot/
chown -R kesiyos-bot:kesiyos-bot /opt/kesiyos-bot

# 5. Python virtual environment
echo "[5/7] Creating Python virtual environment..."
cd /opt/kesiyos-bot
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
echo "  Dependencies installed"

# 6. Create .env from template
echo "[6/7] Preparing .env file..."
if [ ! -f /opt/kesiyos-bot/.env ]; then
    cp .env.example .env
    # Fill in the DB password
    sed -i "s/CHANGE_ME_STRONG_PASSWORD/${DB_PASSWORD}/" .env
    chown kesiyos-bot:kesiyos-bot .env
    chmod 600 .env
    echo "  .env created — EDIT IT NOW to fill in Meta, WhatsApp, and Claude tokens"
else
    echo "  .env already exists — skipping"
fi

# 7. Install systemd service
echo "[7/7] Installing systemd service..."
cp kesiyos-bot.service /etc/systemd/system/
systemctl daemon-reload
echo "  Service installed (not started yet)"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit /opt/kesiyos-bot/.env with your actual tokens"
echo "  2. Run database migrations:"
echo "     cd /opt/kesiyos-bot && venv/bin/alembic upgrade head"
echo "  3. Add Nginx config (see nginx-kesiyos-bot.conf)"
echo "  4. Start the service:"
echo "     sudo systemctl enable --now kesiyos-bot"
echo "  5. Check status:"
echo "     curl https://kesiyos.com/meta/health"
echo ""
