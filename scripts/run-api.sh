#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")/.." >/dev/null

if [[ -z "${AOP_DATABASE_URL:-}" ]] && [[ ! -f config.toml ]]; then
  echo "数据库未配置。"
  echo "请创建 config.toml 文件或设置 AOP_DATABASE_URL 环境变量。"
  echo "参考示例: cp config.toml.example config.toml"
  exit 1
fi

uv run uvicorn agent_platform.main:app --reload
