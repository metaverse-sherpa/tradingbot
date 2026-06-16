cat << 'INNER_EOF' | sudo tee /etc/nginx/sites-available/bot.metaversesherpa.io
server {
    server_name bot.metaversesherpa.io;

    root /home/gilesasp/tradingbot/webapp;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location ~ ^/(api|unsubscribe) {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/bot.metaversesherpa.io/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/bot.metaversesherpa.io/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot
}

server {
    if ($host = bot.metaversesherpa.io) {
        return 301 https://$host$request_uri;
    } # managed by Certbot

    listen 80;
    server_name bot.metaversesherpa.io;
    return 404; # managed by Certbot
}
INNER_EOF
sudo systemctl restart nginx
