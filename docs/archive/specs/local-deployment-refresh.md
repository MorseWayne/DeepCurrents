# Local Deployment Refresh Design

- 日期: 2026-03-13
- 状态: 已归档（历史设计稿）
- 适用范围: `.env.example`、`docker-compose.yml`、`README.md`、`README.en.md`
- 关联背景:
  - `docs/archive/specs/event-intelligence-layer.md`
  - `docs/archive/specs/event-intelligence-legacy-retirement.md`

## 0. 背景

当前正式主链路已经完全切换到 Event Intelligence runtime。

本地或容器部署要想真正跑通采集与报告，至少需要：

1. PostgreSQL
2. Qdrant
3. Redis
4. 可选 RSSHub（用于 `is_rss_hub=True` 的信息源）

但当前仓库里的本地部署说明仍存在明显不一致：

1. README 仍保留“只跑 RSSHub + Redis 就能本地开发”的表述
2. `docker-compose.yml` 只提供 `deep-currents + rsshub + redis`
3. `.env.example` 中 Event Intelligence runtime 仍被弱化为注释里的可选项
4. 宿主机运行与容器内运行的地址口径没有统一

这会导致用户按文档部署时，采集与报告入口直接 fail-closed，看起来像“系统无法启动”，但根因其实是部署文档已落后于代码。

## 1. 目标

本票目标：

1. 更新本地部署文档，使其与当前 event-centric 运行方式一致
2. 升级 `docker-compose.yml`，使其能支持正式本地栈
3. 统一宿主机模式与 compose 模式的环境变量口径

本票非目标：

1. 不修改 Event Intelligence runtime 代码
2. 不新增生产级运维编排系统
3. 不处理云部署或 Kubernetes 方案

## 2. 方案选择

采用“单 compose 文件，同时支持 infra-only 与 full-stack”方案。

不采用“只改文档不改 compose”的原因：

1. 文档和可执行部署描述会继续脱节
2. 用户仍然无法直接通过 compose 拉起完整本地栈

不采用“拆多个 compose 文件”的原因：

1. 会增加理解和维护成本
2. 对当前仓库阶段来说复杂度收益不匹配

最终方案：

1. 一个 `docker-compose.yml`
2. 同时支持：
   - 宿主机运行 app
   - 容器内运行 app

## 3. Compose 结构

`docker-compose.yml` 调整为 5 个服务：

1. `postgres`
2. `qdrant`
3. `redis`
4. `rsshub`
5. `deep-currents`

### 3.1 网络策略

不再使用 `network_mode: host`，统一使用 compose 默认网络。

原因：

1. host network 对 Linux/macOS 行为不一致
2. 当前项目同时需要“宿主机访问”和“容器间访问”
3. 服务名寻址更稳定、更易于文档说明

### 3.2 地址口径

容器内地址：

1. PostgreSQL: `postgresql://postgres:postgres@postgres:5432/deepcurrents`
2. Qdrant: `http://qdrant:6333`
3. Redis: `redis://redis:6379/0`
4. RSSHub: `http://rsshub:1200`

宿主机地址：

1. PostgreSQL: `postgresql://postgres:postgres@localhost:5432/deepcurrents`
2. Qdrant: `http://localhost:6333`
3. Redis: `redis://localhost:6379/0`
4. RSSHub: `http://localhost:1200`

### 3.3 端口映射

对宿主机公开：

1. `5432:5432`
2. `6333:6333`
3. `6379:6379`
4. `1200:1200`

### 3.4 服务职责

- `postgres`
  - 初始化数据库 `deepcurrents`
  - 持久化 volume
- `qdrant`
  - 提供向量存储
  - 持久化 volume
- `redis`
  - 提供 runtime cache
- `rsshub`
  - 提供 RSSHub 路由
  - 依赖 `redis`
- `deep-currents`
  - 读取 `.env`
  - 在 compose 内覆盖 Event Intelligence runtime 地址与 `RSSHUB_BASE_URL`

## 4. 环境变量更新

### 4.1 `.env.example`

将 Event Intelligence runtime 从“隐含可选”改为“本地正式部署必填示例”。

应明确：

1. `AI_API_KEY`
2. `EVENT_INTELLIGENCE_ENABLED=true`
3. `EVENT_INTELLIGENCE_POSTGRES_DSN`
4. `EVENT_INTELLIGENCE_QDRANT_URL`
5. `EVENT_INTELLIGENCE_REDIS_URL`
6. 可选 `RSSHUB_BASE_URL=http://localhost:1200`

并明确说明：

1. 宿主机运行 app 时使用 `localhost`
2. compose 全栈模式下，容器内地址由 compose 自动覆盖，无需手改 `.env`

## 5. README 更新

### 5.1 正式本地部署路径

文档只保留两条正式路径：

1. 宿主机开发模式
   - `docker compose up -d postgres qdrant redis rsshub`
   - 宿主机执行 `uv run -m src.main` 或 `uv run -m src.run_report`
2. Compose 全栈模式
   - `docker compose up -d --build`
   - `docker compose logs -f deep-currents`

### 5.2 启动前检查

补充最小检查步骤：

1. 端口是否可达
2. `.env` 是否启用 Event Intelligence runtime
3. AI API key 是否已配置

### 5.3 行为说明

需要明确告知：

1. `EVENT_INTELLIGENCE_ENABLED=false` 时不会回退旧文章级链路
2. `run_report --report-only` 需要已有 event-intelligence 数据
3. “只配 AI key 即可本地跑完整系统”的旧表述已失效

### 5.4 中英文同步

`README.md` 与 `README.en.md` 的本地部署说明采用同一信息架构，不再保留旧版 SQLite / article-level 主链路描述。

## 6. 成功标准

本票完成后应满足：

1. 用户按 README 的本地部署步骤，能够启动与当前代码一致的运行环境
2. `docker-compose.yml` 可以同时支持 infra-only 和 full-stack 启动
3. `.env.example` 不再误导用户把 Event Intelligence runtime 当成“可完全忽略的可选项”
