from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from apps.api.adapters.base import (
    AdapterCapability,
    HealthCheckResult,
    NormalizedDailyBar,
    NormalizedStock,
    ProviderMetadata,
    StockDataSourceAdapter,
    normalize_daily_bar_adjust_type,
)


# =============================================================================
# 【小白必读】stock_sdk.py 是什么？
# =============================================================================
#
# 这个适配器和其他所有适配器都不同 —— 它不是调用 Python 包，
# 而是启动一个 Node.js 子进程来运行 stock-sdk（一个 JavaScript/TypeScript 包）。
#
# 为什么会有这种设计？
#   某些股票数据 SDK 只有 Node.js 版本，没有 Python 版本。
#   与其等别人写 Python 封装，不如直接用子进程调用 Node.js 脚本。
#
# 工作原理：
#   Python（主进程）
#     │
#     ├─ subprocess.run(["node", "-e", NODE_STOCK_SDK_SCRIPT], input=json)
#     │
#     └─ Node.js 子进程
#          ├─ require("stock-sdk")
#          ├─ 调用对应的函数
#          └─ stdout 输出 JSON 结果
#
# 这是一种常见的"跨语言调用"模式：
#   Python ←—JSON→ Node.js（通过标准输入/输出通信）
#
# 这个文件的特殊之处：
#   ① 内含一大段 JavaScript 代码（NODE_STOCK_SDK_SCRIPT）
#   ② 用 subprocess 启动 Node.js 进程
#   ③ 通过 JSON 标准输入/输出和子进程通信
#   ④ 需要 Node.js 环境 + stock-sdk npm 包


# =============================================================================
# 内嵌的 JavaScript 脚本
# =============================================================================
#
# 这段 JS 代码会被保存为字符串，然后通过 node -e 执行。
# 它是一个通用的 SDK 调用桥接器：接收 JSON 输入，调用 stock-sdk，输出 JSON 结果。
#
# 输入格式（通过 stdin）：
#   {"action": "codes.cn",      "params": {"market": "A_SHARE"}}
#   {"action": "kline.cn",      "params": {"symbol": "600519", ...}}
#   {"action": "health",        "params": {}}
#   {"action": "namespace.fn",  "params": {...}}              ← 通用调用
#
# 输出格式（通过 stdout）：
#   JSON 数组 [{"code": "600519", "name": "贵州茅台"}, ...]

NODE_STOCK_SDK_SCRIPT = r"""
const fs = require("fs");
const { createRequire } = require("module");
const { pathToFileURL } = require("url");

function compactError(error) {
  const code = error && (error.code || error.sdkCode);
  const provider = error && error.provider;
  const status = error && error.status;
  const url = error && error.url;
  const message = error && error.message ? error.message : String(error);
  const cause = error && error.cause && error.cause.message;
  const parts = ["stock-sdk request failed"];
  if (code) {
    parts.push(`code=${code}`);
  }
  if (provider) {
    parts.push(`provider=${provider}`);
  }
  if (status) {
    parts.push(`status=${status}`);
  }
  if (message) {
    parts.push(`message=${message}`);
  }
  if (url) {
    parts.push(`url=${url}`);
  }
  if (cause && cause !== message) {
    parts.push(`cause=${cause}`);
  }
  return parts.join("; ");
}

(async () => {
  // ---- 步骤 1：读取 Python 端发来的 JSON 指令 ----
  const input = JSON.parse(fs.readFileSync(0, "utf8") || "{}");

  // ---- 步骤 2：加载 stock-sdk 包 ----
  // createRequire 从当前工作目录加载，保证找到用户安装的 stock-sdk
  const requireFromCwd = createRequire(process.cwd() + "/package.json");
  let mod;
  try {
    // 优先用 ESM import（现代 JS）
    mod = await import(pathToFileURL(requireFromCwd.resolve("stock-sdk")).href);
  } catch (importError) {
    // 降级到 CommonJS require（传统 JS）
    mod = requireFromCwd("stock-sdk");
  }

  // ---- 步骤 3：获取 SDK 实例 ----
  // stock-sdk 可能以多种方式导出，逐一尝试；只接受真正暴露 codes/kline 的对象。
  function hasSdkApi(candidate) {
    return Boolean(candidate && (
      candidate.codes ||
      candidate.kline ||
      candidate.batch ||
      candidate.getAShareCodeList ||
      candidate.getAllAShareQuotes ||
      candidate.getHistoryKline ||
      candidate.getKlineWithIndicators
    ));
  }

  function instantiate(candidate) {
    if (!candidate) {
      return null;
    }
    if (typeof candidate === "function") {
      return new candidate();
    }
    if (typeof candidate.StockSDK === "function") {
      return new candidate.StockSDK();
    }
    return candidate;
  }

  const sdkCandidates = [
    mod.StockSDK,
    mod.default && mod.default.StockSDK,
    mod.default,
    mod.stock,
    mod.default && mod.default.stock,
    mod
  ];
  let sdk = null;
  for (const candidate of sdkCandidates) {
    const instance = instantiate(candidate);
    if (hasSdkApi(instance)) {
      sdk = instance;
      break;
    }
  }
  if (!sdk) {
    throw new Error("stock-sdk did not export a usable SDK instance or constructor.");
  }

  // ---- 步骤 4：检查可用方法（用于健康检查） ----
  const stockListCallable = Boolean(
    (sdk.codes && sdk.codes.cn) ||
    (sdk.batch && sdk.batch.cn) ||
    sdk.getAShareCodeList ||
    sdk.getAllAShareQuotes
  );
  const klineCallable = Boolean(
    (sdk.kline && (sdk.kline.cn || sdk.kline.getHistoryKline || sdk.kline.withIndicators)) ||
    sdk.getHistoryKline ||
    sdk.getKlineWithIndicators
  );

  if (input.action === "health") {
    process.stdout.write(JSON.stringify({
      hasCodes: stockListCallable,
      hasKline: klineCallable
    }));
    return;
  }

  // ---- 步骤 5：包装股票列表调用 ----
  async function callStockList(params) {
    if (sdk.codes && typeof sdk.codes.cn === "function") {
      return sdk.codes.cn(params || {});
    }
    if (sdk.batch && typeof sdk.batch.cn === "function") {
      return sdk.batch.cn(params || {});
    }
    if (typeof sdk.getAShareCodeList === "function") {
      return sdk.getAShareCodeList(params || {});
    }
    if (typeof sdk.getAllAShareQuotes === "function") {
      return sdk.getAllAShareQuotes(params || {});
    }
    throw new Error("stock-sdk does not expose codes.cn, batch.cn, getAShareCodeList or getAllAShareQuotes.");
  }

  // ---- 步骤 6：包装 K 线调用 ----
  function normalizeDate(value) {
    if (value == null || value === "") {
      return undefined;
    }
    const text = String(value);
    const digits = text.replace(/[-/]/g, "").slice(0, 8);
    return /^\d{8}$/.test(digits) ? digits : text;
  }

  async function callKline(params) {
    const symbol = params.symbol || params.code;
    if (!symbol) {
      throw new Error("stock-sdk kline request requires a symbol.");
    }
    const options = {
      ...params,
      period: params.period || "daily",
      adjust: params.adjust === undefined ? "" : params.adjust,
      startDate: normalizeDate(params.startDate || params.start_date),
      endDate: normalizeDate(params.endDate || params.end_date)
    };
    delete options.symbol;
    delete options.code;

    // 尝试多种 K 线 API 路径
    if (sdk.kline && typeof sdk.kline.cn === "function") {
      if (sdk.kline.cn.length >= 2) {
        return sdk.kline.cn(symbol, options);
      }
      return sdk.kline.cn(params || {});
    }
    if (sdk.kline && typeof sdk.kline.getHistoryKline === "function") {
      return sdk.kline.getHistoryKline(symbol, options);
    }
    if (sdk.kline && typeof sdk.kline.withIndicators === "function") {
      return sdk.kline.withIndicators(symbol, options);
    }
    if (typeof sdk.getHistoryKline === "function") {
      return sdk.getHistoryKline(symbol, options);
    }
    if (typeof sdk.getKlineWithIndicators === "function") {
      return sdk.getKlineWithIndicators(symbol, options);
    }
    throw new Error("stock-sdk does not expose kline.cn, kline.getHistoryKline, kline.withIndicators, getHistoryKline or getKlineWithIndicators.");
  }

  // ---- 步骤 7：根据 action 分发 ----
  if (input.action === "codes.cn") {
    const result = await callStockList(input.params || {});
    process.stdout.write(JSON.stringify(result == null ? [] : result));
    return;
  }

  if (input.action === "kline.cn") {
    const result = await callKline(input.params || {});
    process.stdout.write(JSON.stringify(result == null ? [] : result));
    return;
  }

  // 通用调用：支持任意 namespace.method
  const [namespaceName, methodName] = String(input.action || "").split(".");
  const namespace = sdk[namespaceName];
  const fn = namespace && namespace[methodName];
  if (typeof fn !== "function") {
    throw new Error(`stock-sdk does not expose ${input.action}.`);
  }

  const result = await fn.call(namespace, input.params || {});
  process.stdout.write(JSON.stringify(result == null ? [] : result));
})().catch((error) => {
  // 出错时写入短诊断，避免把本地 node_modules 路径和 JS 堆栈泄漏到管理页面。
  process.stderr.write(
    typeof compactError === "function"
      ? compactError(error)
      : (error && error.message ? error.message : String(error))
  );
  process.exit(1);
});
"""


# =============================================================================
# Python 端工具函数
# =============================================================================


def _clean_text(value: Any) -> str | None:
    """清洗文本值。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--", "nan", "NaN", "None"}:
        return None
    return text


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    """
    从 Node.js 返回的 JSON 中提取字典列表。

    这个函数比 _records_from_frame 更复杂，因为：
      Node.js 返回的 JSON 格式不固定 ——
      有时直接是数组 [{...}, {...}]
      有时是 {"data": [{...}], "total": 100}
      有时是 {"items": [{...}]}
      有时数组元素是字符串而不是字典

    这个函数把所有这些情况都兜住，输出统一的字典列表。
    """
    def record_from_item(item: Any) -> dict[str, Any] | None:
        """把单个元素转成字典。"""
        if isinstance(item, dict):
            return item
        # 如果元素是字符串，创建一个 {"code": 字符串, "name": 字符串} 的字典
        text = _clean_text(item)
        if text is None:
            return None
        return {"code": text, "name": text}

    # 情况一：pandas DataFrame（极少数情况，Node.js 端可能返回）
    if hasattr(payload, "to_dict"):
        records = payload.to_dict(orient="records")
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]

    # 情况二：直接就是数组（最常见）
    if isinstance(payload, list):
        return [
            record
            for item in payload
            if (record := record_from_item(item)) is not None
        ]

    # 情况三：带包装的对象 {"data": [...], "total": 100}
    if isinstance(payload, dict):
        for key in ("data", "items", "records", "list", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [
                    record
                    for item in value
                    if (record := record_from_item(item)) is not None
                ]
        # 如果就是一个普通的单条记录，直接包成列表
        return [payload]

    raise TypeError("stock-sdk returned an unsupported payload.")


def _parse_date(value: Any) -> date | None:
    """解析各种可能的日期格式。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _clean_text(value)
    if text is None:
        return None
    digits = text.replace("-", "").replace("/", "")[:8]
    if len(digits) == 8 and digits.isdigit():
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    return date.fromisoformat(text.replace("/", "-")[:10])


def _to_float(value: Any, *, default: float | None = None) -> float | None:
    """安全转浮点数。"""
    text = _clean_text(value)
    if text is None:
        return default
    return float(text)


def _normalize_exchange(value: Any, *, symbol: str) -> str:
    """统一交易所代码（和 adata.py 里逻辑一致）。"""
    text = (_clean_text(value) or "").upper()
    exchange_map = {
        "SH": "SSE", "SSE": "SSE", "XSHG": "SSE", "上海": "SSE",
        "SZ": "SZSE", "SZSE": "SZSE", "XSHE": "SZSE", "深圳": "SZSE",
        "BJ": "BSE", "BSE": "BSE", "北京": "BSE",
    }
    if text in exchange_map:
        return exchange_map[text]
    if symbol.startswith(("43", "83", "87", "88", "92")):
        return "BSE"
    if symbol.startswith(("5", "6", "9")):
        return "SSE"
    return "SZSE"


def _split_symbol_and_exchange(
    raw_symbol: Any, raw_exchange: Any = None
) -> tuple[str | None, str | None]:
    """从各种代码格式中提取 (纯代码, 交易所)，和 adata.py 逻辑一致。"""
    text = _clean_text(raw_symbol)
    if text is None:
        return None, None

    normalized = text.replace("_", ".")
    exchange_hint = raw_exchange

    if "." in normalized:
        left, _, right = normalized.partition(".")
        if left.isdigit():
            normalized = left
            exchange_hint = exchange_hint or right
        elif right.isdigit():
            normalized = right
            exchange_hint = exchange_hint or left
    else:
        lower = normalized.lower()
        for prefix in ("sh", "sz", "bj"):
            if lower.startswith(prefix) and normalized[2:].isdigit():
                normalized = normalized[2:]
                exchange_hint = exchange_hint or prefix
                break

    symbol = "".join(
        character for character in normalized if character.isdigit()
    )
    if not symbol:
        return None, None
    return symbol, _normalize_exchange(exchange_hint, symbol=symbol)


def _status_from_record(record: dict[str, Any]) -> str:
    """判断股票状态，和 adata.py 逻辑一致。"""
    raw_status = (
        _clean_text(
            record.get("status")
            or record.get("listStatus")
            or record.get("list_status")
        )
        or ""
    ).lower()
    raw_name = (
        _clean_text(
            record.get("name")
            or record.get("shortName")
            or record.get("short_name")
        )
        or ""
    ).lower()

    if raw_status in {"0", "delisted", "d", "退市"} or "退" in raw_name:
        return "DELISTED"
    if raw_status in {"suspended", "s", "暂停"}:
        return "SUSPENDED"
    return "LISTED"


# =============================================================================
# Node.js 子进程管理辅助类
# =============================================================================


class _NodeStockSdkNamespace:
    """
    模拟 Python 的层级式 API 调用。

    这个类让 Python 端可以这样写：
      client.codes.cn(market="A_SHARE")    # 实际上调用 Node 端 codes.cn
      client.kline.cn(symbol="600519", ...) # 实际上调用 Node 端 kline.cn

    原理：
      _NodeStockSdkNamespace("codes") → 记住自己属于 "codes" 命名空间
      调用 .cn(**kwargs) → 转发为 client.run("codes.cn", kwargs)
    """
    def __init__(self, client: "_NodeStockSdkClient", namespace: str) -> None:
        self._client = client
        self._namespace = namespace

    def cn(self, **kwargs: Any) -> list[dict[str, Any]]:
        """调用 Node 端的 namespace.cn 方法。"""
        return self._client.run(f"{self._namespace}.cn", kwargs)


class _NodeStockSdkClient:
    """
    Node.js 子进程客户端 —— 负责启动和管理 Node.js 子进程。

    关键设计：
      - 每次调用都是独立的子进程（用完就关，不留长连接）
      - 通过 JSON stdin/stdout 和子进程通信
      - 30 秒超时
    """

    def __init__(self) -> None:
        # 可以通过环境变量指定 Node.js 路径
        self.node_executable = os.getenv("STOCK_SDK_NODE", "node")
        self.cwd = _stock_sdk_cwd()

        # 暴露 codes 和 kline 两个命名空间
        self.codes = _NodeStockSdkNamespace(self, "codes")
        self.kline = _NodeStockSdkNamespace(self, "kline")

    def health_check(self) -> dict[str, Any]:
        """健康检查：问 Node 端 stock-sdk 有没有需要的函数。"""
        return self.run("health", {})

    def run(self, action: str, params: dict[str, Any]) -> Any:
        """
        启动 Node.js 子进程，发送 JSON 指令，读取 JSON 结果。

        这是 Python ↔ Node.js 通信的核心方法。

        流程图：
          Python                                Node.js 子进程
          ──────                                ─────────────
          subprocess.run(                       json.loads(stdin)
              input='{"action":"codes.cn",...}'  → 解析指令
          )                                     → 调用 sdk.codes.cn(...)
                                                → stdout.write(JSON结果)

          json.loads(completed.stdout)          子进程退出
          → 返回 Python 对象

        错误处理：
          - Node 没装 → ModuleNotFoundError
          - 超时 → RuntimeError
          - Node 报错 → RuntimeError（包含 Node 端的错误信息）
        """
        try:
            completed = subprocess.run(
                [self.node_executable, "-e", NODE_STOCK_SDK_SCRIPT],
                # -e 表示把后面的字符串当 JS 代码执行
                input=json.dumps(
                    {"action": action, "params": params},
                    ensure_ascii=False,
                ),
                capture_output=True,  # 捕获 stdout 和 stderr
                text=True,            # 文本模式（不是 bytes）
                encoding="utf-8",
                cwd=str(self.cwd),    # 在 stock-sdk 所在目录执行
                timeout=30,           # 30 秒超时
                check=False,          # 不自动抛异常，我们自己处理
            )
        except FileNotFoundError as exc:
            # Node.js 没装
            logger.warning("Node.js not found: %s", exc)
            raise ModuleNotFoundError(
                "Node.js is required to use stock-sdk."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "stock-sdk request timed out."
            ) from exc

        # Node 端执行失败（return_code != 0）
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            if (
                "Cannot find module 'stock-sdk'" in stderr
                or "Cannot find package 'stock-sdk'" in stderr
            ):
                raise ModuleNotFoundError(
                    "stock-sdk Node package is not installed. "
                    "Install stock-sdk@beta to enable this source."
                )
            raise RuntimeError(
                stderr or "stock-sdk request failed."
            )

        # 解析 Node 端返回的 JSON
        stdout = completed.stdout.strip()
        if not stdout:
            return []
        return json.loads(stdout)


def _stock_sdk_cwd() -> Path:
    """
    确定 stock-sdk Node 包所在的目录。

    优先级：
      ① 环境变量 STOCK_SDK_CWD（用户显式指定）
      ② apps/web 目录（monorepo 的标准位置）
      ③ 项目根目录（兜底）
    """
    configured = os.getenv("STOCK_SDK_CWD")
    if configured:
        return Path(configured)

    # __file__ 是当前文件的绝对路径
    # .resolve().parents[3] 向上 3 级：
    #   stock_sdk.py → adapters/ → api/ → apps/ → Quant/（项目根目录）
    repo_root = Path(__file__).resolve().parents[3]
    web_app = repo_root / "apps" / "web"
    if web_app.exists():
        return web_app
    return repo_root


# =============================================================================
# 主类：Stock SDK 适配器
# =============================================================================


class StockSdkAdapter(StockDataSourceAdapter):
    """
    Stock SDK 适配器 —— 通过 Node.js 子进程调用 stock-sdk。

    和其他适配器的关键区别：
      - 不是 import Python 包，而是 subprocess.run Node.js
      - provider_type = "node_package"（而非 "python_package"）
      - 默认不启用（因为需要 Node.js + npm 环境）
      - 优先级最低（45），作为最后的备选方案
    """

    code = "stock_sdk"
    name = "Stock SDK"
    priority = 45           # ★ 最低优先级，实验性质
    requires_token = False
    default_enabled = False # ★ 默认关闭，需要用户手动配置 Node 环境

    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(
            stock_list=True,
            daily_bars=True,
            daily_bar_exchanges=("SSE", "SZSE", "BSE"),
        )

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_type="node_package",  # ★ 注意：不是 python_package
            homepage_url="https://github.com/chengzuopeng/stock-sdk",
            docs_url="https://stock-sdk-v2.linkdiary.cn/",
            auth_mode="none",
            stability="community",
            rate_limit_note="Uses stock-sdk public upstream data sources; keep this source disabled unless the Node package is installed.",
            install_note="Install optional Node package in apps/web or STOCK_SDK_CWD: npm install stock-sdk@beta.",
        )

    def health_check(self) -> HealthCheckResult:
        """
        检查 Node.js + stock-sdk 是否可用。

        和 Python 适配器不同，这里的 health_check 会真的启动 Node 子进程。
        所以如果 Node 没装，这里就会暴露出来。
        """
        try:
            client = self._get_client()
            if hasattr(client, "health_check"):
                result = client.health_check()
                if not result.get("hasCodes") or not result.get("hasKline"):
                    return HealthCheckResult(
                        healthy=False,
                        status="unhealthy",
                        message="stock-sdk is installed, but stock list or kline APIs were not found.",
                    )
            else:
                codes = getattr(client, "codes", None)
                kline = getattr(client, "kline", None)
                if not hasattr(codes, "cn") or not hasattr(kline, "cn"):
                    return HealthCheckResult(
                        healthy=False,
                        status="unhealthy",
                        message="stock-sdk client does not expose codes.cn and kline.cn.",
                    )
        except ModuleNotFoundError as exc:
            logger.warning("stock-sdk health check failed (unavailable): %s", exc)
            return HealthCheckResult(
                healthy=False, status="unavailable", message=str(exc)
            )
        except Exception as exc:
            logger.warning("stock-sdk health check failed: %s", exc)
            return HealthCheckResult(
                healthy=False, status="unhealthy", message=str(exc)
            )

        return HealthCheckResult(
            healthy=True,
            status="healthy",
            message="stock-sdk package is available.",
        )

    # ===== 获取股票列表 =====

    def fetch_stock_list(self, *, market: str) -> list[dict[str, Any]]:
        """
        通过 Node.js 子进程获取股票列表。

        调用链：
          Python fetch_stock_list()
            → client.codes.cn(market="A_SHARE")
              → _NodeStockSdkNamespace.cn()
                → _NodeStockSdkClient.run("codes.cn", {...})
                  → subprocess.run(node -e SCRIPT)
                    → Node.js: callStockList({market: "A_SHARE"})
                      → sdk.codes.cn({market: "A_SHARE"})
                        → stdout: JSON 数组
        """
        if market.upper() != "A_SHARE":
            raise ValueError(
                "stock-sdk stock list adapter currently supports A_SHARE only."
            )

        client = self._get_client()
        codes = getattr(client, "codes", None)
        if not hasattr(codes, "cn"):
            raise RuntimeError(
                "stock-sdk client does not expose codes.cn."
            )
        return _records_from_payload(codes.cn(market="A_SHARE"))

    def normalize_stock_list(
        self, raw_records: list[dict[str, Any]]
    ) -> list[NormalizedStock]:
        """
        把 stock-sdk 原始数据转成统一格式。

        stock-sdk 的字段名是 camelCase 风格（JavaScript 惯例）：
          code / symbol / stockCode / stock_code
          name / shortName / short_name / stockName
          listDate / list_date / listingDate
        """
        normalized: list[NormalizedStock] = []

        for record in raw_records:
            symbol, exchange = _split_symbol_and_exchange(
                record.get("code")
                or record.get("symbol")
                or record.get("stockCode")
                or record.get("stock_code"),
                record.get("exchange") or record.get("market"),
            )
            name = _clean_text(
                record.get("name")
                or record.get("shortName")
                or record.get("short_name")
                or record.get("stockName")
            )

            if symbol is None or exchange is None or name is None:
                continue

            normalized.append(
                NormalizedStock(
                    symbol=symbol,
                    exchange=exchange,
                    market="A_SHARE",
                    name=name,
                    status=_status_from_record(record),
                    industry=_clean_text(
                        record.get("industry") or record.get("sector")
                    ),
                    listing_date=_parse_date(
                        record.get("listDate")
                        or record.get("list_date")
                        or record.get("listingDate")
                    ),
                    delisting_date=_parse_date(
                        record.get("delistDate")
                        or record.get("delist_date")
                        or record.get("delistingDate")
                    ),
                    source=self.code,
                )
            )

        return normalized

    # ===== 获取日K线 =====

    def fetch_daily_bars(
        self,
        *,
        symbol: str,
        exchange: str | None,
        market: str,
        start_date: date,
        end_date: date,
        adjust_type: str = "none",
    ) -> list[dict[str, Any]]:
        """
        通过 Node.js 子进程获取日K线。

        和 fetch_stock_list 一样通过 client.kline.cn() → subprocess → Node.js 的链路。
        同时传 snake_case 和 camelCase 的参数，兼容 stock-sdk 的不同版本。
        """
        if market.upper() != "A_SHARE":
            raise ValueError(
                "stock-sdk daily bars adapter currently supports A_SHARE only."
            )
        adjust_type_code = normalize_daily_bar_adjust_type(adjust_type)
        if adjust_type_code != "none":
            raise ValueError("stock-sdk daily bars adapter currently supports unadjusted bars only.")

        client = self._get_client()
        kline = getattr(client, "kline", None)
        if not hasattr(kline, "cn"):
            raise RuntimeError(
                "stock-sdk client does not expose kline.cn."
            )
        return _records_from_payload(
            kline.cn(
                symbol=symbol,
                code=symbol,
                exchange=exchange,
                period="daily",
                adjust="",
                # 同时传两种命名风格，兼容不同版本
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                startDate=start_date.strftime("%Y%m%d"),
                endDate=end_date.strftime("%Y%m%d"),
            )
        )

    def normalize_daily_bars(
        self, raw_records: list[dict[str, Any]]
    ) -> list[NormalizedDailyBar]:
        """
        把 stock-sdk 原始日K线转成统一格式。

        字段名兼容 snake_case 和 camelCase：
          code / symbol / stockCode / stock_code
          date / tradeDate / trade_date / day
          open / openPrice, close / closePrice, ...
        """
        normalized: list[NormalizedDailyBar] = []

        for record in raw_records:
            symbol, exchange = _split_symbol_and_exchange(
                record.get("code")
                or record.get("symbol")
                or record.get("stockCode")
                or record.get("stock_code"),
                record.get("exchange") or record.get("market"),
            )
            trade_date = _parse_date(
                record.get("date")
                or record.get("tradeDate")
                or record.get("trade_date")
                or record.get("day")
            )

            if symbol is None or exchange is None or trade_date is None:
                continue

            open_price = _to_float(
                record.get("open") or record.get("openPrice")
            )
            high = _to_float(
                record.get("high") or record.get("highPrice")
            )
            low = _to_float(
                record.get("low") or record.get("lowPrice")
            )
            close = _to_float(
                record.get("close") or record.get("closePrice")
            )

            if (
                open_price is None
                or high is None
                or low is None
                or close is None
            ):
                continue

            normalized.append(
                NormalizedDailyBar(
                    symbol=symbol,
                    exchange=exchange,
                    market="A_SHARE",
                    trade_date=trade_date,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    pre_close=_to_float(
                        record.get("preClose")
                        or record.get("pre_close")
                        or record.get("preclose")
                    ),
                    volume=_to_float(
                        record.get("volume") or record.get("vol"),
                        default=0.0,
                    )
                    or 0.0,
                    amount=_to_float(
                        record.get("amount") or record.get("turnover"),
                        default=0.0,
                    )
                    or 0.0,
                    adjust_factor=1.0,
                    adjust_type="none",
                    source=self.code,
                )
            )

        return normalized

    def _get_client(self) -> Any:
        """
        获取 Stock SDK 客户端。

        和其他适配器的 _get_client 不同：
          这里不是 import Python 模块，
          而是创建一个管理 Node.js 子进程的 Python 对象。
        """
        if self._client is None:
            self._client = _NodeStockSdkClient()
        return self._client
