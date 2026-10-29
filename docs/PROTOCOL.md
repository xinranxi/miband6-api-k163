# Protocol reference — Mi Band 6 authentication

This document specifies the Bluetooth authentication handshake used by the
Mi Band 6 with recent firmware. It is provided as an interoperability
reference so that independent client software can talk to a device the
owner already possesses.

> The specification below describes the message formats and cryptographic
> steps only. It intentionally does not describe how to obtain the pairing
> key from any particular vendor application — see the README for the
> supported, documented options.

## Transport

All handshake traffic goes over the vendor's *chunked transfer*
characteristic:

| Role   | UUID                                     |
|--------|------------------------------------------|
| Write  | `00000016-0000-3512-2118-0009af100700`    |
| Read   | `00000017-0000-3512-2118-0009af100700`    |

Default ATT MTU is 23 bytes.

## Chunked framing

See `miband6/chunked.py`. In short:

```
first frame (11-byte header):
  03 | flags | 00 | xh | count | length(LE u32) | tag(2) | data (≤ 9 bytes)

continuation frame (5-byte header):
  03 | flags | 00 | xh | count | data (≤ 15 bytes)
```

`flags`: `0x01` = first frame, `0x06` = last frame, `0x07` = single frame.

`tag` identifies the message class:

| tag      | meaning                    |
|----------|----------------------------|
| `0x0000` | session init               |
| `0x8200` | authentication             |
| `0x9000` | encrypted payload          |
| `0x0300` | identity                   |
| `0x0500` | feature toggles            |
| `0x3200` | data request               |
| `0x0a00` | time / status              |

## Handshake

```
host → band    tag 0x0000   [03]
host → band    tag 0x8200   [00]
host → band    tag 0x8200   [04 02 00 02] + client_public_key (48 bytes)
band → host    tag 0x8200   [10 04 01] + nonce (16 bytes) + band_public_key (48 bytes)
host → band    tag 0x8200   [05] + enc1 (16) + enc2 (16)
band → host    tag 0x8200   [10 05 01]      ← success
```

### Public key encoding

Keys lie on **sect163r2 (NIST B-163)**, a binary-field curve, *not* a prime
curve. Each public key is 48 bytes:

```
X : 6 × little-endian uint32   (24 bytes, low 163 bits significant)
Y : 6 × little-endian uint32   (24 bytes)
```

### Session key derivation

```
shared       = ECDH_sect163r2(client_private, band_public)   # 24 bytes
session_key  = shared[8:24] XOR pairing_key                  # 16 bytes
```

### Challenge response

```
enc1 = AES-128-ECB(pairing_key, nonce)
enc2 = AES-128-ECB(session_key, nonce)
```

Both 16-byte ciphertexts are concatenated after the `0x05` opcode.

A response status byte of `0x01` (i.e. `10 05 01`) means the pairing key
was accepted. `0x07` / `0x08` indicate a rejected key or malformed proof.

## Curve parameters (sect163r2)

```
field:     GF(2^163), x^163 + x^7 + x^6 + x^3 + 1
equation:  y^2 + xy = x^3 + a*x^2 + b
a = 1
b = 0x20A601907B8C953CA1481EB10512F78744A3205FD
Gx= 0x03F0EBA16286A2D57EA0991168D4994637E8343E36
Gy= 0xD51FBC6C71A0094FA2CDD545B11C5C0C797324F1
n = 0x040000000000000000000292FE77E70C12A4234C33
```

The full arithmetic lives in `miband6/crypto/k163.py`; `tests/test_k163.py`
contains known-answer vectors so the implementation can be verified
without any hardware.

## Post-authentication reads

After a successful handshake the following standard/vendor characteristics
are readable:

| Data        | UUID                                     |
|-------------|------------------------------------------|
| Battery     | `00002a19-0000-1000-8000-00805f9b34fb`   |
| Steps (raw) | `00000007-0000-3512-2118-0009af100700`   |
| Time        | `00002a2b-0000-1000-8000-00805f9b34fb`   |
| Heart rate  | `00002a37-0000-1000-8000-00805f9b34fb`   |

Heart-rate measurement requires the band to be worn (the optical sensor
must detect skin contact); otherwise the device suppresses samples.

## Historical data fetch

Stored activity/health records are fetched over the **fetch**
characteristic (`00000004`), with samples streamed on the **activity-data**
characteristic (`00000005`).

Verified flow:

```
1. subscribe 00000005 (activity data)
2. write chunked message (tag 0x0500) = [01]              # feature toggle
3. subscribe 00000004 (fetch)   -- start reply arrives here
4. write fetch command: [01, data_type] + time_bytes(since)
5. band → host  10 01 01  (0x10 response, 0x01 start-date, 0x01 success)
6. write [02]                    # start streaming
7. band → host  activity samples on 00000005
8. band → host  10 02 01         # completion
```

### Time encoding — exactly 8 bytes

```
year (uint16 little-endian) | month | day | hour | minute | 0x00 | timezone
```

`timezone = utc_offset_hours * 4` (e.g. UTC+8 → `0x20`).

> A trailing extra byte here makes the firmware reject the request with
> status `0x02` — the length is critical.

### Data types (`data_type`)

| type   | meaning                 |
|--------|-------------------------|
| `0x01` | activity (steps/hr/sleep) |
| `0x02` | manual heart rate       |
| `0x05` | sports summaries        |
| `0x12` | stress (manual)         |
| `0x13` | stress (automatic)      |
| `0x25` | SpO2 (normal)           |
| `0x26` | SpO2 (sleep)            |
| `0x3a` | resting heart rate      |
| `0x3d` | max heart rate          |

### Activity sample format

Sleep-related field meanings and historical data completeness require further validation.

Each notification on `00000005` is `counter (1 byte)` followed by N
fixed 8-byte samples (one sample per minute):

```
kind | intensity | steps | heart_rate | unknown | sleep | deep_sleep | rem_sleep
```

- `heart_rate == 0xFF` → not measured (common in sleep `kind` ranges like `0xF0`)
- `deep_sleep` / `rem_sleep == 0x80` → not applicable
- `kind` classifies the sample: `0x50` activity, `0x70` light activity,
  `0xF0`–`0xFA` sleep, etc.

Samples are one minute apart starting at the `since` time of the fetch
command.

