# Update packages and install prerequisites
sudo apt update
sudo apt install -y ca-certificates curl gnupg lsb-release

# Add Docker official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker APT repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package list again
sudo apt update

# Install Docker Engine + Compose plugin
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Install Git
sudo apt install -y git

# Verify Docker with sudo first
sudo docker run hello-world

# Allow current user to run Docker without sudo
sudo groupadd docker
sudo usermod -aG docker $USER

# Refresh group membership for current session
newgrp docker

# Verify Docker without sudo
docker run hello-world

# Verify installs
docker --version
docker compose version
git --version

git config --global credential.helper 'cache --timeout=3600'
git clone https://github.com/jagadishchandu/SCMS.git cloud
Username = jagadishchandu
Password = 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

git clone https://jagadishchandu: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@github.com/jagadishchandu/SCMS.git cloud
cd SCMS
docker compose up --build
docker compose up -d
docker compose up -d --build

git clone --branch cloud --single-branch https://jagadishchandu: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@github.com/jagadishchandu/SCMS.git



sudo apt update && sudo apt install -y nginx

sudo tee /etc/nginx/sites-available/default >/dev/null <<'EOF'
server {
    listen 80 default_server;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

sudo nginx -t && sudo systemctl restart nginx && sudo systemctl enable nginx


sudo ufw allow 80/tcp

sudo ss -tulpn | grep :3000
#If nothing shows, start your app first.

sudo apt update
sudo apt install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx

cat <<'EOF' | sudo tee /etc/nginx/conf.d/websocket_map.conf
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
EOF

cat <<'EOF' | sudo tee /etc/nginx/sites-available/app3000
server {
    listen 80;
    listen [::]:80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:3000;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 75s;
        proxy_send_timeout 75s;
        proxy_read_timeout 3600s;

        # Uncomment if you see websocket lag/issues
        # proxy_buffering off;
    }
}
EOF

sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -s /etc/nginx/sites-available/app3000 /etc/nginx/sites-enabled/app3000

sudo nginx -t
sudo systemctl reload nginx

Quick troubleshooting
sudo systemctl status nginx --no-pager
sudo tail -n 50 /var/log/nginx/error.log
sudo ss -tulpn | grep -E ':80|:3000'


