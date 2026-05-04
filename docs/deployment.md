# Linux 部署方案

## 1. 部署目标

本项目部署目标为：

- 运行在 Linux 内网环境
- 提供网页控制台
- 控制 CloudflareSpeedTest 二进制程序
- 使用 systemd 托管 Web 服务
- 使用 systemd timer 托管定时任务
- 使用文件存储保存配置、结果与日志

---

## 2. 推荐环境

建议环境：
- Linux 发行版：Debian / Ubuntu / CentOS / Rocky Linux 等
- Python 3.11+
- systemd 可用
- 具备访问阿里云和 Cloudflare API 的网络能力

---

## 3. 推荐目录规划

部署时建议规划如下目录：

```text
/opt/cfst-controller/
  app/
  docs/
  data/
    configs/
    templates/
    runs/
    results/
    pushes/
    schedules/
  logs/
  deploy/
    systemd/
  scripts/
```

说明：
- `app/` 存放程序代码
- `data/` 存放业务数据
- `logs/` 存放运行日志
- `deploy/systemd/` 存放 service 和 timer 模板

---

## 4. CloudflareSpeedTest 二进制部署建议

建议单独放置 CloudflareSpeedTest 二进制，例如：

```text
/opt/cfst-bin/cfst
```

要求：
- 文件路径固定
- 具备执行权限
- 由配置文件引用，不写死在代码里

如需升级，只替换该二进制文件并做兼容验证即可。

---

## 5. Web 服务部署建议

建议 Web 服务由 systemd 托管。

基本要求：
- 指定固定工作目录
- 指定 Python 虚拟环境
- 指定日志输出方式
- 指定最小运行账户权限

Web 服务建议能力：
- 提供健康检查接口
- 提供页面访问入口
- 能读取与写入 data 目录
- 能读取 logs 目录

---

## 6. 权限规划建议

由于系统没有登录鉴权，Linux 层面的权限控制就更重要。

建议：
- Web 服务使用专用用户运行
- CloudflareSpeedTest 执行权限最小化
- DNS 配置文件权限仅允许服务用户读取
- 日志目录和数据目录单独授权
- 不使用 root 长期运行应用

---

## 7. systemd 托管建议

建议至少包含两类 systemd 单元：

1. Web 服务单元
2. 定时执行单元

定时执行又拆分为：
- service
- timer

这样能把“应用服务”和“计划任务”管理边界分清楚。

---

## 8. 配置文件部署建议

建议将配置文件放在：

- `data/configs/binary_config.yaml`
- `data/configs/parameter_definitions.yaml`
- `data/configs/dns_aliyun.yaml`
- `data/configs/dns_cloudflare.yaml`

部署要求：
- 先准备默认配置模板
- 首次启动前完成路径校验
- 敏感字段文件设置严格权限

---

## 9. 日志策略建议

建议日志按以下方式组织：

- 应用运行日志
- 任务 stdout 日志
- 任务 stderr 日志
- DNS 推送日志
- systemd 运行日志

建议规范：
- 日志文件按任务 ID 或日期命名
- 页面只读取必要的日志片段
- 长期运行时考虑轮转策略

---

## 10. 结果与记录保存建议

由于项目数据量很小，建议直接保存：

- 最近任务结果
- 历史任务结果
- 推送记录
- 计划任务配置

无需数据库，也无需复杂归档系统。

如果担心历史文件增长，可以采用：
- 保留最近 N 次结果
- 或按时间清理旧文件

---

## 11. 内网访问建议

虽然项目不做登录鉴权，但仍建议：

1. 限制访问来源 IP 或网段
2. 配合反向代理做来源控制
3. 不暴露到公网
4. 危险操作增加前端确认
5. 对关键配置文件做系统级权限限制

---

## 12. 备份建议

建议定期备份以下目录：

- `data/configs/`
- `data/templates/`
- `data/schedules/`
- `data/results/`
- `data/pushes/`

日志目录是否备份，可根据排障需求决定。

---

## 13. 上线顺序建议

建议按以下顺序上线：

1. 部署 CloudflareSpeedTest 二进制
2. 部署 Python Web 应用
3. 完成基础配置
4. 验证网页启动任务
5. 验证网页停止和重启任务
6. 验证结果解析
7. 验证 DNS 推送
8. 最后启用 systemd timer

这样可以先验证核心链路，再开启自动化任务。

---

## 14. 运维检查清单

上线前建议确认：

- Python 运行环境正常
- CloudflareSpeedTest 二进制可执行
- 配置目录权限正确
- 日志目录可写
- Web 页面可访问
- 手动测速链路正常
- DNS 推送测试通过
- timer 状态读取正常

---

## 15. 最终建议

对这个项目来说，最重要的不是堆积很多基础设施，而是把下面几件事做稳：

- 网页控制稳定
- 二进制执行稳定
- 结果保存稳定
- DNS 推送稳定
- systemd 定时稳定

只要这五点稳定，这套系统在 Linux 内网里就会非常实用。