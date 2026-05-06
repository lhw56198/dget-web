# dget-web

> 基于 [dget](https://gitee.com/extrame/dget) 的 Docker 镜像可视化下载平台，提供账号登录、实时进度、文件管理等功能，支持 Docker 一键部署。






***

## ✨ 功能特性

- **账号登录**：用户名 + 密码验证，Session Token 管理，安全访问控制
- **可视化下载**：输入镜像名，选择目标架构，一键触发 dget 下载
- **实时日志**：基于 SSE（Server-Sent Events）推送 dget 输出，进度条实时更新
- **任务管理**：任务状态跟踪（pending / running / done / error），支持删除记录
- **文件管理**：按 `tmp_*` 目录分组展示 `.tar.gz` 文件，支持下载和删除
- **明暗主题**：内置白天 / 夜间模式切换
- **后台运行**：`docker compose up -d` 完全后台守护，不占用终端
- **数据持久化**：下载文件和任务记录均挂载到宿主机，容器重建不丢失
- **多架构支持**：镜像同时提供 `linux/amd64` 和 `linux/arm64` 版本

***

## 📸 界面预览

| 夜间模式 | 白天模式 |
|---------|---------|
| 蓝紫渐变主题，适合长时间使用 | 清爽浅色主题 |

***

## 🚀 快速开始

### 前置要求

- Docker 20.10+
- Docker Compose v2+
- `dget` 可执行文件（Linux 二进制，从 [dget releases](https://gitee.com/extrame/dget/releases) 下载）

### 部署步骤

**1. 克隆项目**

```bash
git clone https://github.com/yourname/dget-web.git
cd dget-web
```

**2. 放入 dget 二进制**

将适合你服务器架构的 `dget` 可执行文件复制到项目根目录：

```bash
# 下载对应架构的 dget，重命名为 dget 放入根目录
cp /path/to/dget ./dget
chmod +x ./dget
```

**3. 修改账号密码（可选）**

编辑 `docker-compose.yml`，修改以下两行：

```yaml
environment:
  - DGET_USER=admin       # ← 修改用户名
  - DGET_PASS=admin123    # ← 修改密码
```

**4. 后台构建并启动**

```bash
docker compose up -d --build
```

**5. 访问网页**

浏览器打开：

```
http://你的服务器IP:8080
```

***

## 📖 使用说明

### 下载镜像

在「新建下载任务」面板中：

- **镜像名**：直接输入镜像名称，支持以下格式：
  ```
  nginx:latest
  mysql:8.0
  alibaba-cloud-linux-3-registry.cn-hangzhou.cr.aliyuncs.com/alinux3/alinux3:220901.1
  ```
- **目标架构**：从下拉菜单选择，或选择「✏ 手动输入」自定义，留空则使用 dget 默认架构

### 实时日志

点击左侧任务列表中的任务，右侧面板将实时显示 dget 输出内容，颜色说明：

| 颜色 | 含义 |
|------|------|
| 🟡 黄色 | 执行的命令 |
| 🟢 绿色 | 成功信息 |
| 🔴 红色 | 错误信息 |

### 下载产物

dget 下载完成后，产物 `.tar.gz` 文件保存在 `./downloads/tmp_<author>/` 目录下，在「已下载文件」面板中可直接下载或删除。

***

## ⚙️ 配置说明

所有配置通过 `docker-compose.yml` 的环境变量管理：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `DGET_USER` | `admin` | 登录用户名 |
| `DGET_PASS` | `admin123` | 登录密码 |
| `WORK_DIR` | `/downloads` | dget 工作目录（产物落盘位置） |
| `DATA_DIR` | `/app/data` | 任务记录持久化目录 |
| `PORT` | `8080` | 服务监听端口 |

修改配置后执行 `docker compose restart` 生效。

***

## 📁 项目结构

```
dget-web/
├── dget                    # dget 可执行文件（需自行放入）
├── Dockerfile              # 容器构建配置
├── docker-compose.yml      # 服务编排配置
├── server.py               # Flask 后端（SSE 实时日志 + 鉴权）
├── static/
│   └── index.html          # 前端页面（纯 HTML + JS，无需构建）
└── downloads/              # 下载产物目录（挂载到宿主机）
```

***

## 🛠️ 常用运维命令

```bash
# 后台启动
docker compose up -d --build

# 查看实时日志
docker compose logs -f

# 重启服务
docker compose restart

# 停止服务
docker compose stop

# 停止并删除容器
docker compose down
```

***

## 🏗️ 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python 3.11 + Flask + Flask-CORS |
| 实时推送 | Server-Sent Events (SSE) |
| 前端 | 原生 HTML / CSS / JavaScript（无框架依赖） |
| 容器化 | Docker + Docker Compose |
| 核心工具 | [dget](https://gitee.com/extrame/dget) |

***

## 🔒 安全说明

- 密码使用 SHA-256 哈希比对，不明文存储
- 文件下载/删除使用 `resolve().relative_to()` 防止路径穿越攻击
- 镜像名通过正则白名单校验，防止命令注入
- 所有 API 接口均需 Token 鉴权

***

## 📦 Docker Hub

```bash
# 拉取最新版本（自动匹配 amd64 / arm64）
docker pull beicheng123/dget-web:latest
```

镜像支持平台：`linux/amd64`、`linux/arm64`

***

## 🙏 致谢

- [dget](https://gitee.com/extrame/dget) — 核心下载工具，支持直接从 Docker Hub 下载镜像 tar 包
