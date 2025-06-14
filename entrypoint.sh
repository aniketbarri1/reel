#!/bin/bash

# Start log rotation
echo "0 * * * * root /usr/sbin/logrotate -f /etc/logrotate.d/instagram_logs" > /etc/cron.d/logrotate-instagram
cron

# Start uploader
python3 main.py >> logs/uploader.log 2>&1
