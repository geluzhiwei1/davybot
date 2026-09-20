# 开发（默认加载 .env.local > .env）

npm run dev

# 用生产配置开发调试

```bash

# 后端
cd nn-bot/agent
cp .env.prod .env
uv run dawei server start --reload

# 前端
cd nn-bot-app
npm run dev -- --mode prod

```
