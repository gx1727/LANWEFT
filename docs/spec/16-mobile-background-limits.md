# 16 移动端后台限制

## Android

- Foreground Service
- 展示同步状态

## iOS

- 仅前台
- 后台视为中断
- 回前台若连接已断，使用 `login` 恢复；仅连接仍存活且会话已显式暂停时使用 `resume_session`（见 13 章）。
