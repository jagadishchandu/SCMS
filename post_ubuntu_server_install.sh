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
