# 23 Client Identity 与设备绑定

## 目标

- 全局唯一、稳定可复用、设备级粒度、低耦合、安全可控

## 生成

- base32(UUIDv4) 或 hash(device_uuid+salt)，持久化安全存储，不得重启重生成
- client_id 与文件哈希（Blake3，32 字节原始摘要）**无关**，两者不可互相推导
- client_id 一旦分配即固定，不得因设备重装、换网或升级而改变

## 生命周期与存储

- Android EncryptedSharedPreferences/Keystore
- iOS Keychain
- 桌面加密文件

## 与认证身份的一致性

- `login` 消息变长区中的 `device_id`（`str`）**必须**与认证凭据绑定的身份一致。
- 不一致时 Server **必须**以 `CLIENT_ID_INVALID` 拒绝登录（见 19 章）。
- 该等价关系是访问控制（21 章）与跨 `client_id` 审计（20 章）的基础，
  两者都依赖「**连接绑定的身份即为已认证的设备身份**」。

## 多设备

- 1 Device ⇔ 1 client_id；1 Account ⇔ N client_id（协议不感知账号）

## 与 Session

- client_id 可并发多 session；不得跨 client_id 使用；Server 校验一致性
- 同一 `client_id` 的多个会话**可以**承载在同一条控制连接上（见 09 章）

## 与控制通道

- 认证在连接握手时完成，连接与 `client_id` **一一绑定**
- 连接存续期间**不得**变更绑定身份

## 隐私

- 不得包含敏感信息；推荐随机或哈希派生
- **认证凭据不得**由 `client_id` 直接推导 —— 设备标识不应等价于凭据
  （见 21 章「认证」）

## 非法行为

- client_id 非法；跨 client_id 的会话操作
