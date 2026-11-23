-- 运营费用：结构化保存账单「本月交易额」，用于计算 ROI
-- @ensure-column storeplatformexpense.transaction_amount REAL DEFAULT 0

-- 历史数据回填：此前交易额只写进了 note（形如「账单 xxx；交易额 6148.96」）
UPDATE storeplatformexpense
SET transaction_amount = CAST(substr(note, instr(note, '交易额') + 3) AS REAL)
WHERE (transaction_amount IS NULL OR transaction_amount = 0)
  AND instr(note, '交易额') > 0;
