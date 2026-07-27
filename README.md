# Stock Noir - 实时库存盘点与临期商品管理

一个本地 Flask Web 应用，支持扫码查询商品、库存汇总、门店库存明细与临期批次清单。

## 启动

1. 将 `.env.example` 复制为 `.env`，并填写数据库密码。
2. 安装依赖：

```powershell
python -m pip install -r requirements.txt
```

3. 启动应用：

```powershell
python app.py
```

打开 <http://127.0.0.1:5000>。

## 扫码枪接入

推荐将扫码枪设置为 **USB/蓝牙 HID 键盘模式**，并设置扫描后自动发送回车。网页的条码框会自动获得焦点；扫码枪输入条码并发送回车后，系统会优先按 `barcode` 匹配，同时也支持按商品编码、名称关键词模糊搜索。点击“同步并保存”会同时同步并保存该条码列。

## 已使用的数据库表

- `bi_t_item_info`：商品主数据，使用 `item_no`、`item_name`、`barcode`。
- `bi_t_item_barcode`：一品多码条码映射。
- `ic_t_branch_stock`：按门店的当前库存，使用 `branch_no`、`stock_qty`。
- `ic_t_branch_stock_more`：按批次的库存和有效期，使用 `batch_no`、`valid_date`、`stock_qty`。

所有当前接口为只读查询。盘点差异确认、库存调整和审批写入应在业务规则确认后单独实现，并使用事务与审计日志。
