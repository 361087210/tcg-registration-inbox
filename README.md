# tcg-registration-inbox

太仓港商品车断电操作标准化指导平台 - 网页端注册申请收集箱。

- `registrations/` 目录由网页端提交的注册申请自动写入(pending_reg_<手机号>.json)
- GitHub Actions 每5分钟将新申请转投至飞书「APP数据备份/注册申请/」,转投成功后自动删除
- 组长在安卓端「组员管理」正常审批,无需任何额外操作
- 本仓库由自动化工作流管理,请勿手动修改
