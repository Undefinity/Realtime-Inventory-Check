# Ubuntu（阿里云）Docker 部署说明

本项目以 Flask 提供 Web 服务，并通过 Microsoft ODBC Driver 18 访问远程 SQL Server。Docker 镜像已包含 Python、Gunicorn、`pyodbc`、`unixODBC` 与 SQL Server ODBC 驱动；服务器无需再安装 Python 或 ODBC。

## 1. 服务器准备

以下命令在 Ubuntu SSH 控制台执行。按 Docker 官方 APT 仓库方式安装 Docker Engine 和 Compose 插件：

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
exit
```

重新 SSH 登录一次，使 `docker` 用户组生效。之后检查：

```bash
docker --version
docker compose version
```

若第二条命令报错、显示 Docker 帮助信息，或提示 `unknown shorthand flag: 'd'`，说明当前 Docker 没有 Compose v2 插件。可先检查旧版 Compose 是否已存在：

```bash
docker-compose --version
```

若该命令可用，后续将文档中的 `docker compose` 全部替换为 `docker-compose`，例如：

```bash
docker-compose up -d --build
```

若旧版命令也不存在，且 Docker 是通过 Docker 官方 APT 仓库安装的，安装 Compose v2 插件：

```bash
sudo apt update
sudo apt install -y docker-compose-plugin
docker compose version
```

如果提示找不到 `docker-compose-plugin`，表示正在使用 Ubuntu 自带的旧版 Docker 包。请按本节前面的官方 APT 安装步骤安装 Docker Engine 和 Compose 插件；如果该服务器已有其他重要容器或镜像，先不要卸载旧 Docker，以免清理时影响已有数据。

若服务器开启了 UFW，只开放实际使用的端口（本例 5000）：

```bash
sudo ufw allow 5000/tcp
```

还需要在阿里云安全组的**入方向**添加 TCP `5000` 端口。生产环境如使用 Nginx/HTTPS，建议只开放 `80`、`443`，不直接公开 `5000`。

## 2. 上传或拉取项目

推荐从 Git 仓库拉取：

```bash
git clone <你的仓库地址> inventory-web
cd inventory-web
```

若仓库尚未推送，可在本机将整个项目目录上传到服务器，例如：

```powershell
scp -r "C:\Users\KID\Desktop\实时库存盘点" <服务器用户>@<服务器公网IP>:~/inventory-web
```

上传后在服务器进入目录：

```bash
cd ~/inventory-web
```

## 3. 创建生产环境配置

`.env` 不会被打进镜像，也不应提交到 Git。请在服务器创建它：

```bash
cp .env.example .env
nano .env
```

填写真实数据库参数，至少需要：

```dotenv
SQLSERVER_HOST=你的SQLServer地址
SQLSERVER_PORT=2433
SQLSERVER_DATABASE=bwshopsy_01
SQLSERVER_USERNAME=inventory_app
SQLSERVER_PASSWORD=你的数据库密码
SQLSERVER_ENCRYPT=no
```

可选：增加 `WEB_PORT=5000` 可修改对外端口，例如 `WEB_PORT=8080`。

请确认阿里云服务器能连接 SQL Server 的主机和端口；若数据库有 IP 白名单，需要放行该服务器的出口公网 IP。

## 4. 构建并启动

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f
```

日志显示 Gunicorn 已启动后，按 `Ctrl+C` 退出日志跟随（容器仍会后台运行）。浏览器访问：

```text
http://<服务器公网IP>:5000
```

验证服务与数据库连接：

```bash
curl http://127.0.0.1:5000/api/health
```

返回 `"ok": true` 表示 Web 服务和数据库均正常；HTTP 503 或 `"ok": false` 通常表示数据库地址、密码、端口或白名单需要检查。

## 日常维护

```bash
# 查看实时日志
docker compose logs -f

# 停止（不删除镜像）
docker compose down

# 更新代码后重新构建并启动
git pull
docker compose up -d --build

# 查看容器状态
docker compose ps
```

`restart: unless-stopped` 已配置：服务器重启后 Docker 启动时，项目会自动恢复运行；人为执行 `docker compose down` 后不会自动恢复。
