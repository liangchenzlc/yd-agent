"""全局测试夹具：用 fakeredis 模拟 Redis，无需启动真实 Redis 服务。"""

import fakeredis


def _mock_redis_connect(self):
    """替换 RedisKVStore._connect 返回 fakeredis 实例。

    所有测试自动生效（通过 conftest.py 的自动发现机制），
    确保即使没有 Redis 服务测试也能正常运行。
    fakeredis 实现了完整的 Redis 命令集。
    """
    return fakeredis.FakeRedis(decode_responses=True)


# 在测试模块加载时自动替换 _connect 方法
# 使用 monkeypatch 需要在 fixture 中做，但这里用简单替换方式
import app.agent.storage.redis_kv_store as rks
rks.RedisKVStore._connect = _mock_redis_connect
