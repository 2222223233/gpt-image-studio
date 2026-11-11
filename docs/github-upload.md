# 上传到 GitHub

建议仓库名：`gpt-image-studio`。源码包已包含 README、MIT 许可证、Git 忽略规则和 Actions 配置，不需要让 GitHub 再生成这些文件。

## 方法一：Git 命令（推荐）

1. 解压发布的项目包，进入包含 `app.py` 和 `README.md` 的 `gpt-image-studio` 文件夹。
2. 在 GitHub 创建一个空仓库，选择 Public 或 Private，不勾选初始化 README、许可证和 .gitignore。
3. 在项目目录打开终端，执行以下命令。将远程地址中的 `YOUR_USERNAME` 换成自己的 GitHub 用户名；如果仓库名不同，也相应替换。

```bash
git init -b main
git add .
git status --short
git commit -m "Initial release"
git remote add origin https://github.com/YOUR_USERNAME/gpt-image-studio.git
git push -u origin main
```

如果 Git 首次使用要求设置身份，按提示配置自己的 `user.name` 和 `user.email`。认证请使用 GitHub 的正常登录或凭据管理流程，不要把访问令牌写入源码或远程 URL。

推送后打开仓库的 **Actions** 标签查看测试状态。首次上传前本地测试通过，不等于 GitHub Actions 已在远程通过；以页面显示为准。

## 方法二：GitHub Desktop

在 GitHub Desktop 新建本地仓库，把项目文件复制到仓库根目录，确认包括 `.github/`、`.gitignore` 和 `.gitattributes`，然后提交并点击 Publish repository。

## 方法三：网页上传

在新仓库点击 **uploading an existing file**，上传解压后的源码文件和目录。不要只上传 ZIP，否则 GitHub 不会把 ZIP 内的 README、源码和工作流当作仓库文件。

Windows 资源管理器可能隐藏点开头文件或文件夹，请确保 `.github/workflows/ci.yml`、`.gitignore` 和 `.gitattributes` 一并上传。README.md 应位于仓库根目录，不要额外套一层目录。

## 发布可下载版本

运行 `python scripts/package_release.py`，将 `dist/` 下生成的 ZIP 上传到 GitHub Release 的附件区，供用户下载运行。`dist/` 不需要提交到源码仓库。

本项目包含 Python 后端，不适合 GitHub Pages 静态托管；仓库发布后，用户仍需下载到本机运行。
