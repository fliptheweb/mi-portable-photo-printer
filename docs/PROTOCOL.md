# Protocol notes

Reverse-engineered from iPhone Bluetooth captures of the Mi Home app talking to a Mi Portable
Photo Printer (`hannto.printer.basil`, model `XMKDDYJ01HM` / `XMKDDYJHT02`, made by Hannto) and
verified by driving real hardware. The frame format is shared with other Hannto printers (Xiaomi
Photo Printer Pro, Liene PixCut), so parts may transfer to those.

## Transport

- Bluetooth Classic, **RFCOMM channel 1** (Serial Port Profile, UUID `00001101-...`).
- The printer drops an idle link after ~15 s; send anything (e.g. `mixed_status`) to keep it.
- On an Apple host the printer also advertises an iAP2 (Made-for-iPhone) channel; it is *not*
  required - channel 1 speaks the full protocol directly, which is what `mizink` uses.
- If a connection suddenly fails to open on macOS, the stored pairing key is likely stale;
  re-pair (`blueutil --unpair <mac> && blueutil --pair <mac>`).

## Frame

Total length `22 + bodyLen`, little-endian fields:

| off | size | field |
|----:|-----:|-------|
| 0 | 1 | `0x7E` head |
| 1 | 1 | `0x64` version |
| 2 | 1 | `0x00` reserved |
| 3 | 1 | channel - `1` JSON, `2` file, `255` auth |
| 4 | 1 | interactive - `6` request, `7` response |
| 5 | 1 | encoding - `2` binary/hex, `3` json |
| 6 | 4 | arcMsgSn (0) |
| 10 | 4 | msgSn - per-side counter |
| 14 | 2 | packageTotal |
| 16 | 2 | packageNum (1-based) |
| 18 | 2 | msgAttribute = `bodyLen | (encType<<10) | (0x2000 if multi-package)` |
| 20 | N | body |
| 20+N | 1 | checksum = `(sum(all bytes, checksum & tail = 0) - 126) & 0xFF` |
| 21+N | 1 | `0x7E` tail |

`encType`: `0` none, `4` = **mijia** (what this model uses). The Pro model uses `5` (AES-ECB
after a Diffie-Hellman handshake); basil does **not** do DH - it uses a pre-provisioned token.

## Encryption

`encType 4` = **RC4**, key = the printer's 12-byte miio device token, with a **fresh key
schedule for every frame**. Consequences:

- The keystream is identical at the same offset in every frame, so one captured 928-byte
  keystream is equivalent to the token (see `tools/recover_keystream_from_pklg.py`).
- The raw token cannot be recovered from a keystream (RC4 KSA is not invertible), but it
  isn't needed to operate the printer.

## Commands (channel 1, JSON-RPC)

Bodies are `{"id":N,"method":...,"params":...}`, encrypted. Print flow:

```
-> clean_data   {"delay_times":0}
-> mixed_status []                         <- {category, sub_category, error, battery, ...}
-> get_prop     ["device_info"]            <- [{fw_ver, hw_ver, mac, sn_pcba, sku, did}]
-> print_job    {copies,channel:64,job_type:0,file_size}  <- {job_id}  (or {"error":{"code":-8006}} if busy)
   (channel 2, encoding 2: file streamed in frames of 4-byte LE job_id + up to 924 JPEG bytes,
    packageNum/packageTotal set, msgAttribute has the multi-package bit)
-> confirm_job  [job_id]                   <- ["OK"]
-> mixed_status [] (poll)                  category: idle -> processing (decoding, pre_heat,
                                           load_paper, printing) -> idle
                                           printer also emits event.big_data on finish
```

Image: baseline JPEG, **1040 × 1560 px**, standard Huffman tables. `job_type 0` = photo.
