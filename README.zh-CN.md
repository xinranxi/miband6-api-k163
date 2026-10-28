# miband6-api-k163

[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](#环境要求)

小米手环6 的**数据接口**。通过蓝牙直接与手环通信，提供认证、历史数据拉取与实时读取能力，无需手机 App 参与。适配固件 `1.0.6.x` 的 sect163k1 ECDH 认证。

> English version: [README.md](README.md)

---

## 背景

小米手环6 的蓝牙连接需要经过一次基于 ECDH 的认证握手。现有开源实现对该协议的曲线选择存在偏差，导致在较新固件上认证失败：

| 项目 | 使用的曲线 | 在固件 1.0.6.20 上的结果 |
|------|-----------|--------------------------|
| Gadgetbridge | P-256（素数域） | 认证失败，提示密钥无效 |
| band6.py | P-192（素数域） | 认证失败，返回状态码 `0x07` |
| **本项目** | **sect163k1（二进制域）** | **认证成功** |

手环实际使用的是 **sect163k1（NIST K-163）二进制域椭圆曲线**，与上述项目假设的素数域曲线属于不同的数学体系。使用正确的曲线后，认证可正常完成。

---

## 功能

- 扫描附近的 BLE 设备
- 完成 ECDH 认证握手
- 读取电量、步数计数、设备时间
- 订阅实时心率（需佩戴手环）
- **拉取历史活动数据**：手环本地存储的分钟级步数、心率、睡眠记录，可导出为 CSV / JSON
- 提供可离线验证的曲线算法测试

---

## 环境要求

| 项目 | 要求 |
|------|------|
| Python | 3.8 及以上 |
| 蓝牙 | 支持 BLE 的适配器 |
| 系统 | Windows / Linux / macOS |
| 依赖 | `pip install -r requirements.txt` |

无需 root 权限，无需安装厂商 App。

---

## 安装

```bash
git clone <repo-url>
cd miband6-api-k163
pip install -r requirements.txt
```

---

## 获取配对密钥

手环与账号之间通过一个 32 位十六进制字符串（配对密钥）建立信任关系。每台设备的密钥各不相同，需从自己的账号获取。

**方式一：从官方 App 日志读取（Android，无需 root）**

1. 打开小米运动健康 App
2. 进入「我的 → 关于」，连续点击 Logo 触发日志开关
3. 连接手环并完成一次同步
4. 在电脑上拉取日志并查找密钥：

```bash
adb pull /sdcard/Android/data/com.mi.health/files/log/XiaomiFit.device.log
grep -o 'huamiAuthKey=[0-9a-f]\{32\}' XiaomiFit.device.log
```

该方法与 Gadgetbridge 官方文档所述一致。

**方式二：从导出的设备数据库读取**

若已导出 App 数据库，密钥位于 `device_db` 中对应手环记录的 `detail` 字段。

---

## 使用

### 扫描设备

```bash
python -m miband6.cli scan
```

### 读取基本信息

```bash
python -m miband6.cli info --mac <MAC地址> --key <32位密钥>
```

输出示例：

```
Authenticated. Session key: ef6ac7839763a82600e373ccd204a894
  Battery: 96%
  Steps (raw u32): [12, 0, 0]
  Device time: 2026-10-29 00:02:44
```

### 订阅实时心率

```bash
python -m miband6.cli hr --mac <MAC地址> --key <32位密钥> --secs 60
```

注意：心率测量依赖光学传感器检测皮肤接触，需将手环佩戴在手腕上，否则设备不会输出采样。

### 导出数据（拉取历史）

从手环拉取本地存储的历史活动数据，导出为 CSV 与 JSON：

```bash
python -m miband6.cli export --mac <MAC地址> --key <32位密钥> --days 3 --out ./data
```

参数：

| 参数 | 说明 |
|------|------|
| `--days` | 回溯天数，默认 3 |
| `--out` | 输出目录，默认 `./miband6-data` |
| `--timeout` | 拉取超时（秒），默认 30 |

生成文件：

```
miband6-activity-<时间戳>.csv   逐分钟明细
miband6-activity-<时间戳>.json  汇总（样本数、总步数、心率统计）
```

CSV 每行一个分钟级样本，列：

```
time, kind, intensity, steps, heart_rate, sleep, deep_sleep, rem_sleep
```

JSON 汇总示例：

```json
{
  "device": { "mac": "AA:BB:CC:DD:EE:FF" },
  "since": "2026-10-27T00:00:00",
  "samples": 2940,
  "first_sample": "2026-10-27T00:00:00",
  "last_sample": "2026-10-29T00:59:00",
  "total_steps": 540,
  "heart_rate": { "count": 2829, "avg": 68, "min": 45, "max": 110 }
}
```

> 手环本地仅保存近期滚动数据（通常最近数天到数周）。更早的历史在厂商云端或手机 App 的本地数据库中。`heart_rate` 为 `0xFF` 的样本表示该分钟未测量心率（如睡眠时段），导出时留空。

### Web 大屏（可选）

```bash
python -m miband6.cli serve --port 8080
```

浏览器打开 `http://127.0.0.1:8080`：点「扫描」发现手环 → 选择设备 → 填配对密钥 → 选时间范围 → 「连接并拉取」，即可看到数据大屏。页面里的「如何获取？」给出了密钥获取步骤，也支持通过 adb 从已连接手机自动提取。

> 浏览器无法直接访问蓝牙，因此由本地 Python 进程作为后端执行 BLE 操作。

### 作为库调用

```python
import asyncio
import datetime
from miband6.device import MiBand6

async def main():
    async with MiBand6("AA:BB:CC:DD:EE:FF", bytes.fromhex("<32位密钥>")) as band:
        await band.authenticate()
        print("电量:", await band.read_battery())
        since = datetime.datetime.now() - datetime.timedelta(days=3)
        samples = await band.fetch_activity(since)
        print("拉到样本数:", len(samples))

asyncio.run(main())
```

---

## 作为数据接口

本项目的核心是一个**面向手环的数据接口**。CLI 与 Web 大屏都只是它的调用方——大屏主要用于让开发者确认数据是否已正确读取。

三种使用方式：

**1. Python 调用**

```python
import asyncio, datetime
from miband6.device import MiBand6

async def main():
    async with MiBand6("AA:BB:CC:DD:EE:FF", bytes.fromhex("<密钥>")) as band:
        await band.authenticate()
        since = datetime.datetime.now() - datetime.timedelta(days=3)
        samples = await band.fetch_activity(since)
        # 每个样本：
        #   {"time": datetime, "kind": int, "steps": int,
        #    "heart_rate": int|None, "sleep": int,
        #    "deep_sleep": int|None, "rem_sleep": int|None}

asyncio.run(main())
```

**2. 本地 HTTP 服务**

```bash
python -m miband6.cli serve --port 8080
```

```bash
curl -X POST http://127.0.0.1:8080/api/fetch \
  -H 'Content-Type: application/json' \
  -d '{"mac":"AA:BB:CC:DD:EE:FF","key":"<32位密钥>","days":3}'
# -> {"ok": true, "agg": { "hr_points": [...], "steps_by_day": {...}, ... }}
```

另提供 `POST /api/scan`（扫描附近手环）与 `POST /api/extract_key`（通过 adb 从已连接手机提取密钥）。

**3. 命令行**

```bash
python -m miband6.cli export --mac AA:BB:CC:DD:EE:FF --key <32位密钥> --days 3
```

---

## 工作原理

认证握手在 chunked transfer 特征上进行，共三步：

```
host → band   [04 02 00 02] + 客户端公钥(48B)
band → host   [10 04 01] + 随机数(16B) + 手环公钥(48B)
host → band   [05] + AES-ECB(配对密钥, 随机数) + AES-ECB(会话密钥, 随机数)
band → host   [10 05 01]        认证成功
```

其中：

```
共享密钥   = ECDH_sect163k1(客户端私钥, 手环公钥)      # 24 字节
会话密钥   = 共享密钥[8:24] XOR 配对密钥               # 16 字节
```

完整的协议规格、分包格式与曲线参数见 [docs/PROTOCOL.md](docs/PROTOCOL.md)。

---

## 测试

曲线与 ECDH 算法提供已知答案测试，无需连接设备即可验证：

```bash
python -m unittest discover -s tests -v
```

测试使用真实握手过程中采集的密钥对作为向量。全部通过即说明本实现产生的共享密钥与固件一致。

---

## 项目结构

```
miband6/
  k163.py      sect163k1 有限域与曲线运算（纯 Python）
  chunked.py   分包传输协议
  auth.py      认证握手
  fetch.py     历史数据拉取协议
  activity.py  活动样本解码
  device.py    设备封装
  cli.py       命令行接口
docs/
  PROTOCOL.md  协议规格
tests/
  test_k163.py 已知答案测试
examples/      示例脚本
```

---

## 适用边界

**支持：**
- 与本人已配对的手环建立连接并读取实时数据
- 拉取手环**本地存储**的历史活动数据（分钟级步数、心率、睡眠）

**不支持：**
- 读取手环本地已不存在的更早历史。手环仅保存近期滚动数据（通常最近数天到数周），完整历史保留在 App 云端或手机本地数据库中。
- 未佩戴状态下读取心率。
- 访问他人设备。每台设备的密钥均不相同。

---

## 常见问题

**Q：提示认证失败 / 密钥无效？**

确认密钥为 32 位十六进制，且对应本台设备。可使用 `--info` 快速验证。

**Q：能读到多久以前的数据？**

本工具直接与手环通信，只能获取手环**当前存储**的数据（通常最近数天到数周）。更早的历史保留在 App 云端或手机本地数据库中。

**Q：为什么心率读不到？**

需将手环佩戴在手腕上。传感器检测不到皮肤接触时，设备会拒绝测量。

---

## 许可

本项目采用 [MIT](LICENSE) 许可证。

小米、华米及相关商标归各自权利人所有，本项目与其无隶属关系。本工具仅用于读取本人已配对手环的数据，不涉及破解加密或访问他人设备。
