# 使用说明：SSH 密钥生成与推送

本目录下包含两个 PowerShell 脚本，用于在本机生成 SSH key 并将项目推送到你的私有 GitHub 仓库：

- `generate_ssh_key.ps1`：在项目根目录创建 `ssh_key_rui3394/`，生成 ed25519 密钥对并将公钥复制到剪贴板。
- `setup_ssh_and_push.ps1`：把生成的私钥复制到用户 `~/.ssh/`，向 `~/.ssh/config` 添加 Host 别名条目（`github-rui3394`），然后设置 git remote 并推送分支（需确认）。

使用步骤（推荐按顺序执行）：

1. 在 PowerShell 中运行（在项目根目录）：
   ```powershell
   ./generate_ssh_key.ps1 -Email "your_email@example.com"
   ```
   然后在 GitHub -> Settings -> SSH and GPG keys -> New SSH key 中粘贴并保存公钥。

2. 添加公钥后，运行：
   ```powershell
   ./setup_ssh_and_push.ps1
   ```
   过程会要求你确认并输入 `yes` 才会执行 `git push`。

安全提醒：
- 私钥会被复制到本机用户目录 `~/.ssh/`，脚本不会将私钥提交到仓库（`ssh_key_rui3394/` 也在 `.gitignore` 中）。
- 请勿在聊天或公开渠道粘贴私钥内容。
