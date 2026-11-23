"""013-I07：指标层。

当前只有店铺层（交易结构），数据源是已有订单表，不依赖商品页采集。
商品层指标（素材/标题/详情）等 I05 批量采集落地后再补。
"""

from inspection.analyze.metrics import shop_metrics

__all__ = ["shop_metrics"]
