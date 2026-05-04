# CloudflareSpeedTest 外部控制系统落地方案

## 1. 建设目标

本方案用于指导在 Linux 环境中，基于 CloudflareSpeedTest 二进制文件开发一套外部控制系统。系统定位为：

- 内网使用
- 网页为主要控制入口
- 无需数据库
- 使用 systemd 实现定时任务
- 支持 DNS 厂商自动推送优选 IP

最终交付重点不是 CloudflareSpeedTest 本身，而是围绕它建立一层稳定、可管理、可操作的外部控制平台。

---

## 2. 适用范围

本方案适用于以下场景：

1. 在 Linux 服务器上周期性执行 CloudflareSpeedTest
2. 通过网页修改测速参数与执行策略
3. 将测速结果中的一个或多个优选 IP 自动写入 DNS
4. 由运维或管理员在内网中进行日常控制和排障

不包含的目标：
- 不面向公网开放
- 不以多租户系统为目标
- 不以海量数据存储和分析为目标
- 不以复杂权限体系为目标

---

## 3. 上游项目使用策略

CloudflareSpeedTest 推荐作为“外部测速引擎”使用，而不是二次修改源码后深度耦合。

推荐方式：

1. 将 Linux 二进制放入固定目录
2. 外部控制系统只负责：
   - 参数生成
   - 进程启动与停止
   - 日志采集
   - 结果解析
3. 上游二进制升级时，只替换文件并做兼容验证

这样做的优点：
- 升级边界清晰
- 维护成本低
- 不容易被上游变更牵连

---

## 4. 技术选型

## 4.1 推荐语言：Python

推荐 Python 的主要原因：

1. 进程控制成熟
2. 文件处理简单
3. Web 开发效率高
4. 适合快速搭建后台控制台
5. 很适合对接阿里云和 Cloudflare 的 HTTP API

## 4.2 推荐技术栈

- Python 3.11+
- FastAPI
- Jinja2
- HTMX 或原生 JavaScript
- PyYAML
- requests 或 httpx
- systemd service / timer

## 4.3 不引入数据库的理由

这个项目的持久化需求本质上是：
- 配置文件
- 任务记录
- 少量结果
- 推送记录
- 日志路径

这类数据完全可以使用文件来承载。数据库会增加：
- 安装成本
- 维护成本
- 备份复杂度
- 部署复杂度

因此首期不建议引入数据库。

---

## 5. 业务能力拆解

## 5.1 能力一：二进制文件控制

目标：让网页可以完整控制 CloudflareSpeedTest。

必须支持：
- 配置二进制路径
- 维护参数定义
- 控制参数启用/禁用
- 启动任务
- 停止任务
- 重启任务
- 查看运行中状态
- 查看日志
- 查看执行结果

## 5.2 能力二：IP 推送

目标：把测速结果中的优选 IP 写入目标 DNS 服务。

首期支持：
- 阿里云 DNS
- Cloudflare DNS

必须支持：
- 配置凭证
- 配置目标域名与记录
- 手动推送
- 自动推送
- 记录推送前后信息

## 5.3 能力三：网页控制台

目标：把前两部分能力全部落到网页中。

必须支持：
- 可视化参数页
- 命令预览
- 运行控制
- 任务状态
- 结果展示
- 定时策略管理
- 推送配置管理

---

## 6. 落地设计

## 6.1 统一文件标准设计

你提出的要求很关键：参数、日志、优选 IP、任务记录等文件，最好都采用一套通用的格式标准，让不同模块都能处理同一类文件。

因此建议本项目统一使用 **JSON 作为运行期标准交换格式**，并约定所有文件都遵循统一信封结构。

统一信封建议如下：

```json
{
  "version": "1.0",
  "kind": "task_run",
  "id": "task_20260504_0001",
  "source": "web_console",
  "timestamps": {
    "created_at": "2026-05-04T10:00:00Z",
    "updated_at": "2026-05-04T10:05:00Z"
  },
  "meta": {},
  "payload": {}
}
```

统一字段说明：
- `version`：文件格式版本，便于后续兼容升级
- `kind`：文件类型标识
- `id`：对象唯一标识
- `source`：文件来源模块
- `timestamps`：时间戳集合
- `meta`：通用元信息
- `payload`：具体业务内容

建议所有模块都只认这一层统一信封，再根据 `kind` 分发给不同处理器。

## 6.2 统一 kind 类型建议

首期建议至少定义以下 kind：

- `parameter_definition_set`
- `parameter_template`
- `task_run`
- `task_result`
- `task_log_index`
- `dns_push_record`
- `schedule_definition`
- `operation_event`

这样做的好处：
- 参数模块、日志模块、结果模块、推送模块都能用统一解析器
- 页面展示层也能按同样结构做渲染
- 后续扩展不容易把文件格式做散

## 6.3 参数定义模型

不要让用户直接输入整段命令，而应把每个 CLI 参数抽象成结构化定义。

建议 `parameter_definition_set` 的 payload 包含：
- 参数集合名称
- 参数列表
- 参数分组
- 校验规则
- 默认模板引用

单个参数建议字段：
- `key`
- `label`
- `cli_flag`
- `type`
- `default`
- `enabled_by_default`
- `required`
- `visible`
- `group`
- `description`
- `validation`

参数值实例则单独保存：
- `enabled`
- `value`

这种设计可让网页天然支持“参数开关”和“参数值编辑”。

参数定义文件示例：

```json
{
  "version": "1.0",
  "kind": "parameter_definition_set",
  "id": "cfst_default_definitions",
  "source": "system",
  "timestamps": {
    "created_at": "2026-05-04T10:00:00Z",
    "updated_at": "2026-05-04T10:00:00Z"
  },
  "meta": {
    "binary": "CloudflareSpeedTest"
  },
  "payload": {
    "groups": ["basic", "latency", "download", "output"],
    "parameters": [
      {
        "key": "test_limit",
        "label": "测速数量",
        "cli_flag": "-dn",
        "type": "integer",
        "default": 20,
        "enabled_by_default": true,
        "required": false,
        "visible": true,
        "group": "download",
        "description": "下载测速节点数量",
        "validation": {
          "min": 1,
          "max": 1000
        }
      }
    ]
  }
}
```

## 6.4 参数模板文件

参数模板建议也改成统一 JSON 格式，而不是各自为政。

示例：

```json
{
  "version": "1.0",
  "kind": "parameter_template",
  "id": "template_daily_ipv4",
  "source": "web_console",
  "timestamps": {
    "created_at": "2026-05-04T10:00:00Z",
    "updated_at": "2026-05-04T10:00:00Z"
  },
  "meta": {
    "definition_id": "cfst_default_definitions"
  },
  "payload": {
    "template_name": "每日 IPv4 优选",
    "parameter_values": {
      "test_limit": {
        "enabled": true,
        "value": 20
      }
    }
  }
}
```

## 6.5 命令构建策略

构建命令时遵循以下规则：

1. 仅拼接启用状态为 true 的参数
2. 布尔型参数只在开启时输出 flag
3. 数值、字符串、路径型参数做类型和空值校验
4. 最终命令只在后端构建
5. 前端只展示命令预览，不负责真实执行

## 6.6 任务执行策略

建议每次执行都创建独立任务。

`task_run` 建议包含：
- 任务 ID
- 参数快照
- 启动时间
- 结束时间
- 状态
- 日志路径
- 结果路径
- PID
- 触发来源

执行过程建议：
1. 创建任务元数据文件
2. 启动子进程
3. 持续采集日志
4. 结束后写回最终状态
5. 解析结果文件
6. 根据推送策略决定是否推送

## 6.7 停止与重启策略

停止：
- 从运行任务记录中读取 PID
- 向对应进程发送终止信号
- 必要时分级处理
- 状态更新为已取消或已停止

重启：
- 读取最近任务参数快照
- 若原任务仍在执行，先停止
- 创建新任务并重新执行

## 6.8 结果解析策略

优先级建议：

1. 结构化文件输出
2. CSV 输出
3. 文本结果文件
4. 终端输出解析

页面最终只关心以下关键数据：
- 任务 ID
- 优选 IP 列表
- 每个 IP 的延迟
- 每个 IP 的速度
- 丢包率
- 地区码

建议结果文件统一为 `task_result`：

```json
{
  "version": "1.0",
  "kind": "task_result",
  "id": "task_20260504_0001",
  "source": "cfst_adapter",
  "timestamps": {
    "created_at": "2026-05-04T10:10:00Z",
    "updated_at": "2026-05-04T10:10:00Z"
  },
  "meta": {
    "task_id": "task_20260504_0001"
  },
  "payload": {
    "selected_ips": [
      {
        "address": "1.1.1.1",
        "family": "ipv4",
        "latency_ms": 89.2,
        "speed_mbps": 23.4,
        "loss_rate": 0,
        "region": "HKG",
        "rank": 1
      }
    ]
  }
}
```

## 6.9 日志文件标准

你特别提到日志也希望统一成通用格式，这一点很有必要。

建议不要只保留 `.log` 纯文本文件，而是采用“双层结构”：

1. 原始日志文本文件
   - 便于人工排障
2. 日志索引 JSON 文件
   - 便于网页和模块统一读取

建议 `task_log_index` 如下：

```json
{
  "version": "1.0",
  "kind": "task_log_index",
  "id": "task_20260504_0001",
  "source": "runner",
  "timestamps": {
    "created_at": "2026-05-04T10:00:00Z",
    "updated_at": "2026-05-04T10:10:00Z"
  },
  "meta": {
    "task_id": "task_20260504_0001"
  },
  "payload": {
    "stdout_path": "logs/task_20260504_0001.stdout.log",
    "stderr_path": "logs/task_20260504_0001.stderr.log",
    "highlights": [
      {
        "level": "error",
        "message": "timeout",
        "at": "2026-05-04T10:08:00Z"
      }
    ]
  }
}
```

这样网页端无需直接理解所有日志内容，只要先读取日志索引即可。

---

## 7. 文件存储方案

## 7.1 配置文件

建议：
- `data/configs/binary_config.json`
- `data/configs/parameter_definitions.json`
- `data/configs/dns_aliyun.json`
- `data/configs/dns_cloudflare.json`

## 7.2 模板文件

建议：
- `data/templates/default.json`
- `data/templates/*.json`

## 7.3 任务与结果文件

建议：
- `data/runs/{task_id}.json`
- `data/results/{task_id}.json`
- `data/logs/{task_id}.json`
- `data/pushes/{push_id}.json`
- `logs/{task_id}.stdout.log`
- `logs/{task_id}.stderr.log`

---

## 8. 网页功能规划

## 8.1 仪表盘

展示：
- 当前运行状态
- 最近一次优选结果
- 最近一次推送状态
- 最近任务列表
- 最近计划任务列表
- 最近日志异常摘要

## 8.2 二进制配置页

配置：
- 程序路径
- 工作目录
- 默认输出目录
- 默认超时
- 是否启用代理前检查

## 8.3 参数控制页

配置：
- 参数分组展示
- 每个参数的启用/禁用开关
- 每个参数的值
- 模板保存和加载
- 恢复默认值
- 当前命令预览

## 8.4 运行控制页

提供：
- 启动
- 停止
- 重启
- 查看命令预览
- 查看当前任务详情

## 8.5 定时策略页

提供：
- 新建计划
- 编辑计划
- 启用/暂停计划
- 查看 timer 状态
- 查看下次运行时间

## 8.6 DNS 配置页

配置：
- 阿里云信息
- Cloudflare 信息
- 域名记录
- 自动推送开关
- 推送阈值
- 目标结果选择策略

## 8.7 日志与结果页

展示：
- stdout
- stderr
- 最近结果
- 历史结果
- 推送记录
- 结构化日志摘要

---

## 9. systemd 集成策略

定时执行不放在应用内部，而通过 systemd 管理。

建议方式：

1. 网页保存计划配置
2. 后端根据计划配置生成：
   - service 文件
   - timer 文件
3. 管理员在 Linux 上部署对应文件
4. 网页读取 systemd 状态进行展示

这样可以做到：
- 应用重启不影响计划任务
- 系统日志和计划任务状态容易排查
- 运维方式更标准

---

## 10. DNS 推送策略

## 10.1 推送模式

建议支持：
- 自动推送
- 手动确认后推送
- 仅保存结果不推送

## 10.2 推送条件

建议支持：
- 取 Top 1
- 取 Top N
- 延迟阈值
- 速度阈值
- IPv4 / IPv6 分别处理

## 10.3 推送记录

每次推送都建议保存：
- 来源任务
- 厂商
- 域名
- 记录类型
- 推送前值
- 推送后值
- 响应摘要
- 推送状态

---

## 11. 实施阶段建议

## 阶段一：网页控制闭环

交付目标：
- 参数定义可用
- 网页启动/停止/重启可用
- 日志可看
- 结果可看
- 统一 JSON 文件标准可用

## 阶段二：模板和定时

交付目标：
- 参数模板可用
- systemd timer 配置可管理
- 页面可查看计划状态

## 阶段三：DNS 推送

交付目标：
- 阿里云和 Cloudflare DNS 接入完成
- 页面可配置推送策略
- 自动/手动推送可用

## 阶段四：部署和运维增强

交付目标：
- 文档完善
- 健康检查完善
- 异常清理和备份策略完善

---

## 12. 最终落地建议

如果你的重点是快速可用和低维护成本，那么最适合的方案是：

- Python 实现
- FastAPI + Jinja2 做网页控制台
- 统一 JSON 作为运行期交换标准
- 原始日志文本 + 结构化日志索引并存
- systemd timer 管理计划任务
- DNS 推送做成独立适配器层

这套方案足够轻，也足够稳，非常适合你描述的 Linux 内网使用场景。