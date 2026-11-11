# 参与开发

本项目使用 Python 标准库提供本地 HTTP 服务，前端为原生 HTML / CSS / JavaScript。

1. Fork 仓库并创建分支。
2. 在 Python 3.10+ 环境运行 `python -m pip install -r requirements-dev.txt`。
3. 修改代码后运行 `python -m unittest discover -s tests -v`。
4. 安装 Node.js 后执行 `node --check web/app.js` 和 `node --check web/references.js`。
5. 界面变更请启动应用，检查桌面和窄屏布局，以及图片上传、移除、参数检查。
6. 提交 Pull Request，说明问题、修改后的行为及验证方式。

测试使用本地模拟接口。不要将真实 API Key、参考图、用户生成图片或带密钥的日志提交到仓库；提交问题时可附脱敏错误信息和复现步骤。

保留运行时零第三方依赖的设计。提交到本项目的代码按仓库的 MIT 许可证提供。
