cat << 'INNER_EOF' | sudo tee /etc/nginx/sites-available/bot.metaversesherpa.io
$(cat update_nginx_live.txt)
INNER_EOF

# Remove default site to prevent default_server port 80 conflict
sudo rm -f /etc/nginx/sites-enabled/default
# Ensure our config is properly linked in sites-enabled
sudo ln -sf /etc/nginx/sites-available/bot.metaversesherpa.io /etc/nginx/sites-enabled/
# Restart nginx service
sudo systemctl restart nginx
