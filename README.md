# vaws-top — NPU Fleet Monitor

面向本地独立部署的 Ascend NPU 服务器监控台。它通过宿主机 SSH 无代理采集，重点展示 NPU 利用率、HBM、CPU、系统内存、磁盘、挂载点和 Docker 容器，并以 SQLite 保存历史数据。

**vaws-top 只观测，不分配。** 它不是设备分配权威：哪些 NPU 可以被使用，由宿主机侧的 NPU 协调器队列决定。vaws-top 的所有 Agent 接口都把数据标注为"带观测时间戳的观测状态"，并明确声明不得据此做设备分配决策。详见 [docs/agent-access.md](docs/agent-access.md) 与 [docs/architecture.md](docs/architecture.md)。

## 主要能力

- 批量添加服务器；先尝试项目专用密钥，再按顺序尝试本次请求中的密码候选。
- 可选地从显式配置的清单文件导入主机（`NFM_INVENTORY_FILES`、`NFM_HOST_POOL_FILES`）；只读取每条记录的主机端点字段。仅出现在主机池、未进入活动清单的设备自动获得"低优先级"标签。
- 密码只通过请求内存和标准输入传给可选的外部密钥引导命令（`NFM_BOOTSTRAP_COMMAND`），不写数据库、文件、命令参数或应用日志。
- 成功认证后自动安装专用 Ed25519 公钥；后续采集使用密钥和复用的 OpenSSH 控制连接。
- Host Key 使用独立 `known_hosts`，首次连接记录指纹，指纹变化时 OpenSSH 会拒绝连接。
- 在裸机宿主机运行 `npu-smi`，可跨容器观察占用；内置并经单元测试的解析器覆盖单 die（910B 类）与双 die（A3/910C 类）设备表、两种进程表布局和 `-t usages` 输出。
- 判忙优先进程与 AICore 利用率，HBM 作为兜底；默认 8 GB 阈值避开 A3 类设备约 6 GB 的驱动常驻占用，可通过 `NFM_HBM_BUSY_THRESHOLD_MB` 调整。
- 页面可选 1、5、10、30 秒实时刷新；多个页面同时打开时采用最快频率。
- 页面关闭或心跳过期后自动回到默认 120 秒巡检；磁盘、挂载和 Docker 默认 60 秒一次。
- 交互态高频结果保留在内存，SQLite 默认最短每 30 秒落一条，避免历史库随 1 秒刷新膨胀。
- 固定服务器侧栏汇总在线状态、NPU 数量、HBM 和 CPU；总览展开物理 die 展示逐 die HBM 占用（A3 为 8 张逻辑卡、16 个 die），AICore 非零时以右上角红色闪光点提示。点击服务器可按逻辑卡分组查看两个 die，以及逐卡 AICore/HBM、温度、功耗、进程、磁盘与 Docker 明细。
- 服务器标签可在管理页新增、编辑并通过侧栏搜索；派生的"低优先级"标签在后续同步中自动维护，低优先级服务器排在普通服务器之后。
- 历史报表覆盖 1 小时到 90 天，包含聚合趋势，以及按日期和 2 小时时段排列的 CPU、内存、NPU、HBM 与逐卡 AICore 热力图；原始数据默认保留 90 天。
- 默认只监听 `127.0.0.1`，不含登录功能，也不应直接暴露到外网。
- 为 Agent 提供统一 CLI/MCP：可按 IP/主机名选择缓存或实时探查，筛选观测到的空闲算力，并查询 NPU、CPU、内存、容器/进程归属及挂载盘；SSH 始终封装在常驻采集器内。结构化 JSON、`observation` 信封和完整参数见 [Agent CLI 与 MCP](docs/agent-access.md)。
- Agent 的完整使用与决策约定随仓库保存在 [`.agents/skills/vaws-top/SKILL.md`](.agents/skills/vaws-top/SKILL.md)。

## 依赖与目录

依赖 Node.js 22.13+、Python 3.11+、系统 OpenSSH 客户端和 `ssh-keygen`。后端只使用 Python 标准库，不依赖 `torch`/`torch_npu`，本地无 NPU 也可运行全部后端测试。支持 Linux systemd user service 和 Windows 原生任务计划程序两种持续运行方式。

```text
app/            Next.js 前端（vinext 构建）
backend/        Python 后端：API、采集调度、npu-smi 解析、SSH 访问、清单导入
backend/tests/  标准库 unittest
deploy/         systemd user unit 模板
scripts/        启动/安装脚本、Agent CLI (vaws-top.py) 与 MCP server (vaws-top-mcp.py)
docs/           架构、Agent 接口、Windows 部署、HANDOFF
.agents/skills/ 随仓库分发的 Agent Skill
```

运行时私有状态保存在 `data/`：SQLite、专用密钥、`known_hosts` 和 SSH 控制套接字。该目录已忽略，不会进入 Git。

## 配置

vaws-top 是一个普通的独立仓库，不会在磁盘或 Git 中搜索其他项目。所有外部输入都通过环境变量显式给出，模板见 [`.env.example`](.env.example)；Linux 的 systemd unit 会自动加载仓库根目录的 `.env`，Windows 安装器把同样的值写入 `data\windows-service.json`。

| 变量 | 作用 |
|------|------|
| `NFM_INVENTORY_FILES` | JSON 主机清单（`{"machines": [{"alias", "host": {"ip", "port", "user", "machine_type"}}]}`），多个路径用平台路径分隔符连接；其中的主机作为活动主机导入 |
| `NFM_HOST_POOL_FILES` | 纯文本主机池，每行取第一个字段；仅出现在这里的主机带"低优先级"标签 |
| `NFM_BOOTSTRAP_COMMAND` | 可选外部命令模板，用一次性密码安装监控公钥；占位符 `{host} {port} {user} {public_key_file} {python}`，密码经 stdin 传入。未配置时只支持已有密钥登录 |
| `NFM_STATE_DIR` | 私有状态目录，默认 `data/` |
| 其余 `NFM_*` | 监听地址/端口、采集周期、保留天数、HBM 判忙阈值 |

自动导入只读取清单中的宿主机地址、端口、用户和机器类型；不会采用容器端口，也不会创建或修改容器。已有数据库记录优先，不会在每次启动时重命名用户维护的服务器。

## 本地运行

```bash
git clone https://github.com/vllm-ascend-workspace/vaws-top.git
cd vaws-top
cp .env.example .env   # 按需填写清单路径和引导命令
npm ci
npm run build
npm run test:backend
npm run serve:local
```

浏览器访问 `http://127.0.0.1:8788`。前端服务将 `/api/*` 固定代理到回环地址的后端端口 `8789`。

Agent 可直接查询已采集的缓存：

```bash
python3 scripts/vaws-top.py npu 192.0.2.21
```

开发时分别运行：

```bash
PYTHONPATH=backend python3 -m npu_fleet_monitor
npm run dev -- --hostname 127.0.0.1
```

## 持续运行

若当前 Linux 用户已启用 systemd user manager，在仓库根目录执行：

```bash
./scripts/install-user-service.sh
```

安装脚本把仓库绝对路径写入 unit，并让 unit 通过 `EnvironmentFile` 读取仓库根目录的 `.env`。检查：

```bash
systemctl --user status npu-fleet-monitor
journalctl --user -u npu-fleet-monitor -f
```

部署脚本不会修改远程服务器上的系统配置，只会在目标 SSH 用户的 `authorized_keys` 中幂等加入监控公钥。

### Windows

在仓库根目录的普通 PowerShell 中运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install-windows-service.ps1
.\scripts\manage-windows-service.ps1 status
```

Windows 版本使用当前用户的任务计划程序在登录后启动，异常退出自动重试，仍然只监听 `127.0.0.1`。无需 NSSM、Docker Desktop 或 WSL；完整安装、参数、日志和卸载说明见 [Windows 原生部署](docs/windows-deployment.md)。

## 批量格式

界面中每行一台服务器：

```text
名称, 主机, SSH端口, SSH用户, 标签1|标签2
example-a3-01, 192.0.2.21, 22, root, A3|训练
```

密码候选一行一个。服务对每台尚未配置密钥的主机按顺序尝试，成功即停止；请求完成后不保留候选密码。

文中的 `192.0.2.x` 为 RFC 5737 文档保留地址，仅作示例。

## 与 vllm-ascend-workspace 的关系

本仓库从 `vllm-ascend-workspace` 脚手架的 `vaws-top` 分支拆出，保留了完整提交历史。脚手架侧的 `npu-fleet-monitor` Skill 负责克隆、构建并管理本仓库的本地服务；需要在脚手架侧做的改动列在 [docs/HANDOFF.md](docs/HANDOFF.md)。本仓库本身不依赖脚手架的任何文件或目录布局。

## 测试与 CI

```bash
npm run test:backend        # 等价于 PYTHONPATH=backend python3 -m unittest discover -s backend/tests -v
python3 scripts/run-backend-tests.py
```

GitHub Actions（`.github/workflows/ci.yml`）在 Python 3.11 与 3.12 上运行后端测试。

## 设计来源

产品交互参考了 [RackTop](https://github.com/Tongzh-SEU/RackTop) 的多服务器资源总览、空闲算力发现和历史热力图思路；实现代码为独立编写，并针对 Ascend 设备与无代理宿主机探测进行了适配。

## License

MIT，见 [LICENSE](LICENSE)。
