# Anuma 2API 网关

一个基于 [Anuma AI](https://anuma.ai) 账号的自托管 API 网关，提供 OpenAI/Anthropic 兼容接口。集成了临时邮箱自动注册、账号池管理、负载均衡及自动故障切换。

> **致谢**: 临时邮箱服务由 [小辣椒的临时邮箱](https://vip.215.im) (vip.215.im) 提供 —— 快速稳定的临时邮箱 API，免费额度充足。

## 功能特性

- **批量注册账号** — 基于临时邮箱的全自动注册，包含 Privy 认证及嵌入式钱包创建。Web 界面实时查看进度。
- **OpenAI & Anthropic 兼容** — 支持 Claude Code、Cherry Studio、ChatBox 及所有兼容 OpenAI/Anthropic 协议的客户端。
- **智能负载均衡** — 账号池轮询调度，自动检测并禁用余额耗尽或 Token 过期的账号。
- **Token 自动续期** — 请求前主动检测 JWT 过期时间并续期，后台守护进程定时巡检。
- **流式传输** — 完整支持 OpenAI 和 Anthropic 格式的 SSE 流式响应。
- **工具调用** — 翻译工具调用请求，完美兼容 Claude Code。
- **代理支持** — 可选 SOCKS5 代理，适用于网络受限环境。

## 项目架构

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────┐
│  AI 客户端    │────▶│  api_server.py   │────▶│  Anuma API   │
│ (Claude Code,│     │  (FastAPI :7895)  │     │  portal.anuma│
│  Cherry St.) │     └────────┬─────────┘     └─────────────┘
└──────────────┘              │
                              │ 读取
                              ▼
┌──────────────┐     ┌──────────────────┐
│  Web 管理界面 │────▶│ privy_manager.py │
│  (Flask)     │     │  (Flask :7894)    │
└──────────────┘     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐     ┌──────────────────┐
                     │  anuma_client.py │────▶│  小辣椒 临时邮箱    │
                     │  (SDK)           │     │  (vip.215.im)     │
                     └──────────────────┘     └──────────────────┘
```

## 项目结构

| 文件 | 说明 |
|------|------|
| `config.py` | 统一配置管理，从环境变量读取 |
| `anuma_client.py` | 底层 SDK：Privy 认证、Anuma 对话、临时邮箱客户端 |
| `privy_manager.py` | Flask Web 界面 + 批量注册引擎 |
| `api_server.py` | FastAPI 网关，提供 OpenAI/Anthropic 兼容接口 |
| `templates/index.html` | Web 管理面板模板 |
| `docker-compose.yml` | Docker 容器编排 |

## 快速开始

### 1. 环境要求

- Python 3.10+
- [小辣椒临时邮箱](https://vip.215.im) 的 API Key
- 可选：SOCKS5 代理（如果所在地区无法直连 Anuma）

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env，填入 MAIL_API_KEY
```

必填：`MAIL_API_KEY` — vip.215.im 的邮箱 API Key。
可选：`SOCKS5_PROXY` — API 请求代理地址。

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 启动注册管理器（Web 界面）

```bash
python3 privy_manager.py
```

访问 http://localhost:7894 — 设置注册总数和并发数，点击「开始任务」批量注册账号。

### 5. 启动 API 网关

```bash
python3 api_server.py
```

网关默认运行在 `http://localhost:7895/v1`（可通过 `API_PORT` 环境变量修改）。

### 6. 接入客户端

**Claude Code:**
```bash
export ANTHROPIC_BASE_URL=http://localhost:7895/v1
export ANTHROPIC_API_KEY=sk-no-auth-needed
claude
```

**Cherry Studio:**
添加 OpenAI 兼容模型库：
- 接口地址：`http://localhost:7895/v1`
- API Key：任意值（不校验）

## API 接口

### `GET /v1/models`

获取可用模型列表。

### `POST /v1/chat/completions`

OpenAI 兼容的聊天补全接口，支持流式。

### `POST /v1/messages`

Anthropic 兼容的消息接口，支持流式和工具调用。

### 模型映射

| 客户端模型名称 | Anuma 上游模型 |
|---------------|---------------|
| `gpt-5.4` | `openai/gpt-5.4` |
| `gpt-4` | `openai/gpt-4` |
| `claude-opus` / `claude-3-7` | `anthropic/claude-opus-4-7` |
| `claude-sonnet` | `anthropic/claude-sonnet-4-6` |

## Docker 部署

```bash
# 构建并启动
docker compose up -d

# 查看日志
docker compose logs -f api-server
```

两个服务共享挂载在 `./data` 的 SQLite 数据库。启动前请先创建 `.env` 文件。

## 环境变量

完整参考见 [`.env.example`](.env.example)。

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `MAIL_API_KEY` | **是** | — | vip.215.im 的邮箱 API Key |
| `MAIL_API_BASE_URL` | 否 | `https://maliapi.215.im/v1` | 自定义邮箱 API 地址 |
| `SOCKS5_PROXY` | 否 | — | 上游请求的 SOCKS5 代理 |
| `DB_PATH` | 否 | `./privy_manager.db` | SQLite 数据库路径 |
| `MANAGER_PORT` | 否 | `7894` | Web 界面端口 |
| `API_PORT` | 否 | `7895` | API 网关端口 |
| `API_HOST` | 否 | `0.0.0.0` | API 绑定地址 |
| `DEFAULT_TOTAL` | 否 | `10` | 默认注册批次数 |
| `DEFAULT_CONCURRENCY` | 否 | `3` | 默认并发线程数 |

## 注意事项

1. 推荐并发数 2-3，过高可能触发频率限制或 IP 被封。
2. 网关会自动停用余额为 0 或 Token 过期的账号。
3. Token 续期在请求前主动检测和后台守护（每 10 分钟）两个时机进行。
4. `identity_token` 是会话关键凭证，SDK 内部处理了复杂的换票逻辑。

## 开源协议

[MIT](LICENSE)