# 21 认证与访问控制（Authentication & Authorization）

## 目标

- 多 Client 隔离
- 防止跨 `device_id` 访问
- 服务端裁决边界明确

## 认证（规范性）

控制通道的认证在**连接握手**阶段完成（见 06 章「连接生命周期」）。

- Server **必须**在 `login` 中校验认证凭据；
  校验失败**必须**以 `login_ack`（`result` = `0`，即 fail）回应并**关闭连接**。
- 凭据**必须**与 `device_id` **绑定**：认证通过后，连接即与该 `device_id` 绑定，
  该连接上的一切会话**必须**属于该 `device_id`。
- 认证方式**必须**至少支持以下其一：

| 方式 | 凭据 | 说明 |
|------|------|------|
| 共享令牌 | `login.token` | Server 侧存储 `token → device_id` 绑定；令牌**必须**随机生成 |
| 客户端证书 | TLS Client Certificate | 证书的 SAN / CN **必须**携带 `device_id`；此时 `login.token` **必须**为空串（长度 0） |

- 令牌**不得**由 `device_id` 直接推导 —— 设备标识不应等价于凭据
  （见 23 章「隐私」）。
- Server **必须**对失败的认证尝试做**速率限制**与**审计**。
- 认证失败**必须**通过 `login_ack.code` 上线路（19 章）：
  `LOGIN_FAILED` / `CLIENT_ID_INVALID` / `PROTO_VERSION_UNSUPPORTED`。

## 访问控制（规范性）

跨 `device_id` 的隔离由以下四层承担：

1. **连接级**：一条控制连接只承载一个 `device_id`。
   跨 `device_id` 的会话**默认无法表达**；**peer 会话是唯一例外**：
   它显式绑定两个 `device_id`，由 Server 通过 share grant 授权（见「C↔C peer 授权」）。
2. **Server 级**：Server **必须**校验会话的 `device_id` 与连接绑定一致；
   对 peer 会话，**必须**校验 `sender_device_id` 与 `receiver_device_id`
   各自与对应控制连接绑定一致。
   不一致**必须**以 `session_abort`（`reason` = `ACL_DENY`）拒绝。
3. **资源级**：素材记录（`asset_id`）的所有权由 Server 维护；
   `asset_recall` **必须**校验发起方的 `device_id` 对该记录的所有权，
   越权时回 `code = ACL_DENY`（见 06 章）。
4. **共享清单级**：**预置素材记录**的归属者是 Server，
   **所有已认证设备**都可以列举（`material_list`）与拉取（`download_start`），
   但**不得**撤回 —— 对预置素材记录发布 `asset_recall`
   **必须**以 `ACL_DENY` 拒绝（见 09 章「预置素材与共享清单」）。

## C↔C peer 授权（规范性）

- peer 会话是**唯一跨两个 `device_id` 的会话类型**：`sender_device_id` 与
  `receiver_device_id` 都必须各自绑定一条已认证控制连接；Server **必须**同时校验两者。
- **share grant**：`(sender_device_id, receiver_device_id, file_hash, expiry)`，
  由 Server 维护。`peer_start` / `peer_offer` **必须**落在该 grant 内，否则 `ACL_DENY`。
- 接收方**可以**拒绝；拒绝经 `peer_response`（`result` = fail，
  `code` = `PEER_DECLINED`）表达，Server 以 `session_abort` 终止。
- **没有 C↔C 的 `login`**：peer 身份完全复用双方与 Server 的既有认证；
  数据面使用 Server 签发的 `transfer_token` 做端点确认（Stage 1）。
- R1 的中转素材/授权**必须**绑定 `transfer_id` 与 grant，完成后回收；
  **不得**让接收方凭 `file_hash` 越权访问其他私有素材。
- 私有素材归属不因 peer 传输改变；Server 侧归属仍按上传 `device_id`。

## 传输安全（规范性）

- 控制通道**必须**支持 TLS；**应当**启用。
- 未启用 TLS 时，认证凭据以**明文**传输 ——
  **不得**在非受信网络（含公共 WiFi）中这样部署。
- 控制通道与数据面**相互独立**：
  数据面**不**复用控制连接的 TLS 会话；UDP 数据面**不**自带加密
  （见 20 章）。

## 强约束

- 一条连接**必须**绑定唯一 `device_id`
- Server **不得**在连接上接受与绑定身份不符的会话
- 会话**必须**绑定唯一 `device_id`

## 审计

- 记录认证失败尝试、跨 `device_id` 的会话操作与 `session_abort` 原因
