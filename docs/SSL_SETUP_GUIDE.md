# VPS Deployment & SSL Setup Guide

This guide covers how to point your Network Solutions domain to your VPS, configure an Nginx reverse proxy, and install a free SSL certificate to enable secure Google Logins for your Web App.

## Step 1: Point Your Domain (Network Solutions)

DNS changes tell the internet that your domain (`metaversesherpa.io`) lives at your VPS IP address (`35.208.90.255`).

1. **Log In:** Go to the Network Solutions Account Manager and log in.
2. **Navigate to Domains:** Click on **Domains** in the left-hand menu, then select your specific domain name.
3. **Access Advanced DNS:** Scroll down to the **Advanced Tools** section and click **Manage** next to **Advanced DNS Records**.
4. **Add or Edit A Records:**
   - Locate the existing **A Records** and click the pencil icon (Edit) or click **+Add Record**.
   - **Record 1 (Root Domain):**
     - **Host/Alias:** `@` (or leave blank depending on the UI)
     - **Numeric IP Address:** `35.208.90.255`
     - **TTL:** Leave as default (usually 7200)
   - **Record 2 (WWW Subdomain):**
     - **Host/Alias:** `www`
     - **Numeric IP Address:** `35.208.90.255`
     - **TTL:** Leave as default
5. **Save Changes:** Click **Add** or **Continue**, and ensure you confirm the changes on the final summary page.

> [!NOTE]
> DNS propagation can take anywhere from 15 minutes to 24 hours. You can proceed to the next steps immediately, but SSL generation won't work until the DNS has fully updated globally.

---

## Step 2: Install Nginx & Set up Reverse Proxy

Your Python Flask server runs on port `5001`. Nginx acts as a "traffic cop", catching standard web traffic on ports 80/443 and securely passing it to your Python app on port `5001`.

1. **SSH into your VPS.**
2. **Install Nginx:**
   ```bash
   sudo apt update
   sudo apt install nginx -y
   ```
3. **Create the Configuration File:**
   ```bash
   sudo nano /etc/nginx/sites-available/metaversesherpa.io
   ```
4. **Paste the Configuration:**
   ```nginx
   server {
       listen 80;
       server_name metaversesherpa.io www.metaversesherpa.io;

       location / {
           proxy_pass http://127.0.0.1:5001;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```
   Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).
5. **Enable the Site and Restart Nginx:**
   ```bash
   sudo ln -s /etc/nginx/sites-available/metaversesherpa.io /etc/nginx/sites-enabled/
   sudo nginx -t     # This verifies your syntax is correct!
   sudo systemctl restart nginx
   ```

---

## Step 3: Install Free SSL with Certbot

Certbot automatically provisions a free Let's Encrypt SSL certificate and permanently updates your Nginx configuration to force HTTPS connections.

1. **Install Certbot:**
   ```bash
   sudo apt install certbot python3-certbot-nginx -y
   ```
2. **Generate the Certificate:**
   ```bash
   sudo certbot --nginx -d metaversesherpa.io -d www.metaversesherpa.io
   ```
3. **Follow the Prompts:**
   - Enter your email address (for urgent renewal and security notices).
   - Agree to the Terms of Service.
   - When asked whether or not to redirect HTTP traffic to HTTPS, choose the **Redirect** option to ensure all users are forced onto a secure connection.

> [!IMPORTANT]
> If Certbot fails with a `DNS problem: NXDOMAIN` error, it means your Network Solutions DNS changes from Step 1 haven't finished propagating yet. Wait 30 minutes and run the command again.

Once complete, your web app will be securely hosted at `https://metaversesherpa.io`, and Google Login will function flawlessly!
