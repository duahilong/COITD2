# DNS 推送集成设计

## 1. 设计目标

测速完成后，系统需要将优选出的一个或多个 IP 推送到 DNS 厂商。首期目标是接入：

- 阿里云 DNS
- Cloudflare DNS

设计重点是：
- 推送过程可控
- 推送记录可追踪
- 失败原因可定位
- 与测速逻辑解耦
- 对接方式尽量贴近官方文档与官方接口模型

---

## 2. 集成原则

1. DNS 推送模块独立于测速模块
2. 推送模块只消费结果文件，不直接参与测速
3. 每个厂商都通过独立适配器实现
4. 统一抽象推送请求与推送结果结构
5. 所有推送操作都要记录
6. 适配器设计尽量按官方接口能力封装，不自行发明与官方语义冲突的模型

---

## 3. 输入与输出

## 3.1 输入

推送模块的输入来自测速结果文件，至少包括：
- 任务 ID
- 优选 IP 列表
- 每个 IP 的延迟
- 每个 IP 的速度
- 丢包率
- 协议类型（IPv4 / IPv6）

以及推送配置：
- 厂商类型
- 域名
- 记录名
- 记录类型
- TTL
- 是否自动推送
- Top 1 / Top N 规则

## 3.2 输出

每次推送输出一份 JSON 记录，至少包括：
- push_id
- task_id
- provider
- record_name
- before_value
- after_value
- status
- response_summary
- pushed_at

---

## 4. 推送流程

### 4.1 自动推送

1. 测速任务完成
2. 系统读取结果文件
3. 根据策略筛选目标 IP
4. 查询当前 DNS 记录
5. 对比变更前后值
6. 有变化则执行推送
7. 保存推送结果记录
8. 页面显示推送结果

### 4.2 手动推送

1. 用户在结果页选择结果
2. 点击推送
3. 后端加载相应厂商配置
4. 查询当前记录
5. 执行变更
6. 保存记录并反馈页面

### 4.3 仅保存不推送

1. 测速完成后仅保存结果
2. 页面允许后续再手动选择推送

---

## 5. 结果选择策略

建议首期支持以下策略：

1. Top 1
2. Top N
3. 延迟低于阈值
4. 速度高于阈值
5. 丢包率低于阈值
6. IPv4 / IPv6 分开选择

如果后续要进一步扩展，可以支持综合评分模型，但首期不建议做复杂评分系统。

---

## 6. 统一 DNS 适配器接口设计

为了让阿里云 DNS 和 Cloudflare DNS 的接口封装具备统一性，建议先定义通用适配器接口，而不是把两个厂商逻辑直接写在业务层。

建议适配器统一暴露以下能力：

1. `validate_config()`
   - 校验配置字段完整性
   - 可选执行一次轻量接口探测

2. `list_records(request)`
   - 查询当前记录

3. `create_record(request)`
   - 新建记录

4. `update_record(request)`
   - 更新已有记录

5. `upsert_records(request)`
   - 业务层优先调用的统一入口
   - 内部自行判断是更新还是新增

6. `mask_config_for_display()`
   - 返回脱敏后的配置用于网页显示

建议统一请求结构：

```json
{
  "provider": "aliyun" ,
  "zone": "example.com",
  "record_name": "cdn",
  "record_type": "A",
  "ttl": 600,
  "values": ["1.1.1.1"],
  "options": {
    "proxied": false,
    "line": "default"
  }
}
```

建议统一响应结构：

```json
{
  "success": true,
  "provider": "aliyun",
  "action": "update_record",
  "request_id": "provider-request-id",
  "records_before": ["2.2.2.2"],
  "records_after": ["1.1.1.1"],
  "raw_summary": {
    "code": "OK",
    "message": "success"
  }
}
```

这样做的好处是：
- 业务层只处理统一结构
- 便于记录日志和推送记录
- 后续新增更多 DNS 厂商时扩展简单

---

## 7. 阿里云 DNS 适配器设计

### 7.1 官方接口参考方向

建议参考阿里云 DNS OpenAPI 的官方能力模型，首期重点围绕以下接口封装：

- 查询记录列表：`DescribeDomainRecords`
- 新增解析记录：`AddDomainRecord`
- 更新解析记录：`UpdateDomainRecord`

如果后续需要删除或更复杂管理，可再扩展：
- `DeleteDomainRecord`
- `SetDomainRecordStatus`

### 7.2 适配器职责

- 查询现有记录
- 创建记录
- 更新记录
- 返回统一格式结果

### 7.3 建议配置字段

- AccessKey ID
- AccessKey Secret
- 域名
- RR
- 记录类型
- TTL
- 解析线路

### 7.4 与官方模型的映射建议

阿里云 DNS 常见业务字段和系统内部字段建议映射如下：

- `zone` -> `DomainName`
- `record_name` -> `RR`
- `record_type` -> `Type`
- `values[0]` 或逐条值 -> `Value`
- `ttl` -> `TTL`
- `options.line` -> `Line`

需要注意：
- 阿里云常见更新流程是先查询记录拿到 `RecordId`，再调用 `UpdateDomainRecord`
- 如果配置为 Top N 且厂商侧一条记录只接受单值，则业务层需要拆分策略或限制使用方式
- 若网页允许多值策略，要先明确是“多条同名记录”还是“单条记录覆盖”

### 7.5 注意点

- Secret 不应直接回显到页面
- 错误返回应保留摘要便于排障
- 页面应支持测试配置有效性
- 建议记录阿里云返回的 `RequestId`，便于后期排查

---

## 8. Cloudflare DNS 适配器设计

### 8.1 官方接口参考方向

建议参考 Cloudflare 官方 DNS Records API，首期重点围绕以下能力封装：

- 查询记录列表：列出 Zone 下 DNS records
- 新增记录：创建 DNS record
- 更新记录：更新 DNS record

### 8.2 适配器职责

- 查询现有记录
- 创建记录
- 更新记录
- 返回统一格式结果

### 8.3 建议配置字段

- API Token
- Zone ID
- 域名
- 记录名
- 记录类型
- TTL
- Proxied 开关

### 8.4 与官方模型的映射建议

Cloudflare 常见业务字段和系统内部字段建议映射如下：

- `zone` -> 通过 `Zone ID` 标识 Zone
- `record_name` -> `name`
- `record_type` -> `type`
- `values[0]` 或逐条值 -> `content`
- `ttl` -> `ttl`
- `options.proxied` -> `proxied`

需要注意：
- Cloudflare 的记录更新通常要先查询已有记录拿到 `record_id`，再进行更新
- `proxied` 只适用于部分记录类型，页面应按类型控制是否展示
- 若采用多值策略，也要明确是多条同名记录还是覆盖式更新

### 8.5 注意点

- Proxied 开关应在页面显式配置
- Token 不应明文展示
- 返回错误信息应做摘要记录
- 建议记录 Cloudflare 返回中的错误码、错误消息和记录 ID

---

## 9. 推送记录设计

建议每次推送保存单独 JSON 文件。

字段建议：
- push_id
- task_id
- provider
- domain
- record_name
- record_type
- selected_ips
- before_records
- after_records
- response_summary
- status
- pushed_at

这样页面就能直接读取历史推送记录，而无需数据库。

建议统一记录格式如下：

```json
{
  "version": "1.0",
  "kind": "dns_push_record",
  "push_id": "push_20260504_0001",
  "task_id": "task_20260504_0001",
  "provider": "cloudflare",
  "target": {
    "zone": "example.com",
    "record_name": "cdn",
    "record_type": "A"
  },
  "selected_ips": [
    {
      "address": "1.1.1.1",
      "latency_ms": 89.2,
      "speed_mbps": 23.4
    }
  ],
  "before_records": ["2.2.2.2"],
  "after_records": ["1.1.1.1"],
  "status": "success",
  "response_summary": {
    "request_id": "provider-request-id",
    "message": "updated"
  },
  "timestamps": {
    "pushed_at": "2026-05-04T10:00:00Z"
  }
}
```

---

## 10. 页面交互建议

在 DNS 配置页建议包括：

### 厂商配置区域
- 配置阿里云或 Cloudflare 凭据
- 配置域名信息
- 保存并测试配置
- 展示脱敏后的当前配置摘要

### 推送策略区域
- 自动推送
- 人工确认后推送
- 仅保存结果
- Top 1 / Top N
- 过滤阈值
- 多值记录策略说明

### 推送历史区域
- 最近推送时间
- 最近推送目标
- 最近推送状态
- 失败摘要
- 最近一次接口返回摘要

在结果页建议包括：
- 针对某条任务结果手动推送
- 查看是否已推送
- 查看推送到哪个厂商
- 查看推送前后记录差异

---

## 11. 失败处理建议

### 11.1 凭据错误

处理方式：
- 记录错误摘要
- 页面高亮提示
- 不覆盖现有记录

### 11.2 当前记录查询失败

处理方式：
- 不盲目覆盖
- 保留失败记录
- 页面允许人工重试

### 11.3 部分成功

如果支持 Top N，可能出现部分记录更新成功、部分失败的情况。建议：
- 在记录中明确成功和失败项
- 页面展示整体状态与明细摘要

### 11.4 官方接口变化

由于阿里云和 Cloudflare 的 API 细节可能演进，建议：
- 适配器只封装必要字段
- 原始响应只保留摘要和关键标识
- 保留 provider adapter version 字段，便于后续兼容升级

---

## 12. 安全建议

虽然系统不做登录鉴权，但 DNS 密钥仍然属于敏感信息。建议：

1. 配置文件权限最小化
2. 页面不直接展示完整密钥
3. 推送前提供确认步骤
4. 操作日志记录推送动作
5. 配置导出时自动脱敏

---

## 13. 最终建议

DNS 推送模块不要做成测速流程里的附带逻辑，而应该做成独立、可追踪、可重试的能力模块。同时，接口封装应尽量贴近官方文档模型：

- 阿里云重点围绕记录查询、新增、更新三类接口
- Cloudflare 重点围绕 DNS Records 的查询、新增、更新三类接口

这样后续即使更换测速引擎或新增 DNS 厂商，也能保持整体结构稳定。